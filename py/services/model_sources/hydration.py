"""Deterministic metadata hydration for freshly downloaded source models.

A CivitAI download writes a fully-populated metadata sidecar as part of the
download itself: the name, the description, the tags, the trigger words and
the example images all arrive with the file.  A download from an external
model source (ModelScope, Hugging Face) has the same information behind a
public API, but historically landed as a bare filename plus a source URL that
the user had to enrich by hand ("Enrich Metadata with AI").

This module closes that gap without involving an LLM.  It fetches the linked
site's model card, hands it to the same :class:`~py.services.agent.post_processor.PostProcessor`
the AI skill uses, and writes the result.  Everything it applies is data the
site published, so it is safe to run automatically on every download and to
treat as a fallback for the gaps the LLM would otherwise fill.

Nothing here may break a download: every failure is logged and normalised to
"the site had nothing to contribute".
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Optional

from .base import ModelCardContext, ModelSourceCache
from .registry import get_source, resolve_source_ref

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .base import ModelSource, SourceRef

logger = logging.getLogger(__name__)

#: How long a fetched repository payload stays usable.  A download batch walks
#: a repository's files one HTTP request at a time, and the README plus the
#: detail payload describe the *repository*, not the file, so re-fetching them
#: per file would be pure waste.  They expire so an edited model card is still
#: picked up by the next batch.
SHARED_CACHE_TTL = 300.0

#: Upper bound on memoised repositories; a long-running server must not grow
#: without limit.
SHARED_CACHE_MAX_ENTRIES = 32

#: ``"<platform>:<source_id>"`` → ``(expiry, memo)``.
_shared_caches: dict[str, tuple[float, ModelSourceCache]] = {}


def shared_source_cache(platform: str, source_id: str) -> ModelSourceCache:
    """Return a short-lived per-repository memo for download-time hydration."""

    now = time.monotonic()
    key = f"{platform}:{source_id}"
    entry = _shared_caches.get(key)
    if entry is not None and entry[0] > now:
        return entry[1]

    for expired in [k for k, (expiry, _) in _shared_caches.items() if expiry <= now]:
        _shared_caches.pop(expired, None)
    if len(_shared_caches) >= SHARED_CACHE_MAX_ENTRIES:
        oldest = min(_shared_caches, key=lambda k: _shared_caches[k][0])
        _shared_caches.pop(oldest, None)

    cache = ModelSourceCache()
    _shared_caches[key] = (now + SHARED_CACHE_TTL, cache)
    return cache


def reset_shared_caches() -> None:
    """Drop every memoised repository — used by tests."""

    _shared_caches.clear()


async def load_model_card(
    source: "ModelSource",
    source_id: str,
    cache: Optional[ModelSourceCache] = None,
) -> str:
    """Return *source_id*'s README, reusing *cache* when one is supplied.

    Only successful reads are memoised, leaving a transient failure to be
    retried for the next file of the same repository.
    """

    key = f"{source.platform}:{source_id}"
    if cache is not None:
        cached = cache.readmes.get(key)
        if cached is not None:
            return cached

    readme = await source.fetch_model_card(source_id)
    if cache is not None and readme:
        cache.readmes[key] = readme
    return readme or ""


async def resolve_site_base_model(context: ModelCardContext) -> str:
    """Resolve the site's base-model hints to a canonical name, or ``""``.

    Sites name base models in their own vocabulary (ModelScope publishes both
    ``krea/Krea-2-Turbo`` and the ``KREA_2_TURBO`` enum).  The resolver is
    strict and only ever returns a name the canonical vocabulary already
    contains, so an uncertain hint yields ``""`` rather than a plausible-looking
    wrong value.
    """

    hints = [*context.base_model_aliases, context.base_model]
    if not any(hints):
        return ""

    # Imported lazily: pulling in the agent package at module scope would make
    # the model-source package import itself while it is still initialising.
    try:
        from ...metadata_ops import list_base_models
        from ..agent.base_model_resolver import resolve_base_model

        known_names = await list_base_models()
    except Exception as exc:
        logger.warning("Could not resolve a site base model: %s", exc)
        return ""
    return resolve_base_model(hints, known_names)


async def hydrate_from_source(
    file_path: str,
    *,
    ref: "SourceRef",
    cache: Optional[ModelSourceCache] = None,
) -> list[str]:
    """Apply the linked site's published metadata to a downloaded model.

    This is the deterministic counterpart of the ``enrich_hf_metadata`` skill:
    it produces the same populated model card a CivitAI download produces,
    without an LLM and without user action.

    Args:
        file_path: The just-downloaded model file, whose sidecar already
            carries the SHA256 used to match the right file in a collection
            repository.
        ref: The source the file came from.
        cache: Optional per-call memo; defaults to a short-lived shared one so
            a batch over one repository fetches its card only once.

    Returns:
        The names of the metadata fields that changed.  Never raises — a site
        that is down, or an API that changed shape, must not fail a download.
    """

    try:
        source = get_source(ref.platform)
        if source is None or not source.supports_enrichment:
            return []

        from ...metadata_ops import read_metadata

        metadata = await read_metadata(file_path)
        if not metadata:
            logger.debug("No metadata to hydrate for %s", file_path)
            return []

        # Only a model that is actually linked to this repository may be
        # updated.  The download path writes those fields just before calling
        # us; a file that merely shares a name with the requested one must not
        # be given another model's card.
        linked = resolve_source_ref(metadata)
        if linked is None or (linked.platform, linked.source_id) != (
            ref.platform,
            ref.source_id,
        ):
            logger.debug(
                "Not hydrating %s: linked to %s, not %s",
                file_path, linked.url if linked else "no model source", ref.url,
            )
            return []

        memo = cache if cache is not None else shared_source_cache(
            ref.platform, ref.source_id
        )
        readme = await load_model_card(source, ref.source_id, memo)
        context = await source.fetch_model_card_context(
            ref.source_id,
            os.path.basename(file_path),
            sha256=(metadata.get("sha256") or "").strip(),
            cache=memo,
        )
        if context.is_empty() and not readme:
            logger.debug(
                "No published metadata for %s on %s", ref.source_id, ref.platform
            )
            return []

        resolved_base_model = await resolve_site_base_model(context)

        from ..agent.post_processor import PostProcessor

        result = await PostProcessor().process(
            skill_name="enrich_hf_metadata",
            model_path=file_path,
            llm_output={},
            metadata=metadata,
            readme_content=readme,
            source_context=context,
            resolved_base_model=resolved_base_model,
            metadata_source=f"source:{ref.platform}",
        )
        if not result.get("success", True):
            logger.debug(
                "Hydration reported failure for %s: %s",
                file_path, result.get("errors"),
            )
            return []

        updated = list(result.get("updated_fields") or [])
        logger.info(
            "Hydrated %s from %s (%s): %s",
            file_path, source.label or ref.platform, ref.source_id,
            ", ".join(updated) or "nothing to change",
        )
        return updated
    except Exception as exc:  # pragma: no cover - defensive by design
        logger.warning("Source hydration failed for %s: %s", file_path, exc)
        return []


__all__ = [
    "SHARED_CACHE_MAX_ENTRIES",
    "SHARED_CACHE_TTL",
    "hydrate_from_source",
    "load_model_card",
    "reset_shared_caches",
    "resolve_site_base_model",
    "shared_source_cache",
]
