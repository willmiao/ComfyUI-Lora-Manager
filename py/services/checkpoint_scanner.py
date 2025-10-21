import logging
from typing import Any, Dict, List, Optional

from ..utils.models import CheckpointMetadata
from ..config import config
from .model_scanner import ModelScanner
from .model_hash_index import ModelHashIndex

logger = logging.getLogger(__name__)

class CheckpointScanner(ModelScanner):
    """Service for scanning and managing checkpoint files"""
    
    def __init__(self):
        # Define supported file extensions
        file_extensions = {'.ckpt', '.pt', '.pt2', '.bin', '.pth', '.safetensors', '.pkl', '.sft', '.gguf'}
        super().__init__(
            model_type="checkpoint",
            model_class=CheckpointMetadata,
            file_extensions=file_extensions,
            hash_index=ModelHashIndex()
        )

    def _resolve_model_type(self, root_path: Optional[str]) -> Optional[str]:
        if not root_path:
            return None

        if config.checkpoints_roots and root_path in config.checkpoints_roots:
            return "checkpoint"

        if config.unet_roots and root_path in config.unet_roots:
            return "diffusion_model"

        return None

    def adjust_metadata(self, metadata, file_path, root_path):
        if hasattr(metadata, "model_type"):
            model_type = self._resolve_model_type(root_path)
            if model_type:
                metadata.model_type = model_type
        return metadata

    def adjust_cached_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        model_type = self._resolve_model_type(
            self._find_root_for_file(entry.get("file_path"))
        )
        if model_type:
            entry["model_type"] = model_type
        return entry

    def get_model_roots(self) -> List[str]:
        """Get checkpoint root directories"""
        return config.base_models_roots
