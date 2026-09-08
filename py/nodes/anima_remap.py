"""
anima_remap.py

Block-index remapping for the Anima model family.
Handles the 28→40 and 40→52 (and composed 28→52) block expansions.

Anima models use interleaved layer expansion:
  Anima Base (28 blocks) → Anima 2.9B (40 blocks) → Anima 3.8B (52 blocks)

New blocks are inserted BETWEEN existing blocks, so applying a LoRA trained
on an older generation directly to a newer model causes block indices to
misalign and produces broken output. This module detects the mismatch and
rewrites LoRA keys to the correct target block positions.
"""

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Block-key patterns (dot-separated and kohya-style underscore-separated)
# ---------------------------------------------------------------------------
BLOCK_PATTERNS = [
    re.compile(r"(\.blocks\.)(\d+)(\.)"),    # net.blocks.12.self_attn...
    re.compile(r"(_blocks_)(\d+)(_)"),        # lora_unet_blocks_12_self_attn...
]

# Keys belonging to separate sub-structures that should NOT be remapped
# - llm_adapter: has its own 6-block structure, unaffected by expansion
# - semantic_attention/connector: Qwen3.5 cross-attention components
_SKIP_KEY_PATTERNS = ("llm_adapter", "semantic_attention", "connector")

# ---------------------------------------------------------------------------
# Expansion manifests
# ---------------------------------------------------------------------------
_MANIFEST_DIR = os.path.join(os.path.dirname(__file__), "anima_manifests")
_MANIFEST_CACHE: dict = {}


def _load_manifest(filename: str) -> Optional[dict]:
    if filename in _MANIFEST_CACHE:
        return _MANIFEST_CACHE[filename]
    path = os.path.join(_MANIFEST_DIR, filename)
    if not os.path.exists(path):
        logger.warning("Anima remap manifest not found: %s", path)
        _MANIFEST_CACHE[filename] = None
        return None
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    _MANIFEST_CACHE[filename] = manifest
    return manifest


def _all_manifests_by_block_counts() -> dict:
    """Build index of {(old_count, new_count): manifest_dict}"""
    index = {}
    if not os.path.isdir(_MANIFEST_DIR):
        return index
    for filename in os.listdir(_MANIFEST_DIR):
        if not filename.endswith(".json"):
            continue
        m = _load_manifest(filename)
        if m is None:
            continue
        try:
            index[(m["old_block_count"], m["new_block_count"])] = m
        except KeyError:
            logger.warning("Manifest %s missing block count fields, skipped", filename)
    return index


# ---------------------------------------------------------------------------
# Block-index detection
# ---------------------------------------------------------------------------
def _should_skip_key(key: str) -> bool:
    """Return True if this key belongs to a sub-structure that shouldn't be remapped."""
    return any(pat in key for pat in _SKIP_KEY_PATTERNS)


def find_block_indices(keys) -> set:
    """Return the set of main transformer block indices referenced by `keys`."""
    indices = set()
    for key in keys:
        if _should_skip_key(key):
            continue
        for pat in BLOCK_PATTERNS:
            m = pat.search(key)
            if m:
                indices.add(int(m.group(2)))
                break
    return indices


def get_block_count(state_dict_keys) -> Optional[int]:
    """Return highest block index + 1, or None if no block keys found."""
    indices = find_block_indices(state_dict_keys)
    return (max(indices) + 1) if indices else None


def get_model_block_count(model_patcher) -> Optional[int]:
    """Detect block count of the connected ComfyUI MODEL."""
    sd = None
    for getter in (
        lambda: model_patcher.model_state_dict(),
        lambda: model_patcher.model.diffusion_model.state_dict(),
        lambda: model_patcher.model.state_dict(),
    ):
        try:
            sd = getter()
            if sd:
                break
        except Exception:
            continue
    if not sd:
        return None
    return get_block_count(sd.keys())


# ---------------------------------------------------------------------------
# Mapping computation
# ---------------------------------------------------------------------------
def build_base_to_target(manifest: dict) -> dict:
    """
    Build {base_block_idx: target_block_idx} from an expansion manifest.
    
    Non-inserted target positions (in ascending order) are the inherited blocks.
    E.g., for 28→40 with 12 insertions, the 28 original blocks map to the
    28 non-inserted positions in the 40-block model.
    """
    old_count = manifest["old_block_count"]
    new_count = manifest["new_block_count"]
    inserted = set(manifest["insertion_positions"])
    old_target_indices = [i for i in range(new_count) if i not in inserted]
    if len(old_target_indices) != old_count:
        logger.warning(
            "Manifest inconsistency: expected %d non-inserted blocks, found %d",
            old_count, len(old_target_indices),
        )
    return {base_idx: target_idx for base_idx, target_idx in enumerate(old_target_indices)}


