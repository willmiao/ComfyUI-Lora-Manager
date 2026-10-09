"""Shared download routing logic.

Decides whether a download initiated from the checkpoint library should be
routed to the unet/diffusion-model roots instead of the checkpoint roots.
Used by both the download manager (at download time) and the download
routing HTTP endpoint (when the user picks a location in the UI), so the
two can never disagree.
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping, Optional, Sequence

from ..utils.constants import (
    CHECKPOINT_BASE_MODELS,
    CIVITAI_FILE_TYPE_TO_OTHER_SUB_TYPE,
    CIVITAI_TYPE_TO_OTHER_SUB_TYPE,
    DIFFUSION_MODEL_BASE_MODELS,
)

logger = logging.getLogger(__name__)

# File types reported by the CivitAI API that indicate a raw diffusion
# model (loaded via UNETLoader in ComfyUI) rather than a full checkpoint.
DIFFUSION_FILE_TYPES = frozenset({"UNet", "Diffusion Model"})

# Allowed values for the "unknown_base_model_routing" setting / the
# unknown_base_model_default parameter below.
ROUTING_DIFFUSION_MODEL = "diffusion_model"
ROUTING_CHECKPOINT = "checkpoint"

# Download-time model type -> download_root_rules folder key. The rule set is
# keyed by folder_paths keys, so a checkpoint download that resolves to the
# unet roots consults the "unet" rules, not the "checkpoints" ones.
MODEL_TYPE_TO_ROOT_RULE_KEY = {
    "lora": "loras",
    "checkpoint": "checkpoints",
    "unet": "unet",
    "embedding": "embeddings",
}

# Download-time model type -> the setting holding its default download root.
MODEL_TYPE_TO_DEFAULT_ROOT_SETTING = {
    "lora": "default_lora_root",
    "checkpoint": "default_checkpoint_root",
    "unet": "default_unet_root",
    "embedding": "default_embedding_root",
}

# match_type values understood by download_root_rules.
RULE_MATCH_TYPE_BASE_MODEL = "base_model"
RULE_MATCH_TYPE_TAG = "tag"


def _normalize_tag_set(tags: Optional[Iterable[object]]) -> frozenset:
    """Case-folded, trimmed tag set for rule matching (never None)."""
    if not tags:
        return frozenset()
    return frozenset(
        tag.strip().casefold()
        for tag in tags
        if isinstance(tag, str) and tag.strip()
    )


def match_download_root_rule(
    rules: Optional[Sequence[Mapping[str, object]]],
    base_model: str,
    tags: Optional[Iterable[object]] = None,
) -> Optional[Mapping[str, object]]:
    """Return the first rule matching this download, else ``None``.

    Rules are ordered; the first match wins. ``base_model`` rules hit when
    their ``match`` list contains ``base_model`` (exact match); ``tag`` rules
    hit when any ``match`` entry equals one of the model's tags (trimmed,
    case-insensitive). A rule with an empty/invalid root never matches.
    """
    if not rules:
        return None

    model_tags = _normalize_tag_set(tags)

    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        match = rule.get("match")
        if not isinstance(match, Sequence) or isinstance(match, (str, bytes)):
            continue
        match_type = rule.get("match_type")
        if match_type == RULE_MATCH_TYPE_BASE_MODEL:
            if not base_model or base_model not in match:
                continue
        elif match_type == RULE_MATCH_TYPE_TAG:
            if not model_tags or not any(
                isinstance(entry, str) and entry.strip().casefold() in model_tags
                for entry in match
            ):
                continue
        else:
            continue
        root = rule.get("root")
        if isinstance(root, str) and root.strip():
            return rule

    return None


def resolve_download_root(
    rules: Optional[Sequence[Mapping[str, object]]],
    base_model: str,
    default_root: str,
    tags: Optional[Iterable[object]] = None,
) -> str:
    """Return the root from the first matching rule, else ``default_root``.

    See :func:`match_download_root_rule` for the matching semantics.
    """
    rule = match_download_root_rule(rules, base_model, tags)
    if rule is not None:
        root = rule["root"]
        logger.info(
            "Download root rule matched (%s), routing to %s",
            rule.get("match_type"),
            root,
        )
        return root

    return default_root


def is_diffusion_model_download(
    model_type: str,
    file_types: Iterable[str] = (),
    base_model: str = "",
    unknown_base_model_default: str = ROUTING_DIFFUSION_MODEL,
) -> bool:
    """Return True when a download should be routed to the unet roots.

    Only applies to downloads initiated from the checkpoint library.
    Priority: (1) any file has type "UNet" or "Diffusion Model" (the more
    direct signal from CivitAI), (2) baseModel is a known diffusion model,
    (3) baseModel is a known full checkpoint -> not diffusion, (4) unknown
    or empty baseModel -> the ``unknown_base_model_default`` setting, which
    defaults to diffusion because the set of true checkpoint families is
    closed while new DiT base models appear all the time.
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

    if base_model in CHECKPOINT_BASE_MODELS:
        return False

    is_diffusion = unknown_base_model_default != ROUTING_CHECKPOINT
    logger.info(
        "baseModel '%s' is unknown, routing to %s folder (unknown_base_model_routing)",
        base_model,
        "unet" if is_diffusion else "checkpoint",
    )
    return is_diffusion


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
