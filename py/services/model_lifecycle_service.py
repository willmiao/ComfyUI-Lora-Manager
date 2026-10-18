"""Service routines for model lifecycle mutations."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional, TYPE_CHECKING, cast

from ..services.service_registry import ServiceRegistry
from ..services.pending_delete_service import get_pending_delete_service
from ..utils.constants import PREVIEW_EXTENSIONS
from ..utils.metadata_manager import MetadataManager
from ..utils.sidecar_paths import get_metadata_path, get_preview_dir, get_sidecar_dir

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..services.model_update_service import ModelUpdateService


async def load_local_metadata(metadata_path: str) -> Dict[str, Any]:
    """Load a metadata sidecar JSON, returning an empty dict when missing.

    Thin equivalent of ``MetadataSyncService.load_local_metadata`` for callers
    (download manager, use cases) that do not hold a sync-service instance.
    """

    if not os.path.exists(metadata_path):
        return {}

    try:
        with open(metadata_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load metadata from %s: %s", metadata_path, exc)
        return {}

    return payload if isinstance(payload, dict) else {}


async def delete_model_artifacts(
    target_dir: str, file_name: str, main_extension: str | None = None
) -> List[str]:
    """Delete the primary model artefacts within ``target_dir``.

    Sidecars and previews are taken from the model's sidecar directory — the
    model's own directory in alongside mode, the centralized mirror otherwise.
    """

    main_extension = ".safetensors" if main_extension is None else main_extension
    main_file = f"{file_name}{main_extension}" if main_extension else file_name
    model_path = os.path.join(target_dir, main_file)
    sidecar_dir = get_sidecar_dir(model_path)
    patterns = [os.path.basename(get_metadata_path(model_path))]
    for ext in PREVIEW_EXTENSIONS:
        patterns.append(f"{file_name}{ext}")

    deleted: List[str] = []
    main_path = model_path.replace(os.sep, "/")

    if os.path.exists(main_path):
        os.remove(main_path)
        deleted.append(main_path)
    else:
        logger.warning("Model file not found: %s", main_file)

    for pattern in patterns:
        path = os.path.join(sidecar_dir, pattern)
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


class BulkRenameContext:
    """Per-session state threaded through ``rename_model`` calls of a bulk rename.

    Holds the lazily built recipe hash index so a bulk rename loop pays the
    O(recipes) index build at most once (on the first recipe-touching rename)
    instead of rescanning every recipe per renamed file. Also tracks whether
    any recipe was re-pointed so the session finalizes recipe maintenance only
    when needed.
    """

    def __init__(self, recipe_scanner: Any) -> None:
        self._recipe_scanner = recipe_scanner
        self._recipe_hash_index: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self.recipes_touched = False

    @property
    def recipe_scanner(self) -> Any:
        return self._recipe_scanner

    async def get_recipe_hash_index(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Return the lora-hash → recipes index, building it on first use."""
        if self._recipe_scanner is None:
            return None
        if self._recipe_hash_index is None:
            self._recipe_hash_index = (
                await self._recipe_scanner.build_lora_hash_index()
            )
        return self._recipe_hash_index


