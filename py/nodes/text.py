class TextLM:
    """A simple text node with autocomplete support."""

    NAME = "Text (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = (
        "A simple text input node with autocomplete support for tags and styles."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "AUTOCOMPLETE_TEXT_PROMPT,STRING",
                    {
                        "widgetType": "AUTOCOMPLETE_TEXT_PROMPT",
                        "placeholder": "Enter text... /char, /artist for quick tag search",
                        "tooltip": "The text output.",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("STRING",)
    OUTPUT_TOOLTIPS = (
        "The text output.",
    )
    FUNCTION = "process"

    def process(self, text: str):
        return (text,)