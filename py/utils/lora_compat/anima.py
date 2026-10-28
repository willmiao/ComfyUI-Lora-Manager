"""Anima block-index compatibility for legacy LoRAs.

Anima 2.9B (40 transformer blocks) and Anima 3.8B (52 transformer blocks) are
depth expansions of the original 28-block Anima model: new blocks were inserted
between the original blocks instead of being appended. A LoRA trained on the
28-block layout therefore has to be rewritten to the expanded numbering before
ComfyUI applies it. Without that rewrite, blocks 2..27 land on unrelated layers
and no ``lora key not loaded`` warning is emitted, because every old index still
exists in the larger model.

The expansion data in ``anima_manifests/`` is the measured layout published by
the community Anima remap packs (see ``anima_manifests/README.md``). Remapping
happens in memory only; the LoRA file is never modified.
"""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import LoraCompatibilityError

logger = logging.getLogger(__name__)

_MANIFEST_DIR = Path(__file__).with_name("anima_manifests")

# Dot-separated layouts:
#   diffusion_model.blocks.5.self_attn...
#   transformer.blocks.5...
#   net.blocks.5...
# The look-behind-ish anchor keeps "double_blocks.5." from matching.
_DOTTED_BLOCK_RE = re.compile(r"(?P<prefix>(?:^|\.)blocks\.)(?P<index>\d+)(?=\.)")

# Kohya / sd-scripts layouts:
#   lora_unet_blocks_5_self_attn_q_proj...
#   lora_unet_net_blocks_5_self_attn_q_proj...
#   lycoris_blocks_5_...
_KOHYA_BLOCK_RE = re.compile(
    r"(?P<prefix>^(?:lora_unet_(?:net_)?|lycoris_)blocks_)(?P<index>\d+)(?=_)"
)

_TEXT_ENCODER_PREFIXES = (
    "lora_te_",
    "lora_te1_",
    "lora_te2_",
    "text_encoder.",
    "text_encoders.",
    "text_conditioner.",
    "clip_",
)
_TEXT_ENCODER_MARKERS = (".text_encoder.", ".text_encoders.", ".text_conditioner.")

# Sub-structures that have their own, independent block numbering and must
# never be treated as part of the main DiT block expansion.
_SKIP_KEY_MARKERS = (
    "llm_adapter",
    "semantic_attention",
    "semantic_attentions",
    "connector",
)

_MANIFESTS: dict[tuple[int, int], dict[int, int]] | None = None


def _is_text_encoder_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith(_TEXT_ENCODER_PREFIXES) or any(
        marker in lowered for marker in _TEXT_ENCODER_MARKERS
    )


def _should_skip_key(key: str) -> bool:
    if _is_text_encoder_key(key):
        return True
    lowered = key.lower()
    return any(marker in lowered for marker in _SKIP_KEY_MARKERS)


def _has_block_index(key: str) -> bool:
    return not _should_skip_key(key) and (
        _DOTTED_BLOCK_RE.search(key) is not None
        or _KOHYA_BLOCK_RE.search(key) is not None
    )


def _collect_block_indices(keys: Iterable[str]) -> set[int]:
    indices: set[int] = set()
    for key in keys:
        if not isinstance(key, str) or _should_skip_key(key):
            continue
        for pattern in (_DOTTED_BLOCK_RE, _KOHYA_BLOCK_RE):
            indices.update(int(match.group("index")) for match in pattern.finditer(key))
    return indices


def detect_lora_block_count(keys: Iterable[str]) -> int | None:
    """Infer the Anima generation a LoRA was trained for.

    The highest referenced block is enough to distinguish the known layouts:
    0..27 -> 28 blocks, 0..39 -> 40 blocks, 0..51 -> 52 blocks. LoRAs that only
    cover a subset of blocks are assigned to the smallest layout that can
    contain their highest index.
    """

    indices = _collect_block_indices(keys)
    if not indices:
        return None

    highest = max(indices)
    if highest < 28:
        return 28
    if highest < 40:
        return 40
    if highest < 52:
        return 52
    raise LoraCompatibilityError(
        f"Unsupported Anima LoRA block index {highest}; known layouts are 28, 40 and 52 blocks."
    )


