import logging

from ..utils.utils import get_lora_info_absolute
from .utils import parse_lora_syntax

logger = logging.getLogger(__name__)


class LoraTriggerWordsLM:
    NAME = "LoRA Trigger Words (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = "Resolve trigger words for LoRAs in loaded_loras syntax."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_syntax": (
                    "STRING",
                    {
                        "forceInput": True,
                        "multiline": True,
                        "tooltip": "LoRA syntax from a loaded_loras / active_loras output",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("trigger_words",)
    FUNCTION = "resolve"

    def resolve(self, lora_syntax: str) -> tuple[str]:
        if not lora_syntax or not lora_syntax.strip():
            return ("",)

        all_trigger_words = []
        for entry in parse_lora_syntax(lora_syntax):
            try:
                _, trigger_words = get_lora_info_absolute(entry["name"])
                all_trigger_words.extend(trigger_words)
            except Exception:
                logger.warning(
                    "Failed to resolve trigger words for LoRA '%s', skipping",
                    entry["name"],
                )

        return (",, ".join(all_trigger_words) if all_trigger_words else "",)
