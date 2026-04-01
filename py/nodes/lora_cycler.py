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


class LoraCyclerLM:
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
        use_same_clip_strength = cycler_config.get("use_same_clip_strength", True)
        use_preset_strength = cycler_config.get("use_preset_strength", False)
        preset_strength_scale = float(cycler_config.get("preset_strength_scale", 1.0))
        sort_by = "filename"

        # Include "no lora" option
        include_no_lora = cycler_config.get("include_no_lora", False)

        # Dual-index mechanism for batch queue synchronization
        execution_index = cycler_config.get("execution_index")  # Can be None
        # next_index_from_config = cycler_config.get("next_index")  # Not used on backend

        # Get scanner and service
        scanner = await ServiceRegistry.get_lora_scanner()
        lora_service = LoraService(scanner)

        # Get filtered and sorted LoRA list
        lora_list = await lora_service.get_cycler_list(
            pool_config=pool_config, sort_by=sort_by
        )

        total_count = len(lora_list)

        # Calculate effective total count (includes no lora option if enabled)
        effective_total_count = total_count + 1 if include_no_lora else total_count

        if total_count == 0 and not include_no_lora:
            logger.warning("[LoraCyclerLM] No LoRAs available in pool")
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

        # Determine which index to use for this execution
        # If execution_index is provided (batch queue case), use it
        # Otherwise use current_index (first execution or non-batch case)
        if execution_index is not None:
            actual_index = execution_index
        else:
            actual_index = current_index

        # Clamp index to valid range (1-based, includes no lora if enabled)
        clamped_index = max(1, min(actual_index, effective_total_count))

        # Check if current index is the "no lora" option (last position when include_no_lora is True)
        is_no_lora = include_no_lora and clamped_index == effective_total_count

        if is_no_lora:
            # "No LoRA" option - return empty stack
            lora_stack = []
            current_lora_name = "No LoRA"
            current_lora_filename = "No LoRA"
        else:
            # Get LoRA at current index (convert to 0-based for list access)
            current_lora = lora_list[clamped_index - 1]
            current_lora_name = current_lora["file_name"]
            current_lora_filename = current_lora["file_name"]

            # Build LORA_STACK with single LoRA
            if current_lora["file_name"] == "None":
                lora_path = None
            else:
                lora_path, _ = get_lora_info(current_lora["file_name"])

            if not lora_path:
                if current_lora["file_name"] != "None":
                    logger.warning(
                        f"[LoraCyclerLM] Could not find path for LoRA: {current_lora['file_name']}"
                    )
                lora_stack = []
            else:
                # Normalize path separators
                lora_path = lora_path.replace("/", os.sep)

                if use_preset_strength:
                    lora_metadata = await lora_service.get_lora_metadata_by_filename(
                        current_lora["file_name"]
                    )
                    if lora_metadata:
                        recommended_strength = (
                            lora_service.get_recommended_strength_from_lora_data(
                                lora_metadata
                            )
                        )
                        if recommended_strength is not None:
                            model_strength = round(
                                recommended_strength * preset_strength_scale, 2
                            )

                        if use_same_clip_strength:
                            clip_strength = model_strength
                        else:
                            recommended_clip_strength = (
                                lora_service.get_recommended_clip_strength_from_lora_data(
                                    lora_metadata
                                )
                            )
                            if recommended_clip_strength is not None:
                                clip_strength = round(
                                    recommended_clip_strength * preset_strength_scale, 2
                                )
                    elif use_same_clip_strength:
                        clip_strength = model_strength
                elif use_same_clip_strength:
                    clip_strength = model_strength

                lora_stack = [(lora_path, model_strength, clip_strength)]

        # Calculate next index (wrap to 1 if at end)
        next_index = clamped_index + 1
        if next_index > effective_total_count:
            next_index = 1

        # Get next LoRA for UI display (what will be used next generation)
        is_next_no_lora = include_no_lora and next_index == effective_total_count
        if is_next_no_lora:
            next_display_name = "No LoRA"
            next_lora_filename = "No LoRA"
        else:
            next_lora = lora_list[next_index - 1]
            next_display_name = next_lora["file_name"]
            next_lora_filename = next_lora["file_name"]

        return {
            "result": (lora_stack,),
            "ui": {
                "current_index": [clamped_index],
                "next_index": [next_index],
                "total_count": [
                    total_count
                ],  # Return actual LoRA count, not effective_total_count
                "current_lora_name": [current_lora_name],
                "current_lora_filename": [current_lora_filename],
                "next_lora_name": [next_display_name],
                "next_lora_filename": [next_lora_filename],
            },
        }
