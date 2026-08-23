import os
import logging
from typing import Any, Dict, Optional

from .base_model_service import BaseModelService
from .auto_tag_service import extract_auto_tags
from ..utils.models import EmbeddingMetadata
from ..config import config

logger = logging.getLogger(__name__)

class EmbeddingService(BaseModelService):
    """Embedding-specific service implementation"""
    
    def __init__(self, scanner, update_service=None):
        """Initialize Embedding service
        
        Args:
            scanner: Embedding scanner instance
            update_service: Optional service for remote update tracking.
        """
        super().__init__("embedding", scanner, EmbeddingMetadata, update_service=update_service)
    
    async def format_response(self, model_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Format Embedding data for API response.

        Returns None when the entry is missing critical fields (corrupted cache
        row), so the handler layer can filter it out. See issue #730.
        """
        # Guard against corrupted cache entries missing critical fields
        file_path = model_data.get("file_path")
        if not file_path or not isinstance(file_path, str):
            logger.warning(
                "Skipping corrupted embedding entry (missing file_path): %s",
                model_data.get("file_name", "<unknown>"),
            )
            return None

        # Get sub_type from cache entry (new canonical field)
        sub_type = model_data.get("sub_type", "embedding")

        file_name = model_data.get("file_name") or ""
        model_name = model_data.get("model_name") or file_name
        folder = model_data.get("folder") or ""

        return {
            "model_name": model_name,
            "file_name": file_name,
            "preview_url": config.get_preview_static_url(model_data.get("preview_url", "")),
            "preview_nsfw_level": model_data.get("preview_nsfw_level", 0),
            "base_model": model_data.get("base_model", ""),
            "folder": folder,
            "sha256": model_data.get("sha256", ""),
            "autov3": model_data.get("autov3"),
            "file_path": file_path.replace(os.sep, "/"),
            "file_size": model_data.get("size", 0),
            "modified": model_data.get("modified", ""),
            "tags": model_data.get("tags", []),
            "from_civitai": model_data.get("from_civitai", True),
            # "usage_count": model_data.get("usage_count", 0), # TODO: Enable when embedding usage tracking is implemented
            "notes": model_data.get("notes", ""),
            "sub_type": sub_type,
            "favorite": model_data.get("favorite", False),
            "exclude": bool(model_data.get("exclude", False)),
            "update_available": bool(model_data.get("update_available", False)),
            "skip_metadata_refresh": bool(model_data.get("skip_metadata_refresh", False)),
            "civitai": self.filter_civitai_data(model_data.get("civitai", {}), minimal=True),
            "auto_tags": model_data.get("auto_tags") or extract_auto_tags(model_data),
            "version_count": model_data.get("version_count"),
            "hf_url": model_data.get("hf_url", ""),
        }
    
    def find_duplicate_hashes(self) -> Dict[str, Any]:
        """Find Embeddings with duplicate SHA256 hashes"""
        return self.scanner._hash_index.get_duplicate_hashes()
    
    def find_duplicate_filenames(self) -> Dict[str, Any]:
        """Find Embeddings with conflicting filenames"""
        return self.scanner._hash_index.get_duplicate_filenames()