def _model_unet_config(model: Any) -> Mapping[str, Any]:
    model_config = getattr(getattr(model, "model", None), "model_config", None)
    unet_config = getattr(model_config, "unet_config", None)
    return unet_config if isinstance(unet_config, Mapping) else {}


def _diffusion_model(model: Any) -> Any:
    return getattr(getattr(model, "model", None), "diffusion_model", None)


def matches(model: Any) -> bool:
    """Return True when the connected model is an Anima model."""

    if _model_unet_config(model).get("image_model") == "anima":
        return True
    # Older ComfyUI builds may not populate image_model, but Anima's LLM
    # adapter is unique to this model family.
    return hasattr(_diffusion_model(model), "llm_adapter")


def get_model_block_count(model: Any) -> int | None:
    """Return the connected Anima model's DiT block count."""

    blocks = getattr(_diffusion_model(model), "blocks", None)
    if blocks is not None:
        try:
            count = len(blocks)
        except TypeError:
            count = 0
        if isinstance(count, int) and count > 0:
            return count

    configured = _model_unet_config(model).get("num_blocks")
    if isinstance(configured, int) and configured > 0:
        return configured

    # Last-resort fallback for wrappers that do not expose model_config or a
    # ModuleList of blocks. This is only reached for models already matched as
    # Anima, so it cannot slow down ordinary LoRA loading.
    try:
        state_dict = model.model.state_dict()
    except Exception:
        return None
    indices = _collect_block_indices(state_dict.keys())
    return max(indices) + 1 if indices else None


