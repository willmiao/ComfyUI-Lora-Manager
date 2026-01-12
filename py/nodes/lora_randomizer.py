"""
Lora Randomizer Node - Randomly selects LoRAs from a pool with configurable settings.

This node accepts optional pool_config input to filter available LoRAs, and outputs
a LORA_STACK with randomly selected LoRAs. Supports both frontend roll (fixed selection)
and backend roll (randomizes each execution).
"""

import logging
import random
import os
from ..utils.utils import get_lora_info
from .utils import extract_lora_name

logger = logging.getLogger(__name__)


class LoraRandomizerNode:
    """Node that randomly selects LoRAs from a pool"""

    NAME = "Lora Randomizer (LoraManager)"
    CATEGORY = "Lora Manager/randomizer"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "randomizer_config": ("RANDOMIZER_CONFIG", {}),
                "loras": ("LORAS", {}),
            },
            "optional": {
                "pool_config": ("POOL_CONFIG", {}),
            },
        }

    RETURN_TYPES = ("LORA_STACK",)
    RETURN_NAMES = ("lora_stack",)

    FUNCTION = "randomize"
    OUTPUT_NODE = False

    async def randomize(self, randomizer_config, loras, pool_config=None):
        """
        Randomize LoRAs based on configuration and pool filters.

        Args:
            randomizer_config: Dict with randomizer settings (count, strength ranges, roll mode)
            loras: List of LoRA dicts from LORAS widget (includes locked state)
            pool_config: Optional config from LoRA Pool node for filtering

        Returns:
            Dictionary with 'result' (LORA_STACK tuple) and 'ui' (for widget display)
        """
        from ..services.service_registry import ServiceRegistry

        # Get lora scanner to access available loras
        scanner = await ServiceRegistry.get_lora_scanner()

        # Parse randomizer settings
        count_mode = randomizer_config.get("count_mode", "range")
        count_fixed = randomizer_config.get("count_fixed", 5)
        count_min = randomizer_config.get("count_min", 3)
        count_max = randomizer_config.get("count_max", 7)
        model_strength_min = randomizer_config.get("model_strength_min", 0.0)
        model_strength_max = randomizer_config.get("model_strength_max", 1.0)
        use_same_clip_strength = randomizer_config.get("use_same_clip_strength", True)
        clip_strength_min = randomizer_config.get("clip_strength_min", 0.0)
        clip_strength_max = randomizer_config.get("clip_strength_max", 1.0)
        roll_mode = randomizer_config.get("roll_mode", "frontend")

        # Determine target count
        if count_mode == "fixed":
            target_count = count_fixed
        else:
            target_count = random.randint(count_min, count_max)

        logger.info(
            f"[LoraRandomizerNode] Target count: {target_count}, Roll mode: {roll_mode}"
        )

        # Extract locked LoRAs from input
        locked_loras = [lora for lora in loras if lora.get("locked", False)]
        locked_count = len(locked_loras)

        logger.info(f"[LoraRandomizerNode] Locked LoRAs: {locked_count}")

        # Get available loras from cache
        try:
            cache_data = await scanner.get_cached_data(force_refresh=False)
            if cache_data and hasattr(cache_data, "raw_data"):
                available_loras = cache_data.raw_data
            else:
                available_loras = []
        except Exception as e:
            logger.warning(f"[LoraRandomizerNode] Failed to get lora cache: {e}")
            available_loras = []

        # Apply pool filters if provided
        if pool_config:
            available_loras = await self._apply_pool_filters(
                available_loras, pool_config, scanner
            )

        logger.info(
            f"[LoraRandomizerNode] Available LoRAs after filtering: {len(available_loras)}"
        )

        # Calculate how many new LoRAs to select
        # In frontend mode, if loras already has data, preserve unlocked ones if roll_mode requires
        # For simplicity in backend mode, we regenerate all unlocked slots
        slots_needed = target_count - locked_count

        if slots_needed < 0:
            slots_needed = 0
            # Too many locked, trim to target
            locked_loras = locked_loras[:target_count]
            locked_count = len(locked_loras)

        # Filter out locked LoRAs from available pool
        locked_names = {lora["name"] for lora in locked_loras}
        available_pool = [
            l for l in available_loras if l["file_name"] not in locked_names
        ]

        # Ensure we don't try to select more than available
        if slots_needed > len(available_pool):
            slots_needed = len(available_pool)

        logger.info(
            f"[LoraRandomizerNode] Selecting {slots_needed} new LoRAs from {len(available_pool)} available"
        )

        # Random sample
        selected = []
        if slots_needed > 0:
            selected = random.sample(available_pool, slots_needed)

        # Generate random strengths for selected LoRAs
        result_loras = []
        for lora in selected:
            model_str = round(random.uniform(model_strength_min, model_strength_max), 2)

            if use_same_clip_strength:
                clip_str = model_str
            else:
                clip_str = round(
                    random.uniform(clip_strength_min, clip_strength_max), 2
                )

            result_loras.append(
                {
                    "name": lora["file_name"],
                    "strength": model_str,
                    "clipStrength": clip_str,
                    "active": True,
                    "expanded": abs(model_str - clip_str) > 0.001,
                    "locked": False,
                }
            )

        # Merge with locked LoRAs
        result_loras.extend(locked_loras)

        logger.info(f"[LoraRandomizerNode] Final LoRA count: {len(result_loras)}")

        # Build LORA_STACK output
        lora_stack = []
        for lora in result_loras:
            if not lora.get("active", False):
                continue

            # Get file path
            lora_path, trigger_words = get_lora_info(lora["name"])
            if not lora_path:
                logger.warning(
                    f"[LoraRandomizerNode] Could not find path for LoRA: {lora['name']}"
                )
                continue

            # Normalize path separators
            lora_path = lora_path.replace("/", os.sep)

            # Extract strengths
            model_strength = lora.get("strength", 1.0)
            clip_strength = lora.get("clipStrength", model_strength)

            lora_stack.append((lora_path, model_strength, clip_strength))

        # Return format: result for workflow + ui for frontend display
        return {"result": (lora_stack,), "ui": {"loras": result_loras}}

    async def _apply_pool_filters(self, available_loras, pool_config, scanner):
        """
        Apply pool_config filters to available LoRAs.

        Args:
            available_loras: List of all LoRA dicts
            pool_config: Dict with filter settings from LoRA Pool node
            scanner: Scanner instance for accessing filter utilities

        Returns:
            Filtered list of LoRA dicts
        """
        from ..services.lora_service import LoraService
        from ..services.model_query import FilterCriteria

        # Create lora service instance for filtering
        lora_service = LoraService(scanner)

        # Extract filter parameters from pool_config
        selected_base_models = pool_config.get("baseModels", [])
        tags_dict = pool_config.get("tags", {})
        include_tags = tags_dict.get("include", [])
        exclude_tags = tags_dict.get("exclude", [])
        folders_dict = pool_config.get("folders", {})
        include_folders = folders_dict.get("include", [])
        exclude_folders = folders_dict.get("exclude", [])
        license_dict = pool_config.get("license", {})
        no_credit_required = license_dict.get("noCreditRequired", False)
        allow_selling = license_dict.get("allowSelling", False)

        # Build tag filters dict
        tag_filters = {}
        for tag in include_tags:
            tag_filters[tag] = "include"
        for tag in exclude_tags:
            tag_filters[tag] = "exclude"

        # Build folder filter
        # LoRA Pool uses include/exclude folders, we need to apply this logic
        # For now, we'll filter based on folder path matching
        if include_folders or exclude_folders:
            filtered = []
            for lora in available_loras:
                folder = lora.get("folder", "")

                # Check exclude folders first
                excluded = False
                for exclude_folder in exclude_folders:
                    if folder.startswith(exclude_folder):
                        excluded = True
                        break

                if excluded:
                    continue

                # Check include folders
                if include_folders:
                    included = False
                    for include_folder in include_folders:
                        if folder.startswith(include_folder):
                            included = True
                            break
                    if not included:
                        continue

                filtered.append(lora)

            available_loras = filtered

        # Apply base model filter
        if selected_base_models:
            available_loras = [
                lora
                for lora in available_loras
                if lora.get("base_model") in selected_base_models
            ]

        # Apply tag filters
        if tag_filters:
            criteria = FilterCriteria(tags=tag_filters)
            available_loras = lora_service.filter_set.apply(available_loras, criteria)

        # Apply license filters
        if no_credit_required:
            available_loras = [
                lora
                for lora in available_loras
                if not lora.get("civitai", {}).get("allowNoCredit", True)
            ]

        if allow_selling:
            available_loras = [
                lora
                for lora in available_loras
                if lora.get("civitai", {}).get("allowCommercialUse", ["None"])[0]
                != "None"
            ]

        return available_loras


# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {"LoraRandomizerNode": LoraRandomizerNode}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {"LoraRandomizerNode": "LoRA Randomizer"}
