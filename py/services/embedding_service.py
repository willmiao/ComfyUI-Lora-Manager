import os
import logging
from typing import Dict

from .base_model_service import BaseModelService
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
    
    async def format_response(self, embedding_data: Dict) -> Dict:
        """Format Embedding data for API response"""
        return {
            "model_name": embedding_data["model_name"],
            "file_name": embedding_data["file_name"],
            "preview_url": config.get_preview_static_url(embedding_data.get("preview_url", "")),
            "preview_nsfw_level": embedding_data.get("preview_nsfw_level", 0),
            "base_model": embedding_data.get("base_model", ""),
            "folder": embedding_data["folder"],
            "sha256": embedding_data.get("sha256", ""),
            "file_path": embedding_data["file_path"].replace(os.sep, "/"),
            "file_size": embedding_data.get("size", 0),
            "modified": embedding_data.get("modified", ""),
            "tags": embedding_data.get("tags", []),
            "from_civitai": embedding_data.get("from_civitai", True),
            "notes": embedding_data.get("notes", ""),
            "model_type": embedding_data.get("model_type", "embedding"),
            "favorite": embedding_data.get("favorite", False),
            "update_available": bool(embedding_data.get("update_available", False)),
            "civitai": self.filter_civitai_data(embedding_data.get("civitai", {}), minimal=True)
        }
    
    def find_duplicate_hashes(self) -> Dict:
        """Find Embeddings with duplicate SHA256 hashes"""
        return self.scanner._hash_index.get_duplicate_hashes()
    
    def find_duplicate_filenames(self) -> Dict:
        """Find Embeddings with conflicting filenames"""
        return self.scanner._hash_index.get_duplicate_filenames()
