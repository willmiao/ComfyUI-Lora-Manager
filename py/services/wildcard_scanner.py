"""Scanner for Civitai and local wildcard artifacts."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from ..config import config
from ..utils.file_utils import calculate_sha256, find_preview_file, normalize_path
from ..utils.metadata_manager import MetadataManager
from ..utils.models import WildcardMetadata
from ..utils.sidecar_paths import get_preview_dir, get_sidecar_base_name
from .model_hash_index import ModelHashIndex
from .model_scanner import ModelScanner
from .websocket_manager import ws_manager
from .wildcard_activation_service import get_wildcard_activation_service
from .wildcard_parser import (
    SUPPORTED_ARTIFACT_EXTENSIONS,
    WildcardParseError,
    parse_wildcard_artifact,
)

logger = logging.getLogger(__name__)


class WildcardScanner(ModelScanner):
    supports_quantization = False
    verify_hashes_on_scan = True

    def __init__(self, activation_service=None):
        super().__init__(
            model_type="wildcard",
            model_class=WildcardMetadata,
            file_extensions=set(SUPPORTED_ARTIFACT_EXTENSIONS),
            hash_index=ModelHashIndex(),
        )
        self.activation_service = activation_service or get_wildcard_activation_service()

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
        if parsed.unreferenceable:
            keys = ", ".join(item["key"] for item in parsed.unreferenceable[:5])
            logger.warning(
                "Wildcard artifact %s has %d key(s) that cannot be referenced "
                "through __key__ syntax: %s",
                file_path,
                len(parsed.unreferenceable),
                keys,
            )
        return metadata

    def adjust_metadata(self, metadata, file_path, root_path):
        if isinstance(metadata, WildcardMetadata) and not metadata.entries and not metadata.errors:
            return self._apply_parsed_index(metadata, file_path)
        return metadata

    async def initialize_in_background(self, reconcile: bool = False) -> None:
        await super().initialize_in_background(reconcile=reconcile)
        if self._cache is not None:
            try:
                rebound = await asyncio.to_thread(
                    self.activation_service.reconcile_resources,
                    self._cache.raw_data,
                )
            except Exception:
                logger.warning("Unable to reconcile wildcard activation paths", exc_info=True)
            else:
                await self._notify_activation_rebindings(rebound)
        await self._backfill_parsed_index()

    async def update_single_model_cache(
        self,
        original_path: str,
        new_path: str,
        metadata: Optional[Dict[str, Any]],
    ):
        result = await super().update_single_model_cache(
            original_path,
            new_path,
            metadata,
        )
        if result and self._path_key(original_path) != self._path_key(new_path):
            await self._rebind_activation_paths({original_path: new_path})
        return result

    async def rename_known_folder(
        self,
        previous_folder: str,
        new_folder: str,
        *,
        previous_path: str,
        new_path: str,
    ) -> bool:
        moves: Dict[str, str] = {}
        old_prefix = self._path_prefix(previous_path)
        new_prefix = self._path_prefix(new_path)
        if self._cache is not None:
            for item in self._cache.raw_data:
                file_path = str(item.get("file_path") or "")
                normalized = file_path.replace("\\", "/")
                if normalized.startswith(old_prefix):
                    moves[file_path] = new_prefix + normalized[len(old_prefix):]

        changed = await super().rename_known_folder(
            previous_folder,
            new_folder,
            previous_path=previous_path,
            new_path=new_path,
        )
        if changed and moves:
            await self._rebind_activation_paths(moves)
        return changed

    @staticmethod
    def _path_key(file_path: str) -> str:
        return os.path.normcase(os.path.abspath(file_path)).replace(os.sep, "/")

    @staticmethod
    def _path_prefix(file_path: str) -> str:
        return file_path.replace("\\", "/").rstrip("/") + "/"

    async def _rebind_activation_paths(self, moves: Mapping[str, str]) -> None:
        try:
            rebound = await asyncio.to_thread(self.activation_service.rebind_paths, moves)
        except Exception:
            logger.warning("Unable to rebind wildcard activation records", exc_info=True)
            return
        await self._notify_activation_rebindings(rebound)

    async def _notify_activation_rebindings(
        self,
        rebound: Mapping[str, Dict[str, Any]],
    ) -> None:
        for previous_path, record in rebound.items():
            file_path = str(record.get("file_path") or "")
            active = record.get("active", True) is not False
            payload = {
                "file_path": file_path,
                "previous_file_path": previous_path,
                "active": active,
            }
            try:
                await ws_manager.broadcast({
                    "type": "wildcard_activation_changed",
                    **payload,
                })
            except Exception:
                logger.debug("Unable to broadcast wildcard path rebind", exc_info=True)
            if os.environ.get("LORA_MANAGER_STANDALONE", "0") != "1":
                try:
                    from server import PromptServer

                    PromptServer.instance.send_sync("lm_wildcards_changed", payload)
                except Exception:
                    logger.debug("Unable to notify ComfyUI wildcard panels", exc_info=True)

    async def _backfill_parsed_index(self) -> None:
        """Fill wildcard fields for entries hydrated from an older cache.

        Cache rows persisted before the wildcard columns existed carry no key
        index, so the manager page and canvas panel would show the resource
        with zero keys until a full rescan. The sidecar written by the scanner
        is the authoritative index; parse the artifact only when the sidecar
        is missing or has no entries.
        """
        cache = self._cache
        if cache is None or not cache.raw_data:
            return
        updated = False
        for entry in cache.raw_data:
            # A present entry_count marks an entry that already went through
            # the parsed-index projection, even when the artifact has no keys.
            if entry.get("entries") or "entry_count" in entry:
                continue
            file_path = entry.get("file_path") or ""
            if not file_path:
                continue
            fields = await self._load_indexed_fields(file_path)
            if not fields:
                continue
            entry.update(fields)
            updated = True
        if updated:
            await self._persist_current_cache()

    async def _load_indexed_fields(self, file_path: str) -> dict:
        payload: dict = {}
        try:
            payload = await MetadataManager.load_metadata_payload(file_path)
        except Exception:
            logger.debug(
                "Unable to read wildcard sidecar for %s", file_path, exc_info=True
            )
        if not payload.get("entries"):
            try:
                parsed = await asyncio.to_thread(parse_wildcard_artifact, file_path)
            except Exception:
                logger.debug(
                    "Unable to parse wildcard artifact %s", file_path, exc_info=True
                )
                return {}
            return {
                "wildcard_format": os.path.splitext(file_path)[1].lower().lstrip("."),
                "files": parsed.files,
                "entries": [entry.summary() for entry in parsed.entries],
                "errors": parsed.errors,
                "unsupported_files": parsed.unsupported_files,
                "entry_count": len(parsed.entries),
                "value_count": parsed.value_count,
            }
        entries = payload.get("entries") or []
        return {
            "wildcard_format": payload.get("wildcard_format")
            or os.path.splitext(file_path)[1].lower().lstrip("."),
            "files": payload.get("files") or [],
            "entries": entries,
            "errors": payload.get("errors") or [],
            "unsupported_files": payload.get("unsupported_files") or [],
            "entry_count": payload.get("entry_count", len(entries)),
            "value_count": payload.get("value_count", 0),
        }

    async def _create_default_metadata(
        self,
        file_path: str,
        *,
        include_remote: bool = False,
        checkpoint_name_hint: str | None = None,
        precomputed_sha256: str | None = None,
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
            sha256 = precomputed_sha256 or await calculate_sha256(real_path)
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
