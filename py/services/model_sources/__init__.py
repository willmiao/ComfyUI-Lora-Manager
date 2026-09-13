"""External model-source providers (Hugging Face, ModelScope, TensorArt).

This package is the single abstraction over "a site that hosts models and
a model card".  See :mod:`py.services.model_sources.base` for the provider
protocol and :mod:`py.services.model_sources.registry` for the lookup and
metadata-normalisation helpers used across the codebase.
"""

from __future__ import annotations

from .base import (
    GROUP_PREFIXES,
    HTTP_TIMEOUT,
    ModelSource,
    ModelSourceError,
    SourceRef,
    USER_AGENT,
    clean_source_url,
    fetch_json,
    fetch_text,
    filter_weight_files,
    is_valid_source_id,
)
from .huggingface import HuggingFaceSource
from .modelscope import ModelScopeSource
from .registry import (
    LEGACY_HF_URL_FIELD,
    SOURCE_PLATFORM_FIELD,
    SOURCE_URL_FIELD,
    detect_source,
    downloadable_sources,
    get_download_source,
    get_source,
    get_source_platform,
    has_external_source,
    list_sources,
    normalize_metadata_source,
    resolve_source_ref,
    source_group_key,
    source_label,
)
from .tensorart import TensorArtSource

__all__ = [
    "GROUP_PREFIXES",
    "HTTP_TIMEOUT",
    "LEGACY_HF_URL_FIELD",
    "ModelSource",
    "ModelSourceError",
    "HuggingFaceSource",
    "ModelScopeSource",
    "SOURCE_PLATFORM_FIELD",
    "SOURCE_URL_FIELD",
    "SourceRef",
    "TensorArtSource",
    "USER_AGENT",
    "clean_source_url",
    "detect_source",
    "downloadable_sources",
    "fetch_json",
    "fetch_text",
    "filter_weight_files",
    "get_download_source",
    "get_source",
    "get_source_platform",
    "has_external_source",
    "is_valid_source_id",
    "list_sources",
    "normalize_metadata_source",
    "resolve_source_ref",
    "source_group_key",
    "source_label",
]
