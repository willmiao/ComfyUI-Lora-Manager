import logging
from ..metadata_collector.metadata_processor import MetadataProcessor

logger = logging.getLogger(__name__)


class DebugMetadataLM:
    NAME = "Debug Metadata (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = "Debug node to verify metadata_processor functionality"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
            },
            "hidden": {
                "id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "process_metadata"

    def process_metadata(self, images, id):
        """
        Process metadata from the execution context and return it for UI display.

        The metadata is returned via the 'ui' key in the return dict, which triggers
        node.onExecuted on the frontend to update the JsonDisplayWidget.

        Args:
            images: Input images (required for execution flow)
            id: Node's unique ID (hidden)

        Returns:
            Dict with 'result' (empty tuple) and 'ui' (metadata dict for widget display)
        """
        try:
            # Get the current execution context's metadata
            from ..metadata_collector import get_metadata

            metadata = get_metadata()

            # Use the MetadataProcessor to convert it to dict
            metadata_dict = MetadataProcessor.to_dict(metadata, id)

            return {
                "result": (),
                # ComfyUI expects ui values to be lists, wrap the dict in a list
                "ui": {"metadata": [metadata_dict]},
            }

        except Exception as e:
            logger.error(f"Error processing metadata: {e}")
            return {
                "result": (),
                "ui": {"metadata": [{"error": str(e)}]},
            }
