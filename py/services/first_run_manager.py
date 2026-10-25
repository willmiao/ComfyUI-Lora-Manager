"""First-run gate: hold the initial library scan until the user confirms it.

On a fresh install no persisted cache snapshot exists, so instead of scanning
every model root at startup the manager shows a welcome page that lists the
configured roots, estimates the scan cost and lets the user pick the sidecar
storage layout before any hashing starts. Upgrading users already have a
snapshot on disk; :meth:`FirstRunManager.check_and_mark_upgrade` detects it
during startup and marks the gate as completed so they never see the page.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import threading
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from ..utils.cache_paths import CacheType, resolve_cache_path_with_migration
from ..utils.recipes_paths import normalized_recipes_dir_key
from .model_scanner import _dir_entry_key, _is_excluded_dir
from .service_registry import ServiceRegistry
from .settings_manager import get_settings_manager
from .websocket_manager import ws_manager

logger = logging.getLogger(__name__)

# Conservative throughput heuristics for the welcome-page estimate: hashing
# large weights files is disk-bound, so 100 MB/s plus a small per-file
# overhead (metadata read, preview probe) errs on the safe side.
_ESTIMATED_BYTES_PER_SECOND = 100 * 1024 * 1024
_ESTIMATED_SECONDS_PER_FILE = 0.05

_VALID_SIDECAR_MODES = ("alongside", "centralized")


def _snapshot_has_rows(path: str, table: str) -> bool:
    """True when the SQLite snapshot exists and contains at least one row.

    Scanner construction creates an empty snapshot file on disk before the
    startup upgrade check runs, so a bare ``os.path.exists`` would misread a
    fresh install as an upgrade. A real library snapshot always has rows in
    its main table.
    """

    if not os.path.exists(path):
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return bool(row and row[0] > 0)
    except sqlite3.Error:
        return False
    finally:
        conn.close()

_FIRST_RUN_MANAGER: Optional["FirstRunManager"] = None
_FIRST_RUN_MANAGER_LOCK = threading.Lock()


def _walk_model_roots(roots: List[str], file_extensions: set) -> Dict[str, Any]:
    """Count model files and accumulate their sizes under ``roots``.

    Synchronous single-pass ``os.scandir`` walk intended for a thread pool.
    Mirrors ``ModelScanner._count_model_files`` (symlink-cycle protection,
    pending-delete and recipes-dir exclusion) and additionally sums
    ``st_size`` for the estimate. Unreadable directories are skipped, never
    fatal.
    """

    entries: List[Dict[str, Any]] = []
    file_count = 0
    total_bytes = 0
    visited_real_paths = set()
    recipes_dir_key = normalized_recipes_dir_key()

    def visit(path: str) -> None:
        nonlocal file_count, total_bytes
        real_path = os.path.realpath(path)
        if real_path in visited_real_paths:
            return
        visited_real_paths.add(real_path)

        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=True):
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in file_extensions:
                            file_count += 1
                            try:
                                total_bytes += entry.stat(
                                    follow_symlinks=True
                                ).st_size
                            except OSError:
                                pass
                    elif entry.is_dir(follow_symlinks=True):
                        if _is_excluded_dir(entry.name):
                            continue
                        if _dir_entry_key(path, entry.name) == recipes_dir_key:
                            continue
                        visit(entry.path)
                except OSError as exc:
                    logger.debug("First-run walk skipped %s: %s", entry.path, exc)

    for root in roots:
        entry: Dict[str, Any] = {"path": root, "exists": os.path.isdir(root)}
        entries.append(entry)
        if not entry["exists"]:
            continue
        try:
            visit(root)
        except OSError as exc:
            # E.g. permission denied on the root itself: report it as
            # unreachable instead of failing the whole estimate.
            logger.debug("First-run walk could not read %s: %s", root, exc)
            entry["accessible"] = False

    return {"roots": entries, "file_count": file_count, "total_bytes": total_bytes}


class FirstRunManager:
    """Coordinate the first-run welcome page and the gated initial scan."""

    def __init__(
        self,
        *,
        settings_manager: Any = None,
        scanner_getters: Optional[
            Mapping[str, Callable[[], Awaitable[Any]]]
        ] = None,
        scan_launcher: Optional[Callable[[], Awaitable[Any]]] = None,
        recipe_scanner_getter: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> None:
        # Only the explicitly injected settings manager is cached; the default
        # resolves per call so library switches and test isolation never leave
        # a stale manager pinned to the singleton.
        self._settings_manager_override = settings_manager
        self._scanner_getters_override = scanner_getters
        self._scan_launcher = scan_launcher
        self._recipe_scanner_getter = (
            recipe_scanner_getter or ServiceRegistry.get_recipe_scanner
        )
        self._start_lock = asyncio.Lock()
        # Stays True for the rest of the session once a scan was launched;
        # makes start_initial_scan idempotent against double clicks.
        self._scan_in_progress = False

    @property
    def _settings(self):
        return self._settings_manager_override or get_settings_manager()

    def _scanner_getters(self) -> Dict[str, Callable[[], Awaitable[Any]]]:
        if self._scanner_getters_override is not None:
            return dict(self._scanner_getters_override)
        return {
            "loras": ServiceRegistry.get_lora_scanner,
            "checkpoints": ServiceRegistry.get_checkpoint_scanner,
            "embeddings": ServiceRegistry.get_embedding_scanner,
            "other": ServiceRegistry.get_other_scanner,
        }

    def _active_scanner_getters(self) -> Dict[str, Callable[[], Awaitable[Any]]]:
        """Drop the opt-in other scanner while Other Models is disabled."""
        getters = self._scanner_getters()
        if "other" in getters and not self._settings.is_other_models_enabled():
            getters.pop("other")
        return getters

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def is_awaiting_first_scan(self) -> bool:
        """True while the welcome page should gate the initial scan."""
        if self._scan_in_progress:
            return False
        return not bool(self._settings.get("initial_scan_completed", False))

    def check_and_mark_upgrade(self) -> None:
        """Mark the gate completed when a persisted cache snapshot exists.

        Existing users upgrading to the version that introduced the gate
        already have a scanner snapshot on disk; skipping the welcome page
        for them preserves the previous startup behaviour. Must run before
        any scanner is constructed, because scanner construction creates an
        empty snapshot file and would make this check useless.
        """
        if self._settings.get("initial_scan_completed", False):
            return
        if self._persistent_snapshot_exists():
            logger.info(
                "First-run gate: persisted cache snapshot found, treating this "
                "startup as an upgrade and skipping the welcome page"
            )
            self._settings.set("initial_scan_completed", True)

    def _persistent_snapshot_exists(self) -> bool:
        try:
            library_name = self._settings.get_active_library_name()
        except Exception:  # pragma: no cover - defensive guard
            library_name = "default"
        candidates = (
            (
                resolve_cache_path_with_migration(
                    CacheType.MODEL,
                    library_name=library_name,
                    env_override=os.environ.get("LORA_MANAGER_CACHE_DB"),
                ),
                "models",
            ),
            (
                resolve_cache_path_with_migration(
                    CacheType.RECIPE,
                    library_name=library_name,
                    env_override=os.environ.get("LORA_MANAGER_RECIPE_CACHE_DB"),
                ),
                "recipes",
            ),
        )
        return any(
            _snapshot_has_rows(path, table) for path, table in candidates
        )

    # ------------------------------------------------------------------
    # Welcome-page info
    # ------------------------------------------------------------------

    async def collect_first_run_info(self) -> Dict[str, Any]:
        """Walk the configured roots and estimate the initial scan cost."""
        settings = self._settings
        loop = asyncio.get_running_loop()

        info: Dict[str, Any] = {}
        total_files = 0
        total_bytes = 0

        for key, getter in self._active_scanner_getters().items():
            scanner = await getter()
            roots = list(scanner.get_model_roots() or [])
            extensions = set(getattr(scanner, "file_extensions", None) or set())
            section = await loop.run_in_executor(
                None, _walk_model_roots, roots, extensions
            )
            info[key] = section
            total_files += section["file_count"]
            total_bytes += section["total_bytes"]

        # Recipes are intentionally omitted: a fresh install always has an
        # empty recipe library, so listing it on the welcome page is noise.

        estimated_seconds = (
            total_bytes / _ESTIMATED_BYTES_PER_SECOND
            + total_files * _ESTIMATED_SECONDS_PER_FILE
        )

        info["file_count"] = total_files
        info["total_bytes"] = total_bytes
        info["estimated_seconds"] = int(round(estimated_seconds))
        info["sidecar_storage_mode"] = settings.get(
            "sidecar_storage_mode", "alongside"
        )
        info["sidecar_storage_path"] = settings.get("sidecar_storage_path", "")
        info["standalone"] = os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"
        return info

    # ------------------------------------------------------------------
    # Scan kickoff
    # ------------------------------------------------------------------

    async def start_initial_scan(
        self,
        *,
        sidecar_storage_mode: Any = None,
        sidecar_storage_path: Any = None,
        defer: bool = False,
    ) -> Dict[str, Any]:
        """Persist the user's choice and start (or defer) the initial scan.

        Idempotent: once the gate is completed or a scan is already running,
        the current status is returned without side effects. Raises
        ``ValueError`` for invalid sidecar options (mapped to HTTP 400 by the
        route handler).
        """
        async with self._start_lock:
            if self._scan_in_progress:
                return {"status": "already_running"}
            if self._settings.get("initial_scan_completed", False):
                return {"status": "completed"}

            # Validate and persist the sidecar layout before flipping the
            # gate flag, so a rejected request leaves state untouched.
            if sidecar_storage_mode is not None or sidecar_storage_path is not None:
                self._apply_sidecar_settings(
                    sidecar_storage_mode, sidecar_storage_path
                )

            self._settings.set("initial_scan_completed", True)

            if defer:
                await self._preset_empty_caches()
                return {"status": "deferred"}

            # Arm the post-scan "fetch metadata" prompt so the frontend can
            # offer a one-click bulk fetch once this first scan finishes.
            # Upgrade shortcuts (check_and_mark_upgrade) and the defer path
            # skip this: those users either already have metadata or have no
            # fresh scan to anchor the prompt to.
            self._settings.set("bulk_fetch_prompt_pending", True)

            self._scan_in_progress = True
            try:
                tasks = await self._launch_scan()
            except Exception:
                self._scan_in_progress = False
                raise

            # No pageType: every connected client (including welcome pages on
            # other tabs) learns the scan has started.
            await ws_manager.broadcast_init_progress(
                {
                    "stage": "scan_started",
                    "progress": 0,
                    "details": "Initial library scan started.",
                }
            )
            return {"status": "scanning", "tasks": len(tasks)}

    def _apply_sidecar_settings(self, mode_value: Any, path_value: Any) -> None:
        """Validate and persist sidecar storage options via SettingsManager."""
        mode: Optional[str] = None
        if mode_value is not None:
            mode = str(mode_value).strip().lower()
            if mode not in _VALID_SIDECAR_MODES:
                raise ValueError(
                    f"Invalid sidecar_storage_mode: {mode_value!r} "
                    f"(expected one of {', '.join(_VALID_SIDECAR_MODES)})"
                )

        path: Optional[str] = None
        if path_value is not None:
            path = str(path_value).strip()

        if mode == "centralized":
            effective_path = path or str(
                self._settings.get("sidecar_storage_path", "") or ""
            ).strip()
            if not effective_path:
                raise ValueError(
                    "sidecar_storage_path is required when "
                    "sidecar_storage_mode is 'centralized'"
                )

        # Persist path before mode so the storage-config refresh hook always
        # observes a consistent pair.
        if path is not None:
            self._settings.set("sidecar_storage_path", path)
        if mode is not None:
            self._settings.set("sidecar_storage_mode", mode)

    async def _launch_scan(self) -> List[asyncio.Task]:
        if self._scan_launcher is not None:
            return await self._scan_launcher()
        # Local import: lora_manager imports this module at top level.
        from ..lora_manager import LoraManager

        return await LoraManager.launch_scanner_initialization()

    async def _preset_empty_caches(self) -> None:
        """Give every scanner an empty cache so pages render an empty library.

        Used by the "later" path: no scan runs, but ``_cache is None`` would
        otherwise keep every page on the initialization screen forever.
        """
        from .model_cache import ModelCache
        from .recipe_cache import RecipeCache

        for key, getter in self._scanner_getters().items():
            try:
                scanner = await getter()
                if getattr(scanner, "_cache", None) is None:
                    scanner._cache = ModelCache(
                        raw_data=[],
                        folders=[],
                        name_display_mode=getattr(
                            scanner, "_name_display_mode", "model_name"
                        ),
                    )
            except Exception as exc:
                logger.error(
                    "First-run gate: failed to preset empty cache for %s: %s",
                    key,
                    exc,
                )

        try:
            recipe_scanner = await self._recipe_scanner_getter()
            if getattr(recipe_scanner, "_cache", None) is None:
                recipe_scanner._cache = RecipeCache(
                    raw_data=[],
                    sorted_by_name=[],
                    sorted_by_date=[],
                    folders=[],
                    folder_tree={},
                )
        except Exception as exc:
            logger.error(
                "First-run gate: failed to preset empty recipe cache: %s", exc
            )


def get_first_run_manager() -> FirstRunManager:
    """Return the lazily initialised global :class:`FirstRunManager`."""
    global _FIRST_RUN_MANAGER
    if _FIRST_RUN_MANAGER is None:
        with _FIRST_RUN_MANAGER_LOCK:
            if _FIRST_RUN_MANAGER is None:
                _FIRST_RUN_MANAGER = FirstRunManager()
    return _FIRST_RUN_MANAGER


def reset_first_run_manager() -> None:
    """Reset the cached manager instance (primarily for tests)."""
    global _FIRST_RUN_MANAGER
    with _FIRST_RUN_MANAGER_LOCK:
        _FIRST_RUN_MANAGER = None
