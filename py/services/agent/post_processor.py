"""Post-processing engine for skill pipeline outputs.

The :class:`PostProcessor` takes the LLM's structured JSON output and applies
it to a model's on-disk metadata via the :mod:`~py.metadata_ops` functions.

It handles all the skill-specific business logic — conditions, transformations,
and orchestration of multiple side-effects (write metadata, download preview,
refresh cache).  All actual I/O is delegated to :mod:`~py.metadata_ops`.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..model_sources import ModelCardContext

logger = logging.getLogger(__name__)


class PostProcessor:
    """Deterministic post-processor for skill pipeline outputs.

    Usage (called by :class:`~py.services.agent.agent_service.AgentService`)::

        processor = PostProcessor()
        result = await processor.process(
            skill_name="enrich_hf_metadata",
            model_path="/path/to/model.safetensors",
            llm_output={...},
            metadata={...},    # from metadata_ops.read_metadata()
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
        source_context: Optional["ModelCardContext"] = None,
        resolved_base_model: str = "",
    ) -> Dict[str, Any]:
        """Route *llm_output* to the correct skill post-processor.

        *readme_content* is optional raw markdown content (e.g. HF README)
        that is converted to HTML and stored as ``modelDescription`` for
        the description tab.

        *source_context* carries the extras the model site publishes outside
        the README (author description, per-file example images, trigger
        words).  It is ``None`` for callers that have none.

        *resolved_base_model* is the canonical base-model name the site's own
        hints resolve to, used when the LLM did not supply one (which is the
        normal case when the LLM was skipped).

        Returns a dict with keys ``success`` (bool), ``updated_fields`` (list),
        ``preview_downloaded`` (bool), and ``errors`` (list).
        """
        if skill_name == "enrich_hf_metadata":
            return await self._process_enrich_hf_metadata(
                model_path, llm_output, metadata, readme_content, source_context,
                resolved_base_model,
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
        source_context: Optional["ModelCardContext"] = None,
        resolved_base_model: str = "",
    ) -> Dict[str, Any]:
        from ...metadata_ops import (
            apply_metadata_updates,
            download_preview,
            refresh_cache,
        )
        from ..model_sources import get_source, has_external_source, resolve_source_ref
        from .skills.enrich_hf_metadata.readme_processor import (
            convert_readme_to_html,
            extract_gallery_images,
            extract_gallery_table_images,
            extract_relevant_section,
            extract_simple_markdown_images,
            extract_html_img_tags,
        )

        updated_fields: List[str] = []
        preview_downloaded = False

        # -- Determine whether this is an externally-sourced model ---------
        # Key off the source fields directly: `from_civitai` records provenance
        # and can be true for a model that is also linked to an external site
        # (both sources coexist, see #1094), so it must not gate enrichment.
        is_source_model = has_external_source(metadata)

        source_ref = resolve_source_ref(metadata)
        source = get_source(source_ref.platform) if source_ref else None
        source_id = source_ref.source_id if source_ref else ""
        asset_base_url = (
            source.asset_base_url(source_id)
            if source is not None and source_id
            else None
        )

        # -- Collect updates -----------------------------------------------
        updates: Dict[str, Any] = {}

        # base_model — the LLM's mapping wins; when it returned nothing usable,
        # fall back to the canonical name the site's own hints resolve to.
        new_base = (llm_output.get("base_model") or "").strip()
        if not new_base:
            new_base = (resolved_base_model or "").strip()
        current_base = metadata.get("base_model", "") or ""
        if new_base and self._should_overwrite(current_base, is_source_model):
            updates["base_model"] = new_base

        # trigger words → civitai.trainedWords
        new_triggers = llm_output.get("trigger_words", [])
        trigger_words_empty = True
        if isinstance(new_triggers, list):
            cleaned = [t.strip() for t in new_triggers if t.strip()]
            cleaned = [t for t in cleaned if t.lower() not in ("none", "null", "n/a")]
            trigger_words_empty = not cleaned
            current_civitai = metadata.get("civitai") or {}
            current_triggers = current_civitai.get("trainedWords") or []
            if self._should_overwrite_list(current_triggers, is_source_model):
                trig_civitai = dict(current_civitai)
                if "civitai" in updates and isinstance(updates["civitai"], dict):
                    trig_civitai.update(updates["civitai"])
                trig_civitai["trainedWords"] = cleaned
                updates["civitai"] = trig_civitai

        # modelDescription — the author's own summary (when the site keeps one
        # outside the README, e.g. ModelScope's ``Description``) followed by the
        # README converted to HTML.
        site_description = (
            (source_context.description if source_context else "") or ""
        ).strip()
        if is_source_model and (site_description or readme_content):
            parts: List[str] = []
            if site_description:
                parts.append(f"<p>{html.escape(site_description)}</p>")
            if readme_content:
                converted = convert_readme_to_html(readme_content)
                if converted:
                    parts.append(converted)
            if parts:
                updates["modelDescription"] = "\n".join(parts)

        # short_description → civitai.description (for "About this version").
        # Falls back to the site's author summary, which for ModelScope AIGC
        # models is frequently the only human-written text available.
        short_desc = (llm_output.get("short_description") or "").strip()
        if not short_desc:
            short_desc = site_description
        if short_desc and is_source_model:
            current_civitai = metadata.get("civitai") or {}
            desc_civitai = dict(current_civitai)
            if "civitai" in updates and isinstance(updates["civitai"], dict):
                desc_civitai.update(updates["civitai"])
            desc_civitai["description"] = short_desc
            updates["civitai"] = desc_civitai

        # gallery images → civitai.images (site example images, YAML frontmatter
        # widget entries, and Sample Gallery markdown tables in the README body)
        rec_width = llm_output.get("recommended_width") or 0
        rec_height = llm_output.get("recommended_height") or 0

        # Example images the site publishes for *this* file.  They are matched
        # by filename, so they are the most precise preview source available
        # and the only one for repositories whose README carries no images.
        site_images: List[Dict[str, Any]] = []
        if is_source_model and source_context is not None:
            site_images = [
                _example_image(url, rec_width, rec_height)
                for url in source_context.example_images
                if url
            ]

        gallery_images: List[Dict[str, Any]] = []
        if (readme_content or site_images) and is_source_model:
            repo = source_id
            readme_images: List[Dict[str, Any]] = []
            if readme_content and repo:
                # 1. Widget images (YAML frontmatter)
                gallery = extract_gallery_images(
                    readme_content, repo,
                    default_width=rec_width, default_height=rec_height,
                    base_url=asset_base_url,
                )

                # 2. Sample Gallery table images (markdown body), deduplicated
                existing_urls = {img["url"] for img in gallery if img.get("url")}
                table_images = extract_gallery_table_images(
                    readme_content, repo,
                    existing_urls=existing_urls,
                    default_width=rec_width, default_height=rec_height,
                    base_url=asset_base_url,
                )
                existing_urls.update(img["url"] for img in table_images if img.get("url"))

                # 3. Simple markdown images `![alt](url)` in the body
                simple_images = extract_simple_markdown_images(
                    readme_content, repo,
                    existing_urls=existing_urls,
                    default_width=rec_width, default_height=rec_height,
                    base_url=asset_base_url,
                )
                existing_urls.update(img["url"] for img in simple_images if img.get("url"))

                # 4. HTML `<img>` tags (used by many collection repos)
                html_images = extract_html_img_tags(
                    readme_content, repo,
                    existing_urls=existing_urls,
                    default_width=rec_width, default_height=rec_height,
                    base_url=asset_base_url,
                )

                readme_images = gallery + table_images + simple_images + html_images

            # Site images come first so the preview fallback below prefers an
            # image that is known to belong to this exact file.
            all_images = _dedupe_images(site_images + readme_images)
            if all_images:
                gallery_images = all_images
                current_civitai = metadata.get("civitai") or {}
                gallery_civitai = dict(current_civitai)
                if "civitai" in updates and isinstance(updates["civitai"], dict):
                    gallery_civitai.update(updates["civitai"])
                gallery_civitai["images"] = all_images
                updates["civitai"] = gallery_civitai

        # tags — the site's curated tags are authoritative content vocabulary, so
        # they are kept alongside whatever the LLM proposed (the LLM is skipped
        # entirely when the site data is complete, which is why this cannot rely
        # on ``llm_output`` alone).
        new_tags = llm_output.get("tags", [])
        candidate_tags: List[str] = []
        if is_source_model and source_context is not None:
            candidate_tags.extend(source_context.official_tags)
        if isinstance(new_tags, list):
            candidate_tags.extend(
                tag for tag in new_tags if tag not in candidate_tags
            )
        if candidate_tags:
            existing_tags = metadata.get("tags") or []
            merged = self._merge_tags(existing_tags, candidate_tags)
            if len(merged) > len(existing_tags) or is_source_model:
                updates["tags"] = merged

        # metadata_source & llm_enriched_at (always set)
        updates["metadata_source"] = "agent:enrich_hf_metadata"
        updates["llm_enriched_at"] = datetime.now(timezone.utc).isoformat()

        # LLM confidence, stored for the enrichment evaluation harness.  The key
        # must NOT start with an underscore: `BaseModelMetadata.from_dict()`
        # deliberately drops underscore-prefixed keys so they never round-trip,
        # which silently erased this field on the next metadata write.
        raw_confidence = (llm_output.get("confidence") or "").strip()
        if raw_confidence:
            updates["llm_confidence"] = raw_confidence

        # Fallback: use the trigger words the site records for this exact file,
        # then the README's YAML `instance_prompt`, when the LLM returned none.
        if trigger_words_empty:
            site_triggers = (
                list(source_context.trigger_words) if source_context else []
            )
            if not site_triggers:
                instance_prompt = _extract_yaml_instance_prompt(readme_content)
                if instance_prompt:
                    site_triggers = [instance_prompt]
            if site_triggers:
                current_civitai = metadata.get("civitai") or {}
                trig_civitai = dict(current_civitai)
                if "civitai" in updates and isinstance(updates["civitai"], dict):
                    trig_civitai.update(updates["civitai"])
                trig_civitai["trainedWords"] = site_triggers
                updates["civitai"] = trig_civitai

        preview_remote_url = (llm_output.get("preview_url") or "").strip()
        # Fallback: if the LLM couldn't find a preview image in the cleaned
        # README, find the first gallery image from the *model-specific
        # section* of the README (not the repo-wide first image, which
        # belongs to a different model in collection repos).
        if not preview_remote_url and readme_content and is_source_model:
            model_basename = os.path.splitext(os.path.basename(model_path))[0]
            relevant_section = extract_relevant_section(
                readme_content, model_basename,
            )
            if relevant_section and relevant_section != readme_content:
                for img in gallery_images:
                    img_url = img.get("url", "")
                    if img_url and img_url in relevant_section:
                        preview_remote_url = img_url
                        break
        # Last resort: use the first gallery image from the full README.
        if not preview_remote_url and gallery_images:
            preview_remote_url = gallery_images[0].get("url", "")
        current_preview = metadata.get("preview_url") or ""
        if preview_remote_url and not (current_preview and os.path.exists(current_preview)):
            local_path = await download_preview(model_path, preview_remote_url)
            if local_path:
                preview_downloaded = True
                updates["preview_url"] = local_path

        # notes — plain-text summary of usage info from the LLM
        new_notes = (llm_output.get("notes") or "").strip()
        if new_notes:
            updates["notes"] = new_notes

        # usage_tips — JSON string (e.g. {"strength_min":0.85,"strength_max":1.4}).
        # When the LLM returned nothing, recover an explicitly stated strength
        # range from the author summary so the value is not lost.
        raw_tips = (llm_output.get("usage_tips") or "").strip()
        if not raw_tips or raw_tips == "{}":
            raw_tips = _extract_usage_tips(site_description)
        if raw_tips and raw_tips != "{}":
            try:
                json.loads(raw_tips)
                updates["usage_tips"] = raw_tips
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "LLM returned invalid usage_tips JSON: %s", raw_tips[:200]
                )

        if updates:
            updated_fields = await apply_metadata_updates(model_path, updates)

        # -- Refresh scanner cache ------------------------------------------
        if updated_fields or preview_downloaded:
            await refresh_cache(model_path)

        return {
            "success": True,
            "updated_fields": updated_fields,
            "preview_downloaded": preview_downloaded,
            "updates": updates,
            "errors": [],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _should_overwrite(current_value: str, is_source_model: bool) -> bool:
        """Return ``True`` when a scalar field should be overwritten."""
        return is_source_model or not current_value or current_value.lower() in (
            "", "unknown",
        )

    @staticmethod
    def _should_overwrite_list(current_list: List[str], is_source_model: bool) -> bool:
        """Return ``True`` when a list field should be overwritten."""
        return is_source_model or not current_list

    @staticmethod
    def _merge_tags(existing: List[str], new: List[str]) -> List[str]:
        """Merge *new* tags into *existing*, all lowercased.

        This matches the behaviour of :class:`TagUpdateService` which
        normalises every tag to lowercase for case-insensitive dedup.
        """
        merged: List[str] = []
        seen: set[str] = set()
        for tag in list(existing) + list(new):
            t = tag.strip().lower()
            if t and t not in seen:
                merged.append(t)
                seen.add(t)
        return merged


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


#: Separator between a label and its value.  Published model cards routinely
#: wrap the numbers in markdown emphasis or quotes (``strength: **0.85 - 1.4**``,
#: ``CLIP 强度「0.5」``), so those are absorbed rather than treated as a break.
_EMPHASIS = "[\"'\u201c\u201d\u300c\u300d*_`\\s]*"

#: An explicitly stated strength/weight range, e.g. ``权重0.5-1.2``,
#: ``强度 0.8 ~ 1.2``, ``strength: **0.85 - 1.4**``.
_RANGE_DASH = "(?:-|\u2010|\u2011|\u2012|\u2013|\u2014|\uff0d|~|\uff5e|\u81f3|\u5230|to)"

_STRENGTH_RANGE_RE = re.compile(
    "(?:\u6743\u91cd|\u5f3a\u5ea6|strength|weight)" + _EMPHASIS + "[:\uff1a]?" + _EMPHASIS
    + r"(\d+(?:\.\d+)?)" + _EMPHASIS + _RANGE_DASH + _EMPHASIS
    + r"(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

#: A single strength/weight value, e.g. ``strength: 0.6``, ``权重 0.8``.
_STRENGTH_VALUE_RE = re.compile(
    "(?:\u6743\u91cd|\u5f3a\u5ea6|strength|weight)" + _EMPHASIS + "[:\uff1a]?" + _EMPHASIS
    + r"(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

#: ``clip strength: 0.5`` / ``CLIP 强度 0.5``.
_CLIP_STRENGTH_RE = re.compile(
    "clip" + _EMPHASIS + "(?:\u5f3a\u5ea6|strength)" + _EMPHASIS + "[:\uff1a]?" + _EMPHASIS
    + r"(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

#: ``clip skip: 2`` / ``CLIP 跳过 2``.
_CLIP_SKIP_RE = re.compile(
    "clip" + _EMPHASIS + "(?:skip|\u8df3\u8fc7)" + _EMPHASIS + "[:\uff1a]?" + _EMPHASIS
    + r"(\d+)",
    re.IGNORECASE,
)


def _extract_usage_tips(text: str) -> str:
    """Extract stated strength/CLIP recommendations from prose.

    This is the deterministic counterpart to the LLM's ``usage_tips`` output,
    used when the LLM was skipped.  It only recognises explicitly written
    values — it never infers a range — and returns ``""`` when it finds none.

    Returns:
        A JSON string matching the skill's ``usage_tips`` schema, or ``""``.
    """

    if not text:
        return ""

    tips: Dict[str, Any] = {}

    # CLIP strength is resolved first and then blanked out, so the generic
    # strength patterns cannot mistake `CLIP 强度 0.5` for the LoRA strength.
    text_for_strength = text
    clip_strength = _CLIP_STRENGTH_RE.search(text_for_strength)
    if clip_strength:
        tips["clip_strength"] = float(clip_strength.group(1))
        text_for_strength = (
            text_for_strength[: clip_strength.start()]
            + " "
            + text_for_strength[clip_strength.end() :]
        )

    range_match = _STRENGTH_RANGE_RE.search(text_for_strength)
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        if low > high:
            low, high = high, low
        tips["strength_min"] = low
        tips["strength_max"] = high
        tips["strength_range"] = f"{low:g}-{high:g}"
    else:
        value_match = _STRENGTH_VALUE_RE.search(text_for_strength)
        if value_match:
            tips["strength"] = float(value_match.group(1))

    clip_skip = _CLIP_SKIP_RE.search(text)
    if clip_skip:
        tips["clip_skip"] = int(clip_skip.group(1))

    if not tips:
        return ""
    return json.dumps(tips, ensure_ascii=False)


def _example_image(url: str, width: int, height: int) -> Dict[str, Any]:
    """Build a ``civitai.images`` entry for a site-provided example image.

    The site publishes no prompt alongside these images, so the entry carries
    empty prompt metadata and the LLM's recommended dimensions when it found
    any (falling back to the same 512px placeholder the README extractors use).
    """

    return {
        "url": url,
        "type": "image",
        "nsfwLevel": 0,
        "width": width or 512,
        "height": height or 512,
        "meta": {"prompt": "", "negativePrompt": ""},
        "hasMeta": False,
        "hasPositivePrompt": False,
    }


def _dedupe_images(images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop later entries that repeat an earlier image URL, keeping order."""

    seen: set[str] = set()
    unique: List[Dict[str, Any]] = []
    for image in images:
        url = image.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(image)
    return unique


def _extract_yaml_instance_prompt(readme_content: str) -> str:
    """Extract ``instance_prompt`` from the YAML frontmatter of a HF README.

    Returns the prompt text, or empty string if not found.  Handles
    ``null`` / ``~`` YAML null values by returning empty string.
    """
    if not readme_content or not readme_content.startswith("---"):
        return ""

    # Find end of frontmatter
    end = readme_content.find("---", 3)
    if end == -1:
        return ""
    frontmatter = readme_content[3:end]

    for line in frontmatter.split("\n"):
        line = line.strip()
        m = re.match(r"^instance_prompt:\s*(.*)", line)
        if m:
            val = m.group(1).strip().strip('"').strip("'")
            if val.lower() in ("null", "~", "none", ""):
                return ""
            return val

    return ""