def resolve_mapping(source_count: int, target_count: int) -> Optional[dict]:
    """
    Resolve the {source_block: target_block} mapping for a given pair.
    
    Handles:
    - Direct mappings (28→40, 40→52)
    - Composed mappings (28→52 via 28→40 then 40→52)
    
    Returns None if no remap is needed or possible.
    """
    if source_count == target_count:
        return None  # No remap needed

    index = _all_manifests_by_block_counts()

    # Direct mapping
    m = index.get((source_count, target_count))
    if m is not None:
        logger.info("Anima remap: using direct mapping %d→%d", source_count, target_count)
        return build_base_to_target(m)

    # Composed mapping: try chaining through intermediate block counts
    # e.g., 28→52 via 28→40 then 40→52
    for (old_a, new_a), m_a in index.items():
        if old_a != source_count:
            continue
        for (old_b, new_b), m_b in index.items():
            if old_b == new_a and new_b == target_count:
                map_a = build_base_to_target(m_a)
                map_b = build_base_to_target(m_b)
                # Compose: source → intermediate → target
                composed = {}
                for src, mid in map_a.items():
                    if mid in map_b:
                        composed[src] = map_b[mid]
                if composed:
                    logger.info(
                        "Anima remap: composed mapping %d→%d→%d (%d keys mapped)",
                        source_count, new_a, target_count, len(composed),
                    )
                    return composed

    logger.warning(
        "Anima remap: no manifest covers %d→%d blocks. Remap skipped.",
        source_count, target_count,
    )
    return None


# ---------------------------------------------------------------------------
# Key rewriting
# ---------------------------------------------------------------------------
def remap_lora_keys(lora_sd: dict, base_to_target: dict) -> dict:
    """
    Rewrite block indices in all LoRA state_dict keys using base_to_target.
    
    - Keys without a block index (embeddings, final_layer, etc.) are kept as-is.
    - Keys referencing a block with no mapping entry are dropped.
    - Keys belonging to skipped sub-structures (llm_adapter, etc.) are kept as-is.
    """
    remapped = {}
    dropped = 0
    
    for key, tensor in lora_sd.items():
        if _should_skip_key(key):
            # Sub-structure key — pass through unchanged
            remapped[key] = tensor
            continue

        rewritten = False
        for pat in BLOCK_PATTERNS:
            m = pat.search(key)
            if m:
                src_idx = int(m.group(2))
                if src_idx not in base_to_target:
                    # This block has no mapping (shouldn't happen for valid LoRAs)
                    dropped += 1
                    rewritten = True  # Mark as handled (dropped)
                    break
                tgt_idx = base_to_target[src_idx]
                new_key = (
                    key[:m.start()]
                    + m.group(1) + str(tgt_idx) + m.group(3)
                    + key[m.end():]
                )
                remapped[new_key] = tensor
                rewritten = True
                break

        if not rewritten:
            # No block index found — pass through (e.g., non-block keys)
            remapped[key] = tensor

    if dropped:
        logger.info("Anima remap: dropped %d keys with unmapped block indices", dropped)
    return remapped


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------
def maybe_remap_lora(lora_sd: dict, model_block_count: Optional[int]) -> dict:
    """
    Detect if a LoRA needs remapping for the target model and apply it.
    Returns the (possibly remapped) state dict.
    
    Behavior:
    - If model_block_count is None (detection failed), returns lora_sd unchanged.
    - If LoRA block count matches or exceeds model, returns unchanged.
    - If LoRA has fewer blocks, attempts remap.
    """
    if model_block_count is None:
        return lora_sd

    lora_block_count = get_block_count(lora_sd.keys())
    if lora_block_count is None:
        return lora_sd

    if lora_block_count >= model_block_count:
        # LoRA already matches or exceeds model — no remap needed
        return lora_sd

    mapping = resolve_mapping(lora_block_count, model_block_count)
    if mapping is None:
        # No valid mapping found — return unchanged (will likely fail at load time)
        return lora_sd

    logger.info(
        "Anima remap: remapping LoRA (%d blocks → %d blocks), %d block mappings",
        lora_block_count, model_block_count, len(mapping),
    )
    return remap_lora_keys(lora_sd, mapping)
