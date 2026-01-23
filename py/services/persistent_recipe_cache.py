"""SQLite-based persistent cache for recipe metadata.

This module provides fast recipe cache persistence using SQLite, enabling
quick startup by loading from cache instead of walking directories and
parsing JSON files.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ..utils.settings_paths import get_project_root, get_settings_dir

logger = logging.getLogger(__name__)


@dataclass
class PersistedRecipeData:
    """Lightweight structure returned by the persistent recipe cache."""

    raw_data: List[Dict]
    file_stats: Dict[str, Tuple[float, int]]  # json_path -> (mtime, size)


class PersistentRecipeCache:
    """Persist recipe metadata in SQLite for fast startup."""

    _DEFAULT_FILENAME = "recipe_cache.sqlite"
    _RECIPE_COLUMNS: Tuple[str, ...] = (
        "recipe_id",
        "file_path",
        "json_path",
        "title",
        "folder",
        "base_model",
        "fingerprint",
        "created_date",
        "modified",
        "file_mtime",
        "file_size",
        "favorite",
        "repair_version",
        "preview_nsfw_level",
        "loras_json",
        "checkpoint_json",
        "gen_params_json",
        "tags_json",
    )
    _instances: Dict[str, "PersistentRecipeCache"] = {}
    _instance_lock = threading.Lock()

    def __init__(self, library_name: str = "default", db_path: Optional[str] = None) -> None:
        self._library_name = library_name or "default"
        self._db_path = db_path or self._resolve_default_path(self._library_name)
        self._db_lock = threading.Lock()
        self._schema_initialized = False
        try:
            directory = os.path.dirname(self._db_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create recipe cache directory %s: %s", directory, exc)
        if self.is_enabled():
            self._initialize_schema()

    @classmethod
    def get_default(cls, library_name: Optional[str] = None) -> "PersistentRecipeCache":
        name = library_name or "default"
        with cls._instance_lock:
            if name not in cls._instances:
                cls._instances[name] = cls(name)
            return cls._instances[name]

    @classmethod
    def clear_instances(cls) -> None:
        """Clear all cached instances (useful for library switching)."""
        with cls._instance_lock:
            cls._instances.clear()

    def is_enabled(self) -> bool:
        return os.environ.get("LORA_MANAGER_DISABLE_PERSISTENT_CACHE", "0") != "1"

    def get_database_path(self) -> str:
        """Expose the resolved SQLite database path."""
        return self._db_path

    def load_cache(self) -> Optional[PersistedRecipeData]:
        """Load all cached recipes from SQLite.

        Returns:
            PersistedRecipeData with raw_data and file_stats if cache exists,
            None if cache is empty or unavailable.
        """
        if not self.is_enabled():
            return None
        if not self._schema_initialized:
            self._initialize_schema()
        if not self._schema_initialized:
            return None

        try:
            with self._db_lock:
                conn = self._connect(readonly=True)
                try:
                    # Load all recipes
                    columns_sql = ", ".join(self._RECIPE_COLUMNS)
                    rows = conn.execute(f"SELECT {columns_sql} FROM recipes").fetchall()

                    if not rows:
                        return None

                finally:
                    conn.close()
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.warning("Failed to load persisted recipe cache: %s", exc)
            return None

        raw_data: List[Dict] = []
        file_stats: Dict[str, Tuple[float, int]] = {}

        for row in rows:
            recipe = self._row_to_recipe(row)
            raw_data.append(recipe)

            json_path = row["json_path"]
            if json_path:
                file_stats[json_path] = (
                    row["file_mtime"] or 0.0,
                    row["file_size"] or 0,
                )

        return PersistedRecipeData(raw_data=raw_data, file_stats=file_stats)

    def save_cache(self, recipes: List[Dict], json_paths: Optional[Dict[str, str]] = None) -> None:
        """Save all recipes to SQLite cache.

        Args:
            recipes: List of recipe dictionaries to persist.
            json_paths: Optional mapping of recipe_id -> json_path for file stats.
        """
        if not self.is_enabled():
            return
        if not self._schema_initialized:
            self._initialize_schema()
        if not self._schema_initialized:
            return

        try:
            with self._db_lock:
                conn = self._connect()
                try:
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("BEGIN")

                    # Clear existing data
                    conn.execute("DELETE FROM recipes")

                    # Prepare and insert all rows
                    recipe_rows = []
                    for recipe in recipes:
                        recipe_id = str(recipe.get("id", ""))
                        if not recipe_id:
                            continue

                        json_path = ""
                        if json_paths:
                            json_path = json_paths.get(recipe_id, "")

                        row = self._prepare_recipe_row(recipe, json_path)
                        recipe_rows.append(row)

                    if recipe_rows:
                        placeholders = ", ".join(["?"] * len(self._RECIPE_COLUMNS))
                        columns = ", ".join(self._RECIPE_COLUMNS)
                        conn.executemany(
                            f"INSERT INTO recipes ({columns}) VALUES ({placeholders})",
                            recipe_rows,
                        )

                    conn.commit()
                    logger.debug("Persisted %d recipes to cache", len(recipe_rows))
                finally:
                    conn.close()
        except Exception as exc:
            logger.warning("Failed to persist recipe cache: %s", exc)

    def get_file_stats(self) -> Dict[str, Tuple[float, int]]:
        """Return stored file stats for all cached recipes.

        Returns:
            Dictionary mapping json_path -> (mtime, size).
        """
        if not self.is_enabled() or not self._schema_initialized:
            return {}

        try:
            with self._db_lock:
                conn = self._connect(readonly=True)
                try:
                    rows = conn.execute(
                        "SELECT json_path, file_mtime, file_size FROM recipes WHERE json_path IS NOT NULL"
                    ).fetchall()
                    return {
                        row["json_path"]: (row["file_mtime"] or 0.0, row["file_size"] or 0)
                        for row in rows
                        if row["json_path"]
                    }
                finally:
                    conn.close()
        except Exception:
            return {}

    def update_recipe(self, recipe: Dict, json_path: Optional[str] = None) -> None:
        """Update or insert a single recipe in the cache.

        Args:
            recipe: The recipe dictionary to persist.
            json_path: Optional path to the recipe JSON file.
        """
        if not self.is_enabled() or not self._schema_initialized:
            return

        recipe_id = str(recipe.get("id", ""))
        if not recipe_id:
            return

        try:
            with self._db_lock:
                conn = self._connect()
                try:
                    row = self._prepare_recipe_row(recipe, json_path or "")
                    placeholders = ", ".join(["?"] * len(self._RECIPE_COLUMNS))
                    columns = ", ".join(self._RECIPE_COLUMNS)
                    conn.execute(
                        f"INSERT OR REPLACE INTO recipes ({columns}) VALUES ({placeholders})",
                        row,
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as exc:
            logger.debug("Failed to update recipe %s in cache: %s", recipe_id, exc)

    def remove_recipe(self, recipe_id: str) -> None:
        """Remove a recipe from the cache by ID.

        Args:
            recipe_id: The ID of the recipe to remove.
        """
        if not self.is_enabled() or not self._schema_initialized:
            return

        if not recipe_id:
            return

        try:
            with self._db_lock:
                conn = self._connect()
                try:
                    conn.execute("DELETE FROM recipes WHERE recipe_id = ?", (str(recipe_id),))
                    conn.commit()
                finally:
                    conn.close()
        except Exception as exc:
            logger.debug("Failed to remove recipe %s from cache: %s", recipe_id, exc)

    def get_indexed_recipe_ids(self) -> Set[str]:
        """Return all recipe IDs in the cache.

        Returns:
            Set of recipe ID strings.
        """
        if not self.is_enabled() or not self._schema_initialized:
            return set()

        try:
            with self._db_lock:
                conn = self._connect(readonly=True)
                try:
                    rows = conn.execute("SELECT recipe_id FROM recipes").fetchall()
                    return {row["recipe_id"] for row in rows if row["recipe_id"]}
                finally:
                    conn.close()
        except Exception:
            return set()

    def get_recipe_count(self) -> int:
        """Return the number of recipes in the cache."""
        if not self.is_enabled() or not self._schema_initialized:
            return 0

        try:
            with self._db_lock:
                conn = self._connect(readonly=True)
                try:
                    result = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()
                    return result[0] if result else 0
                finally:
                    conn.close()
        except Exception:
            return 0

    # Internal helpers

    def _resolve_default_path(self, library_name: str) -> str:
        override = os.environ.get("LORA_MANAGER_RECIPE_CACHE_DB")
        if override:
            return override
        try:
            settings_dir = get_settings_dir(create=True)
        except Exception as exc:
            logger.warning("Falling back to project directory for recipe cache: %s", exc)
            settings_dir = get_project_root()
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", library_name or "default")
        if safe_name.lower() in ("default", ""):
            legacy_path = os.path.join(settings_dir, self._DEFAULT_FILENAME)
            if os.path.exists(legacy_path):
                return legacy_path
        return os.path.join(settings_dir, "recipe_cache", f"{safe_name}.sqlite")

    def _initialize_schema(self) -> None:
        with self._db_lock:
            if self._schema_initialized:
                return
            try:
                with self._connect() as conn:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS recipes (
                            recipe_id TEXT PRIMARY KEY,
                            file_path TEXT,
                            json_path TEXT,
                            title TEXT,
                            folder TEXT,
                            base_model TEXT,
                            fingerprint TEXT,
                            created_date REAL,
                            modified REAL,
                            file_mtime REAL,
                            file_size INTEGER,
                            favorite INTEGER DEFAULT 0,
                            repair_version INTEGER DEFAULT 0,
                            preview_nsfw_level INTEGER DEFAULT 0,
                            loras_json TEXT,
                            checkpoint_json TEXT,
                            gen_params_json TEXT,
                            tags_json TEXT
                        );

                        CREATE INDEX IF NOT EXISTS idx_recipes_json_path ON recipes(json_path);
                        CREATE INDEX IF NOT EXISTS idx_recipes_fingerprint ON recipes(fingerprint);

                        CREATE TABLE IF NOT EXISTS cache_metadata (
                            key TEXT PRIMARY KEY,
                            value TEXT
                        );
                        """
                    )
                    conn.commit()
                self._schema_initialized = True
            except Exception as exc:
                logger.warning("Failed to initialize persistent recipe cache schema: %s", exc)

    def _connect(self, readonly: bool = False) -> sqlite3.Connection:
        uri = False
        path = self._db_path
        if readonly:
            if not os.path.exists(path):
                raise FileNotFoundError(path)
            path = f"file:{path}?mode=ro"
            uri = True
        conn = sqlite3.connect(path, check_same_thread=False, uri=uri, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn

    def _prepare_recipe_row(self, recipe: Dict, json_path: str) -> Tuple:
        """Convert a recipe dict to a row tuple for SQLite insertion."""
        loras = recipe.get("loras")
        loras_json = json.dumps(loras) if loras else None

        checkpoint = recipe.get("checkpoint")
        checkpoint_json = json.dumps(checkpoint) if checkpoint else None

        gen_params = recipe.get("gen_params")
        gen_params_json = json.dumps(gen_params) if gen_params else None

        tags = recipe.get("tags")
        tags_json = json.dumps(tags) if tags else None

        # Get file stats if json_path exists
        file_mtime = 0.0
        file_size = 0
        if json_path and os.path.exists(json_path):
            try:
                stat = os.stat(json_path)
                file_mtime = stat.st_mtime
                file_size = stat.st_size
            except OSError:
                pass

        return (
            str(recipe.get("id", "")),
            recipe.get("file_path"),
            json_path,
            recipe.get("title"),
            recipe.get("folder"),
            recipe.get("base_model"),
            recipe.get("fingerprint"),
            float(recipe.get("created_date") or 0.0),
            float(recipe.get("modified") or 0.0),
            file_mtime,
            file_size,
            1 if recipe.get("favorite") else 0,
            int(recipe.get("repair_version") or 0),
            int(recipe.get("preview_nsfw_level") or 0),
            loras_json,
            checkpoint_json,
            gen_params_json,
            tags_json,
        )

    def _row_to_recipe(self, row: sqlite3.Row) -> Dict:
        """Convert a SQLite row to a recipe dictionary."""
        loras = []
        if row["loras_json"]:
            try:
                loras = json.loads(row["loras_json"])
            except json.JSONDecodeError:
                pass

        checkpoint = None
        if row["checkpoint_json"]:
            try:
                checkpoint = json.loads(row["checkpoint_json"])
            except json.JSONDecodeError:
                pass

        gen_params = {}
        if row["gen_params_json"]:
            try:
                gen_params = json.loads(row["gen_params_json"])
            except json.JSONDecodeError:
                pass

        tags = []
        if row["tags_json"]:
            try:
                tags = json.loads(row["tags_json"])
            except json.JSONDecodeError:
                pass

        recipe = {
            "id": row["recipe_id"],
            "file_path": row["file_path"] or "",
            "title": row["title"] or "",
            "folder": row["folder"] or "",
            "base_model": row["base_model"] or "",
            "fingerprint": row["fingerprint"] or "",
            "created_date": row["created_date"] or 0.0,
            "modified": row["modified"] or 0.0,
            "favorite": bool(row["favorite"]),
            "repair_version": row["repair_version"] or 0,
            "preview_nsfw_level": row["preview_nsfw_level"] or 0,
            "loras": loras,
            "gen_params": gen_params,
        }

        if tags:
            recipe["tags"] = tags

        if checkpoint:
            recipe["checkpoint"] = checkpoint

        return recipe


def get_persistent_recipe_cache() -> PersistentRecipeCache:
    """Get the default persistent recipe cache instance for the active library."""
    from .settings_manager import get_settings_manager

    library_name = get_settings_manager().get_active_library_name()
    return PersistentRecipeCache.get_default(library_name)
