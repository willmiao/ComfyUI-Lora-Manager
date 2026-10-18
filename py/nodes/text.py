from __future__ import annotations

from ..services.wildcard_service import (
    contains_dynamic_syntax,
    get_wildcard_service,
    linked_text_requires_rerun,
)


class TextLM:
    """A simple text node with autocomplete support."""

    NAME = "Text (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = (
        "A simple text input node with autocomplete support for tags, styles, and wildcard expansion."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "AUTOCOMPLETE_TEXT_PROMPT,STRING",
                    {
                        "widgetType": "AUTOCOMPLETE_TEXT_PROMPT",
                        "placeholder": "Enter text... /character, /artist, /wildcard for quick search",
                        "tooltip": "The text output. Wildcard references inserted with /wildcard are expanded at runtime.",
                    },
                ),
            },
            "optional": {
                "seed": (
                    "INT",
                    {
                        "forceInput": True,
                        "tooltip": "Optional seed for wildcard generation. Leave unconnected for non-deterministic wildcard expansion.",
                    },
                ),
            },
            "hidden": {
                "prompt": "PROMPT",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("STRING",)
    OUTPUT_TOOLTIPS = ("The text output.",)
    FUNCTION = "process"

    @classmethod
    def IS_CHANGED(
        cls,
        text: str,
        seed: int | None = None,
        prompt: dict | None = None,
        unique_id: str | None = None,
    ):
        if seed is not None:
            return False
        if contains_dynamic_syntax(text):
            return float("NaN")
        if text is None and linked_text_requires_rerun(prompt, unique_id, "text"):
            return float("NaN")
        return False

    def process(
        self,
        text: str,
        seed: int | None = None,
        prompt: dict | None = None,
        unique_id: str | None = None,
    ):
        del prompt, unique_id
        return (get_wildcard_service().expand_text(text, seed=seed),)
