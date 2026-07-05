"""Metadata operations — thin in-process wrappers around LoRA Manager internal services.

All functions are simple Python async functions that delegate to the
appropriate internal service.  They use **relative imports** within the
``py`` package, so ``sys.modules`` caching works normally and there is no
risk of double import or circular dependencies.

Usage (in-process, primary)::

    from py.metadata_ops import list_base_models, read_metadata

    models = await list_base_models()
    meta   = await read_metadata("/path/to/model.safetensors")

Usage (subprocess, debugging / external)::

    python -m py.metadata_ops base-models list
    python -m py.metadata_ops metadata read /path/to/model.safetensors
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCANNER_TYPE_MAP: dict[str, str] = {
    "get_lora_scanner": "lora",
    "get_checkpoint_scanner": "checkpoint",
    "get_embedding_scanner": "embedding",
}

SCANNER_GETTER_NAMES = tuple(SCANNER_TYPE_MAP.keys())


async def _find_scanner_for_model(
    model_path: str,
) -> tuple[object, object] | tuple[None, None]:
    """Find the (scanner, cache_entry) responsible for *model_path*.

    Iterates all known scanner types and returns the first one whose cache
    contains the given path.  Returns ``(None, None)`` when no scanner
    claims the model.
    """
    from ..services.service_registry import ServiceRegistry

    normalized = os.path.normpath(model_path)
    for getter_name in SCANNER_GETTER_NAMES:
        getter = getattr(ServiceRegistry, getter_name, None)
        if getter is None:
            continue
        try:
            scanner = await getter()
            if scanner is None:
                continue
            cache = await scanner.get_cached_data()
            for entry in cache.raw_data:
                if os.path.normpath(entry.get("file_path", "")) == normalized:
                    return scanner, entry
        except Exception as exc:
            logger.debug(
                "Scanner %s check failed for %s: %s",
                getter_name,
                model_path,
                exc,
            )
    return None, None


async def identify_model_type(model_path: str) -> str:
    """Determine the model type (``\"lora\"``, ``\"checkpoint\"``, or
    ``\"embedding\"``) for *model_path*.

    Iterates all known scanners; the first scanner that claims the path
    determines the type.  Falls back to ``\"lora\"`` when unknown.
    """
    from ..services.service_registry import ServiceRegistry

    normalized = os.path.normpath(model_path)
    for getter_name in SCANNER_GETTER_NAMES:
        getter = getattr(ServiceRegistry, getter_name, None)
        if getter is None:
            continue
        try:
            scanner = await getter()
            if scanner is None:
                continue
            cache = await scanner.get_cached_data()
            for entry in cache.raw_data:
                if os.path.normpath(entry.get("file_path", "")) == normalized:
                    return SCANNER_TYPE_MAP[getter_name]
        except Exception as exc:
            logger.debug(
                "identify_model_type scanner %s error for %s: %s",
                getter_name,
                model_path,
                exc,
            )
    return "lora"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def list_base_models(limit: int = 0) -> List[str]:
    """Return all valid CivitAI base model names.

    Uses ``CivitaiBaseModelService.get_base_models()`` which merges a
    hardcoded list (``SUPPORTED_DOWNLOAD_SKIP_BASE_MODELS``) with remote
    models fetched from the CivitAI API.  Never empty — the hardcoded
    fallback always provides a complete set.

    The result is sorted alphabetically.  Pass *limit* = 0 for all models.
    """
    from ..services.civitai_base_model_service import (
        CivitaiBaseModelService,
    )

    try:
        service = await CivitaiBaseModelService.get_instance()
        response = await service.get_base_models()
        names: List[str] = response.get("models", [])
    except Exception as exc:
        logger.warning("list_base_models failed: %s", exc)
        names = []
    if limit > 0:
        return names[:limit]
    return names


async def read_metadata(model_path: str) -> Dict[str, Any]:
    """Load the full metadata payload for *model_path* from disk.

    Returns an empty dict when the metadata file does not exist or cannot
    be parsed — never raises.
    """
    from ..utils.metadata_manager import MetadataManager

    try:
        return await MetadataManager.load_metadata_payload(model_path) or {}
    except Exception as exc:
        logger.warning("read_metadata failed for %s: %s", model_path, exc)
        return {}


async def apply_metadata_updates(
    model_path: str,
    updates: Dict[str, Any],
) -> List[str]:
    """Merge *updates* into the model's on-disk metadata and persist.

    Returns the list of field names that actually changed.
    """
    from ..utils.metadata_manager import MetadataManager

    metadata = await read_metadata(model_path)
    updated_fields: List[str] = []
    for key, value in updates.items():
        old = metadata.get(key)
        if old != value:
            metadata[key] = value
            updated_fields.append(key)
    if updated_fields:
        await MetadataManager.save_metadata(model_path, metadata)
    return updated_fields


async def download_preview(
    model_path: str,
    url: str,
    *,
    target_width: int = 480,
    quality: int = 85,
) -> str | None:
    """Download a preview image from *url*, optimise to .webp, and save it.

    The output file is placed alongside the model file with a ``.webp``
    extension.  Returns the local file path on success, ``None`` on failure.
    """
    from ..services.downloader import get_downloader
    from ..utils.exif_utils import ExifUtils

    if not url or not url.strip():
        return None

    base_name = os.path.splitext(os.path.basename(model_path))[0]
    preview_dir = os.path.dirname(model_path)
    output_path = os.path.join(preview_dir, base_name + ".webp")

    downloader = await get_downloader()

    # Try in-memory download + optimise first
    success, content, _headers = await downloader.download_to_memory(
        url, use_auth=False,
    )
    if success and content:
        try:
            optimized_data, _ = ExifUtils.optimize_image(
                image_data=content,
                target_width=target_width,
                format="webp",
                quality=quality,
                preserve_metadata=False,
            )
            with open(output_path, "wb") as f:
                f.write(optimized_data)
            return output_path
        except Exception as exc:
            logger.warning("Preview optimisation failed, saving raw: %s", exc)
            # Fall through to raw save

    # Fallback: download directly to file
    try:
        ok, _ = await downloader.download_file(url, output_path, use_auth=False)
        if ok:
            return output_path
    except Exception as exc:
        logger.warning("Preview fallback download failed for %s: %s", model_path, exc)

    return None


async def refresh_cache(model_path: str) -> bool:
    """Invalidate and reload the scanner cache entry for *model_path*.

    Returns ``True`` when the model was found and the cache was refreshed.
    """
    scanner, entry = await _find_scanner_for_model(model_path)
    if scanner is None:
        logger.warning("refresh_cache: no scanner found for %s", model_path)
        return False
    try:
        metadata = await read_metadata(model_path)
        if not metadata:
            logger.warning("refresh_cache: no metadata for %s", model_path)
            return False
        await scanner.update_single_model_cache(model_path, model_path, metadata)
        return True
    except Exception as exc:
        logger.warning("refresh_cache failed for %s: %s", model_path, exc)
        return False
