from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

_GROUP_ORDER = {"IN": 0, "MID": 1, "OUT": 2, "DOUBLE": 3, "SINGLE": 4}
_GROUP_LABELS = {
    "input_blocks": ("IN", "IN"),
    "middle_block": ("MID", "MID"),
    "output_blocks": ("OUT", "OUT"),
    "double_blocks": ("DOUBLE", "D"),
    "single_blocks": ("SINGLE", "S"),
}
_BLOCK_PATTERNS = (
    re.compile(r"(?:^|\.)(input_blocks|middle_block|output_blocks|double_blocks|single_blocks)\.(\d+)(?:\.|$)"),
    re.compile(r"(?:^|_)(input_blocks|middle_block|output_blocks|double_blocks|single_blocks)_(\d+)(?:[._]|$)"),
)
_WEIGHT_ID_PATTERN = re.compile(r"^(?:BASE|IN|MID|OUT|DOUBLE|SINGLE|IN\d+|MID\d+|OUT\d+|D\d+|S\d+)$")


def block_id_from_key(key: Any) -> tuple[str, str, int] | None:
    if isinstance(key, tuple):
        key = key[0]
    key_text = str(key)
    for pattern in _BLOCK_PATTERNS:
        match = pattern.search(key_text)
        if match:
            group, prefix = _GROUP_LABELS[match.group(1)]
            index = int(match.group(2))
            return f"{prefix}{index:02d}", group, index
    return None


def normalize_lbw_config(config: Any) -> dict[str, Any]:
    if not config:
        return {"enabled": False, "weights": {}}
    if not isinstance(config, dict):
        raise ValueError("LoRA block weights must be an object")

    enabled = config.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("LoRA block weights 'enabled' must be a boolean")
    raw_weights = config.get("weights", {})
    if not isinstance(raw_weights, dict):
        raise ValueError("LoRA block weights 'weights' must be an object")

    weights = {}
    for block_id, raw_value in raw_weights.items():
        if not isinstance(block_id, str) or not _WEIGHT_ID_PATTERN.fullmatch(block_id):
            raise ValueError(f"Unknown LoRA block weight ID: {block_id}")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"LoRA block weight {block_id} must be a finite number")
        value = float(raw_value)
        if not math.isfinite(value):
            raise ValueError(f"LoRA block weight {block_id} must be a finite number")
        weights[block_id] = value

    return {"enabled": enabled, "weights": weights}


def has_active_lbw(config: Any) -> bool:
    normalized = normalize_lbw_config(config)
    return normalized["enabled"] and any(
        value != 1.0 for value in normalized["weights"].values()
    )


def format_lbw_syntax(config: Any) -> str:
    if not has_active_lbw(config):
        return ""
    normalized = normalize_lbw_config(config)
    parts = []
    for block_id, value in normalized["weights"].items():
        formatted = f"{value:.4f}".rstrip("0").rstrip(".")
        parts.append(f"{block_id}={formatted}")
    return f"LBW={';'.join(parts)}"


def parse_lbw_syntax(value: Any) -> dict[str, Any] | None:
    text = str(value or "")
    if not text.upper().startswith("LBW="):
        return None
    raw_weights = {}
    for item in text[4:].split(";"):
        block_id, separator, raw_value = item.partition("=")
        if not separator:
            continue
        try:
            raw_weights[block_id] = float(raw_value)
        except ValueError:
            continue
    return normalize_lbw_config({"enabled": True, "weights": raw_weights})


def get_lbw_schema_from_keys(keys) -> dict[str, Any]:
    blocks = []
    for key in keys:
        block = block_id_from_key(key)
        if block is not None:
            blocks.append({"id": block[0], "group": block[1], "index": block[2]})

    unique_blocks = {
        block["id"]: block
        for block in sorted(
            blocks,
            key=lambda block: (
                _GROUP_ORDER[block["group"]],
                block["index"],
                block["id"],
            ),
        )
    }
    ordered_blocks = list(unique_blocks.values())
    kind = "unsupported"
    if any(block["group"] in {"DOUBLE", "SINGLE"} for block in ordered_blocks):
        kind = "flux"
    elif ordered_blocks:
        kind = "unet"

    groups = []
    for group in _GROUP_ORDER:
        if any(block["group"] == group for block in ordered_blocks):
            groups.append(group)
    return {"kind": kind, "groups": groups, "blocks": ordered_blocks}


def _ratio_for_key(key: Any, weights: dict[str, float]) -> float:
    block = block_id_from_key(key)
    if block is None:
        return weights.get("BASE", 1.0)
    block_id, group, _ = block
    return weights.get(block_id, weights.get(group, 1.0))


def load_lora_with_block_weights(model, clip, lora, strength_model, strength_clip, config):
    import comfy.lora  # pyright: ignore[reportMissingImports]  # noqa: C0415
    import comfy.lora_convert  # pyright: ignore[reportMissingImports]  # noqa: C0415

    normalized = normalize_lbw_config(config)
    weights = normalized["weights"]
    key_map = {}
    if model is not None:
        key_map = comfy.lora.model_lora_keys_unet(model.model, key_map)
    if clip is not None:
        key_map = comfy.lora.model_lora_keys_clip(clip.cond_stage_model, key_map)

    converted = comfy.lora_convert.convert_lora(lora)
    loaded = comfy.lora.load_lora(converted, key_map)
    if not any(block_id_from_key(key) is not None for key in loaded):
        raise ValueError("LBW supports only SD/SDXL U-Net and FLUX LoRA block layouts")

    patches_by_ratio = defaultdict(dict)
    for key, patch in loaded.items():
        ratio = _ratio_for_key(key, weights)
        if ratio != 0.0:
            patches_by_ratio[ratio][key] = patch

    new_model = model.clone() if model is not None else None
    new_clip = clip.clone() if clip is not None else None
    applied_keys = set()
    for ratio, patches in patches_by_ratio.items():
        if new_model is not None:
            applied_keys.update(new_model.add_patches(patches, strength_model * ratio))
        if new_clip is not None:
            applied_keys.update(new_clip.add_patches(patches, strength_clip * ratio))

    for patches in patches_by_ratio.values():
        for key in patches:
            if key not in applied_keys:
                logger.warning("NOT LOADED %s", key)
    return new_model, new_clip
