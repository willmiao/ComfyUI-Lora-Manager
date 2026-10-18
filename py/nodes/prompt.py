from __future__ import annotations

from typing import Any

from ..services.wildcard_service import (
    contains_dynamic_syntax,
    get_wildcard_service,
    is_trigger_words_input,
    linked_text_requires_rerun,
)


class _PromptOptionalInputs(dict):
    """Optional-input mapping that also resolves dynamically added trigger slots.

    Inheriting ``dict`` keeps ``INPUT_TYPES()`` JSON-serializable for ComfyUI's
    ``/object_info`` route: it serializes the stored entries, exactly as the plain
    dict did before. The overridden ``__contains__``/``__getitem__`` let the
    execution side resolve ``trigger_words3``-style inputs the frontend adds on
    demand. This replaces the previous ``inspect.stack()`` check for the
    ``get_input_info`` caller, which the registry security scan reports as
    anti-debugging.
    """

    def __init__(self, explicit_inputs: dict[str, tuple[str, dict[str, Any]]]) -> None:
        super().__init__(explicit_inputs)

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        return super().__contains__(item) or is_trigger_words_input(item)

    def __getitem__(self, key: str) -> tuple[str, dict[str, Any]]:
        if super().__contains__(key):
            return super().__getitem__(key)
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
            "optional": _PromptOptionalInputs(optional_inputs),
            "hidden": {
                "prompt": "PROMPT",
                "unique_id": "UNIQUE_ID",
            },
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
        prompt: dict | None = None,
        unique_id: str | None = None,
        **kwargs: Any,
    ):
        del clip, kwargs
        if seed is not None:
            return False
        if contains_dynamic_syntax(text):
            return float("NaN")
        if text is None and linked_text_requires_rerun(prompt, unique_id, "text"):
            return float("NaN")
        return False

    def encode(
        self,
        text: str,
        clip: Any,
        seed: int | None = None,
        prompt: dict | None = None,
        unique_id: str | None = None,
        **kwargs: Any,
    ):
        del prompt, unique_id
        expanded_text = get_wildcard_service().expand_text(text, seed=seed)

        trigger_words = []
        for key, value in kwargs.items():
            if is_trigger_words_input(key) and value:
                trigger_words.append(value)

        if trigger_words:
            prompt = ", ".join(trigger_words + [expanded_text])
        else:
            prompt = expanded_text

        from nodes import CLIPTextEncode  # pyright: ignore[reportMissingImports, reportAttributeAccessIssue]

        conditioning = CLIPTextEncode().encode(clip, prompt)[0]
        return (conditioning, prompt)