class ModelLifecycleService:
    """Co-ordinate destructive and mutating model operations."""

    def __init__(
        self,
        *,
        scanner,
        metadata_manager,
        metadata_loader: Callable[[str], Awaitable[Dict[str, object]]],
        recipe_scanner_factory: Callable[[], Awaitable[Any]] | None = None,
        update_service: Optional["ModelUpdateService"] = None,
    ) -> None:
        self._scanner = scanner
        self._metadata_manager = metadata_manager
        self._metadata_loader = metadata_loader
        self._recipe_scanner_factory = (
            recipe_scanner_factory or ServiceRegistry.get_recipe_scanner
        )
        self._update_service = update_service

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

        # Stage the delete into the pending-delete service when undo is
        # enabled; a successful stage renames the artifacts away, otherwise
        # fall back to the direct hard delete.
        pending_delete_service = await get_pending_delete_service()
        batch_id = await pending_delete_service.stage_model_delete(
            scanner=self._scanner,
            target_dir=target_dir,
            file_name=file_name,
            main_extension=main_extension,
            original_file_path=file_path,
            cached_entry=cached_entry,
        )
        deleted_files: List[str] = []
        if batch_id is None:
            deleted_files = await delete_model_artifacts(
                target_dir, file_name, main_extension=main_extension
            )

        if cache:
            cache.raw_data = [
                item for item in cache.raw_data if item.get("file_path") != file_path
            ]
            await cache.resort()
            bump_cache_version = getattr(self._scanner, "bump_cache_version", None)
            if callable(bump_cache_version):
                bump_cache_version()

        if hasattr(self._scanner, "_hash_index") and self._scanner._hash_index:
            self._scanner._hash_index.remove_by_path(file_path)

        await self._sync_update_for_model(model_id)

        persist_current_cache = getattr(self._scanner, "_persist_current_cache", None)
        if callable(persist_current_cache):
            await cast(Awaitable[Any], persist_current_cache())

        return {
            "success": True,
            "deleted_files": deleted_files,
            "batch_id": batch_id,
        }

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

        metadata_path = get_metadata_path(file_path)
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
            bump_cache_version = getattr(self._scanner, "bump_cache_version", None)
            if callable(bump_cache_version):
                bump_cache_version()

        excluded = getattr(self._scanner, "_excluded_models", None)
        if isinstance(excluded, list):
            if file_path not in excluded:
                excluded.append(file_path)

        persist_current_cache = getattr(self._scanner, "_persist_current_cache", None)
        if callable(persist_current_cache):
            await cast(Awaitable[Any], persist_current_cache())

        message = f"Model {os.path.basename(file_path)} excluded"
        return {"success": True, "message": message}

    async def unexclude_model(self, file_path: str) -> Dict[str, object]:
        """Restore a previously excluded model to the active cache."""

        if not file_path:
            raise ValueError("Model path is required")

        _require_path_in_library_roots(file_path, self._scanner, label="File path")

        if not os.path.exists(file_path):
            raise ValueError("Model file does not exist")

        metadata_path = get_metadata_path(file_path)
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

    @asynccontextmanager
    async def bulk_rename_session(self) -> AsyncIterator[BulkRenameContext]:
        """Context for bulk rename loops (filename-template "Apply to Library").

        While active, the per-file ``update_single_model_cache`` resort/persist
        chain and the per-file recipe folder-metadata refresh/resort are
        deferred; both run exactly once when the outermost session exits — see
        ``ModelScanner.defer_cache_persist`` and
        ``RecipeScanner.finalize_bulk_filename_updates``. The finalize steps run
        even on cancellation or mid-loop errors, because files are already
        renamed on disk and the caches must not be left diverging.

        Yields a :class:`BulkRenameContext` to pass as ``bulk_context`` into
        each ``rename_model`` call of the loop.
        """
        recipe_scanner = await self._recipe_scanner_factory()
        context = BulkRenameContext(recipe_scanner)
        async with self._scanner.defer_cache_persist():
            try:
                yield context
            finally:
                if recipe_scanner is not None and context.recipes_touched:
                    try:
                        await recipe_scanner.finalize_bulk_filename_updates()
                    except Exception as exc:  # pragma: no cover - defensive logging
                        logger.error(
                            "Error finalizing bulk recipe updates: %s", exc
                        )

    async def rename_model(
        self, *, file_path: str, new_file_name: str, bulk_context: Optional[BulkRenameContext] = None
    ) -> Dict[str, object]:
        """Rename a model and its companion artefacts.

        When ``bulk_context`` is given (bulk rename loop), the recipe
        re-pointing uses the session's prebuilt hash index and defers recipe
        maintenance to the session finalize; the scanner cache persist is
        likewise deferred by the surrounding ``bulk_rename_session``.
        """

        if not file_path or not new_file_name:
            raise ValueError("File path and new file name are required")

        _require_path_in_library_roots(file_path, self._scanner, label="File path")

        invalid_chars = {"/", "\\", ":", "*", "?", '"', "<", ">", "|"}
        if any(char in new_file_name for char in invalid_chars):
            raise ValueError("Invalid characters in file name")

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

        metadata_filename = os.path.basename(get_metadata_path(file_path))
        # Sidecars/previews live in the sidecar dir (the model's own dir in
        # alongside mode, the centralized mirror otherwise); the model file
        # itself always stays in target_dir.
        sidecar_dir = get_sidecar_dir(file_path)
        patterns: List[tuple[str, str]] = [
            (target_dir, f"{old_file_name}{old_extension}"),
            (sidecar_dir, metadata_filename),
            (sidecar_dir, f"{metadata_filename}.bak"),
        ]
        for ext in PREVIEW_EXTENSIONS:
            patterns.append((sidecar_dir, f"{old_file_name}{ext}"))

        existing_files: List[tuple[str, str]] = []
        for pattern_dir, pattern in patterns:
            path = os.path.join(pattern_dir, pattern)
            if os.path.exists(path):
                existing_files.append((path, pattern))

        metadata_path = get_metadata_path(file_path)
        metadata: Optional[Dict[str, object]] = None
        hash_value: Optional[str] = None

        if os.path.exists(metadata_path):
            metadata = await self._metadata_loader(metadata_path)
            raw_hash = metadata.get("sha256") if isinstance(metadata, dict) else None
            hash_value = raw_hash if isinstance(raw_hash, str) else None

        new_preview: Optional[str] = None

        renamed_files, new_metadata_path = await asyncio.to_thread(
            self._rename_companion_files, existing_files, new_file_name
        )

        if metadata and new_metadata_path:
            metadata["file_name"] = new_file_name
            metadata["file_path"] = new_file_path
            # Preserve the pre-rename stem so the original download filename
            # stays recoverable after template-driven renames.
            metadata.setdefault("original_file_name", old_file_name)

            if metadata.get("preview_url"):
                old_preview = str(metadata["preview_url"])
                ext = self._get_multipart_ext(old_preview)
                new_preview = os.path.join(
                    get_preview_dir(new_file_path), f"{new_file_name}{ext}"
                ).replace(os.sep, "/")
                metadata["preview_url"] = new_preview

            await self._metadata_manager.save_metadata(new_file_path, metadata)

        if metadata:
            await self._scanner.update_single_model_cache(
                file_path, new_file_path, metadata
            )

            if hash_value and getattr(self._scanner, "model_type", "") == "lora":
                if bulk_context is not None:
                    recipe_scanner = bulk_context.recipe_scanner
                    hash_index = await bulk_context.get_recipe_hash_index()
                    defer_maintenance = True
                else:
                    recipe_scanner = await self._recipe_scanner_factory()
                    hash_index = None
                    defer_maintenance = False
                if recipe_scanner:
                    try:
                        file_count, cache_count = (
                            await recipe_scanner.update_lora_filename_by_hash(
                                hash_value,
                                new_file_name,
                                hash_index=hash_index,
                                defer_maintenance=defer_maintenance,
                            )
                        )
                        if bulk_context is not None and (file_count or cache_count):
                            bulk_context.recipes_touched = True
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
            "reload_required": False,
        }

    def _rename_companion_files(
        self,
        existing_files: List[tuple[str, str]],
        new_file_name: str,
    ) -> tuple[List[str], Optional[str]]:
        """Rename all companion files, off the event loop thread.

        Runs the blocking ``os.rename`` sequence for one model in a worker
        thread so a single file's HDD I/O does not stall the event loop.
        Never parallelized across files: one model's renames stay sequential
        and the helper holds no locks.
        """
        renamed_files: List[str] = []
        new_metadata_path: Optional[str] = None

        for old_path, pattern in existing_files:
            ext = self._get_multipart_ext(pattern)
            new_path = os.path.join(
                os.path.dirname(old_path), f"{new_file_name}{ext}"
            ).replace(os.sep, "/")
            os.rename(old_path, new_path)
            renamed_files.append(new_path)

            if ext == ".metadata.json":
                new_metadata_path = new_path

        return renamed_files, new_metadata_path

    @staticmethod
    def _get_multipart_ext(filename: str) -> str:
        """Return the extension for files with compound suffixes."""

        known_suffixes = [
            ".metadata.json.bak",
            ".metadata.json",
            ".safetensors",
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
