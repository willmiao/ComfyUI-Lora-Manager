"""Model-family adapters that prepare LoRA state dicts before ComfyUI loads them.

The generic LoRA loader only calls :func:`prepare_lora`; model-specific
knowledge (block layouts, compatibility rules) lives in the adapter modules so
the loader UI stays generic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import anima
from .errors import LoraCompatibilityError

_ADAPTERS = (anima,)


def prepare_lora(
    lora_sd: Mapping[str, Any],
    model: Any,
    name: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Run the matching model-family adapter for ``model``.

    Returns the state dict to load and an optional human-readable report.
    """

    for adapter in _ADAPTERS:
        if adapter.matches(model):
            return adapter.prepare(lora_sd, model, name=name)
    return dict(lora_sd), None


__all__ = ["LoraCompatibilityError", "prepare_lora"]
