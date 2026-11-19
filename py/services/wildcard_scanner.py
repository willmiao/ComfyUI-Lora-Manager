"""Scanner for Civitai and local wildcard artifacts."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from ..config import config
from ..utils.file_utils import calculate_sha256, find_preview_file, normalize_path
from ..utils.metadata_manager import MetadataManager
from ..utils.models import WildcardMetadata
from ..utils.sidecar_paths import get_preview_dir, get_sidecar_base_name
from .model_hash_index import ModelHashIndex
from .model_scanner import ModelScanner
from .wildcard_parser import (
    SUPPORTED_ARTIFACT_EXTENSIONS,
    WildcardParseError,
    parse_wildcard_artifact,
)

logger = logging.getLogger(__name__)


class WildcardScanner(ModelScanner):
    supports_quantization = False
    verify_hashes_on_scan = True

    def __init__(self):
        super().__init__(
            model_type="wildcard",
            model_class=WildcardMetadata,
            file_extensions=set(SUPPORTED_ARTIFACT_EXTENSIONS),
            hash_index=ModelHashIndex(),
        )

    def get_model_roots(self) -> List[str]:
        try:
            from .settings_manager import get_settings_manager

            if not get_settings_manager().is_wildcards_enabled():
                return []
        except Exception:
            return []
        return [root for root in (config.wildcards_roots or []) if root]

    def _is_indexable_filename(self, filename: str) -> bool:
        lowered = filename.lower()
        return not lowered.endswith(".metadata.json") and lowered not in {
            "catalog.json",
            "activations.json",
        }

    @staticmethod
    def _apply_parsed_index(metadata: WildcardMetadata, file_path: str) -> WildcardMetadata:
        metadata.wildcard_format = os.path.splitext(file_path)[1].lower().lstrip(".")
        try:
            parsed = parse_wildcard_artifact(file_path)
        except WildcardParseError as exc:
            metadata.files = []
            metadata.entries = []
            metadata.entry_count = 0
            metadata.value_count = 0
            metadata.errors = [str(exc)]
            return metadata
        metadata.files = parsed.files
        metadata.entries = [entry.summary() for entry in parsed.entries]
        metadata.entry_count = len(parsed.entries)
        metadata.value_count = parsed.value_count
        metadata.errors = parsed.errors
        metadata.unsupported_files = parsed.unsupported_files
        return metadata

    def adjust_metadata(self, metadata, file_path, root_path):
        if isinstance(metadata, WildcardMetadata) and not metadata.entries and not metadata.errors:
            return self._apply_parsed_index(metadata, file_path)
        return metadata

    async def _create_default_metadata(
        self,
        file_path: str,
        *,
        include_remote: bool = False,
        checkpoint_name_hint: str | None = None,
    ) -> Optional[WildcardMetadata]:
        del include_remote, checkpoint_name_hint
        try:
            real_path = os.path.realpath(file_path)
            if not os.path.isfile(real_path):
                return None
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            preview_url = find_preview_file(
                get_sidecar_base_name(file_path), get_preview_dir(file_path)
            )
            sha256 = await calculate_sha256(real_path)
            if not sha256:
                return None
            metadata = WildcardMetadata(
                file_name=base_name,
                model_name=base_name,
                file_path=normalize_path(file_path),
                size=os.path.getsize(real_path),
                modified=datetime.now().timestamp(),
                sha256=sha256,
                base_model="Unknown",
                preview_url=normalize_path(preview_url),
                tags=[],
                modelDescription="",
                from_civitai=False,
            )
            self._apply_parsed_index(metadata, file_path)
            await MetadataManager.save_metadata(file_path, metadata)
            return metadata
        except Exception:
            logger.error("Error creating wildcard metadata for %s", file_path, exc_info=True)
            return None

    async def register_local_artifact(self, file_path: str) -> Optional[WildcardMetadata]:
        metadata = await self._create_default_metadata(file_path)
        if metadata is None:
            return None
        await self.sync_cache_from_metadata(file_path, metadata.to_dict())
        return metadata
