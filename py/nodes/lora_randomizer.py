"""
Lora Randomizer Node - Randomly selects LoRAs from a pool with configurable settings.

This node accepts optional pool_config input to filter available LoRAs, and outputs
a LORA_STACK with randomly selected LoRAs. Returns UI updates with new random LoRAs
and tracks the last used combination for reuse.
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
    RETURN_NAMES = ("LORA_STACK",)

    FUNCTION = "randomize"
    OUTPUT_NODE = False

    def _preprocess_loras_input(self, loras):
        """
        Preprocess loras input to handle different widget formats.

        Args:
            loras: Input from widget, either:
                  - List of LoRA dicts (expected format)
                  - Dict with '__value__' key containing the list

        Returns:
            List of LoRA dicts
        """
        if isinstance(loras, dict) and "__value__" in loras:
            return loras["__value__"]
        return loras

    async def randomize(self, randomizer_config, loras, pool_config=None):
        """
        Randomize LoRAs based on configuration and pool filters.

        Args:
            randomizer_config: Dict with randomizer settings (count, strength ranges, roll_mode)
            loras: List of LoRA dicts from LORAS widget (includes locked state)
            pool_config: Optional config from LoRA Pool node for filtering

        Returns:
            Dictionary with 'result' (LORA_STACK tuple) and 'ui' (for widget display)
        """
        from ..services.service_registry import ServiceRegistry

        loras = self._preprocess_loras_input(loras)

        roll_mode = randomizer_config.get("roll_mode", "always")
        logger.debug(f"[LoraRandomizerNode] roll_mode: {roll_mode}")

        if roll_mode == "fixed":
            ui_loras = loras
        else:
            scanner = await ServiceRegistry.get_lora_scanner()
            ui_loras = await self._generate_random_loras_for_ui(
                scanner, randomizer_config, loras, pool_config
            )

        print("pool config", pool_config)

        execution_stack = self._build_execution_stack_from_input(loras)

        return {
            "result": (execution_stack,),
            "ui": {"loras": ui_loras, "last_used": loras},
        }

    def _build_execution_stack_from_input(self, loras):
        """
        Build LORA_STACK tuple from input loras list for execution.

        Args:
            loras: List of LoRA dicts with name, strength, clipStrength, active

        Returns:
            List of tuples (lora_path, model_strength, clip_strength)
        """
        lora_stack = []
        for lora in loras:
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

            # Extract strengths (convert to float to prevent string subtraction errors)
            model_strength = float(lora.get("strength", 1.0))
            clip_strength = float(lora.get("clipStrength", model_strength))

            lora_stack.append((lora_path, model_strength, clip_strength))

        return lora_stack

    async def _generate_random_loras_for_ui(
        self, scanner, randomizer_config, input_loras, pool_config=None
    ):
        """
        Generate new random loras for UI display.

        Args:
            scanner: LoraScanner instance
            randomizer_config: Dict with randomizer settings
            input_loras: Current input loras (for extracting locked loras)
            pool_config: Optional pool filters

        Returns:
            List of LoRA dicts for UI display
        """
        from ..services.lora_service import LoraService

        # Parse randomizer settings (convert numeric values to float to prevent type errors)
        count_mode = randomizer_config.get("count_mode", "range")
        count_fixed = int(randomizer_config.get("count_fixed", 5))
        count_min = int(randomizer_config.get("count_min", 3))
        count_max = int(randomizer_config.get("count_max", 7))
        model_strength_min = float(randomizer_config.get("model_strength_min", 0.0))
        model_strength_max = float(randomizer_config.get("model_strength_max", 1.0))
        use_same_clip_strength = randomizer_config.get("use_same_clip_strength", True)
        clip_strength_min = float(randomizer_config.get("clip_strength_min", 0.0))
        clip_strength_max = float(randomizer_config.get("clip_strength_max", 1.0))
        use_recommended_strength = randomizer_config.get(
            "use_recommended_strength", False
        )
        recommended_strength_scale_min = float(
            randomizer_config.get("recommended_strength_scale_min", 0.5)
        )
        recommended_strength_scale_max = float(
            randomizer_config.get("recommended_strength_scale_max", 1.0)
        )

        # Extract locked LoRAs from input
        locked_loras = [lora for lora in input_loras if lora.get("locked", False)]

        # Use LoraService to generate random LoRAs
        lora_service = LoraService(scanner)
        result_loras = await lora_service.get_random_loras(
            count=count_fixed,
            model_strength_min=model_strength_min,
            model_strength_max=model_strength_max,
            use_same_clip_strength=use_same_clip_strength,
            clip_strength_min=clip_strength_min,
            clip_strength_max=clip_strength_max,
            locked_loras=locked_loras,
            pool_config=pool_config,
            count_mode=count_mode,
            count_min=count_min,
            count_max=count_max,
            use_recommended_strength=use_recommended_strength,
            recommended_strength_scale_min=recommended_strength_scale_min,
            recommended_strength_scale_max=recommended_strength_scale_max,
        )

        return result_loras
