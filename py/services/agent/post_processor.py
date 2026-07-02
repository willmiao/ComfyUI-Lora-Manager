"""Post-processing engine for agent skill outputs.

The :class:`PostProcessor` takes the LLM's structured JSON output and applies
it to a model's on-disk metadata via the :mod:`~py.agent_cli` functions.

It handles all the skill-specific business logic — conditions, transformations,
and orchestration of multiple side-effects (write metadata, download preview,
refresh cache).  All actual I/O is delegated to :mod:`~py.agent_cli`.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PostProcessor:
    """Deterministic post-processor for agent skill outputs.

    Usage (called by :class:`~py.services.agent.agent_service.AgentService`)::

        processor = PostProcessor()
        result = await processor.process(
            skill_name="enrich_hf_metadata",
            model_path="/path/to/model.safetensors",
            llm_output={...},
            metadata={...},    # from agent_cli.read_metadata()
        )
    """

    async def process(
        self,
        *,
        skill_name: str,
        model_path: str,
        llm_output: Dict[str, Any],
        metadata: Dict[str, Any],
        readme_content: str = "",
    ) -> Dict[str, Any]:
        """Route *llm_output* to the correct skill post-processor.

        *readme_content* is optional raw markdown content (e.g. HF README)
        that is converted to HTML and stored as ``modelDescription`` for
        the description tab.

        Returns a dict with keys ``success`` (bool), ``updated_fields`` (list),
        ``preview_downloaded`` (bool), and ``errors`` (list).
        """
        if skill_name == "enrich_hf_metadata":
            return await self._process_enrich_hf_metadata(
                model_path, llm_output, metadata, readme_content,
            )
        return {
            "success": False,
            "updated_fields": [],
            "errors": [f"No post-processor registered for skill: {skill_name}"],
        }

    # ------------------------------------------------------------------
    # enrich_hf_metadata
    # ------------------------------------------------------------------

    async def _process_enrich_hf_metadata(
        self,
        model_path: str,
        llm_output: Dict[str, Any],
        metadata: Dict[str, Any],
        readme_content: str = "",
    ) -> Dict[str, Any]:
        from ...agent_cli import (
            apply_metadata_updates,
            download_preview,
            refresh_cache,
        )
        from .skills.enrich_hf_metadata.md_to_html import (
            convert_readme_to_html,
            extract_gallery_images,
            extract_repo_from_hf_url,
        )

        updated_fields: List[str] = []
        preview_downloaded = False

        # -- Determine whether this is an HF-sourced model -----------------
        is_hf_model = not metadata.get("from_civitai", True)

        # -- Collect updates -----------------------------------------------
        updates: Dict[str, Any] = {}

        # base_model
        new_base = (llm_output.get("base_model") or "").strip()
        current_base = metadata.get("base_model", "") or ""
        if new_base and self._should_overwrite(current_base, is_hf_model):
            updates["base_model"] = new_base

        # trigger words → civitai.trainedWords
        new_triggers = llm_output.get("trigger_words", [])
        if isinstance(new_triggers, list):
            cleaned = [t.strip() for t in new_triggers if t.strip()]
            cleaned = [t for t in cleaned if t.lower() not in ("none", "null", "n/a")]
            current_civitai = metadata.get("civitai") or {}
            current_triggers = current_civitai.get("trainedWords") or []
            if self._should_overwrite_list(current_triggers, is_hf_model):
                trig_civitai = dict(current_civitai)
                if "civitai" in updates and isinstance(updates["civitai"], dict):
                    trig_civitai.update(updates["civitai"])
                trig_civitai["trainedWords"] = cleaned
                updates["civitai"] = trig_civitai

        # modelDescription — from raw README content (converted to HTML)
        if readme_content and is_hf_model:
            converted = convert_readme_to_html(readme_content)
            if converted:
                updates["modelDescription"] = converted

        # short_description → civitai.description (for "About this version")
        short_desc = (llm_output.get("short_description") or "").strip()
        if short_desc and is_hf_model:
            current_civitai = metadata.get("civitai") or {}
            desc_civitai = dict(current_civitai)
            if "civitai" in updates and isinstance(updates["civitai"], dict):
                desc_civitai.update(updates["civitai"])
            desc_civitai["description"] = short_desc
            updates["civitai"] = desc_civitai

        # gallery images → civitai.images (from YAML frontmatter widget entries)
        if readme_content and is_hf_model:
            hf_url = metadata.get("hf_url", "") or ""
            repo = extract_repo_from_hf_url(hf_url)
            if repo:
                rec_w = llm_output.get("recommended_width") or 0
                rec_h = llm_output.get("recommended_height") or 0
                gallery = extract_gallery_images(
                    readme_content, repo,
                    default_width=rec_w, default_height=rec_h,
                )
                if gallery:
                    current_civitai = metadata.get("civitai") or {}
                    gallery_civitai = dict(current_civitai)
                    if "civitai" in updates and isinstance(updates["civitai"], dict):
                        gallery_civitai.update(updates["civitai"])
                    gallery_civitai["images"] = gallery
                    updates["civitai"] = gallery_civitai

        # tags
        new_tags = llm_output.get("tags", [])
        if isinstance(new_tags, list) and new_tags:
            existing_tags = metadata.get("tags") or []
            merged = self._merge_tags(existing_tags, new_tags)
            if len(merged) > len(existing_tags) or is_hf_model:
                updates["tags"] = merged

        # metadata_source & llm_enriched_at (always set)
        updates["metadata_source"] = "agent:enrich_hf_metadata"
        updates["llm_enriched_at"] = datetime.now(timezone.utc).isoformat()

        preview_remote_url = (llm_output.get("preview_url") or "").strip()
        current_preview = metadata.get("preview_url") or ""
        if preview_remote_url and not (current_preview and os.path.exists(current_preview)):
            local_path = await download_preview(model_path, preview_remote_url)
            if local_path:
                preview_downloaded = True
                updates["preview_url"] = local_path

        if updates:
            updated_fields = await apply_metadata_updates(model_path, updates)

        # -- Refresh scanner cache ------------------------------------------
        if updated_fields or preview_downloaded:
            await refresh_cache(model_path)

        return {
            "success": True,
            "updated_fields": updated_fields,
            "preview_downloaded": preview_downloaded,
            "errors": [],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _should_overwrite(current_value: str, is_hf_model: bool) -> bool:
        """Return ``True`` when a scalar field should be overwritten."""
        return is_hf_model or not current_value or current_value.lower() in (
            "", "unknown",
        )

    @staticmethod
    def _should_overwrite_list(current_list: List[str], is_hf_model: bool) -> bool:
        """Return ``True`` when a list field should be overwritten."""
        return is_hf_model or not current_list

    @staticmethod
    def _merge_tags(existing: List[str], new: List[str]) -> List[str]:
        """Merge *new* tags into *existing*, all lowercased.

        This matches the behaviour of :class:`TagUpdateService` which
        normalises every tag to lowercase for case-insensitive dedup.
        """
        merged: List[str] = []
        seen: set = set()
        for tag in list(existing) + list(new):
            t = tag.strip().lower()
            if t and t not in seen:
                merged.append(t)
                seen.add(t)
        return merged
