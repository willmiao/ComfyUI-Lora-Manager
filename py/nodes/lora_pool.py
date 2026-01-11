"""
LoRA Pool Node - Defines filter configuration for LoRA selection.

This node provides a visual filter editor that generates a LORA_POOL_CONFIG
object for use by downstream nodes (like LoRA Randomizer).
"""

import logging

logger = logging.getLogger(__name__)


class LoraPoolNode:
    """
    A node that defines LoRA filter criteria through a Vue-based widget.

    Outputs a LORA_POOL_CONFIG that can be consumed by:
    - Frontend: LoRA Randomizer widget reads connected pool's widget value
    - Backend: LoRA Randomizer receives config during workflow execution
    """

    NAME = "Lora Pool (LoraManager)"
    CATEGORY = "Lora Manager/pools"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pool_config": ("LORA_POOL_CONFIG", {}),
            },
            "hidden": {
                # Hidden input to pass through unique node ID for frontend
                "unique_id": "UNIQUE_ID",
            }
        }

    RETURN_TYPES = ("LORA_POOL_CONFIG",)
    RETURN_NAMES = ("pool_config",)

    FUNCTION = "process"
    OUTPUT_NODE = False

    def process(self, pool_config, unique_id=None):
        """
        Pass through the pool configuration.

        The config is generated entirely by the frontend widget.
        This function validates and passes through the configuration.

        Args:
            pool_config: Dict containing filter criteria from widget
            unique_id: Node's unique ID (hidden)

        Returns:
            Tuple containing the validated pool_config
        """
        # Validate required structure
        if not isinstance(pool_config, dict):
            logger.warning("Invalid pool_config type, using empty config")
            pool_config = self._default_config()

        # Ensure version field exists
        if "version" not in pool_config:
            pool_config["version"] = 1

        # Log for debugging
        logger.debug(f"[LoraPoolNode] Processing config: {pool_config}")

        return (pool_config,)

    @staticmethod
    def _default_config():
        """Return default empty configuration."""
        return {
            "version": 1,
            "filters": {
                "baseModels": [],
                "tags": {"include": [], "exclude": []},
                "folder": {"path": None, "recursive": True},
                "favoritesOnly": False,
                "license": {
                    "noCreditRequired": None,
                    "allowSellingGeneratedContent": None
                }
            },
            "preview": {"matchCount": 0, "lastUpdated": 0}
        }


# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {
    "LoraPoolNode": LoraPoolNode
}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoraPoolNode": "LoRA Pool (Filter)"
}
