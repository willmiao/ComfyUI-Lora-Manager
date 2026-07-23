"""Service routines for model lifecycle mutations."""

from __future__ import annotations

import asyncio
import logging
import json
import difflib
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional, TYPE_CHECKING

from ..services.service_registry import ServiceRegistry
from ..utils.constants import PREVIEW_EXTENSIONS
from ..utils.metadata_manager import MetadataManager

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..services.model_update_service import ModelUpdateService


async def delete_model_artifacts(
    target_dir: str, file_name: str, main_extension: str | None = None
) -> List[str]:
    """Delete the primary model artefacts within ``target_dir``."""

    main_extension = ".safetensors" if main_extension is None else main_extension
    main_file = f"{file_name}{main_extension}" if main_extension else file_name
    patterns = [main_file, f"{file_name}.metadata.json"]
    for ext in PREVIEW_EXTENSIONS:
        patterns.append(f"{file_name}{ext}")

    deleted: List[str] = []
    main_path = os.path.join(target_dir, main_file).replace(os.sep, "/")

    if os.path.exists(main_path):
        os.remove(main_path)
        deleted.append(main_path)
    else:
        logger.warning("Model file not found: %s", main_file)

    for pattern in patterns[1:]:
        path = os.path.join(target_dir, pattern)
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted.append(pattern)
            except Exception as exc:  # pragma: no cover - defensive path
                logger.warning("Failed to delete %s: %s", pattern, exc)

    return deleted


def _require_path_in_library_roots(file_path: str, scanner, *, label: str = "path") -> None:
    """Raise ``ValueError`` if *file_path* is not inside a configured model root.

    Uses ``os.path.abspath()`` (NOT ``realpath``) to resolve ``..`` and ``.``
    while preserving symlinks — this keeps the check in business-path space.
    Skips when the scanner does not expose ``get_model_roots`` or the list
    is empty.
    """

    roots = None
    if hasattr(scanner, "get_model_roots"):
        try:
            roots = scanner.get_model_roots()
        except NotImplementedError:
            roots = None
    if not roots:
        return

    resolved = os.path.abspath(os.path.normpath(file_path))

    for root in roots:
        root_resolved = os.path.abspath(os.path.normpath(root))
        if resolved == root_resolved or resolved.startswith(root_resolved + os.sep):
            return

    raise ValueError(
        f"{label} '{file_path}' is outside configured library directories"
    )


