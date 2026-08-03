"""Shared helpers for Metadata Overwrite node metadata collection.

Used by both the MetadataOverwriteLM node (execution time) and the
MetadataOverwriteExtractor (hook time) so the conversion/filtering logic
cannot drift between the two paths.
"""

import logging
from typing import Any, Dict

from ..utils.utils import model_patcher_to_name
from .constants import CLIP_SKIP_SENTINEL, METADATA_OVERWRITE_FIELDS

logger = logging.getLogger(__name__)


def collect_overwrite_params(values: Dict[str, Any]) -> Dict[str, Any]:
    """Convert node input values into non-default overwrite parameters.

    For most fields, a falsy value (empty string, 0) means "not set" and is
    skipped.  clip_skip uses a dedicated sentinel (-25) so that a wired value
    of 0 is preserved.  The ``model`` field accepts either a manual string or
    a wired MODEL (ModelPatcher) connection; in the latter case the source
    model name is extracted from the patcher's ``cached_patcher_init`` and
    stored as a ComfyUI-style relative path.
    """
    result: Dict[str, Any] = {}
    for key in METADATA_OVERWRITE_FIELDS:
        value = values.get(key)
        if key == "model" and not isinstance(value, str):
            value = model_patcher_to_name(value)
            if value is None:
                logger.warning(
                    "Could not extract model name from wired MODEL input "
                    "(no cached_patcher_init); model metadata overwrite skipped"
                )
        if key == "clip_skip":
            if value != CLIP_SKIP_SENTINEL:
                result[key] = value
        elif value:
            result[key] = value
    return result
