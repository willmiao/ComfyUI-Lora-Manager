"""Wildcard resource service on the shared model-management pipeline."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from ..config import config
from ..utils.models import WildcardMetadata
from .auto_tag_service import extract_auto_tags
from .base_model_service import BaseModelService
from .wildcard_activation_service import get_wildcard_activation_service

logger = logging.getLogger(__name__)


class WildcardModelService(BaseModelService):
    def __init__(self, scanner, update_service=None, activation_service=None):
        super().__init__(
            "wildcard", scanner, WildcardMetadata, update_service=update_service
        )
        self.activation_service = activation_service or get_wildcard_activation_service()

    async def format_response(self, model_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        file_path = model_data.get("file_path")
        if not file_path:
            return None
        result = {
            "model_name": model_data.get("model_name") or model_data.get("file_name") or "",
            "file_name": model_data.get("file_name") or "",
            "preview_url": config.get_preview_static_url(model_data.get("preview_url", "")),
            "preview_nsfw_level": model_data.get("preview_nsfw_level", 0),
            "base_model": model_data.get("base_model", ""),
            "folder": model_data.get("folder") or "",
            "sha256": model_data.get("sha256", ""),
            "file_path": file_path.replace(os.sep, "/"),
            "file_size": model_data.get("size", 0),
            "modified": model_data.get("modified", ""),
            "tags": model_data.get("tags", []),
            "from_civitai": model_data.get("from_civitai", True),
            "notes": model_data.get("notes", ""),
            "sub_type": "wildcard",
            "favorite": model_data.get("favorite", False),
            "exclude": bool(model_data.get("exclude", False)),
            "update_available": bool(model_data.get("update_available", False)),
            "skip_metadata_refresh": bool(model_data.get("skip_metadata_refresh", False)),
            "civitai": self.filter_civitai_data(model_data.get("civitai", {}), minimal=True),
            "auto_tags": model_data.get("auto_tags") or extract_auto_tags(model_data),
            "version_count": model_data.get("version_count"),
            "source_platform": model_data.get("source_platform", ""),
            "source_url": model_data.get("source_url", ""),
            "source_model_id": model_data.get("source_model_id", ""),
            "source_version_id": model_data.get("source_version_id", ""),
            "wildcard_format": model_data.get("wildcard_format", ""),
            "files": model_data.get("files", []),
            "entries": model_data.get("entries", []),
            "errors": model_data.get("errors", []),
            "unsupported_files": model_data.get("unsupported_files", []),
            "entry_count": model_data.get("entry_count", 0),
            "value_count": model_data.get("value_count", 0),
        }
        return self.activation_service.decorate(result)

    def find_duplicate_hashes(self) -> Dict[str, Any]:
        return self.scanner._hash_index.get_duplicate_hashes()

    def find_duplicate_filenames(self) -> Dict[str, Any]:
        return self.scanner._hash_index.get_duplicate_filenames()
