"""Registry and metadata helpers for external model sources.

The registry is the single place the rest of the codebase asks "which site
is this URL from?", "what is this model's source?", and "can we enrich it?".
Import from :mod:`py.services.model_sources` rather than this module
directly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

from .base import GROUP_PREFIXES, ModelSource, SourceRef, clean_source_url
from .huggingface import HuggingFaceSource
from .modelscope import ModelScopeSource
from .tensorart import TensorArtSource

logger = logging.getLogger(__name__)

#: Order matters only for disambiguation; the URL patterns are disjoint.
_SOURCES: tuple[ModelSource, ...] = (
    HuggingFaceSource(),
    ModelScopeSource(),
    TensorArtSource(),
)

_BY_PLATFORM: Dict[str, ModelSource] = {s.platform: s for s in _SOURCES}

#: Metadata keys that carry the canonical external-source identity.
SOURCE_PLATFORM_FIELD = "source_platform"
SOURCE_URL_FIELD = "source_url"
#: Legacy field kept as a read/write alias for Hugging Face models so that
#: older sidecars, cached rows, and third-party consumers keep working.
LEGACY_HF_URL_FIELD = "hf_url"


def list_sources() -> list[ModelSource]:
    """Return every known model source."""

    return list(_SOURCES)


def get_source(platform: Optional[str]) -> Optional[ModelSource]:
    """Return the source registered for *platform*, or ``None``."""

    if not platform or not isinstance(platform, str):
        return None
    return _BY_PLATFORM.get(platform.strip().lower())


def source_label(platform: Optional[str], default: str = "") -> str:
    """Return the human-readable label for *platform*."""

    source = get_source(platform)
    return source.label if source else default


def downloadable_sources() -> list[ModelSource]:
    """Return the sources whose repositories can be downloaded directly."""

    return [source for source in _SOURCES if source.supports_download]


def get_download_source(platform: Optional[str]) -> Optional[ModelSource]:
    """Return the source for *platform*, but only when it supports downloads."""

    source = get_source(platform)
    if source is None or not source.supports_download:
        return None
    return source


def detect_source(url: Optional[str], *, strict: bool = False) -> Optional[SourceRef]:
    """Return the :class:`SourceRef` for *url*, or ``None`` if unsupported."""

    if not url or not isinstance(url, str):
        return None
    for source in _SOURCES:
        ref = source.ref(url, strict=strict)
        if ref is not None:
            return ref
    return None


def resolve_source_ref(metadata: Mapping[str, Any]) -> Optional[SourceRef]:
    """Return the source reference described by a model's metadata.

    Handles all three storage states found in the wild:

    1. ``source_url`` + ``source_platform`` (current format)
    2. ``hf_url`` only (legacy Hugging Face storage)
    3. ``hf_url`` plus a newer ``source_url`` (both written by older builds)
    """

    if not isinstance(metadata, Mapping):
        return None

    platform = clean_source_url(metadata.get(SOURCE_PLATFORM_FIELD)).lower()
    url = clean_source_url(metadata.get(SOURCE_URL_FIELD))
    legacy = clean_source_url(metadata.get(LEGACY_HF_URL_FIELD))

    source = get_source(platform)
    if url:
        if source is not None:
            ref = source.ref(url)
            if ref is not None:
                return ref
        ref = detect_source(url)
        if ref is not None:
            return ref
        # Unknown platform but a URL is present: keep it addressable.
        return SourceRef(platform=platform or "unknown", source_id="", url=url)

    if legacy:
        return detect_source(legacy)
    return None


def normalize_metadata_source(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise the external-source fields on *metadata* in place.

    Guarantees that ``source_url``/``source_platform`` are present and
    consistent, and that ``hf_url`` mirrors ``source_url`` for Hugging Face
    models (never for other platforms, so a stale alias can't make a
    ModelScope model look like a Hugging Face one).

    Returns the same dict for convenient chaining.
    """

    if not isinstance(metadata, dict):
        return metadata

    platform = clean_source_url(metadata.get(SOURCE_PLATFORM_FIELD)).lower()
    url = clean_source_url(metadata.get(SOURCE_URL_FIELD))
    legacy = clean_source_url(metadata.get(LEGACY_HF_URL_FIELD))

    source = get_source(platform)
    ref: Optional[SourceRef] = None

    if url:
        ref = source.ref(url) if source is not None else None
        if ref is None:
            ref = detect_source(url)
    elif legacy:
        ref = detect_source(legacy)

    if ref is not None and ref.source_id:
        platform = ref.platform
        url = ref.url or url

    if platform:
        metadata[SOURCE_PLATFORM_FIELD] = platform
    else:
        metadata.setdefault(SOURCE_PLATFORM_FIELD, "")

    metadata[SOURCE_URL_FIELD] = url

    # Keep the legacy alias in sync, but only for Hugging Face.
    if url and platform == "huggingface":
        metadata[LEGACY_HF_URL_FIELD] = url
    elif LEGACY_HF_URL_FIELD in metadata and platform and platform != "huggingface":
        metadata[LEGACY_HF_URL_FIELD] = ""
    elif legacy and not url:
        metadata[LEGACY_HF_URL_FIELD] = legacy

    return metadata


def has_external_source(item: Mapping[str, Any]) -> bool:
    """Return ``True`` when *item* is linked to any external model site."""

    if not isinstance(item, Mapping):
        return False
    return bool(
        clean_source_url(item.get(SOURCE_URL_FIELD))
        or clean_source_url(item.get(LEGACY_HF_URL_FIELD))
    )


def get_source_platform(item: Mapping[str, Any]) -> str:
    """Return the platform id stored on *item* (may be empty)."""

    if not isinstance(item, Mapping):
        return ""
    platform = clean_source_url(item.get(SOURCE_PLATFORM_FIELD)).lower()
    if platform:
        return platform
    ref = resolve_source_ref(item)
    return ref.platform if ref else ""


def source_group_key(item: Mapping[str, Any]) -> Optional[str]:
    """Return the version-group key for *item*, or ``None``.

    Hugging Face keeps the historical ``hf:{owner}/{repo}`` shape; other
    platforms use their own short prefix (see :data:`GROUP_PREFIXES`).
    """

    ref = resolve_source_ref(item)
    if ref is None or not ref.source_id:
        return None
    source = get_source(ref.platform)
    if source is None:
        return None
    return source.group_key(ref.source_id)


__all__ = [
    "GROUP_PREFIXES",
    "LEGACY_HF_URL_FIELD",
    "SOURCE_PLATFORM_FIELD",
    "SOURCE_URL_FIELD",
    "detect_source",
    "downloadable_sources",
    "get_download_source",
    "get_source",
    "get_source_platform",
    "has_external_source",
    "list_sources",
    "normalize_metadata_source",
    "resolve_source_ref",
    "source_group_key",
    "source_label",
]
