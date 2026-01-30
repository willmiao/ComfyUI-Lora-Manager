import os
import logging
from typing import Dict

from .base_model_service import BaseModelService
from ..utils.models import MiscMetadata
from ..config import config

logger = logging.getLogger(__name__)

class MiscService(BaseModelService):
    """Misc-specific service implementation (VAE, Upscaler)"""

    def __init__(self, scanner, update_service=None):
        """Initialize Misc service

        Args:
            scanner: Misc scanner instance
            update_service: Optional service for remote update tracking.
        """
        super().__init__("misc", scanner, MiscMetadata, update_service=update_service)

    async def format_response(self, misc_data: Dict) -> Dict:
        """Format Misc data for API response"""
        # Get sub_type from cache entry (new canonical field)
        sub_type = misc_data.get("sub_type", "vae")

        return {
            "model_name": misc_data["model_name"],
            "file_name": misc_data["file_name"],
            "preview_url": config.get_preview_static_url(misc_data.get("preview_url", "")),
            "preview_nsfw_level": misc_data.get("preview_nsfw_level", 0),
            "base_model": misc_data.get("base_model", ""),
            "folder": misc_data["folder"],
            "sha256": misc_data.get("sha256", ""),
            "file_path": misc_data["file_path"].replace(os.sep, "/"),
            "file_size": misc_data.get("size", 0),
            "modified": misc_data.get("modified", ""),
            "tags": misc_data.get("tags", []),
            "from_civitai": misc_data.get("from_civitai", True),
            "usage_count": misc_data.get("usage_count", 0),
            "notes": misc_data.get("notes", ""),
            "sub_type": sub_type,
            "favorite": misc_data.get("favorite", False),
            "update_available": bool(misc_data.get("update_available", False)),
            "civitai": self.filter_civitai_data(misc_data.get("civitai", {}), minimal=True)
        }

    def find_duplicate_hashes(self) -> Dict:
        """Find Misc models with duplicate SHA256 hashes"""
        return self.scanner._hash_index.get_duplicate_hashes()

    def find_duplicate_filenames(self) -> Dict:
        """Find Misc models with conflicting filenames"""
        return self.scanner._hash_index.get_duplicate_filenames()