def _load_manifests() -> dict[tuple[int, int], dict[int, int]]:
    global _MANIFESTS

    if _MANIFESTS is not None:
        return _MANIFESTS

    manifests: dict[tuple[int, int], dict[int, int]] = {}

    for path in sorted(_MANIFEST_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            old_count = int(data["old_block_count"])
            new_count = int(data["new_block_count"])
            inserted = tuple(int(index) for index in data.get("insertion_positions", ()))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            logger.warning("Ignoring invalid Anima remap manifest %s: %s", path.name, exc)
            continue

        inserted_set = set(inserted)
        if (
            old_count <= 0
            or new_count <= old_count
            or len(inserted_set) != len(inserted)
            or any(index < 0 or index >= new_count for index in inserted)
            or old_count + len(inserted) != new_count
        ):
            logger.warning("Ignoring inconsistent Anima remap manifest %s", path.name)
            continue

        kept = [index for index in range(new_count) if index not in inserted_set]
        if len(kept) != old_count:
            logger.warning("Ignoring inconsistent Anima remap manifest %s", path.name)
            continue

        manifests[(old_count, new_count)] = {
            source: kept[source] for source in range(old_count)
        }

    _MANIFESTS = manifests
    return manifests


def resolve_mapping(source_blocks: int, target_blocks: int) -> dict[int, int] | None:
    """Return ``{source_block: target_block}`` for an Anima layout change.

    Direct expansion steps are used when available; multi-generation jumps
    (for example 28 -> 52) are composed from adjacent manifests.
    """

    if source_blocks == target_blocks:
        return None

    if source_blocks > target_blocks:
        raise LoraCompatibilityError(
            f"Anima LoRA targets {source_blocks} blocks, but the connected model has "
            f"{target_blocks}. A newer-generation LoRA cannot be remapped down."
        )

    manifests = _load_manifests()
    direct = manifests.get((source_blocks, target_blocks))
    if direct is not None:
        return dict(direct)

    identity = {index: index for index in range(source_blocks)}
    queue = deque([(source_blocks, identity)])
    seen = {source_blocks}

    while queue:
        current, current_map = queue.popleft()
        for (old_count, new_count), step in manifests.items():
            if old_count != current or new_count in seen:
                continue

            composed = {
                source: step[intermediate]
                for source, intermediate in current_map.items()
                if intermediate in step
            }
            if len(composed) != source_blocks:
                continue
            if new_count == target_blocks:
                return composed

            seen.add(new_count)
            queue.append((new_count, composed))

    raise LoraCompatibilityError(
        f"No Anima block mapping for {source_blocks} -> {target_blocks} blocks. "
        "Update the compatibility manifests or disable the legacy Anima remap setting."
    )


def _rewrite_key(key: str, mapping: Mapping[int, int]) -> str:
    def replace(match: re.Match[str]) -> str:
        source = int(match.group("index"))
        target = mapping.get(source)
        if target is None:
            raise LoraCompatibilityError(
                f"LoRA block {source} has no counterpart in the target Anima layout "
                f"({key!r})."
            )
        return f"{match.group('prefix')}{target}"

    rewritten = _DOTTED_BLOCK_RE.sub(replace, key)
    return _KOHYA_BLOCK_RE.sub(replace, rewritten)


@dataclass(frozen=True)
class AnimaRemapStats:
    source_blocks: int
    target_blocks: int
    total_keys: int
    block_keys: int
    changed_keys: int
    mapped_source_blocks: tuple[int, ...]
    inserted_target_blocks: tuple[int, ...]
    name: str | None = None

    def report(self) -> str:
        label = f'"{self.name}": ' if self.name else ""
        inserted = ", ".join(str(index) for index in self.inserted_target_blocks) or "none"
        return (
            f"Anima block remap {label}{self.source_blocks} -> {self.target_blocks} blocks; "
            f"{self.changed_keys}/{self.block_keys} block keys rewritten; "
            f"{len(self.mapped_source_blocks)} source blocks mapped; "
            f"inserted blocks {inserted} left untouched"
        )


def remap_lora_state_dict(
    lora_sd: Mapping[str, Any],
    mapping: Mapping[int, int],
    *,
    name: str | None = None,
) -> tuple[dict[str, Any], AnimaRemapStats]:
    """Return a shallow-copied state dict with Anima block indices rewritten."""

    if not mapping:
        raise LoraCompatibilityError("Anima remap mapping is empty.")

    mapped_values = set(mapping.values())
    target_blocks = max(mapped_values) + 1
    inserted = tuple(
        index for index in range(target_blocks) if index not in mapped_values
    )

    remapped: dict[str, Any] = {}
    sources: dict[str, str] = {}
    block_keys = 0
    changed_keys = 0

    for key, value in lora_sd.items():
        if not isinstance(key, str):
            remapped[key] = value
            continue

        if _should_skip_key(key) or not _has_block_index(key):
            remapped[key] = value
            sources.setdefault(key, key)
            continue

        block_keys += 1
        new_key = _rewrite_key(key, mapping)
        if new_key != key:
            changed_keys += 1

        if new_key in remapped:
            previous = sources.get(new_key, new_key)
            raise LoraCompatibilityError(
                "Anima LoRA key collision after remap: "
                f"{previous!r} and {key!r} both map to {new_key!r}."
            )

        remapped[new_key] = value
        sources[new_key] = key

    stats = AnimaRemapStats(
        source_blocks=len(mapping),
        target_blocks=target_blocks,
        total_keys=len(lora_sd),
        block_keys=block_keys,
        changed_keys=changed_keys,
        mapped_source_blocks=tuple(sorted(mapping)),
        inserted_target_blocks=inserted,
        name=name,
    )
    return remapped, stats


def prepare(
    lora_sd: Mapping[str, Any],
    model: Any,
    name: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Prepare an Anima LoRA for the connected model.

    Returns the state dict to load (a shallow copy) and an optional one-line
    report. Raises :class:`LoraCompatibilityError` when the LoRA is newer than
    the model or when no verified mapping exists.
    """

    target_blocks = get_model_block_count(model)
    source_blocks = detect_lora_block_count(lora_sd.keys())

    if source_blocks is None:
        return dict(lora_sd), None

    if target_blocks is None:
        raise LoraCompatibilityError(
            "Could not determine the Anima model's transformer block count. "
            "Update ComfyUI or disable the legacy Anima block remap setting."
        )

    if source_blocks == target_blocks:
        return dict(lora_sd), None

    mapping = resolve_mapping(source_blocks, target_blocks)
    if mapping is None:
        return dict(lora_sd), None

    remapped, stats = remap_lora_state_dict(lora_sd, mapping, name=name)
    return remapped, stats.report()
