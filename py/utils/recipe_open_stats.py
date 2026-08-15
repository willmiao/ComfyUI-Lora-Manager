"""Track recipe modal open timestamps for the "Recently Opened" sort.

The data is deliberately kept OUTSIDE the recipe metadata files: recording an
open must be cheap and must never rewrite recipe JSON or EXIF (which the
generic metadata update path does). A tiny JSON map of
``recipe_id -> unix timestamp`` lives under
``{settings_dir}/stats/recipe_last_opened.json`` and is written atomically on
a short debounce.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from ..utils.settings_paths import get_settings_dir

logger = logging.getLogger(__name__)


class RecipeOpenStats:
    """Persist the last time each recipe was opened in the recipe modal."""

    STATS_FILENAME: str = "recipe_last_opened.json"
    SAVE_DELAY: float = 1.0  # seconds of debounce between consecutive writes

    _instance: "RecipeOpenStats | None" = None
    _opened: dict[str, float]
    _file_mtime: float | None
    _dirty: bool
    _lock: asyncio.Lock
    _save_task: "asyncio.Task[None] | None"
    _stats_file_path: str
    _initialized: bool

    def __new__(cls) -> "RecipeOpenStats":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._opened = {}
        self._file_mtime = None
        self._dirty = False
        self._lock = asyncio.Lock()
        self._save_task = None
        self._stats_file_path = self._get_stats_file_path()
        self._load_stats()
        self._initialized = True

    def _get_stats_file_path(self) -> str:
        settings_dir = get_settings_dir(create=True)
        return os.path.join(settings_dir, "stats", self.STATS_FILENAME)

    def _load_stats(self) -> None:
        """Load the opened map from disk, tolerating corrupt/absent files.

        The mtime is recorded even when parsing fails so a corrupt file is
        not re-read (and re-logged) on every lookup.
        """
        if not os.path.exists(self._stats_file_path):
            return
        try:
            mtime = os.path.getmtime(self._stats_file_path)
        except OSError:
            return
        try:
            with open(self._stats_file_path, "r", encoding="utf-8") as file_obj:
                raw = json.load(file_obj)
            if isinstance(raw, dict):
                self._opened = {
                    str(key): float(value)
                    for key, value in raw.items()
                    if isinstance(value, (int, float))
                }
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.error("Error loading recipe open stats: %s", exc)
            self._opened = {}
        self._file_mtime = mtime

    def get_opened_map(self) -> dict[str, float]:
        """Return a copy of ``recipe_id -> last opened timestamp``.

        Refreshes from disk when the file changed since the last load so a
        second server process (or manual edit) is picked up without restart.
        """
        try:
            if os.path.exists(self._stats_file_path):
                mtime = os.path.getmtime(self._stats_file_path)
                if self._file_mtime is None or mtime != self._file_mtime:
                    self._load_stats()
        except OSError:
            pass
        return dict(self._opened)

    def record_open(self, recipe_id: str) -> None:
        """Mark a recipe as opened now; persists shortly in the background."""
        if not recipe_id:
            return
        self._opened[str(recipe_id)] = time.time()
        self._dirty = True
        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._delayed_save())

    async def _delayed_save(self) -> None:
        """Debounced writer: batches rapid consecutive opens into one write."""
        await asyncio.sleep(self.SAVE_DELAY)
        _ = await self.save_stats()

    async def save_stats(self, force: bool = False) -> bool:
        """Persist the opened map atomically if dirty (or when forced).

        The on-disk map is merged in first so a second process sharing the
        settings dir does not lose its entries; the larger timestamp wins
        per recipe.
        """
        if not force and not self._dirty:
            return False
        async with self._lock:
            if not force and not self._dirty:
                return False
            try:
                merged = self._merge_with_disk()
                os.makedirs(os.path.dirname(self._stats_file_path), exist_ok=True)
                temp_path = f"{self._stats_file_path}.tmp"
                with open(temp_path, "w", encoding="utf-8") as file_obj:
                    json.dump(merged, file_obj, indent=2)
                os.replace(temp_path, self._stats_file_path)
                self._opened = merged
                self._file_mtime = os.path.getmtime(self._stats_file_path)
                self._dirty = False
                return True
            except Exception as exc:  # pragma: no cover - defensive logging path
                logger.error("Error saving recipe open stats: %s", exc, exc_info=True)
                return False

    def _merge_with_disk(self) -> dict[str, float]:
        """Merge the in-memory map with the current on-disk map."""
        disk: dict[str, float] = {}
        try:
            if os.path.exists(self._stats_file_path):
                with open(self._stats_file_path, "r", encoding="utf-8") as file_obj:
                    raw = json.load(file_obj)
                if isinstance(raw, dict):
                    disk = {
                        str(key): float(value)
                        for key, value in raw.items()
                        if isinstance(value, (int, float))
                    }
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.error("Error reading recipe open stats for merge: %s", exc)
        merged = dict(disk)
        for key, value in self._opened.items():
            merged[key] = max(value, disk.get(key, 0.0))
        return merged