class ModelLifecycleService:
    """Co-ordinate destructive and mutating model operations."""

    def __init__(
        self,
        *,
        scanner,
        metadata_manager,
        metadata_loader: Callable[[str], Awaitable[Dict[str, object]]],
        recipe_scanner_factory: Callable[[], Awaitable] | None = None,
        update_service: "ModelUpdateService" | None = None,
    ) -> None:
        self._scanner = scanner
        self._metadata_manager = metadata_manager
        self._metadata_loader = metadata_loader
        self._recipe_scanner_factory = (
            recipe_scanner_factory or ServiceRegistry.get_recipe_scanner
        )
        self._update_service = update_service
        self._smart_rename_page_cache: Dict[tuple[int, int], List[Dict[str, object]]] = {}
        self._smart_rename_page_cache_times: Dict[tuple[int, int], float] = {}
        self._smart_rename_page_tasks: Dict[tuple[int, int], asyncio.Task] = {}
        self._smart_rename_identity_cache: Dict[str, Optional[tuple[int, int]]] = {}
        self._smart_rename_identity_cache_times: Dict[str, float] = {}

    async def delete_model(self, file_path: str) -> Dict[str, object]:
        """Delete a model file and associated artefacts."""

        if not file_path:
            raise ValueError("Model path is required")

        _require_path_in_library_roots(file_path, self._scanner, label="File path")

        cache = await self._scanner.get_cached_data()

        cached_entry = None
        if cache and hasattr(cache, "raw_data"):
            cached_entry = next(
                (item for item in cache.raw_data if item.get("file_path") == file_path),
                None,
            )

        metadata_payload = {}
        try:
            metadata_payload = await self._metadata_manager.load_metadata_payload(file_path)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("Failed to load metadata payload for %s: %s", file_path, exc)

        model_id = (
            self._extract_model_id_from_payload(metadata_payload)
            or self._extract_model_id_from_payload(cached_entry)
        )

        target_dir = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)
        file_name, main_extension = os.path.splitext(base_name)
        deleted_files = await delete_model_artifacts(
            target_dir, file_name, main_extension=main_extension
        )

        if cache:
            cache.raw_data = [
                item for item in cache.raw_data if item.get("file_path") != file_path
            ]
            await cache.resort()

        if hasattr(self._scanner, "_hash_index") and self._scanner._hash_index:
            self._scanner._hash_index.remove_by_path(file_path)

        await self._sync_update_for_model(model_id)

        persist_current_cache = getattr(self._scanner, "_persist_current_cache", None)
        if callable(persist_current_cache):
            await persist_current_cache()

        return {"success": True, "deleted_files": deleted_files}

    @staticmethod
    def _extract_model_id_from_payload(payload: Any) -> Optional[int]:
        if not isinstance(payload, Mapping):
            return None
        civitai = payload.get("civitai")
        if isinstance(civitai, Mapping):
            candidate = civitai.get("modelId") or civitai.get("model_id")
            if candidate is None:
                model_section = civitai.get("model")
                if isinstance(model_section, Mapping):
                    candidate = model_section.get("id")
            normalized = ModelLifecycleService._coerce_int(candidate)
            if normalized is not None:
                return normalized
        fallback = payload.get("model_id") or payload.get("civitai_model_id")
        return ModelLifecycleService._coerce_int(fallback)

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def _sync_update_for_model(self, model_id: Optional[int]) -> None:
        if self._update_service is None or model_id is None:
            return

        try:
            versions = await self._scanner.get_model_versions_by_id(model_id)
        except Exception as exc:  # pragma: no cover - defensive log
            logger.debug(
                "Failed to collect local versions for model %s: %s", model_id, exc
            )
            versions = []

        version_ids = set()
        for version in versions or []:
            candidate = (
                version.get("versionId")
                or version.get("id")
                or version.get("version_id")
            )
            normalized = ModelLifecycleService._coerce_int(candidate)
            if normalized is not None:
                version_ids.add(normalized)

        try:
            await self._update_service.update_in_library_versions(
                self._scanner.model_type,
                model_id,
                sorted(version_ids),
            )
        except Exception as exc:  # pragma: no cover - defensive log
            logger.debug(
                "Failed to sync update record for model %s: %s", model_id, exc
            )

    async def exclude_model(self, file_path: str) -> Dict[str, object]:
        """Mark a model as excluded and prune cache references."""

        if not file_path:
            raise ValueError("Model path is required")

        _require_path_in_library_roots(file_path, self._scanner, label="File path")

        metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
        metadata = await self._metadata_loader(metadata_path)
        metadata["exclude"] = True

        await self._metadata_manager.save_metadata(file_path, metadata)

        cache = await self._scanner.get_cached_data()
        model_to_remove = next(
            (item for item in cache.raw_data if item["file_path"] == file_path),
            None,
        )

        if model_to_remove:
            for tag in model_to_remove.get("tags", []):
                if tag in getattr(self._scanner, "_tags_count", {}):
                    self._scanner._tags_count[tag] = max(
                        0, self._scanner._tags_count[tag] - 1
                    )
                    if self._scanner._tags_count[tag] == 0:
                        del self._scanner._tags_count[tag]

            if hasattr(self._scanner, "_hash_index") and self._scanner._hash_index:
                self._scanner._hash_index.remove_by_path(file_path)

            cache.raw_data = [
                item for item in cache.raw_data if item["file_path"] != file_path
            ]
            await cache.resort()

        excluded = getattr(self._scanner, "_excluded_models", None)
        if isinstance(excluded, list):
            if file_path not in excluded:
                excluded.append(file_path)

        persist_current_cache = getattr(self._scanner, "_persist_current_cache", None)
        if callable(persist_current_cache):
            await persist_current_cache()

        message = f"Model {os.path.basename(file_path)} excluded"
        return {"success": True, "message": message}

    async def unexclude_model(self, file_path: str) -> Dict[str, object]:
        """Restore a previously excluded model to the active cache."""

        if not file_path:
            raise ValueError("Model path is required")

        _require_path_in_library_roots(file_path, self._scanner, label="File path")

        if not os.path.exists(file_path):
            raise ValueError("Model file does not exist")

        metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
        metadata_payload = await self._metadata_loader(metadata_path)
        metadata_payload["exclude"] = False

        await self._metadata_manager.save_metadata(file_path, metadata_payload)

        metadata, should_skip = await MetadataManager.load_metadata(
            file_path,
            self._scanner.model_class,
        )
        if should_skip:
            metadata = None
        if metadata is None:
            metadata = metadata_payload

        excluded = getattr(self._scanner, "_excluded_models", None)
        if isinstance(excluded, list):
            self._scanner._excluded_models = [
                path for path in excluded if path != file_path
            ]

        await self._scanner.update_single_model_cache(
            file_path,
            file_path,
            metadata,
            recalculate_type=True,
        )

        message = f"Model {os.path.basename(file_path)} restored"
        return {"success": True, "message": message}

    async def bulk_delete_models(self, file_paths: Iterable[str]) -> Dict[str, object]:
        """Delete a collection of models via the scanner bulk operation."""

        file_paths = list(file_paths)
        if not file_paths:
            raise ValueError("No file paths provided for deletion")

        for path in file_paths:
            _require_path_in_library_roots(path, self._scanner, label="File path")

        return await self._scanner.bulk_delete_models(file_paths)

    async def rename_model(
        self, *, file_path: str, new_file_name: str
    ) -> Dict[str, object]:
        """Rename a model and its companion artefacts."""

        if not file_path or not new_file_name:
            raise ValueError("File path and new file name are required")

        _require_path_in_library_roots(file_path, self._scanner, label="File path")

        invalid_chars = {"/", "\\", ":", "*", "?", '"', "<", ">", "|"}
        if any(char in new_file_name for char in invalid_chars):
            raise ValueError("Invalid characters in file name")

        cache = (
            await self._scanner.get_cached_data()
            if hasattr(self._scanner, "get_cached_data")
            else None
        )
        cached_entry = next(
            (
                dict(item)
                for item in getattr(cache, "raw_data", []) if cache is not None
                if item.get("file_path") == file_path
            ),
            None,
        )

        target_dir = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)
        old_file_name, old_extension = os.path.splitext(base_name)
        if not old_extension:
            old_extension = ".safetensors"
        new_file_path = os.path.join(
            target_dir, f"{new_file_name}{old_extension}"
        ).replace(os.sep, "/")

        if os.path.exists(new_file_path):
            raise ValueError("A file with this name already exists")

        patterns = [
            f"{old_file_name}{old_extension}",
            f"{old_file_name}.metadata.json",
            f"{old_file_name}.metadata.json.bak",
            f"{old_file_name}.civitai.info",
            f"{old_file_name}.info",
            f"{old_file_name}.txt",
            f"{old_file_name}.yaml",
        ]
        for ext in PREVIEW_EXTENSIONS:
            patterns.append(f"{old_file_name}{ext}")

        existing_files: List[tuple[str, str]] = []
        for pattern in patterns:
            path = os.path.join(target_dir, pattern)
            if os.path.exists(path):
                existing_files.append((path, pattern))

        metadata_path = os.path.join(target_dir, f"{old_file_name}.metadata.json")
        metadata: Optional[Dict[str, object]] = None
        hash_value: Optional[str] = None

        if os.path.exists(metadata_path):
            metadata = await self._metadata_loader(metadata_path)
            hash_value = metadata.get("sha256") if isinstance(metadata, dict) else None

        rename_pairs: List[tuple[str, str]] = []
        orphan_metadata: Optional[Dict[str, object]] = None
        orphan_source_metadata_path: Optional[str] = None
        for old_path, pattern in existing_files:
            ext = self._get_multipart_ext(pattern)
            new_path = os.path.join(target_dir, f"{new_file_name}{ext}").replace(
                os.sep, "/"
            )
            if old_path != new_path and os.path.exists(new_path):
                if ext == ".metadata.json":
                    try:
                        target_metadata = await self._metadata_loader(new_path)
                    except Exception:
                        target_metadata = None
                    source_metadata = metadata or cached_entry or {}
                    if self._is_matching_orphan_metadata(
                        target_metadata,
                        source_metadata,
                        expected_target_path=new_file_path,
                    ):
                        orphan_metadata = dict(target_metadata or {})
                        orphan_source_metadata_path = old_path
                        continue
                raise ValueError(f"Associated target already exists: {new_path}")
            rename_pairs.append((old_path, new_path))

        renamed_pairs: List[tuple[str, str]] = []
        renamed_files: List[str] = []
        new_metadata_path: Optional[str] = None
        new_preview: Optional[str] = None

        try:
            for old_path, new_path in rename_pairs:
                if old_path == new_path:
                    continue
                os.rename(old_path, new_path)
                renamed_pairs.append((old_path, new_path))
                renamed_files.append(new_path)

                if new_path.endswith(".metadata.json"):
                    new_metadata_path = new_path
        except Exception:
            for old_path, new_path in reversed(renamed_pairs):
                try:
                    if os.path.exists(new_path) and not os.path.exists(old_path):
                        os.rename(new_path, old_path)
                except Exception as rollback_error:  # pragma: no cover - defensive path
                    logger.error(
                        "Failed to roll back rename %s -> %s: %s",
                        new_path,
                        old_path,
                        rollback_error,
                    )
            raise

        metadata = metadata or cached_entry
        if metadata and orphan_metadata is not None:
            metadata = self._merge_metadata_payloads(orphan_metadata, metadata)
        if metadata:
            metadata["file_name"] = new_file_name
            metadata["file_path"] = new_file_path

            if metadata.get("preview_url"):
                old_preview = str(metadata["preview_url"])
                ext = self._get_multipart_ext(old_preview)
                new_preview = os.path.join(target_dir, f"{new_file_name}{ext}").replace(
                    os.sep, "/"
                )
                metadata["preview_url"] = new_preview

            await self._metadata_manager.save_metadata(new_file_path, metadata)
            if (
                orphan_source_metadata_path
                and os.path.exists(orphan_source_metadata_path)
            ):
                os.remove(orphan_source_metadata_path)
                renamed_files.append(
                    os.path.splitext(new_file_path)[0] + ".metadata.json"
                )

        if metadata:
            await self._scanner.update_single_model_cache(
                file_path, new_file_path, metadata
            )

            if hash_value and getattr(self._scanner, "model_type", "") == "lora":
                recipe_scanner = await self._recipe_scanner_factory()
                if recipe_scanner:
                    try:
                        await recipe_scanner.update_lora_filename_by_hash(
                            hash_value, new_file_name
                        )
                    except Exception as exc:  # pragma: no cover - defensive logging
                        logger.error(
                            "Error updating recipe references for %s: %s",
                            file_path,
                            exc,
                        )

        return {
            "success": True,
            "new_file_path": new_file_path,
            "new_preview_path": new_preview,
            "renamed_files": renamed_files,
            "rename_pairs": [
                {"old_path": old_path, "new_path": new_path}
                for old_path, new_path in renamed_pairs
            ],
            "reload_required": False,
        }

    @classmethod
    def _is_matching_orphan_metadata(
        cls,
        target: Any,
        source: Any,
        *,
        expected_target_path: str,
    ) -> bool:
        if not isinstance(target, Mapping) or not isinstance(source, Mapping):
            return False
        source_sha = str(source.get("sha256") or "").casefold()
        target_sha = str(target.get("sha256") or "").casefold()
        if source_sha and target_sha:
            return source_sha == target_sha
        if not source_sha or target_sha:
            return False

        try:
            same_size = int(source.get("size") or -1) == int(target.get("size") or -2)
        except (TypeError, ValueError):
            same_size = False
        target_path = str(target.get("file_path") or "").replace(os.sep, "/")
        expected_path = expected_target_path.replace(os.sep, "/")
        expected_name = os.path.splitext(os.path.basename(expected_path))[0]
        target_name = str(target.get("file_name") or "")
        return (
            same_size
            and target_path.casefold() == expected_path.casefold()
            and cls._comparison_key(target_name) == cls._comparison_key(expected_name)
        )

    @staticmethod
    def _merge_metadata_payloads(
        orphan: Mapping[str, object], source: Mapping[str, object]
    ) -> Dict[str, object]:
        merged = dict(orphan)
        merged.update(source)
        for key in (
            "notes",
            "tags",
            "favorite",
            "exclude",
            "sub_type",
            "usage_tips",
            "trainedWords",
        ):
            source_value = source.get(key)
            orphan_value = orphan.get(key)
            if source_value in (None, "", [], {}) and orphan_value not in (
                None,
                "",
                [],
                {},
            ):
                merged[key] = orphan_value
        return merged

    async def preview_smart_renames(
        self,
        file_paths: Optional[Iterable[str]] = None,
        progress_callback: Optional[
            Callable[[Dict[str, object]], Awaitable[None]]
        ] = None,
    ) -> Dict[str, object]:
        """Build a collision-safe smart rename plan without changing files."""

        cache = await self._scanner.get_cached_data()
        selected = set(file_paths or [])
        entries = [
            dict(item)
            for item in getattr(cache, "raw_data", [])
            if not selected or item.get("file_path") in selected
        ]

        if len(entries) > 1:
            total = len(entries)
            completed = 0
            semaphore = asyncio.Semaphore(3)

            if progress_callback is not None:
                await progress_callback(
                    {"status": "started", "completed": 0, "total": total}
                )

            async def warm_entry(entry: Dict[str, object]) -> None:
                nonlocal completed
                file_path = str(entry.get("file_path") or "")
                async with semaphore:
                    if file_path:
                        await self.preview_smart_renames([file_path])
                completed += 1
                if progress_callback is not None:
                    await progress_callback(
                        {
                            "status": "processing",
                            "completed": completed,
                            "total": total,
                            "current_name": str(entry.get("file_name") or ""),
                        }
                    )

            await asyncio.gather(*(warm_entry(entry) for entry in entries))

            if progress_callback is not None:
                await progress_callback(
                    {"status": "completed", "completed": total, "total": total}
                )

        candidates: List[Dict[str, object]] = []
        civitai_page_cache = self._smart_rename_page_cache
        for entry in entries:
            file_path = str(entry.get("file_path") or "")
            if not file_path or not os.path.isfile(file_path):
                candidates.append(
                    self._plan_item(entry, status="skipped", reason="file_missing")
                )
                continue

            payload = dict(entry)
            try:
                disk_payload = await self._metadata_manager.load_metadata_payload(file_path)
                if isinstance(disk_payload, Mapping):
                    cached_civitai = payload.get("civitai")
                    disk_civitai = disk_payload.get("civitai")
                    payload.update(disk_payload)
                    if isinstance(cached_civitai, Mapping):
                        merged_civitai = dict(cached_civitai)
                        if isinstance(disk_civitai, Mapping):
                            merged_civitai.update(disk_civitai)
                        payload["civitai"] = merged_civitai
            except Exception as exc:  # pragma: no cover - defensive path
                logger.debug("Failed to hydrate smart rename candidate %s: %s", file_path, exc)

            await self._use_current_civitai_filenames(payload, civitai_page_cache)

            smart_name = self._build_smart_name(payload)
            if not smart_name:
                candidates.append(
                    self._plan_item(
                        entry,
                        status="skipped",
                        reason="missing_unique_uploaded_filename",
                    )
                )
                continue

            old_stem, extension = os.path.splitext(os.path.basename(file_path))
            if smart_name.casefold() == old_stem.casefold():
                uploaded_names = self._matching_civitai_names(payload)
                unchanged_reason = (
                    "already_uploaded_name"
                    if len(uploaded_names) == 1
                    else "missing_unique_uploaded_filename"
                )
                candidates.append(
                    self._plan_item(
                        entry,
                        status="unchanged",
                        reason=unchanged_reason,
                        new_name=old_stem,
                        new_path=file_path,
                    )
                )
                continue

            new_path = os.path.join(os.path.dirname(file_path), smart_name + extension).replace(
                os.sep, "/"
            )
            candidates.append(
                self._plan_item(
                    entry,
                    status="ready",
                    reason="civitai_uploaded_filename",
                    new_name=smart_name,
                    new_path=new_path,
                    payload=payload,
                )
            )

        ready = [item for item in candidates if item["status"] == "ready"]
        grouped: Dict[str, List[Dict[str, object]]] = {}
        for item in ready:
            grouped.setdefault(str(item["new_path"]).casefold(), []).append(item)

        occupied_sources = {
            str(item.get("old_path") or "").casefold() for item in candidates
        }
        reserved_targets: set[str] = set()
        for group in grouped.values():
            if len(group) > 1:
                for item in group:
                    item["status"] = "unchanged"
                    item["reason"] = "duplicate_uploaded_filename"
                    item["new_name"] = item["old_name"]
                    item["new_path"] = item["old_path"]
                continue
            for item in group:
                target = str(item["new_path"])
                target_key = target.casefold()
                if target_key in reserved_targets or (
                    os.path.exists(target)
                    and target.casefold() != str(item["old_path"]).casefold()
                    and target.casefold() not in occupied_sources
                ):
                    item["status"] = "conflict"
                    item["reason"] = "target_exists"
                else:
                    reserved_targets.add(target_key)

        for item in candidates:
            item.pop("payload", None)

        counts: Dict[str, int] = {}
        for item in candidates:
            status = str(item["status"])
            counts[status] = counts.get(status, 0) + 1
        return {"success": True, "items": candidates, "counts": counts}

    async def apply_smart_renames(
        self, file_paths: Optional[Iterable[str]] = None
    ) -> Dict[str, object]:
        """Apply a freshly generated smart rename plan and write an undo journal."""

        plan = await self.preview_smart_renames(file_paths)
        ready = [item for item in plan["items"] if item["status"] == "ready"]
        renamed: List[Dict[str, object]] = []
        failed: List[Dict[str, str]] = []

        for item in ready:
            old_path = str(item["old_path"])
            try:
                result = await self.rename_model(
                    file_path=old_path,
                    new_file_name=str(item["new_name"]),
                )
                renamed.append(
                    {
                        "model_type": getattr(self._scanner, "model_type", "model"),
                        "old_path": old_path,
                        "new_path": result["new_file_path"],
                        "sha256": item.get("sha256", ""),
                    }
                )
            except Exception as exc:
                logger.error("Smart rename failed for %s: %s", old_path, exc)
                failed.append({"old_path": old_path, "error": str(exc)})

        history_id = self._write_rename_history(renamed, failed) if renamed else None
        return {
            "success": not failed,
            "renamed": renamed,
            "renamed_count": len(renamed),
            "failed": failed,
            "failed_count": len(failed),
            "skipped_count": len(plan["items"]) - len(ready),
            "history_id": history_id,
            "plan_counts": plan["counts"],
        }

    async def undo_smart_renames(self, history_id: str) -> Dict[str, object]:
        """Undo one smart rename operation in reverse order."""

        if not history_id or os.path.basename(history_id) != history_id:
            raise ValueError("Invalid smart rename history id")
        history_path = os.path.join(self._smart_rename_history_dir(), history_id)
        if not os.path.isfile(history_path):
            raise ValueError("Smart rename history was not found")
        with open(history_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        restored: List[Dict[str, str]] = []
        failed: List[Dict[str, str]] = []
        for item in reversed(payload.get("renamed", [])):
            current_path = str(item.get("new_path") or "")
            old_path = str(item.get("old_path") or "")
            if not current_path or not old_path:
                continue
            try:
                if os.path.exists(old_path):
                    raise ValueError("Original path is already occupied")
                result = await self.rename_model(
                    file_path=current_path,
                    new_file_name=os.path.splitext(os.path.basename(old_path))[0],
                )
                restored.append(
                    {"old_path": current_path, "new_path": str(result["new_file_path"])}
                )
            except Exception as exc:
                failed.append({"old_path": current_path, "error": str(exc)})

        return {
            "success": not failed,
            "restored": restored,
            "restored_count": len(restored),
            "failed": failed,
            "failed_count": len(failed),
        }

    @classmethod
    def _build_smart_name(cls, payload: Mapping[str, object]) -> Optional[str]:
        file_path = str(payload.get("file_path") or "")
        current_name = os.path.splitext(os.path.basename(file_path))[0]
        uploaded_names = cls._matching_civitai_names(payload)
        if len(uploaded_names) > 1:
            selected_name = cls._select_ambiguous_uploaded_name(
                current_name, uploaded_names
            )
            if selected_name is None:
                return current_name or None
            uploaded_names = [selected_name]
        if len(uploaded_names) != 1:
            return current_name or None

        uploaded_name = os.path.splitext(os.path.basename(uploaded_names[0]))[0]
        uploaded_name = cls._truncate_name(uploaded_name, max_length=180)
        if not uploaded_name or cls._is_generic_uploaded_name(uploaded_name):
            return current_name or None
        return uploaded_name

    async def _use_current_civitai_filenames(
        self,
        payload: Dict[str, object],
        page_cache: Dict[tuple[int, int], List[Dict[str, object]]],
    ) -> None:
        """Replace stale REST filenames with the names shown by Civitai now."""

        civitai = payload.get("civitai")
        civitai = civitai if isinstance(civitai, Mapping) else {}
        try:
            model_id = int(civitai.get("modelId"))
            version_id = int(civitai.get("id"))
        except (TypeError, ValueError):
            sha256 = str(payload.get("sha256") or "").casefold()
            now = time.monotonic()
            identity_cached_at = self._smart_rename_identity_cache_times.get(sha256, 0.0)
            cached_identity = self._smart_rename_identity_cache.get(sha256)
            identity_ttl = 900 if cached_identity is not None else 60
            if sha256 in self._smart_rename_identity_cache and now - identity_cached_at < identity_ttl:
                identity = self._smart_rename_identity_cache[sha256]
            else:
                identity = await self._fetch_civitai_identity_by_sha(sha256)
                self._smart_rename_identity_cache[sha256] = identity
                self._smart_rename_identity_cache_times[sha256] = now
            if identity is None:
                return
            model_id, version_id = identity

        key = (model_id, version_id)
        now = time.monotonic()
        cached_at = self._smart_rename_page_cache_times.get(key, 0.0)
        page_ttl = 900 if page_cache.get(key) else 60
        if key not in page_cache or now - cached_at >= page_ttl:
            task = self._smart_rename_page_tasks.get(key)
            if task is None:
                task = asyncio.create_task(
                    self._fetch_current_civitai_files(model_id, version_id)
                )
                self._smart_rename_page_tasks[key] = task
            try:
                page_cache[key] = await task
                self._smart_rename_page_cache_times[key] = time.monotonic()
            finally:
                if self._smart_rename_page_tasks.get(key) is task:
                    self._smart_rename_page_tasks.pop(key, None)

        # Never fall back to a stale REST filename when the current page is unavailable.
        current_civitai = dict(civitai)
        current_civitai.update({"id": version_id, "modelId": model_id})
        current_civitai["files"] = page_cache[key]
        payload["civitai"] = current_civitai

    @classmethod
    async def _fetch_current_civitai_files(
        cls, model_id: int, version_id: int
    ) -> List[Dict[str, object]]:
        url = (
            f"https://civitai.red/models/{model_id}"
            f"?modelVersionId={version_id}"
        )
        try:
            process = await asyncio.create_subprocess_exec(
                "/usr/bin/curl",
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--connect-timeout",
                "5",
                "--max-time",
                "15",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=18)
            if process.returncode != 0:
                logger.warning(
                    "Civitai filename page request failed for version %s: %s",
                    version_id,
                    _stderr.decode("utf-8", errors="replace").strip(),
                )
                return []
            return cls._parse_current_civitai_files(
                stdout.decode("utf-8", errors="replace"), version_id
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return []
        except Exception as exc:  # pragma: no cover - network guard
            logger.debug(
                "Failed to fetch current Civitai filenames for %s: %s",
                version_id,
                exc,
            )
            return []

    @staticmethod
    async def _fetch_civitai_identity_by_sha(
        sha256: str,
    ) -> Optional[tuple[int, int]]:
        if not re.fullmatch(r"[0-9A-Fa-f]{64}", sha256 or ""):
            return None
        url = f"https://civitai.red/api/v1/model-versions/by-hash/{sha256}"
        try:
            process = await asyncio.create_subprocess_exec(
                "/usr/bin/curl",
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--connect-timeout",
                "5",
                "--max-time",
                "15",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=18)
            if process.returncode != 0:
                return None
            response = json.loads(stdout.decode("utf-8", errors="replace"))
            if not isinstance(response, Mapping):
                return None
            return int(response["modelId"]), int(response["id"])
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return None
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        except Exception as exc:  # pragma: no cover - network guard
            logger.debug("Failed to resolve Civitai identity for SHA %s: %s", sha256, exc)
            return None

    @staticmethod
    def _parse_current_civitai_files(
        page_html: str, version_id: int
    ) -> List[Dict[str, object]]:
        """Extract Civitai's current SSR file names and SHA256 values."""

        sha_pattern = re.compile(
            r'"type":"SHA256","hash":"([0-9A-Fa-f]{64})"'
        )
        name_pattern = re.compile(r'"name":"((?:\\.|[^"\\])*)"')
        version_pattern = re.compile(r'"modelVersionId":(\d+)')
        matches: Dict[str, str] = {}
        for sha_match in sha_pattern.finditer(page_html or ""):
            object_start = page_html.rfind(
                '{"id":', max(0, sha_match.start() - 6000), sha_match.start()
            )
            if object_start < 0:
                continue
            fragment = page_html[object_start:sha_match.end()]
            version_matches = list(version_pattern.finditer(fragment))
            if not version_matches or int(version_matches[-1].group(1)) != version_id:
                continue
            name_matches = list(name_pattern.finditer(fragment))
            if not name_matches:
                continue
            try:
                name = json.loads(f'"{name_matches[-1].group(1)}"')
            except json.JSONDecodeError:
                continue
            if name:
                matches[sha_match.group(1).casefold()] = name
        return [
            {"name": name, "hashes": {"SHA256": sha256}}
            for sha256, name in matches.items()
        ]

    @classmethod
    def _select_ambiguous_uploaded_name(
        cls, current_name: str, uploaded_names: Iterable[str]
    ) -> Optional[str]:
        """Select an alias only when keyword evidence produces a clear winner."""

        current_tokens = cls._filename_keywords(current_name)
        current_technical = {
            cls._comparison_key(token) for token in cls._technical_tokens(current_name)
        }
        scored: List[tuple[float, str, bool, int]] = []
        contradiction_count = 0
        contradictory_semantic_match = False
        for uploaded_name in uploaded_names:
            candidate = os.path.splitext(os.path.basename(uploaded_name))[0]
            candidate_tokens = cls._filename_keywords(candidate)
            candidate_technical = {
                cls._comparison_key(token) for token in cls._technical_tokens(candidate)
            }
            overlap = current_tokens & candidate_tokens
            technical_keywords = current_technical | candidate_technical
            semantic_overlap = {
                token
                for token in overlap
                if cls._comparison_key(token) not in technical_keywords
            }
            if cls._has_technical_contradiction(
                current_technical, candidate_technical
            ):
                contradiction_count += 1
                contradictory_semantic_match = (
                    contradictory_semantic_match or bool(semantic_overlap)
                )
                continue
            candidate_coverage = len(overlap) / max(1, len(candidate_tokens))
            current_coverage = len(overlap) / max(1, len(current_tokens))
            technical_overlap = len(current_technical & candidate_technical)
            similarity = difflib.SequenceMatcher(
                None,
                cls._comparison_key(current_name),
                cls._comparison_key(candidate),
            ).ratio()
            score = (
                candidate_coverage * 45
                + current_coverage * 20
                + similarity * 25
                + technical_overlap * 18
            )
            scored.append(
                (score, uploaded_name, bool(semantic_overlap), technical_overlap)
            )

        if not scored:
            return None
        scored.sort(key=lambda item: (-item[0], item[1].casefold()))
        best_score, best_name, has_semantic_overlap, technical_overlap = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        if not has_semantic_overlap:
            if (
                len(scored) != 1
                or contradiction_count == 0
                or contradictory_semantic_match
                or technical_overlap == 0
            ):
                return None
        if best_score < 38 or best_score - runner_up < 8:
            return None
        return best_name

    @classmethod
    def _filename_keywords(cls, value: str) -> set[str]:
        value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value or "")
        value = unicodedata.normalize("NFKC", value).casefold()
        tokens = set(re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", value))
        return {
            token
            for token in tokens
            if len(token) >= 2
            and token not in {
                "adapter", "checkpoint", "lora", "model", "safetensors", "gguf"
            }
        }

    @staticmethod
    def _has_technical_contradiction(
        current_tokens: set[str], candidate_tokens: set[str]
    ) -> bool:
        exclusive_groups = (
            {"i2v", "t2v", "ti2v", "v2v"},
            {"high", "highnoise", "low", "lownoise"},
            {"fp8", "fp16", "fp32", "bf16", "nf4", "int4", "int8"},
        )
        for group in exclusive_groups:
            current_values = current_tokens & group
            candidate_values = candidate_tokens & group
            if current_values and candidate_values and current_values.isdisjoint(candidate_values):
                return True

        for prefix in ("q", "rank", "r"):
            current_values = {token for token in current_tokens if token.startswith(prefix)}
            candidate_values = {token for token in candidate_tokens if token.startswith(prefix)}
            if current_values and candidate_values and current_values.isdisjoint(candidate_values):
                return True
        return False

    @classmethod
    def _matching_civitai_names(cls, payload: Mapping[str, object]) -> List[str]:
        civitai = payload.get("civitai")
        civitai = civitai if isinstance(civitai, Mapping) else {}
        files = civitai.get("files")
        files = files if isinstance(files, list) else []
        sha256 = str(payload.get("sha256") or "").casefold()
        matches: set[str] = set()
        for file_info in files:
            if not isinstance(file_info, Mapping):
                continue
            hashes = file_info.get("hashes")
            hashes = hashes if isinstance(hashes, Mapping) else {}
            if sha256 and str(hashes.get("SHA256") or "").casefold() == sha256:
                name = str(file_info.get("name") or "").strip()
                if name:
                    matches.add(name)
        return sorted(matches, key=str.casefold)

    @classmethod
    def _is_generic_uploaded_name(cls, value: str) -> bool:
        key = cls._comparison_key(value)
        return key in {
            "adaptermodel",
            "checkpoint",
            "diffusionpytorchmodel",
            "lora",
            "model",
            "pytorchloraweights",
            "textencoder",
            "unet",
        }

    @classmethod
    def _short_display_component(cls, value: str) -> str:
        value = re.sub(r"(?i)\.(?:safetensors?|ckpt|pt|pth|gguf)\b", " ", value or "")
        value = "".join(
            char
            for char in value
            if unicodedata.category(char) not in {"So", "Sk"}
            and unicodedata.category(char) != "Cn"
            and char not in {"\ufe0e", "\ufe0f"}
        )
        value = re.split(
            r"(?i)\s+(?:LoRA\s+)?for\s+(?=(?:RedCraft|Wan|SD|Flux|Pony|Illustrious|XL|ZIT|ZIB)\b)",
            value,
            maxsplit=1,
        )[0]
        architecture_pattern = re.compile(
            r"(?i)\b(?:SD(?:XL|1\.5)?|Pony|Illustrious|NoobAI|Flux|F1D|ZIT|ZIB|XL)\b"
        )
        for bracketed in list(re.finditer(r"[\[(]([^\])]+)[\])]", value)):
            if len(architecture_pattern.findall(bracketed.group(1))) >= 2:
                value = value.replace(bracketed.group(0), " ")
        plus_index = value.find(" + ")
        if plus_index >= 0 and len(architecture_pattern.findall(value[plus_index:])) >= 2:
            value = value[:plus_index]
        value = cls._sanitize_filename(value)
        if len(value) > 72:
            shortened = value[:72]
            boundary = max(shortened.rfind(" "), shortened.rfind("_"), shortened.rfind("|"))
            value = shortened[:boundary] if boundary >= 42 else shortened
        return value.rstrip(" ._|_-")

    @classmethod
    def _matching_civitai_file(
        cls, payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        civitai = payload.get("civitai")
        civitai = civitai if isinstance(civitai, Mapping) else {}
        files = civitai.get("files")
        files = files if isinstance(files, list) else []
        sha256 = str(payload.get("sha256") or "").casefold()
        for file_info in files:
            if not isinstance(file_info, Mapping):
                continue
            hashes = file_info.get("hashes")
            hashes = hashes if isinstance(hashes, Mapping) else {}
            if sha256 and str(hashes.get("SHA256") or "").casefold() == sha256:
                return file_info
        return {}

    @staticmethod
    def _technical_tokens(value: str) -> List[str]:
        patterns = (
            r"(?i)(?<![0-9A-Z])Q[2-8](?:_[0-9A-Z]+)?(?![0-9A-Z])",
            r"(?i)(?<![0-9A-Z])(?:FP8|FP16|FP32|BF16|NF4|INT4|INT8|E4M3FN|E5M2|SCALED)(?![0-9A-Z])",
            r"(?i)(?<![0-9A-Z])(?:RANK|R)[-_ ]?\d{1,4}(?![0-9A-Z])",
            r"(?i)(?<![0-9A-Z])\d{1,3}[-_ ]?STEPS?(?![0-9A-Z])",
            r"(?i)(?<![0-9A-Z])(?:I2V|T2V|TI2V|V2V|A?\d{1,3}B|\d{3,4}P)(?![0-9A-Z])",
            r"(?i)(?<![0-9A-Z])(?:HIGH|LOW)(?:[-_ ]?NOISE)?(?![0-9A-Z])",
        )
        found: List[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, value or ""):
                token = re.sub(r"\s+", "", match.group(0))
                if token.casefold() not in {item.casefold() for item in found}:
                    found.append(token)
        return found

    @classmethod
    def _prefer_existing_name(cls, current: str, proposed: str) -> bool:
        current = cls._sanitize_filename(current)
        if not current:
            return False
        current_tokens = cls._technical_tokens(current)
        wordish_parts = [part for part in re.split(r"[\s_.-]+", current) if len(part) >= 3]
        descriptive = len(wordish_parts) >= 3 or bool(current_tokens)
        if current_tokens and len(proposed) >= len(current) + 16:
            return True
        return descriptive and len(proposed) > max(len(current) * 1.5, len(current) + 30)

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        value = unicodedata.normalize("NFKC", value or "")
        value = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
        value = re.sub(r"[\\/:*?\"<>|]+", " ", value)
        value = re.sub(r"\s+", " ", value).strip(" ._")
        if value.upper() in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            value = f"_{value}"
        return value

    @staticmethod
    def _comparison_key(value: str) -> str:
        return re.sub(r"[^0-9a-z]+", "", value.casefold())

    @classmethod
    def _truncate_name(cls, value: str, *, max_length: int) -> str:
        value = cls._sanitize_filename(value)
        if len(value) <= max_length:
            return value
        return value[:max_length].rstrip(" ._")

    @classmethod
    def _variant_suffix(cls, payload: Mapping[str, object], sha256: str) -> str:
        civitai = payload.get("civitai")
        civitai = civitai if isinstance(civitai, Mapping) else {}
        files = civitai.get("files")
        files = files if isinstance(files, list) else []
        matched: Mapping[str, object] = {}
        for file_info in files:
            if not isinstance(file_info, Mapping):
                continue
            hashes = file_info.get("hashes")
            hashes = hashes if isinstance(hashes, Mapping) else {}
            if str(hashes.get("SHA256") or "").casefold() == sha256.casefold():
                matched = file_info
                break

        metadata = matched.get("metadata") if isinstance(matched, Mapping) else {}
        metadata = metadata if isinstance(metadata, Mapping) else {}
        tokens = []
        for key in ("fp", "size", "format"):
            value = cls._sanitize_filename(str(metadata.get(key) or ""))
            if value and value.casefold() not in {token.casefold() for token in tokens}:
                tokens.append(value)
        if sha256:
            tokens.append(sha256[:8].lower())
        return "-".join(tokens) or "variant"

    @staticmethod
    def _plan_item(
        entry: Mapping[str, object],
        *,
        status: str,
        reason: str,
        new_name: Optional[str] = None,
        new_path: Optional[str] = None,
        payload: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
        old_path = str(entry.get("file_path") or "")
        old_name = os.path.splitext(os.path.basename(old_path))[0]
        return {
            "old_path": old_path,
            "old_name": old_name,
            "new_path": new_path or old_path,
            "new_name": new_name or old_name,
            "sha256": str(entry.get("sha256") or ""),
            "status": status,
            "reason": reason,
            "payload": payload,
        }

    @staticmethod
    def _smart_rename_history_dir() -> str:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        history_dir = os.path.join(project_root, "cache", "smart_rename_history")
        os.makedirs(history_dir, exist_ok=True)
        return history_dir

    def _write_rename_history(
        self,
        renamed: List[Dict[str, object]],
        failed: List[Dict[str, str]],
    ) -> str:
        timestamp = datetime.now(timezone.utc)
        history_id = timestamp.strftime("%Y%m%dT%H%M%S.%fZ") + ".json"
        history_path = os.path.join(self._smart_rename_history_dir(), history_id)
        payload = {
            "created_at": timestamp.isoformat(),
            "model_type": getattr(self._scanner, "model_type", "model"),
            "renamed": renamed,
            "failed": failed,
        }
        temp_path = history_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, history_path)
        return history_id

    @staticmethod
    def _get_multipart_ext(filename: str) -> str:
        """Return the extension for files with compound suffixes."""

        known_suffixes = [
            ".metadata.json.bak",
            ".metadata.json",
            ".civitai.info",
            ".info",
            ".safetensors",
            ".txt",
            ".yaml",
            *PREVIEW_EXTENSIONS,
        ]

        for suffix in sorted(known_suffixes, key=len, reverse=True):
            if filename.endswith(suffix):
                return suffix

        basename = os.path.basename(filename)
        dot_index = basename.rfind(".")
        if dot_index != -1:
            return basename[dot_index:]

        return os.path.splitext(basename)[1]
