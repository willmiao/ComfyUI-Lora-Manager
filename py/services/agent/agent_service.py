"""Pipeline orchestration service.

The :class:`AgentService` coordinates LLM-powered pipeline execution:

1. Look up the pipeline definition in :class:`SkillRegistry`
2. Validate input against its ``input_schema``
3. Prepare context via :mod:`~py.metadata_ops` (read metadata, list base models, fetch HF README)
4. If ``llm_required``: call :class:`LLMService` with the rendered prompt
5. Post-process via :class:`PostProcessor` (delegates I/O to :mod:`~py.metadata_ops`)
6. Broadcast progress and completion via :class:`WebSocketManager`

Pipeline definitions (*skills*) describe *what* to do (prompt template).
The AgentService handles *how* (LLM calls, context gathering, validation,
progress).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...config import config
from ..llm_service import LLMService
from ..model_sources import (
    ModelCardContext,
    ModelSourceCache,
    get_source,
    resolve_source_ref,
    source_label,
)
from ..model_sources.hydration import load_model_card, resolve_site_base_model
from ..websocket_manager import ws_manager
from .post_processor import PostProcessor
from .skill_registry import SkillRegistry
from .skills.enrich_hf_metadata.readme_processor import (
    clean_readme_for_llm,
    extract_relevant_section,
)

logger = logging.getLogger(__name__)


class AgentProgressReporter:
    """Protocol-compatible progress reporter backed by WebSocket broadcast."""

    async def on_progress(self, payload: Dict[str, Any]) -> None:
        await ws_manager.broadcast(payload)


@dataclass
class SkillResult:
    """Outcome of a skill execution."""

    success: bool
    updated_models: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    summary: str = ""


def _validate_schema(data: Any, schema: Dict[str, Any], path: str = "") -> List[str]:
    """Minimal JSON schema validator.

    Supports a subset of JSON Schema: ``type``, ``properties``, ``required``,
    ``items``, ``enum``.  Returns a list of error messages (empty = valid).
    """

    errors: List[str] = []
    if not schema:
        return errors

    expected_type = schema.get("type")
    if expected_type:
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        expected_py = type_map.get(expected_type)
        if expected_py is not None and not isinstance(data, expected_py):
            errors.append(f"{path or 'root'}: expected {expected_type}, got {type(data).__name__}")
            return errors

    if expected_type == "object" and isinstance(data, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for req_key in required:
            if req_key not in data:
                errors.append(f"{path or 'root'}: missing required property '{req_key}'")
        for key, value in data.items():
            if key in properties:
                errors.extend(_validate_schema(value, properties[key], f"{path}.{key}"))

    if expected_type == "array" and isinstance(data, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(data):
                errors.extend(_validate_schema(item, items_schema, f"{path}[{i}]"))

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path or 'root'}: value '{data}' not in enum {schema['enum']}")

    return errors


# ------------------------------------------------------------------
# Prompt template rendering
# ------------------------------------------------------------------


def _render_prompt(template: str, variables: Dict[str, Any]) -> str:
    """Render a prompt template with ``{{variable}}`` placeholders.

    Uses simple regex substitution — no Jinja2 dependency needed.
    """

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = variables.get(key, "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    return re.sub(r"\{\{(\w+)\}\}", replace, template)


class AgentService:
    """Orchestrate agent skill execution.

    Usage::

        service = await AgentService.get_instance()
        result = await service.execute_skill(
            skill_name="enrich_hf_metadata",
            input_data={"model_paths": ["/path/to/model.safetensors"]},
            progress_callback=AgentProgressReporter(),
        )
    """

    _instance: Optional["AgentService"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(
        self,
        *,
        skill_registry: Optional[SkillRegistry] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        self._registry = skill_registry
        self._llm_service = llm_service

    @classmethod
    async def get_instance(cls) -> "AgentService":
        """Return the lazily-initialised global ``AgentService``."""

        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(
                        skill_registry=await SkillRegistry.get_instance(),
                        llm_service=await LLMService.get_instance(),
                    )
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the cached singleton — primarily for tests."""

        cls._instance = None

    async def _ensure_registry(self) -> SkillRegistry:
        if self._registry is None:
            self._registry = await SkillRegistry.get_instance()
        return self._registry

    async def _ensure_llm(self) -> LLMService:
        if self._llm_service is None:
            self._llm_service = await LLMService.get_instance()
        return self._llm_service

    async def list_skills(self) -> List[Dict[str, Any]]:
        """Return a JSON-serialisable list of available skills."""

        registry = await self._ensure_registry()
        return [
            {
                "name": s.name,
                "title": s.title,
                "description": s.description,
                "llm_required": s.llm_required,
                "model_type_filter": s.model_type_filter,
            }
            for s in registry.list_skills()
        ]

    async def execute_skill(
        self,
        *,
        skill_name: str,
        input_data: Dict[str, Any],
        progress_callback: Optional[AgentProgressReporter] = None,
    ) -> SkillResult:
        """Execute a pipeline (skill) on the given models.

        Args:
            skill_name: Name of the pipeline to execute
            input_data: Input validated against the pipeline's ``input_schema``
            progress_callback: Optional WebSocket progress reporter

        Returns:
            :class:`SkillResult` with success status and updated model info
        """

        registry = await self._ensure_registry()
        skill = registry.get_skill(skill_name)
        if skill is None:
            return SkillResult(
                success=False,
                errors=[f"Skill not found: {skill_name}"],
                summary=f"Skill '{skill_name}' does not exist",
            )

        input_errors = _validate_schema(input_data, skill.input_schema)
        if input_errors:
            return SkillResult(
                success=False,
                errors=input_errors,
                summary=f"Invalid input: {'; '.join(input_errors)}",
            )

        model_paths = input_data.get("model_paths", [])
        if not model_paths:
            return SkillResult(
                success=False,
                errors=["No model_paths provided"],
                summary="No models to process",
            )

        total = len(model_paths)
        processed = 0
        success_count = 0
        skipped_count = 0
        updated_models: List[Dict[str, Any]] = []
        errors: List[str] = []
        post_processor = PostProcessor()

        await self._emit_progress(
            progress_callback, skill_name, status="started",
            total=total, processed=0, success=0,
        )

        llm = await self._ensure_llm()
        llm_configured = llm.is_configured() if skill.llm_required else True

        # A collection repository holds many model files under one source id;
        # this memo keeps the README and the repository metadata from being
        # re-fetched once per file.  It lives for this run only.
        source_cache = ModelSourceCache()

        for model_path in model_paths:
            model_filename = os.path.basename(model_path)
            logger.info(
                "[%s] [%d/%d] %s",
                skill_name, processed + 1, total, model_filename,
            )
            updated_data: Dict[str, Any] = {}
            skip_model = False
            try:
                from ...metadata_ops import read_metadata
                metadata = await read_metadata(model_path)

                # Fast-fail: enrich_hf_metadata needs an external model source
                # that exposes an accessible model card.
                if skill_name == "enrich_hf_metadata":
                    skip_reason = self._enrichment_skip_reason(metadata)
                    if skip_reason:
                        logger.info(
                            "[%s] SKIP %s — %s",
                            skill_name, model_filename, skip_reason,
                        )
                        skipped_count += 1
                        skip_model = True

                if not skip_model:
                    # The site's own data is deterministic and must land whether
                    # or not an LLM is available: a user without a key still gets
                    # the author summary, the example images and the tags.
                    source_vars, source_context = await self._load_source_card(
                        model_path, metadata, cache=source_cache,
                    )
                    resolved_base_model = ""
                    if skill_name == "enrich_hf_metadata" and not (
                        metadata.get("base_model") or ""
                    ).strip():
                        resolved_base_model = await self._resolve_site_base_model(
                            source_context,
                        )

                    llm_response: Optional[Dict[str, Any]] = None
                    if skill.llm_required and not llm_configured:
                        # Without a provider the deterministic model-source data
                        # still lands; the LLM-only fields simply stay untouched.
                        logger.info(
                            "[%s] No LLM configured for %s — applying %s data only",
                            skill_name, model_filename,
                            "model-source"
                            if not source_context.is_empty()
                            else "README",
                        )
                    elif skill.llm_required:
                        prompt_vars = await self._build_prompt_context(
                            skill_name, model_path, metadata, registry, llm,
                            source_vars=source_vars,
                            source_context=source_context,
                        )
                        prompt_template = registry.load_prompt(skill_name)
                        rendered = _render_prompt(prompt_template, prompt_vars)
                        llm_response = await llm.chat_completion_json(
                            system_prompt=prompt_vars.get(
                                "system_prompt",
                                "You are a helpful assistant that extracts structured metadata.",
                            ),
                            user_prompt=rendered,
                        )
                        if llm_response:
                            logger.info(
                                "[%s] [%d/%d] %s → base_model=%s confidence=%s",
                                skill_name, processed + 1, total, model_filename,
                                (llm_response.get("base_model") or "?")[:50],
                                llm_response.get("confidence", "?"),
                            )

                    model_result = await post_processor.process(
                        skill_name=skill_name,
                        model_path=model_path,
                        llm_output=llm_response or {},
                        metadata=metadata,
                        readme_content=source_vars.get("readme_content_full", ""),
                        source_context=source_context,
                        resolved_base_model=resolved_base_model,
                    )

                    if model_result.get("success", True):
                        success_count += 1
                        uf = model_result.get("updated_fields", [])
                        if uf:
                            updated_models.append({"path": model_path, "updated_fields": uf})
                        updated_data = model_result.get("updates", {})
                        if "preview_url" in updated_data and updated_data["preview_url"]:
                            updated_data["preview_url"] = config.get_preview_static_url(
                                updated_data["preview_url"]
                            )
                    else:
                        errors.extend(
                            model_result.get("errors", [model_result.get("error", "Unknown error")])
                        )

            except Exception as exc:
                logger.error("Skill %s failed for %s: %s", skill_name, model_path, exc)
                errors.append(f"{model_path}: {exc}")

            processed += 1
            await self._emit_progress(
                progress_callback, skill_name, status="processing",
                total=total, processed=processed, success=success_count,
                skipped=skipped_count,
                current_path=model_path,
                updated_data=updated_data,
            )

        result = SkillResult(
            success=success_count > 0,
            updated_models=updated_models,
            errors=errors,
            summary=f"Processed {processed}/{total} models, {success_count} succeeded, {skipped_count} skipped",
        )

        await self._emit_progress(
            progress_callback, skill_name, status="completed",
            total=total, processed=processed, success=success_count,
            skipped=skipped_count,
            updated_models=updated_models, errors=errors, summary=result.summary,
        )

        return result

    # ------------------------------------------------------------------
    # Base model grouping (keeps the prompt compact)
    # ------------------------------------------------------------------

    @staticmethod
    def _enrichment_skip_reason(metadata: Dict[str, Any]) -> str:
        """Return why ``enrich_hf_metadata`` cannot run, or ``""`` if it can.

        Distinguishes the three cases the user can act on: no source linked,
        a source we don't know, and a known source whose model card is not
        reachable from the backend (TensorArt).
        """

        ref = resolve_source_ref(metadata)
        if ref is None:
            return "no model source linked (source_url missing)"
        source = get_source(ref.platform)
        if source is None:
            return f"unsupported model source platform '{ref.platform}'"
        if not source.supports_enrichment:
            return (
                f"{source.label} does not expose a model card to the backend; "
                "AI metadata enrichment is not available for this source"
            )
        return ""

    @staticmethod
    def _format_base_models(models: List[str]) -> str:
        """Format the base model list as a flat, one-per-line list.

        Attempts to group by family consistently degraded LLM extraction
        accuracy — the LLM finds individual model names harder to spot
        in comma-separated groups than in a simple ``- Name`` list.
        """
        return "\n".join(f"- {m}" for m in models)

    async def _load_source_card(
        self,
        model_path: str,
        metadata: Dict[str, Any],
        *,
        cache: Optional[ModelSourceCache] = None,
    ) -> tuple[Dict[str, Any], ModelCardContext]:
        """Fetch the model card and site-published extras for one model.

        Runs for every source-backed enrichment regardless of LLM
        availability, because everything it returns is deterministic data that
        should be applied even without a configured provider.

        *cache* is the per-run memo created by :meth:`execute_skill`.  The
        README is repository-wide, so it is fetched once per source id; only
        successful reads are memoised, leaving a transient failure to be
        retried for the next file.
        """

        variables: Dict[str, Any] = {
            "asset_base_url": "",
            "source_description": "",
            "source_base_model": "",
            "source_official_tags": "",
            "source_example_images": "",
            "source_trigger_words": "",
            "readme_content": "(README not available)",
            "readme_content_full": "",
        }

        ref = resolve_source_ref(metadata)
        source = get_source(ref.platform) if ref is not None else None
        if ref is None or source is None or not source.supports_enrichment:
            return variables, ModelCardContext()

        raw_basename = os.path.splitext(os.path.basename(model_path))[0]
        variables["asset_base_url"] = source.asset_base_url(ref.source_id)

        readme = await load_model_card(source, ref.source_id, cache)

        # Sites such as ModelScope keep part of the model card outside the
        # README (author summary, curated tags, per-file example images).  The
        # recorded hash identifies the file even after the user renames it.
        card_context = await source.fetch_model_card_context(
            ref.source_id,
            os.path.basename(model_path),
            sha256=(metadata.get("sha256") or "").strip(),
            cache=cache,
        )
        variables["source_description"] = card_context.description
        variables["source_base_model"] = card_context.base_model
        variables["source_official_tags"] = "\n".join(
            f"- {tag}" for tag in card_context.official_tags
        )
        variables["source_example_images"] = "\n".join(
            f"- {url}" for url in card_context.example_images
        )
        variables["source_trigger_words"] = ", ".join(card_context.trigger_words)

        # Trim README to the section relevant to this model file
        # (collection repos often have multiple models in one README).
        if readme and raw_basename:
            trimmed = extract_relevant_section(readme, raw_basename)
            cleaned = clean_readme_for_llm(trimmed) if trimmed else ""
        else:
            cleaned = clean_readme_for_llm(readme) if readme else ""
        variables["readme_content"] = cleaned if cleaned else "(README not available)"
        variables["readme_content_full"] = readme or ""

        return variables, card_context

    async def _resolve_site_base_model(self, source_context: ModelCardContext) -> str:
        """Resolve the site's base-model hints to a canonical name, or ``""``."""

        return await resolve_site_base_model(source_context)

    async def _build_prompt_context(
        self,
        skill_name: str,
        model_path: str,
        metadata: Dict[str, Any],
        registry: SkillRegistry,
        llm: Any,
        *,
        source_vars: Optional[Dict[str, Any]] = None,
        source_context: Optional[ModelCardContext] = None,
    ) -> Dict[str, Any]:
        """Gather variables for the skill's prompt template.

        Reads metadata, fetches the model card (unless a pre-fetched
        *source_vars* / *source_context* pair is supplied), lists available
        base models, loads user priority tags, and returns a dict that maps to
        ``{{variable}}`` placeholders in ``prompt.md``.
        """
        from ...metadata_ops import identify_model_type, list_base_models
        from ..settings_manager import SettingsManager

        if source_vars is None or source_context is None:
            source_vars, source_context = await self._load_source_card(
                model_path, metadata,
            )

        context: Dict[str, Any] = {
            "model_path": model_path,
            "model_basename": "",
            # Canonical external-source variables
            "source_url": "",
            "source_id": "",
            "source_platform": "",
            "source_label": "",
            "asset_base_url": "",
            # Site-provided card extras (see ModelSource.fetch_model_card_context)
            "source_description": "",
            "source_base_model": "",
            "source_official_tags": "",
            "source_example_images": "",
            "source_trigger_words": "",
            # Carrier for the structured context handed to the post-processor;
            # never rendered into the prompt.
            "source_context": ModelCardContext(),
            # Legacy Hugging Face aliases (kept so older prompt templates and
            # third-party skills keep rendering)
            "hf_url": "",
            "repo": "",
            "readme_content": "",
            "readme_content_full": "",
            "current_metadata": {},
            "base_models": [],
            "priority_tags": "",
        }

        # Extract model basename (filename without extension) for the LLM
        # to use when locating the matching section in collection repos.
        raw_basename = os.path.splitext(os.path.basename(model_path))[0]
        context["model_basename"] = raw_basename or ""

        context["current_metadata"] = {
            "file_name": metadata.get("file_name", ""),
            "base_model": metadata.get("base_model", ""),
            "tags": metadata.get("tags", []),
            "modelDescription": metadata.get("modelDescription", ""),
            "sha256": (metadata.get("sha256") or "")[:16] + "..." if metadata.get("sha256") else "",
            "size": metadata.get("size", 0),
        }

        ref = resolve_source_ref(metadata)
        if ref is not None:
            context["source_url"] = ref.url
            context["source_id"] = ref.source_id
            context["source_platform"] = ref.platform
            context["source_label"] = source_label(ref.platform, ref.platform)
            if ref.platform == "huggingface":
                context["hf_url"] = ref.url
            context["repo"] = ref.source_id

        source = get_source(ref.platform) if ref is not None else None
        if ref is not None and source is not None and source.supports_enrichment:
            # Values fetched once by _load_source_card and shared with the
            # post-processor, so the network is not hit twice per model.
            context["asset_base_url"] = source_vars["asset_base_url"]
            context["source_context"] = source_context
            context["source_description"] = source_vars["source_description"]
            context["source_base_model"] = source_vars["source_base_model"]
            context["source_official_tags"] = source_vars["source_official_tags"]
            context["source_example_images"] = source_vars["source_example_images"]
            context["source_trigger_words"] = source_vars["source_trigger_words"]
            context["readme_content"] = source_vars["readme_content"]
            context["readme_content_full"] = source_vars["readme_content_full"]

        try:
            raw_models = await list_base_models()
            context["base_models"] = self._format_base_models(raw_models)
        except Exception as exc:
            logger.debug("Failed to list base models: %s", exc)
            context["base_models"] = "</not available>"

        # Determine model type and load the corresponding priority_tags
        try:
            model_type = await identify_model_type(model_path)
            context["model_type"] = model_type
            settings = SettingsManager()
            priority_config = settings.get_priority_tag_config()
            context["priority_tags"] = priority_config.get(model_type, "")
        except Exception as exc:
            logger.debug("Failed to load priority tags: %s", exc)
            context["model_type"] = "lora"
            context["priority_tags"] = ""

        return context

    @staticmethod
    def _extract_repo_from_url(hf_url: str) -> Optional[str]:
        """Extract ``user/repo`` from a HuggingFace URL."""
        if not hf_url:
            return None
        m = re.match(r"https?://huggingface\.co/([^/]+/[^/]+)", hf_url)
        return m.group(1) if m else None

    @staticmethod
    async def _fetch_readme(repo: str) -> str:
        """Fetch a Hugging Face README (tries ``main``, then ``master``).

        Kept for backward compatibility; new code should go through the
        model-source registry so every supported site works.
        """
        from ..model_sources import HuggingFaceSource

        return await HuggingFaceSource().fetch_model_card(repo)

    async def _emit_progress(
        self,
        callback: Optional[AgentProgressReporter],
        skill_name: str,
        *,
        status: str,
        **extra: Any,
    ) -> None:
        """Send a progress update via WebSocket (if callback is set)."""
        payload: Dict[str, Any] = {"type": "agent_progress", "skill": skill_name, "status": status}
        payload.update(extra)
        if callback is not None:
            await callback.on_progress(payload)
