from __future__ import annotations

from typing import Any
import inspect

from ..services.wildcard_service import (
    contains_dynamic_syntax,
    get_wildcard_service,
    is_trigger_words_input,
)


class _PromptOptionalInputs:
    """Lookup that preserves explicit optional inputs and dynamic trigger slots."""

    def __init__(self, explicit_inputs: dict[str, tuple[str, dict[str, Any]]]) -> None:
        self._explicit_inputs = explicit_inputs

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        return item in self._explicit_inputs or is_trigger_words_input(item)

    def __getitem__(self, key: str) -> tuple[str, dict[str, Any]]:
        if key in self._explicit_inputs:
            return self._explicit_inputs[key]
        if is_trigger_words_input(key):
            return (
                "STRING",
                {
                    "forceInput": True,
                    "tooltip": "Trigger words to prepend. Connect to add more inputs.",
                },
            )
        raise KeyError(key)


class PromptLM:
    """Encodes text (and optional trigger words) into CLIP conditioning."""

    NAME = "Prompt (LoraManager)"
    CATEGORY = "Lora Manager/conditioning"
    DESCRIPTION = (
        "Encodes a text prompt using a CLIP model into an embedding that can be used "
        "to guide the diffusion model towards generating specific images. "
        "Supports dynamic trigger words inputs and runtime wildcard expansion."
    )

    @classmethod
    def INPUT_TYPES(cls):
        optional_inputs: dict[str, tuple[str, dict[str, Any]]] = {
            "seed": (
                "INT",
                {
                    "forceInput": True,
                    "tooltip": "Optional seed for wildcard generation. Leave unconnected for non-deterministic wildcard expansion.",
                },
            ),
            "trigger_words1": (
                "STRING",
                {
                    "forceInput": True,
                    "tooltip": "Trigger words to prepend. Connect to add more inputs.",
                },
            ),
        }

        stack = inspect.stack()
        if len(stack) > 2 and stack[2].function == "get_input_info":
            optional_inputs = _PromptOptionalInputs(optional_inputs)  # type: ignore[assignment]

        return {
            "required": {
                "text": (
                    "AUTOCOMPLETE_TEXT_PROMPT,STRING",
                    {
                        "widgetType": "AUTOCOMPLETE_TEXT_PROMPT",
                        "placeholder": "Enter prompt... /character, /artist, /wildcard for quick search",
                        "tooltip": "The text to be encoded. Wildcard references inserted with /wildcard are expanded at runtime.",
                    },
                ),
                "clip": (
                    "CLIP",
                    {"tooltip": "The CLIP model used for encoding the text."},
                ),
            },
            "optional": optional_inputs,
        }

    RETURN_TYPES = ("CONDITIONING", "STRING")
    RETURN_NAMES = ("CONDITIONING", "PROMPT")
    OUTPUT_TOOLTIPS = (
        "A conditioning containing the embedded text used to guide the diffusion model.",
    )
    FUNCTION = "encode"

    @classmethod
    def IS_CHANGED(
        cls,
        text: str,
        clip: Any | None = None,
        seed: int | None = None,
        **kwargs: Any,
    ):
        del clip, kwargs
        if contains_dynamic_syntax(text) and seed is None:
            return float("NaN")
        return False

    def encode(
        self,
        text: str,
        clip: Any,
        seed: int | None = None,
        **kwargs: Any,
    ):
        expanded_text = get_wildcard_service().expand_text(text, seed=seed)

        trigger_words = []
        for key, value in kwargs.items():
            if is_trigger_words_input(key) and value:
                trigger_words.append(value)

        if trigger_words:
            prompt = ", ".join(trigger_words + [expanded_text])
        else:
            prompt = expanded_text

        from nodes import CLIPTextEncode  # type: ignore

        conditioning = CLIPTextEncode().encode(clip, prompt)[0]
        return (conditioning, prompt)
