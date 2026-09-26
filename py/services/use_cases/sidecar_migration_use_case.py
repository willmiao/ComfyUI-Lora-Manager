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
After the move, scanner caches are reconciled so the list API immediately
serves the new preview locations instead of stale pre-migration URLs.

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
from ...utils.file_utils import find_preview_file, get_preview_extension
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
DIRECTION_RELOCATE_ROOT = "relocate_root"

# Same candidate set find_preview_file recognizes: every PREVIEW_EXTENSIONS
# suffix plus the legacy ".example.0.jpeg" (issue #225).
_PREVIEW_CANDIDATE_EXTENSIONS = tuple(PREVIEW_EXTENSIONS) + (".example.0.jpeg",)


def _enumerate_preview_names(directory: str, stem: str) -> List[str]:
    """Return preview filenames for ``stem`` present in ``directory``.

    Case-insensitive full-name match against the preview candidate set, so
    files like ``model.WEBP`` or ``model.Png`` placed by external tools are
    migrated along with the exact-case variants.
    """

    targets = {f"{stem.lower()}{ext}" for ext in _PREVIEW_CANDIDATE_EXTENSIONS}
    try:
        entries = os.listdir(directory)
    except OSError:
        return []
    return [entry for entry in entries if entry.lower() in targets]


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

    async def migrate_root(
        self,
        old_root: str,
        progress_cb: Optional[SidecarMigrationProgressReporter] = None,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Relocate the whole mirror tree from a previous root to the configured one.

        Used after ``sidecar_storage_path`` changes while centralized storage
        is active: without it, every asset under the old root would silently
        disappear from the application. Moves every file keeping the
        root-relative structure, rewrites the ``preview_url`` prefix inside
        moved sidecars, reconciles scanner caches, and prunes the emptied old
        tree. Keep-newer conflict resolution matches :meth:`_transfer`.
        """

        if not force and get_storage_mode() != STORAGE_MODE_CENTRALIZED:
            return self._refusal(
                DIRECTION_RELOCATE_ROOT,
                "sidecar storage is not centralized; pass force=true to relocate anyway",
            )
        new_root = get_configured_sidecar_root()
        if not new_root:
            return self._refusal(
                DIRECTION_RELOCATE_ROOT,
                "cannot resolve the centralized sidecar root",
            )
        old = (
            os.path.abspath(os.path.expanduser(old_root.strip()))
            if isinstance(old_root, str) and old_root.strip()
            else ""
        )
        if not old:
            return self._refusal(DIRECTION_RELOCATE_ROOT, "old_root is required")
        if os.path.normpath(old) == os.path.normpath(new_root):
            return self._refusal(
                DIRECTION_RELOCATE_ROOT,
                "old_root matches the configured sidecar root",
            )

        files: List[Tuple[str, str]] = []
        if os.path.isdir(old):
            for dirpath, _dirnames, filenames in os.walk(old):
                rel = os.path.relpath(dirpath, old)
                target_dir = new_root if rel == os.curdir else os.path.join(new_root, rel)
                for filename in filenames:
                    files.append(
                        (os.path.join(dirpath, filename), os.path.join(target_dir, filename))
                    )

        errors: List[Dict[str, str]] = []
        counters: Dict[str, Any] = {"moved": 0, "conflicts": 0}
        moved_sidecars: List[str] = []

        async def emit(status: str, **extra: Any) -> None:
            if progress_cb is None:
                return
            payload: Dict[str, Any] = {
                "type": "sidecar_migration_progress",
                "status": status,
                "direction": DIRECTION_RELOCATE_ROOT,
                "total": len(files),
                "processed": extra.pop("processed", 0),
                "moved": counters["moved"],
                "skipped": 0,
                "conflicts": counters["conflicts"],
                "errors": len(errors),
            }
            payload.update(extra)
            await progress_cb.on_progress(payload)

        await emit("started")

        for index, (src, dst) in enumerate(files, start=1):
            try:
                if self._transfer(src, dst, counters) and src.endswith(METADATA_SUFFIX):
                    moved_sidecars.append(dst)
            except Exception as exc:
                self._logger.error(
                    "Sidecar root relocation failed for %s: %s", src, exc, exc_info=True
                )
                errors.append({"model": os.path.basename(src), "error": str(exc)})
            await emit("processing", processed=index, current=os.path.basename(src))

        old_prefix = old.replace(os.sep, "/").rstrip("/") + "/"
        new_prefix = new_root.replace(os.sep, "/").rstrip("/") + "/"
        for sidecar in moved_sidecars:
            self._rewrite_root_prefix(sidecar, old_prefix, new_prefix)
        await self._reconcile_root_prefix(old_prefix, new_prefix)

        # Prune the emptied old tree, best-effort.
        if os.path.isdir(old):
            for dirpath, dirnames, filenames in os.walk(old, topdown=False):
                if filenames:
                    continue
                for dirname in dirnames:
                    try:
                        os.rmdir(os.path.join(dirpath, dirname))
                    except OSError:
                        pass
                try:
                    os.rmdir(dirpath)
                except OSError:
                    pass

        await emit("completed")

        return {
            "success": not errors,
            "direction": DIRECTION_RELOCATE_ROOT,
            "models_total": len(files),
            "models_processed": len(files),
            "models_moved": 0,
            "moved": counters["moved"],
            "skipped": 0,
            "conflicts": counters["conflicts"],
            "errors": errors,
            "error_count": len(errors),
        }

    def _rewrite_root_prefix(
        self, sidecar_path: str, old_prefix: str, new_prefix: str
    ) -> None:
        """Repoint preview_url inside a relocated sidecar from old to new root."""

        try:
            with open(sidecar_path, "r", encoding="utf-8") as handle:
                metadata = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self._logger.warning(
                "Sidecar root relocation: cannot read %s: %s", sidecar_path, exc
            )
            return

        preview_url = metadata.get("preview_url")
        if not isinstance(preview_url, str) or not preview_url.startswith(old_prefix):
            return
        metadata["preview_url"] = new_prefix + preview_url[len(old_prefix):]
        try:
            with open(sidecar_path, "w", encoding="utf-8") as handle:
                json.dump(metadata, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._logger.warning(
                "Sidecar root relocation: cannot rewrite %s: %s", sidecar_path, exc
            )

    async def _reconcile_root_prefix(self, old_prefix: str, new_prefix: str) -> None:
        """Rewrite old-root preview URLs in every scanner cache after relocation."""

        for model_type, factory in self._active_scanner_factories():
            try:
                scanner = await factory()
                cache = await scanner.get_cached_data()
                changed = False
                for item in cache.raw_data:
                    preview_url = item.get("preview_url")
                    if (
                        isinstance(preview_url, str)
                        and preview_url.startswith(old_prefix)
                    ):
                        item["preview_url"] = new_prefix + preview_url[len(old_prefix):]
                        changed = True
                if changed and hasattr(scanner, "_persist_current_cache"):
                    await scanner._persist_current_cache()
            except Exception as exc:
                self._logger.error(
                    "Sidecar root relocation: failed to reconcile %s cache: %s",
                    model_type,
                    exc,
                    exc_info=True,
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

    async def _collect_model_paths(
        self, errors: List[Dict[str, str]]
    ) -> List[Tuple[Any, List[str]]]:
        """Enumerate model file paths grouped by the scanner that owns them."""

        groups: List[Tuple[Any, List[str]]] = []
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
            paths = [
                entry["file_path"]
                for entry in cache.raw_data
                if entry.get("file_path")
            ]
            groups.append((scanner, paths))
        return groups

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
        scanner_groups = await self._collect_model_paths(errors)

        total = sum(len(paths) for _, paths in scanner_groups)
        processed = 0
        models_moved = 0
        moved = 0
        skipped = 0
        conflicts = 0
        # (file_path, final preview path at the destination layout), grouped
        # by scanner so caches can be reconciled after the move.
        preview_updates: List[Tuple[Any, List[Tuple[str, str]]]] = []

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

        for scanner, model_paths in scanner_groups:
            updates: List[Tuple[str, str]] = []
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
                    else:
                        updates.append((model_path, result["preview_url"]))
                    if result["moved"]:
                        models_moved += 1
                except Exception as exc:
                    self._logger.error(
                        "Sidecar migration failed for %s: %s", model_path, exc, exc_info=True
                    )
                    errors.append({"model": current, "error": str(exc)})
                await emit("processing", current=current)
            preview_updates.append((scanner, updates))

        await self._reconcile_scanner_caches(preview_updates)

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
    ) -> Dict[str, Any]:
        """Migrate one model's sidecar + previews; return per-model counters.

        ``preview_url`` in the result is the model's final preview path in the
        destination layout ("" when none), used to reconcile scanner caches.
        """

        result: Dict[str, Any] = {"moved": 0, "conflicts": 0, "skipped": 0, "preview_url": ""}

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
        for preview_name in _enumerate_preview_names(src_dir, stem):
            src = os.path.join(src_dir, preview_name)
            dst = os.path.join(dst_dir, preview_name)
            if self._transfer(src, dst, result):
                moved_previews.append(dst)

        sidecar_src = os.path.join(src_dir, sidecar_name)
        sidecar_moved = False
        sidecar_dst = os.path.join(dst_dir, sidecar_name)
        if os.path.exists(sidecar_src):
            sidecar_moved = self._transfer(sidecar_src, sidecar_dst, result)

        if sidecar_moved:
            await self._rewrite_sidecar_paths(sidecar_dst, model_path, moved_previews)

        # Ground truth from the destination directory: covers conflict-keep
        # and partial moves, not just the previews transferred in this run.
        final_preview = find_preview_file(stem, dst_dir)
        if final_preview:
            result["preview_url"] = final_preview.replace(os.sep, "/")

        return result

    async def _reconcile_scanner_caches(
        self, preview_updates: List[Tuple[Any, List[Tuple[str, str]]]]
    ) -> None:
        """Point scanner cache entries at the post-migration preview locations.

        Without this the list API keeps serving pre-migration ``preview_url``
        values whose files no longer exist; hitting one triggers the preview
        route's stale-URL cleanup, which would wipe the reference for good.
        A failing scanner is logged and skipped — the on-disk migration has
        already succeeded, and a full rescan repairs the cache.
        """

        for scanner, updates in preview_updates:
            if not updates:
                continue
            try:
                cache = await scanner.get_cached_data()
                changed = False
                for file_path, preview_url in updates:
                    entry = next(
                        (item for item in cache.raw_data if item.get("file_path") == file_path),
                        None,
                    )
                    if entry is None:
                        continue
                    if entry.get("preview_url", "") == preview_url:
                        continue
                    if hasattr(cache, "update_preview_url"):
                        await cache.update_preview_url(
                            file_path,
                            preview_url,
                            entry.get("preview_nsfw_level", 0),
                        )
                    else:  # pragma: no cover - minimal cache doubles
                        entry["preview_url"] = preview_url
                    changed = True
                if changed and hasattr(scanner, "_persist_current_cache"):
                    await scanner._persist_current_cache()
            except Exception as exc:
                self._logger.error(
                    "Sidecar migration: failed to reconcile scanner cache: %s",
                    exc,
                    exc_info=True,
                )

    def _transfer(self, src: str, dst: str, result: Dict[str, Any]) -> bool:
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
        old_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Wrapper providing progress notification on unexpected failures."""

        try:
            if direction == DIRECTION_TO_CENTRALIZED:
                return await self.migrate_to_centralized(progress_cb, force=force)
            if direction == DIRECTION_TO_ALONGSIDE:
                return await self.migrate_to_alongside(progress_cb, force=force)
            if direction == DIRECTION_RELOCATE_ROOT:
                return await self.migrate_root(old_root or "", progress_cb, force=force)
            raise ValueError(
                f"direction must be {DIRECTION_TO_CENTRALIZED!r}, "
                f"{DIRECTION_TO_ALONGSIDE!r} or {DIRECTION_RELOCATE_ROOT!r}"
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
