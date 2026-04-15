from __future__ import annotations

from ..services.wildcard_service import get_wildcard_service


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
                        "placeholder": "Enter text... /char, /artist, /wild for quick search",
                        "tooltip": "The text output. Wildcard references inserted with /wild are expanded at runtime.",
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
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("STRING",)
    OUTPUT_TOOLTIPS = ("The text output.",)
    FUNCTION = "process"

    def process(self, text: str, seed: int | None = None):
        return (get_wildcard_service().expand_text(text, seed=seed),)
