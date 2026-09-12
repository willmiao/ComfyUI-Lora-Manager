"""Shared download routing logic.

Decides whether a download initiated from the checkpoint library should be
routed to the unet/diffusion-model roots instead of the checkpoint roots.
Used by both the download manager (at download time) and the download
routing HTTP endpoint (when the user picks a location in the UI), so the
two can never disagree.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from ..utils.constants import (
    CIVITAI_FILE_TYPE_TO_OTHER_SUB_TYPE,
    CIVITAI_TYPE_TO_OTHER_SUB_TYPE,
    DIFFUSION_MODEL_BASE_MODELS,
)

logger = logging.getLogger(__name__)

# File types reported by the CivitAI API that indicate a raw diffusion
# model (loaded via UNETLoader in ComfyUI) rather than a full checkpoint.
DIFFUSION_FILE_TYPES = frozenset({"UNet", "Diffusion Model"})


def is_diffusion_model_download(
    model_type: str,
    file_types: Iterable[str] = (),
    base_model: str = "",
) -> bool:
    """Return True when a download should be routed to the unet roots.

    Only applies to downloads initiated from the checkpoint library.
    Priority: (1) any file has type "UNet" or "Diffusion Model" (the more
    direct signal from CivitAI), (2) baseModel is a known diffusion model.
    """
    if model_type != "checkpoint":
        return False

    for file_type in file_types:
        if file_type in DIFFUSION_FILE_TYPES:
            logger.info(
                "File type '%s' detected, routing checkpoint to unet folder",
                file_type,
            )
            return True

    if base_model in DIFFUSION_MODEL_BASE_MODELS:
        logger.info(
            "baseModel '%s' is a known diffusion model, routing to unet folder",
            base_model,
        )
        return True

    return False


def resolve_other_download_sub_type(
    civitai_model_type: str,
    file_types: Iterable[str] = (),
    selected_file_type: Optional[str] = None,
) -> Optional[str]:
    """Resolve the "other"-page sub_type for a download.

    Fixed priority (locked design, docs/plans/other-models-page.md §9.2):

    1. Explicit user file pick — when the picked file's type maps, it wins
       even when model.type maps to something else.
    2. model.type via CIVITAI_TYPE_TO_OTHER_SUB_TYPE.
    3. file.type fallback — only when model.type maps to nothing. Must NOT
       override a mapped model.type: checkpoint models routinely bundle
       VAE/Text Encoder component files.
    4. Still undecidable -> None (caller must ask the user for a folder).
    """
    if selected_file_type:
        mapped = CIVITAI_FILE_TYPE_TO_OTHER_SUB_TYPE.get(selected_file_type)
        if mapped:
            logger.info(
                "Explicit file pick type '%s' routes other download to '%s'",
                selected_file_type,
                mapped,
            )
            return mapped

    normalized_model_type = (civitai_model_type or "").strip().lower()
    mapped = CIVITAI_TYPE_TO_OTHER_SUB_TYPE.get(normalized_model_type)
    if mapped:
        return mapped

    for file_type in file_types:
        mapped = CIVITAI_FILE_TYPE_TO_OTHER_SUB_TYPE.get(file_type)
        if mapped:
            logger.info(
                "model.type '%s' unmapped; file type '%s' routes other download to '%s'",
                civitai_model_type,
                file_type,
                mapped,
            )
            return mapped

    return None
