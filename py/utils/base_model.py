"""Base-model architecture families and compatibility relations.

CivitAI base-model labels describe fine-tune lineages, not architectures.
A LoRA physically loads on any checkpoint sharing its tensor architecture,
so e.g. Pony / Illustrious / NoobAI / SDXL 1.0 LoRAs are interchangeable
(quality varies, but nothing breaks). Different architectures (SD 1.5 vs
SDXL vs Flux) are guaranteed failures and must stay hard-rejected.

Only families with high-confidence architecture equivalence are listed.
Anything not in the table is treated as its own family, i.e. only an exact
label match is accepted — unknown new labels never get wrongly waved through.
"""

from __future__ import annotations

from typing import Optional

# Normalized (casefolded, stripped) base-model label -> architecture family.
_BASE_MODEL_FAMILIES = {
    # SD 1.x — all share the original 512px latent UNet.
    "sd 1.4": "sd1",
    "sd 1.5": "sd1",
    "sd 1.5 lcm": "sd1",
    "sd 1.5 hyper": "sd1",
    # SDXL lineage — Pony / Illustrious / NoobAI are SDXL fine-tunes.
    # Note: Pony V7 is AuraFlow-based, NOT SDXL, so it is deliberately absent.
    "sdxl 1.0": "sdxl",
    "sdxl lightning": "sdxl",
    "sdxl hyper": "sdxl",
    "pony": "sdxl",
    "pony diffusion": "sdxl",
    "pony diffusion v6 xl": "sdxl",
    "illustrious": "sdxl",
    "illustrious 0.1": "sdxl",
    "illustrious 1.0": "sdxl",
    "illustrious 1.1": "sdxl",
    "noobai": "sdxl",
    # Flux.1 — dev/schnell/Krea share the 12B rectified-flow transformer.
    "flux.1 d": "flux1",
    "flux.1 s": "flux1",
    "flux.1 krea": "flux1",
    # SD 3.5 Large and its Turbo distill share the 8B MMDiT. SD 3 (2B) and
    # SD 3.5 Medium (2.5B) have different shapes and stay unlisted.
    "sd 3.5 large": "sd35-large",
    "sd 3.5 large turbo": "sd35-large",
}

_UNKNOWN_TOKENS = {"", "unknown", "other", "none", "null"}

# Relation constants returned by base_model_relation().
RELATION_UNKNOWN = "unknown"  # at least one side has no usable label
RELATION_SAME = "same"  # identical labels
RELATION_COMPATIBLE = "compatible"  # different labels, same architecture family
RELATION_INCOMPATIBLE = "incompatible"  # different labels, different/unknown family


def _normalize(label: Optional[str]) -> str:
    return (label or "").strip().casefold()


def base_model_relation(a: Optional[str], b: Optional[str]) -> str:
    """Classify how two base-model labels relate for reconnect purposes.

    ``RELATION_UNKNOWN`` when either side has no usable label (callers treat
    it as lenient-allow), ``RELATION_SAME`` for identical labels,
    ``RELATION_COMPATIBLE`` when both labels map to the same architecture
    family, and ``RELATION_INCOMPATIBLE`` otherwise — including when a label
    is missing from the family table (conservative fallback).
    """
    na, nb = _normalize(a), _normalize(b)
    if na in _UNKNOWN_TOKENS or nb in _UNKNOWN_TOKENS:
        return RELATION_UNKNOWN
    if na == nb:
        return RELATION_SAME
    fa = _BASE_MODEL_FAMILIES.get(na)
    fb = _BASE_MODEL_FAMILIES.get(nb)
    if fa is not None and fa == fb:
        return RELATION_COMPATIBLE
    return RELATION_INCOMPATIBLE
