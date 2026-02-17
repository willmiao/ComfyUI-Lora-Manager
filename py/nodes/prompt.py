from typing import Any
import inspect


class _AllContainer:
    """Container that accepts any key for dynamic input validation."""

    def __contains__(self, item):
        return True

    def __getitem__(self, key):
        return ("STRING", {"forceInput": True})


class PromptLM:
    """Encodes text (and optional trigger words) into CLIP conditioning."""

    NAME = "Prompt (LoraManager)"
    CATEGORY = "Lora Manager/conditioning"
    DESCRIPTION = (
        "Encodes a text prompt using a CLIP model into an embedding that can be used "
        "to guide the diffusion model towards generating specific images. "
        "Supports dynamic trigger words inputs."
    )

    @classmethod
    def INPUT_TYPES(cls):
        dyn_inputs = {
            "trigger_words1": (
                "STRING",
                {
                    "forceInput": True,
                    "tooltip": "Trigger words to prepend. Connect to add more inputs.",
                },
            ),
        }

        # Bypass validation for dynamic inputs during graph execution
        stack = inspect.stack()
        if len(stack) > 2 and stack[2].function == "get_input_info":
            dyn_inputs = _AllContainer()

        return {
            "required": {
                "text": (
                    "AUTOCOMPLETE_TEXT_PROMPT,STRING",
                    {
                        "widgetType": "AUTOCOMPLETE_TEXT_PROMPT",
                        "placeholder": "Enter prompt... /char, /artist for quick tag search",
                        "tooltip": "The text to be encoded.",
                    },
                ),
                "clip": (
                    "CLIP",
                    {"tooltip": "The CLIP model used for encoding the text."},
                ),
            },
            "optional": dyn_inputs,
        }

    RETURN_TYPES = ("CONDITIONING", "STRING")
    RETURN_NAMES = ("CONDITIONING", "PROMPT")
    OUTPUT_TOOLTIPS = (
        "A conditioning containing the embedded text used to guide the diffusion model.",
    )
    FUNCTION = "encode"

    def encode(self, text: str, clip: Any, **kwargs):
        # Collect all trigger words from dynamic inputs
        trigger_words = []
        for key, value in kwargs.items():
            if key.startswith("trigger_words") and value:
                trigger_words.append(value)

        # Build final prompt
        if trigger_words:
            prompt = ", ".join(trigger_words + [text])
        else:
            prompt = text

        from nodes import CLIPTextEncode  # type: ignore

        conditioning = CLIPTextEncode().encode(clip, prompt)[0]
        return (conditioning, prompt)