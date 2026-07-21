"""Create Hook LoRA (LoraManager) — multi-LoRA hook node compatible with ComfyUI's built-in hook pipeline.

Produces ``("HOOKS",)`` output that chains seamlessly with downstream hook consumers
(ConditioningSetProperties, SetHookKeyframes, CombineHooks, SetClipHooks, etc.).
"""

from __future__ import annotations

import logging
import os

import comfy.hooks  # type: ignore
import comfy.utils  # type: ignore

from ..utils.utils import get_lora_info_absolute
from .utils import (
    FlexibleOptionalInputType,
    any_type,
    apply_lora_syntax_format,
    get_loras_list,
)

logger = logging.getLogger(__name__)


class CreateHookLoraLM:
    NAME = "Create Hook LoRA (LoraManager)"
    CATEGORY = "Lora Manager/hooks"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "AUTOCOMPLETE_TEXT_LORAS",
                    {
                        "placeholder": "Search LoRAs to add...",
                        "tooltip": (
                            "Search and select LoRAs. Each LoRA gets its own "
                            "model/clip strength. Hooks chain with prev_hooks."
                        ),
                    },
                ),
            },
            "optional": FlexibleOptionalInputType(any_type),
        }

    RETURN_TYPES = ("HOOKS", "STRING", "STRING")
    RETURN_NAMES = ("HOOKS", "trigger_words", "active_loras")
    FUNCTION = "create_hook"

    def create_hook(self, text: str, **kwargs):
        """Create a HookGroup from the selected LoRAs, chained with prev_hooks.

        Each active LoRA from the widget is loaded and wrapped in a WeightHook
        via :func:`comfy.hooks.create_hook_lora`.  All hooks are combined into a
        single group and returned alongside trigger words and a human-readable
        summary of the active LoRAs.
        """
        del text  # used by the frontend widget only

        prev_hooks: comfy.hooks.HookGroup | None = kwargs.get("prev_hooks")

        hook_group = prev_hooks.clone() if prev_hooks is not None else comfy.hooks.HookGroup()

        all_trigger_words: list[str] = []
        active_loras: list[tuple[str, float, float]] = []

        for lora in get_loras_list(kwargs):
            if not lora.get("active", False):
                continue

            lora_name = apply_lora_syntax_format(lora["name"])
            model_strength = float(lora["strength"])
            clip_strength = float(lora.get("clipStrength", model_strength))

            # Skip useless no-op entries (both strengths are zero)
            if model_strength == 0.0 and clip_strength == 0.0:
                continue

            lora_path, trigger_words = get_lora_info_absolute(lora_name)
            if not lora_path or not os.path.isfile(lora_path):
                logger.warning("LoRA '%s' not found — skipping", lora_name)
                continue

            try:
                lora_weights = comfy.utils.load_torch_file(lora_path, safe_load=True)

                lora_hooks = comfy.hooks.create_hook_lora(
                    lora=lora_weights,
                    strength_model=model_strength,
                    strength_clip=clip_strength,
                )
            except Exception:
                logger.exception("Failed to load LoRA '%s' — skipping", lora_name)
                continue
            hook_group = hook_group.clone_and_combine(lora_hooks)

            active_loras.append((lora_name, model_strength, clip_strength))
            all_trigger_words.extend(trigger_words)

        # Format trigger words (group mode separator)
        trigger_words_text = ",, ".join(all_trigger_words) if all_trigger_words else ""

        # Format active LoRAs summary
        formatted_loras = []
        for name, model_s, clip_s in active_loras:
            if abs(model_s - clip_s) > 0.001:
                formatted_loras.append(
                    f"<lora:{name}:{model_s}:{clip_s}>"
                )
            else:
                formatted_loras.append(f"<lora:{name}:{model_s}>")
        active_loras_text = " ".join(formatted_loras)

        return (hook_group, trigger_words_text, active_loras_text)
