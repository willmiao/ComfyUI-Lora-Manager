"""Shared download routing logic.

Decides whether a download initiated from the checkpoint library should be
routed to the unet/diffusion-model roots instead of the checkpoint roots.
Used by both the download manager (at download time) and the download
routing HTTP endpoint (when the user picks a location in the UI), so the
two can never disagree.
"""

from __future__ import annotations

import logging
from typing import Iterable

from ..utils.constants import DIFFUSION_MODEL_BASE_MODELS

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
