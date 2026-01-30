import logging
from typing import Any, Dict, List, Optional

from ..utils.models import MiscMetadata
from ..config import config
from .model_scanner import ModelScanner
from .model_hash_index import ModelHashIndex

logger = logging.getLogger(__name__)

class MiscScanner(ModelScanner):
    """Service for scanning and managing misc files (VAE, Upscaler)"""

    def __init__(self):
        # Define supported file extensions (combined from VAE and upscaler)
        file_extensions = {'.safetensors', '.pt', '.bin', '.ckpt', '.pth'}
        super().__init__(
            model_type="misc",
            model_class=MiscMetadata,
            file_extensions=file_extensions,
            hash_index=ModelHashIndex()
        )

    def _resolve_sub_type(self, root_path: Optional[str]) -> Optional[str]:
        """Resolve the sub-type based on the root path."""
        if not root_path:
            return None

        if config.vae_roots and root_path in config.vae_roots:
            return "vae"

        if config.upscaler_roots and root_path in config.upscaler_roots:
            return "upscaler"

        return None

    def adjust_metadata(self, metadata, file_path, root_path):
        """Adjust metadata during scanning to set sub_type."""
        sub_type = self._resolve_sub_type(root_path)
        if sub_type:
            metadata.sub_type = sub_type
        return metadata

    def adjust_cached_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust entries loaded from the persisted cache to ensure sub_type is set."""
        sub_type = self._resolve_sub_type(
            self._find_root_for_file(entry.get("file_path"))
        )
        if sub_type:
            entry["sub_type"] = sub_type
        return entry

    def get_model_roots(self) -> List[str]:
        """Get misc root directories (VAE and upscaler)"""
        return config.misc_roots
