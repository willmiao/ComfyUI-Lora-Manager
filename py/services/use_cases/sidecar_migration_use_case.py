"""Use case migrating sidecar metadata and previews between storage layouts.

Two storage layouts exist (see :mod:`py.utils.sidecar_paths`):

- ``alongside``: ``<model_dir>/<name>.metadata.json`` and preview files live
  next to the model file.
- ``centralized``: the same files live under the configured sidecar root,
  mirroring the library-relative directory structure.

This use case moves the ``.metadata.json`` sidecar and preview files for every
known model from one layout to the other. Model files themselves NEVER move.
Paths inside the moved sidecar (``file_path``, ``file_name``, ``preview_url``)
are rewritten the same way :meth:`ModelScanner._update_metadata_paths` does.

Intended flow (settings-first):

1. The user switches ``sidecar_storage_mode`` (and optionally
   ``sidecar_storage_path``) in settings.
2. The migration runs in the direction of the NEW mode with ``force=True``.
   After the switch, files in the OLD layout are the source of truth; the
   guard below would otherwise refuse to run because the active mode already
   matches the migration target.

Both orderings work because all path computations are mode-independent: the
alongside location is derived from the model path directly, and the mirror
location is resolved via ``get_configured_sidecar_root()``, which ignores the
active mode.

Guards (pass ``force=True`` to bypass):

- ``migrate_to_centralized`` refuses when centralized storage is already the
  active, resolvable mode.
- ``migrate_to_alongside`` refuses when the active mode is ``alongside``.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from ..service_registry import ServiceRegistry
from ..settings_manager import get_settings_manager
from ...utils.constants import PREVIEW_EXTENSIONS
from ...utils.file_utils import get_preview_extension
from ...utils.metadata_manager import MetadataManager
from ...utils.sidecar_paths import (
    METADATA_SUFFIX,
    STORAGE_MODE_CENTRALIZED,
    get_configured_sidecar_root,
    get_sidecar_root,
    get_storage_mode,
    resolve_centralized_dir_for_dir,
)


class SidecarMigrationProgressReporter(Protocol):
    """Protocol for progress reporters used during sidecar migration."""

    async def on_progress(self, payload: Dict[str, Any]) -> None:
        """Handle a sidecar migration progress update."""


ScannerFactory = Callable[[], Awaitable[Any]]

DIRECTION_TO_CENTRALIZED = "to_centralized"
DIRECTION_TO_ALONGSIDE = "to_alongside"


class SidecarMigrationUseCase:
    """Move sidecars and previews between alongside and centralized layouts."""

    def __init__(
        self,
        *,
        scanner_factories: Sequence[Tuple[str, ScannerFactory]] | None = None,
        settings_service=None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._settings = settings_service or get_settings_manager()
        self._scanner_factories: Tuple[Tuple[str, ScannerFactory], ...] = tuple(
            scanner_factories
            or (
                ("lora", ServiceRegistry.get_lora_scanner),
                ("checkpoint", ServiceRegistry.get_checkpoint_scanner),
                ("embedding", ServiceRegistry.get_embedding_scanner),
                ("other", ServiceRegistry.get_other_scanner),
            )
        )
        self._logger = logger or logging.getLogger(__name__)

    async def migrate_to_centralized(
        self,
        progress_cb: Optional[SidecarMigrationProgressReporter] = None,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Move sidecars/previews from alongside the models into the mirror root."""

        if (
            not force
            and get_storage_mode() == STORAGE_MODE_CENTRALIZED
            and get_sidecar_root()
        ):
            return self._refusal(
                DIRECTION_TO_CENTRALIZED,
                "sidecar storage is already centralized; pass force=true to migrate anyway",
            )
        return await self._migrate(
            direction=DIRECTION_TO_CENTRALIZED,
            to_centralized=True,
            progress_cb=progress_cb,
        )

    async def migrate_to_alongside(
        self,
        progress_cb: Optional[SidecarMigrationProgressReporter] = None,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Move sidecars/previews from the mirror root back next to the models."""

        if not force and get_storage_mode() != STORAGE_MODE_CENTRALIZED:
            return self._refusal(
                DIRECTION_TO_ALONGSIDE,
                "sidecar storage is already alongside; pass force=true to migrate anyway",
            )
        return await self._migrate(
            direction=DIRECTION_TO_ALONGSIDE,
            to_centralized=False,
            progress_cb=progress_cb,
        )

    @staticmethod
    def _refusal(direction: str, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "error": message,
            "direction": direction,
            "models_total": 0,
            "models_processed": 0,
            "models_moved": 0,
            "moved": 0,
            "skipped": 0,
            "conflicts": 0,
            "errors": [],
            "error_count": 0,
        }

    def _active_scanner_factories(self) -> Tuple[Tuple[str, ScannerFactory], ...]:
        """Drop the opt-in other scanner while Other Models is disabled."""

        if self._settings.is_other_models_enabled():
            return self._scanner_factories
        return tuple(entry for entry in self._scanner_factories if entry[0] != "other")

    async def _collect_model_paths(self, errors: List[Dict[str, str]]) -> List[str]:
        """Enumerate model file paths across every active scanner's cache."""

        paths: List[str] = []
        for model_type, factory in self._active_scanner_factories():
            try:
                scanner = await factory()
                cache = await scanner.get_cached_data()
            except Exception as exc:
                self._logger.error(
                    "Sidecar migration: failed to enumerate %s models: %s",
                    model_type,
                    exc,
                )
                errors.append({"model": model_type, "error": f"enumeration failed: {exc}"})
                continue
            for entry in cache.raw_data:
                file_path = entry.get("file_path")
                if file_path:
                    paths.append(file_path)
        return paths

    @staticmethod
    def _move_file(src: str, dst: str) -> None:
        """Move a file, tolerating EXDEV when the layouts span filesystems."""

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.rename(src, dst)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            shutil.copy2(src, dst)
            os.remove(src)

    async def _migrate(
        self,
        *,
        direction: str,
        to_centralized: bool,
        progress_cb: Optional[SidecarMigrationProgressReporter],
    ) -> Dict[str, Any]:
        root = get_configured_sidecar_root()
        if not root:
            return self._refusal(
                direction,
                "cannot resolve the centralized sidecar root",
            )

        errors: List[Dict[str, str]] = []
        model_paths = await self._collect_model_paths(errors)

        total = len(model_paths)
        processed = 0
        models_moved = 0
        moved = 0
        skipped = 0
        conflicts = 0

        async def emit(status: str, **extra: Any) -> None:
            if progress_cb is None:
                return
            payload: Dict[str, Any] = {
                "type": "sidecar_migration_progress",
                "status": status,
                "direction": direction,
                "total": total,
                "processed": processed,
                "moved": moved,
                "skipped": skipped,
                "conflicts": conflicts,
                "errors": len(errors),
            }
            payload.update(extra)
            await progress_cb.on_progress(payload)

        await emit("started")

        for model_path in model_paths:
            processed += 1
            current = os.path.basename(model_path)
            try:
                result = await self._migrate_model(
                    model_path,
                    root=root,
                    to_centralized=to_centralized,
                )
                moved += result["moved"]
                conflicts += result["conflicts"]
                if result["skipped"]:
                    skipped += 1
                if result["moved"]:
                    models_moved += 1
            except Exception as exc:
                self._logger.error(
                    "Sidecar migration failed for %s: %s", model_path, exc, exc_info=True
                )
                errors.append({"model": current, "error": str(exc)})
            await emit("processing", current=current)

        await emit("completed")

        return {
            "success": not errors,
            "direction": direction,
            "models_total": total,
            "models_processed": processed,
            "models_moved": models_moved,
            "moved": moved,
            "skipped": skipped,
            "conflicts": conflicts,
            "errors": errors,
            "error_count": len(errors),
        }

    async def _migrate_model(
        self,
        model_path: str,
        *,
        root: str,
        to_centralized: bool,
    ) -> Dict[str, int]:
        """Migrate one model's sidecar + previews; return per-model counters."""

        result = {"moved": 0, "conflicts": 0, "skipped": 0}

        model_path = os.path.abspath(model_path)
        if not os.path.exists(model_path):
            self._logger.warning(
                "Sidecar migration: model file missing, skipping: %s", model_path
            )
            result["skipped"] = 1
            return result

        model_dir = os.path.dirname(model_path)
        mirror_dir = resolve_centralized_dir_for_dir(model_dir, sidecar_root=root)
        if mirror_dir is None:
            self._logger.warning(
                "Sidecar migration: %s is outside configured model roots, skipping",
                model_path,
            )
            result["skipped"] = 1
            return result

        if to_centralized:
            src_dir, dst_dir = model_dir, mirror_dir
        else:
            src_dir, dst_dir = mirror_dir, model_dir

        if os.path.normpath(src_dir) == os.path.normpath(dst_dir):
            result["skipped"] = 1
            return result

        stem = os.path.splitext(os.path.basename(model_path))[0]
        sidecar_name = stem + METADATA_SUFFIX

        moved_previews: List[str] = []
        for ext in PREVIEW_EXTENSIONS:
            src = os.path.join(src_dir, stem + ext)
            if not os.path.exists(src):
                continue
            dst = os.path.join(dst_dir, stem + ext)
            if self._transfer(src, dst, result):
                moved_previews.append(dst)

        sidecar_src = os.path.join(src_dir, sidecar_name)
        sidecar_moved = False
        sidecar_dst = os.path.join(dst_dir, sidecar_name)
        if os.path.exists(sidecar_src):
            sidecar_moved = self._transfer(sidecar_src, sidecar_dst, result)

        if sidecar_moved:
            await self._rewrite_sidecar_paths(sidecar_dst, model_path, moved_previews)

        return result

    def _transfer(self, src: str, dst: str, result: Dict[str, int]) -> bool:
        """Move ``src`` to ``dst`` with keep-newer conflict resolution.

        Returns True when the file was actually moved to the destination. On a
        conflict the newer file wins: a newer source replaces the destination;
        a newer (or equal) destination is kept and the source is deleted.
        """

        if os.path.exists(dst):
            result["conflicts"] += 1
            if os.path.getmtime(src) > os.path.getmtime(dst):
                self._logger.info(
                    "Sidecar migration: conflict at %s; source is newer, replacing", dst
                )
                os.remove(dst)
            else:
                self._logger.info(
                    "Sidecar migration: conflict at %s; destination is newer, keeping it",
                    dst,
                )
                os.remove(src)
                return False
        self._move_file(src, dst)
        result["moved"] += 1
        return True

    async def _rewrite_sidecar_paths(
        self,
        sidecar_path: str,
        model_path: str,
        moved_previews: List[str],
    ) -> None:
        """Update path fields inside a moved sidecar, mirroring ModelScanner."""

        with open(sidecar_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)

        stem = os.path.splitext(os.path.basename(model_path))[0]
        metadata["file_path"] = model_path.replace(os.sep, "/")
        metadata["file_name"] = stem

        if moved_previews and metadata.get("preview_url"):
            recorded_ext = get_preview_extension(metadata["preview_url"])
            chosen = next(
                (
                    path
                    for path in moved_previews
                    if get_preview_extension(path) == recorded_ext
                ),
                moved_previews[0],
            )
            metadata["preview_url"] = chosen.replace(os.sep, "/")

        await MetadataManager.save_metadata(sidecar_path, metadata)

    async def execute_with_error_handling(
        self,
        *,
        direction: str,
        progress_cb: Optional[SidecarMigrationProgressReporter] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Wrapper providing progress notification on unexpected failures."""

        try:
            if direction == DIRECTION_TO_CENTRALIZED:
                return await self.migrate_to_centralized(progress_cb, force=force)
            if direction == DIRECTION_TO_ALONGSIDE:
                return await self.migrate_to_alongside(progress_cb, force=force)
            raise ValueError(
                f"direction must be {DIRECTION_TO_CENTRALIZED!r} or {DIRECTION_TO_ALONGSIDE!r}"
            )
        except Exception as exc:
            if progress_cb is not None:
                await progress_cb.on_progress(
                    {
                        "type": "sidecar_migration_progress",
                        "status": "error",
                        "direction": direction,
                        "error": str(exc),
                    }
                )
            raise
