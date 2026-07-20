"""Node to resolve `<lora:name:strength>` syntax to absolute file system paths.

Takes the loaded_loras / active_loras STRING output from LoraLoaderLM or
LoraStackerLM and resolves each lora name to its absolute path on disk via
the scanner cache. Unknown names are returned as-is.
"""

import logging

from ..utils.utils import get_lora_info_absolute
from .utils import parse_lora_syntax

logger = logging.getLogger(__name__)


class LoraSyntaxToPath:
    NAME = "LoRA Syntax → Path (LoraManager)"
    CATEGORY = "Lora Manager/utils"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_syntax": (
                    "STRING",
                    {
                        "forceInput": True,
                        "multiline": True,
                        "tooltip": (
                            "<lora:name:strength> formatted text from "
                            "loaded_loras / active_loras output"
                        ),
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("paths",)
    FUNCTION = "resolve"

    def resolve(self, lora_syntax: str) -> tuple[str]:
        """Parse <lora:...> syntax and resolve each name to its absolute path."""
        if not lora_syntax or not lora_syntax.strip():
            logger.info("Received empty lora_syntax input")
            return ("",)

        parsed = parse_lora_syntax(lora_syntax)
        if not parsed:
            logger.info("No valid <lora:...> entries found in input")
            return ("",)

        paths: list[str] = []
        for entry in parsed:
            try:
                absolute_path, _ = get_lora_info_absolute(entry["name"])
                paths.append(absolute_path)
            except Exception:
                logger.warning("Failed to resolve lora '%s', skipping", entry["name"])
                continue

        return ("\n".join(paths),)
