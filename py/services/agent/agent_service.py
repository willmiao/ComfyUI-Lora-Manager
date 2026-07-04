"""Agent orchestration service.

The :class:`AgentService` coordinates skill execution:

1. Look up the skill in :class:`SkillRegistry`
2. Validate input against the skill's ``input_schema``
3. Prepare context via :mod:`~py.agent_cli` (read metadata, list base models, fetch HF README)
4. If ``llm_required``: call :class:`LLMService` with the rendered prompt
5. Post-process via :class:`PostProcessor` (delegates I/O to :mod:`~py.agent_cli`)
6. Broadcast progress and completion via :class:`WebSocketManager`

Skills define *what* to do (prompt template).  The AgentService handles *how*
(LLM calls, context gathering, validation, progress).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp

import os

from ...config import config
from ..llm_service import LLMService
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

    def replace(match: re.Match) -> str:
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
        """Execute an agent skill.

        Args:
            skill_name: Name of the skill to execute
            input_data: Input validated against the skill's ``input_schema``
            progress_callback: Optional WebSocket progress reporter

        Returns:
            :class:`SkillResult` with success status and updated model info
        """

        registry = await self._ensure_registry()
        logger.info("execute_skill '%s': looking up skill", skill_name)
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
        updated_models: List[Dict[str, Any]] = []
        errors: List[str] = []
        post_processor = PostProcessor()

        logger.info("execute_skill '%s': starting with %d model(s)", skill_name, total)
        await self._emit_progress(
            progress_callback, skill_name, status="started",
            total=total, processed=0, success=0,
        )

        llm = await self._ensure_llm()
        llm_configured = llm.is_configured() if skill.llm_required else True

        for model_path in model_paths:
            logger.info(
                "execute_skill '%s': processing model %d/%d: %s",
                skill_name, processed + 1, total, model_path,
            )
            updated_data: Dict[str, Any] = {}
            try:
                from ...agent_cli import read_metadata
                metadata = await read_metadata(model_path)

                prompt_vars: Dict[str, Any] = {"model_path": model_path}
                if skill.llm_required and llm_configured:
                    prompt_vars = await self._build_prompt_context(
                        skill_name, model_path, metadata, registry, llm,
                    )

                llm_response: Optional[Dict[str, Any]] = None
                if skill.llm_required and llm_configured:
                    prompt_template = registry.load_prompt(skill_name)
                    rendered = _render_prompt(prompt_template, prompt_vars)
                    logger.info(
                        "execute_skill '%s': LLM call for %s (prompt=%d chars)",
                        skill_name, model_path, len(rendered),
                    )
                    llm_response = await llm.chat_completion_json(
                        system_prompt=prompt_vars.get(
                            "system_prompt",
                            "You are a helpful assistant that extracts structured metadata.",
                        ),
                        user_prompt=rendered,
                    )

                model_result = await post_processor.process(
                    skill_name=skill_name,
                    model_path=model_path,
                    llm_output=llm_response or {},
                    metadata=metadata,
                    readme_content=prompt_vars.get("readme_content_full", ""),
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
                current_path=model_path,
                updated_data=updated_data,
            )

        result = SkillResult(
            success=success_count > 0,
            updated_models=updated_models,
            errors=errors,
            summary=f"Processed {processed}/{total} models, {success_count} succeeded",
        )

        logger.info("execute_skill '%s': done — %s", skill_name, result.summary)
        await self._emit_progress(
            progress_callback, skill_name, status="completed",
            total=total, processed=processed, success=success_count,
            updated_models=updated_models, errors=errors, summary=result.summary,
        )

        return result

    async def _build_prompt_context(
        self,
        skill_name: str,
        model_path: str,
        metadata: Dict[str, Any],
        registry: SkillRegistry,
        llm: Any,
    ) -> Dict[str, Any]:
        """Gather variables for the skill's prompt template.

        Reads metadata, fetches the HF README (if applicable), lists available
        base models, loads user priority tags, and returns a dict that maps to
        ``{{variable}}`` placeholders in ``prompt.md``.
        """
        from ...agent_cli import identify_model_type, list_base_models
        from ..settings_manager import SettingsManager

        context: Dict[str, Any] = {
            "model_path": model_path,
            "model_basename": "",
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
            "trainedWords": metadata.get("trainedWords", []),
            "sha256": (metadata.get("sha256") or "")[:16] + "..." if metadata.get("sha256") else "",
            "size": metadata.get("size", 0),
        }

        hf_url = metadata.get("hf_url", "")
        context["hf_url"] = hf_url
        repo = self._extract_repo_from_url(hf_url) if hf_url else ""
        context["repo"] = repo or ""
        if repo:
            readme = await self._fetch_readme(repo)
            # Trim README to the section relevant to this model file
            # (collection repos often have multiple models in one README).
            if readme and raw_basename:
                trimmed = extract_relevant_section(readme, raw_basename)
                cleaned = clean_readme_for_llm(trimmed) if trimmed else ""
            else:
                cleaned = clean_readme_for_llm(readme) if readme else ""
            context["readme_content"] = cleaned if cleaned else "(README not available)"
            context["readme_content_full"] = readme or ""
            logger.info(
                "Cleaned README for %s (%d chars): ---BEGIN---\n%s\n---END---",
                repo, len(cleaned), cleaned[:800] if cleaned else "(empty)",
            )

        try:
            context["base_models"] = await list_base_models()
        except Exception as exc:
            logger.debug("Failed to list base models: %s", exc)

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
        """Fetch README.md from HuggingFace (tries ``main``, then ``master``)."""
        async with aiohttp.ClientSession(
            headers={"User-Agent": "ComfyUI-LoRA-Manager/1.0"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as session:
            for branch in ("main", "master"):
                url = f"https://huggingface.co/{repo}/raw/{branch}/README.md"
                try:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            return await resp.text()
                except Exception as exc:
                    logger.debug("Failed to fetch README from %s: %s", url, exc)
        return ""

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
