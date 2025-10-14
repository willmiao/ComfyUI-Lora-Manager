from typing import Any, Optional

class PromptLoraManager:
    """Encodes text (and optional trigger words) into CLIP conditioning."""

    NAME = "Prompt (LoraManager)"
    CATEGORY = "Lora Manager/conditioning"
    DESCRIPTION = (
        "Encodes a text prompt using a CLIP model into an embedding that can be used "
        "to guide the diffusion model towards generating specific images."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    'STRING',
                    {
                        "multiline": True,
                        "pysssss.autocomplete": False, 
                        "dynamicPrompts": True,
                        "tooltip": "The text to be encoded.",
                    },
                ),
                "clip": (
                    'CLIP',
                    {"tooltip": "The CLIP model used for encoding the text."},
                ),
            },
            "optional": {
                "trigger_words": (
                    'STRING',
                    {
                        "forceInput": True,
                        "tooltip": (
                            "Optional trigger words to prepend to the text before "
                            "encoding."
                        )
                    },
                )
            },
        }

    RETURN_TYPES = ('CONDITIONING', 'STRING',)
    RETURN_NAMES = ('CONDITIONING', 'PROMPT',)
    OUTPUT_TOOLTIPS = (
        "A conditioning containing the embedded text used to guide the diffusion model.",
    )
    FUNCTION = "encode"

    def encode(self, text: str, clip: Any, trigger_words: Optional[str] = None):
        prompt = text
        if trigger_words:
            prompt = ", ".join([trigger_words, text])

        from nodes import CLIPTextEncode  # type: ignore
        conditioning = CLIPTextEncode().encode(clip, prompt)[0]
        return (conditioning, prompt,)