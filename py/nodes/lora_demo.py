"""
Lora Demo Node - Demonstrates LORAS custom widget type usage.

This node accepts LORAS widget input and outputs a summary string.
"""

import logging
import random

logger = logging.getLogger(__name__)


class LoraDemoNode:
    """Demo node that uses LORAS custom widget type."""

    NAME = "Lora Demo (LoraManager)"
    CATEGORY = "Lora Manager/demo"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "loras": ("LORAS", {}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("summary",)

    FUNCTION = "process"
    OUTPUT_NODE = False

    async def process(self, loras):
        """
        Process LoRAs input and return summary + UI data for widget.

        Args:
            loras: List of LoRA dictionaries with structure:
                [{'name': str, 'strength': float, 'clipStrength': float, 'active': bool, ...}]

        Returns:
            Dictionary with 'result' (for workflow) and 'ui' (for frontend display)
        """
        from ..services.service_registry import ServiceRegistry

        # Get lora scanner to access available loras
        scanner = await ServiceRegistry.get_lora_scanner()

        # Get available loras from cache
        available_loras = []
        try:
            cache_data = await scanner.get_cached_data(force_refresh=False)
            if cache_data and hasattr(cache_data, "raw_data"):
                available_loras = cache_data.raw_data
        except Exception as e:
            logger.warning(f"[LoraDemoNode] Failed to get lora cache: {e}")

        # Randomly select 3-5 loras
        num_to_select = random.randint(3, 5)
        if len(available_loras) < num_to_select:
            num_to_select = len(available_loras)

        selected_loras = (
            random.sample(available_loras, num_to_select) if num_to_select > 0 else []
        )

        # Generate random loras data for widget
        widget_loras = []
        for lora in selected_loras:
            strength = round(random.uniform(0.1, 1.0), 2)
            widget_loras.append(
                {
                    "name": lora.get("file_name", "Unknown"),
                    "strength": strength,
                    "clipStrength": strength,
                    "active": True,
                    "expanded": False,
                }
            )

        # Create summary string
        active_names = [l["name"] for l in widget_loras]
        summary = f"Randomized {len(active_names)} LoRAs: {', '.join(active_names)}"

        logger.info(f"[LoraDemoNode] {summary}")

        # Return format: result for workflow + ui for frontend
        return {"result": (summary,), "ui": {"loras": widget_loras}}


# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {"LoraDemoNode": LoraDemoNode}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {"LoraDemoNode": "LoRA Demo"}
