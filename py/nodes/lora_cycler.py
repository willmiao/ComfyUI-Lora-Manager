"""
Lora Cycler Node - Sequentially cycles through LoRAs from a pool.

This node accepts optional pool_config input to filter available LoRAs, and outputs
a LORA_STACK with one LoRA at a time. Returns UI updates with current/next LoRA info
and tracks the cycle progress which persists across workflow save/load.
"""

import logging
import os
from ..utils.utils import get_lora_info

logger = logging.getLogger(__name__)


class LoraCyclerNode:
    """Node that sequentially cycles through LoRAs from a pool"""

    NAME = "Lora Cycler (LoraManager)"
    CATEGORY = "Lora Manager/randomizer"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cycler_config": ("CYCLER_CONFIG", {}),
            },
            "optional": {
                "pool_config": ("POOL_CONFIG", {}),
            },
        }

    RETURN_TYPES = ("LORA_STACK",)
    RETURN_NAMES = ("LORA_STACK",)

    FUNCTION = "cycle"
    OUTPUT_NODE = False

    async def cycle(self, cycler_config, pool_config=None):
        """
        Cycle through LoRAs based on configuration and pool filters.

        Args:
            cycler_config: Dict with cycler settings (current_index, model_strength, clip_strength, sort_by)
            pool_config: Optional config from LoRA Pool node for filtering

        Returns:
            Dictionary with 'result' (LORA_STACK tuple) and 'ui' (for widget display)
        """
        from ..services.service_registry import ServiceRegistry
        from ..services.lora_service import LoraService

        # Extract settings from cycler_config
        current_index = cycler_config.get("current_index", 1)  # 1-based
        model_strength = float(cycler_config.get("model_strength", 1.0))
        clip_strength = float(cycler_config.get("clip_strength", 1.0))
        sort_by = cycler_config.get("sort_by", "filename")

        # Get scanner and service
        scanner = await ServiceRegistry.get_lora_scanner()
        lora_service = LoraService(scanner)

        # Get filtered and sorted LoRA list
        lora_list = await lora_service.get_cycler_list(
            pool_config=pool_config, sort_by=sort_by
        )

        total_count = len(lora_list)

        if total_count == 0:
            logger.warning("[LoraCyclerNode] No LoRAs available in pool")
            return {
                "result": ([],),
                "ui": {
                    "current_index": [1],
                    "next_index": [1],
                    "total_count": [0],
                    "current_lora_name": [""],
                    "current_lora_filename": [""],
                    "error": ["No LoRAs available in pool"],
                },
            }

        # Clamp index to valid range (1-based)
        clamped_index = max(1, min(current_index, total_count))

        # Get LoRA at current index (convert to 0-based for list access)
        current_lora = lora_list[clamped_index - 1]

        # Build LORA_STACK with single LoRA
        lora_path, _ = get_lora_info(current_lora["file_name"])
        if not lora_path:
            logger.warning(
                f"[LoraCyclerNode] Could not find path for LoRA: {current_lora['file_name']}"
            )
            lora_stack = []
        else:
            # Normalize path separators
            lora_path = lora_path.replace("/", os.sep)
            lora_stack = [(lora_path, model_strength, clip_strength)]

        # Calculate next index (wrap to 1 if at end)
        next_index = clamped_index + 1
        if next_index > total_count:
            next_index = 1

        # Get next LoRA for UI display (what will be used next generation)
        next_lora = lora_list[next_index - 1]

        # Determine display name based on sort_by setting
        if sort_by == "filename":
            next_display_name = next_lora["file_name"]
        else:
            next_display_name = next_lora.get("model_name", next_lora["file_name"])

        return {
            "result": (lora_stack,),
            "ui": {
                "current_index": [clamped_index],
                "next_index": [next_index],
                "total_count": [total_count],
                "current_lora_name": [
                    current_lora.get("model_name", current_lora["file_name"])
                ],
                "current_lora_filename": [current_lora["file_name"]],
                "next_lora_name": [next_display_name],
                "next_lora_filename": [next_lora["file_name"]],
                "sort_by": [sort_by],
            },
        }
