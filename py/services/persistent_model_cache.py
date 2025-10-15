import json
import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from ..utils.settings_paths import get_settings_dir

logger = logging.getLogger(__name__)


@dataclass
class PersistedCacheData:
    """Lightweight structure returned by the persistent cache."""

    raw_data: List[Dict]
    hash_rows: List[Tuple[str, str]]
    excluded_models: List[str]


class PersistentModelCache:
    """Persist core model metadata and hash index data in SQLite."""

    _DEFAULT_FILENAME = "model_cache.sqlite"
    _MODEL_COLUMNS: Tuple[str, ...] = (
        "model_type",
        "file_path",
        "file_name",
        "model_name",
        "folder",
        "size",
        "modified",
        "sha256",
        "base_model",
        "preview_url",
        "preview_nsfw_level",
        "from_civitai",
        "favorite",
        "notes",
        "usage_tips",
        "metadata_source",
        "civitai_id",
        "civitai_model_id",
        "civitai_name",
        "civitai_creator_username",
        "trained_words",
        "civitai_deleted",
        "exclude",
        "db_checked",
        "last_checked_at",
    )
    _MODEL_UPDATE_COLUMNS: Tuple[str, ...] = _MODEL_COLUMNS[2:]
    _instances: Dict[str, "PersistentModelCache"] = {}
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
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Could not create cache directory %s: %s", directory, exc)
        if self.is_enabled():
            self._initialize_schema()

    @classmethod
    def get_default(cls, library_name: Optional[str] = None) -> "PersistentModelCache":
        name = (library_name or "default")
        with cls._instance_lock:
            if name not in cls._instances:
                cls._instances[name] = cls(name)
            return cls._instances[name]

    def is_enabled(self) -> bool:
        return os.environ.get("LORA_MANAGER_DISABLE_PERSISTENT_CACHE", "0") != "1"

    def get_database_path(self) -> str:
        """Expose the resolved SQLite database path."""

        return self._db_path

    def load_cache(self, model_type: str) -> Optional[PersistedCacheData]:
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
                    model_columns_sql = ", ".join(self._MODEL_COLUMNS[1:])
                    rows = conn.execute(
                        f"SELECT {model_columns_sql} FROM models WHERE model_type = ?",
                        (model_type,),
                    ).fetchall()

                    if not rows:
                        return None

                    tags = self._load_tags(conn, model_type)
                    hash_rows = conn.execute(
                        "SELECT sha256, file_path FROM hash_index WHERE model_type = ?",
                        (model_type,),
                    ).fetchall()
                    excluded = conn.execute(
                        "SELECT file_path FROM excluded_models WHERE model_type = ?",
                        (model_type,),
                    ).fetchall()
                finally:
                    conn.close()
        except Exception as exc:
            logger.warning("Failed to load persisted cache for %s: %s", model_type, exc)
            return None

        raw_data: List[Dict] = []
        for row in rows:
            file_path: str = row["file_path"]
            trained_words = []
            if row["trained_words"]:
                try:
                    trained_words = json.loads(row["trained_words"])
                except json.JSONDecodeError:
                    trained_words = []

            creator_username = row["civitai_creator_username"]
            civitai: Optional[Dict] = None
            civitai_has_data = any(
                row[col] is not None for col in ("civitai_id", "civitai_model_id", "civitai_name")
            ) or trained_words or creator_username
            if civitai_has_data:
                civitai = {}
                if row["civitai_id"] is not None:
                    civitai["id"] = row["civitai_id"]
                if row["civitai_model_id"] is not None:
                    civitai["modelId"] = row["civitai_model_id"]
                if row["civitai_name"]:
                    civitai["name"] = row["civitai_name"]
                if trained_words:
                    civitai["trainedWords"] = trained_words
                if creator_username:
                    civitai.setdefault("creator", {})["username"] = creator_username

            item = {
                "file_path": file_path,
                "file_name": row["file_name"],
                "model_name": row["model_name"],
                "folder": row["folder"] or "",
                "size": row["size"] or 0,
                "modified": row["modified"] or 0.0,
                "sha256": row["sha256"] or "",
                "base_model": row["base_model"] or "",
                "preview_url": row["preview_url"] or "",
                "preview_nsfw_level": row["preview_nsfw_level"] or 0,
                "from_civitai": bool(row["from_civitai"]),
                "favorite": bool(row["favorite"]),
                "notes": row["notes"] or "",
                "usage_tips": row["usage_tips"] or "",
                "metadata_source": row["metadata_source"] or None,
                "exclude": bool(row["exclude"]),
                "db_checked": bool(row["db_checked"]),
                "last_checked_at": row["last_checked_at"] or 0.0,
                "tags": tags.get(file_path, []),
                "civitai": civitai,
                "civitai_deleted": bool(row["civitai_deleted"]),
            }
            raw_data.append(item)

        hash_pairs = [(entry["sha256"].lower(), entry["file_path"]) for entry in hash_rows if entry["sha256"]]
        if not hash_pairs:
            # Fall back to hashes stored on the model rows
            for item in raw_data:
                sha_value = item.get("sha256")
                if sha_value:
                    hash_pairs.append((sha_value.lower(), item["file_path"]))

        excluded_paths = [row["file_path"] for row in excluded]
        return PersistedCacheData(raw_data=raw_data, hash_rows=hash_pairs, excluded_models=excluded_paths)

    def save_cache(self, model_type: str, raw_data: Sequence[Dict], hash_index: Dict[str, List[str]], excluded_models: Sequence[str]) -> None:
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

                    model_rows = [self._prepare_model_row(model_type, item) for item in raw_data]
                    model_map: Dict[str, Tuple] = {
                        row[1]: row for row in model_rows if row[1]  # row[1] is file_path
                    }

                    existing_models = conn.execute(
                        "SELECT "
                        + ", ".join(self._MODEL_COLUMNS[1:])
                        + " FROM models WHERE model_type = ?",
                        (model_type,),
                    ).fetchall()
                    existing_model_map: Dict[str, sqlite3.Row] = {
                        row["file_path"]: row for row in existing_models
                    }

                    to_remove_models = [
                        (model_type, path)
                        for path in existing_model_map.keys()
                        if path not in model_map
                    ]
                    if to_remove_models:
                        conn.executemany(
                            "DELETE FROM models WHERE model_type = ? AND file_path = ?",
                            to_remove_models,
                        )
                        conn.executemany(
                            "DELETE FROM model_tags WHERE model_type = ? AND file_path = ?",
                            to_remove_models,
                        )
                        conn.executemany(
                            "DELETE FROM hash_index WHERE model_type = ? AND file_path = ?",
                            to_remove_models,
                        )
                        conn.executemany(
                            "DELETE FROM excluded_models WHERE model_type = ? AND file_path = ?",
                            to_remove_models,
                        )

                    insert_rows: List[Tuple] = []
                    update_rows: List[Tuple] = []

                    for file_path, row in model_map.items():
                        existing = existing_model_map.get(file_path)
                        if existing is None:
                            insert_rows.append(row)
                            continue

                        existing_values = tuple(
                            existing[column] for column in self._MODEL_COLUMNS[1:]
                        )
                        current_values = row[1:]
                        if existing_values != current_values:
                            update_rows.append(row[2:] + (model_type, file_path))

                    if insert_rows:
                        conn.executemany(self._insert_model_sql(), insert_rows)

                    if update_rows:
                        set_clause = ", ".join(
                            f"{column} = ?"
                            for column in self._MODEL_UPDATE_COLUMNS
                        )
                        update_sql = (
                            f"UPDATE models SET {set_clause} WHERE model_type = ? AND file_path = ?"
                        )
                        conn.executemany(update_sql, update_rows)

                    existing_tags_rows = conn.execute(
                        "SELECT file_path, tag FROM model_tags WHERE model_type = ?",
                        (model_type,),
                    ).fetchall()
                    existing_tags: Dict[str, set] = {}
                    for row in existing_tags_rows:
                        existing_tags.setdefault(row["file_path"], set()).add(row["tag"])

                    new_tags: Dict[str, set] = {}
                    for item in raw_data:
                        file_path = item.get("file_path")
                        if not file_path:
                            continue
                        tags = set(item.get("tags") or [])
                        if tags:
                            new_tags[file_path] = tags

                    tag_inserts: List[Tuple[str, str, str]] = []
                    tag_deletes: List[Tuple[str, str, str]] = []

                    all_tag_paths = set(existing_tags.keys()) | set(new_tags.keys())
                    for path in all_tag_paths:
                        existing_set = existing_tags.get(path, set())
                        new_set = new_tags.get(path, set())
                        to_add = new_set - existing_set
                        to_remove = existing_set - new_set

                        for tag in to_add:
                            tag_inserts.append((model_type, path, tag))
                        for tag in to_remove:
                            tag_deletes.append((model_type, path, tag))

                    if tag_deletes:
                        conn.executemany(
                            "DELETE FROM model_tags WHERE model_type = ? AND file_path = ? AND tag = ?",
                            tag_deletes,
                        )
                    if tag_inserts:
                        conn.executemany(
                            "INSERT INTO model_tags (model_type, file_path, tag) VALUES (?, ?, ?)",
                            tag_inserts,
                        )

                    existing_hash_rows = conn.execute(
                        "SELECT sha256, file_path FROM hash_index WHERE model_type = ?",
                        (model_type,),
                    ).fetchall()
                    existing_hash_map: Dict[str, set] = {}
                    for row in existing_hash_rows:
                        sha_value = (row["sha256"] or "").lower()
                        if not sha_value:
                            continue
                        existing_hash_map.setdefault(sha_value, set()).add(row["file_path"])

                    new_hash_map: Dict[str, set] = {}
                    for sha_value, paths in hash_index.items():
                        normalized_sha = (sha_value or "").lower()
                        if not normalized_sha:
                            continue
                        bucket = new_hash_map.setdefault(normalized_sha, set())
                        for path in paths:
                            if path:
                                bucket.add(path)

                    hash_inserts: List[Tuple[str, str, str]] = []
                    hash_deletes: List[Tuple[str, str, str]] = []

                    all_shas = set(existing_hash_map.keys()) | set(new_hash_map.keys())
                    for sha_value in all_shas:
                        existing_paths = existing_hash_map.get(sha_value, set())
                        new_paths = new_hash_map.get(sha_value, set())

                        for path in existing_paths - new_paths:
                            hash_deletes.append((model_type, sha_value, path))
                        for path in new_paths - existing_paths:
                            hash_inserts.append((model_type, sha_value, path))

                    if hash_deletes:
                        conn.executemany(
                            "DELETE FROM hash_index WHERE model_type = ? AND sha256 = ? AND file_path = ?",
                            hash_deletes,
                        )
                    if hash_inserts:
                        conn.executemany(
                            "INSERT OR IGNORE INTO hash_index (model_type, sha256, file_path) VALUES (?, ?, ?)",
                            hash_inserts,
                        )

                    existing_excluded_rows = conn.execute(
                        "SELECT file_path FROM excluded_models WHERE model_type = ?",
                        (model_type,),
                    ).fetchall()
                    existing_excluded = {row["file_path"] for row in existing_excluded_rows}
                    new_excluded = {path for path in excluded_models if path}

                    excluded_deletes = [
                        (model_type, path)
                        for path in existing_excluded - new_excluded
                    ]
                    excluded_inserts = [
                        (model_type, path)
                        for path in new_excluded - existing_excluded
                    ]

                    if excluded_deletes:
                        conn.executemany(
                            "DELETE FROM excluded_models WHERE model_type = ? AND file_path = ?",
                            excluded_deletes,
                        )
                    if excluded_inserts:
                        conn.executemany(
                            "INSERT OR IGNORE INTO excluded_models (model_type, file_path) VALUES (?, ?)",
                            excluded_inserts,
                        )

                    conn.commit()
                finally:
                    conn.close()
        except Exception as exc:
            logger.warning("Failed to persist cache for %s: %s", model_type, exc)

    # Internal helpers -------------------------------------------------

    def _resolve_default_path(self, library_name: str) -> str:
        override = os.environ.get("LORA_MANAGER_CACHE_DB")
        if override:
            return override
        try:
            settings_dir = get_settings_dir(create=True)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Falling back to project directory for cache: %s", exc)
            settings_dir = os.path.dirname(os.path.dirname(self._db_path)) if hasattr(self, "_db_path") else os.getcwd()
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", library_name or "default")
        if safe_name.lower() in ("default", ""):
            legacy_path = os.path.join(settings_dir, self._DEFAULT_FILENAME)
            if os.path.exists(legacy_path):
                return legacy_path
        return os.path.join(settings_dir, "model_cache", f"{safe_name}.sqlite")

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
                        CREATE TABLE IF NOT EXISTS models (
                            model_type TEXT NOT NULL,
                            file_path TEXT NOT NULL,
                            file_name TEXT,
                            model_name TEXT,
                            folder TEXT,
                            size INTEGER,
                            modified REAL,
                            sha256 TEXT,
                            base_model TEXT,
                            preview_url TEXT,
                            preview_nsfw_level INTEGER,
                            from_civitai INTEGER,
                            favorite INTEGER,
                            notes TEXT,
                            usage_tips TEXT,
                            metadata_source TEXT,
                            civitai_id INTEGER,
                            civitai_model_id INTEGER,
                            civitai_name TEXT,
                            civitai_creator_username TEXT,
                            trained_words TEXT,
                            civitai_deleted INTEGER,
                            exclude INTEGER,
                            db_checked INTEGER,
                            last_checked_at REAL,
                            PRIMARY KEY (model_type, file_path)
                        );

                        CREATE TABLE IF NOT EXISTS model_tags (
                            model_type TEXT NOT NULL,
                            file_path TEXT NOT NULL,
                            tag TEXT NOT NULL,
                            PRIMARY KEY (model_type, file_path, tag)
                        );

                        CREATE TABLE IF NOT EXISTS hash_index (
                            model_type TEXT NOT NULL,
                            sha256 TEXT NOT NULL,
                            file_path TEXT NOT NULL,
                            PRIMARY KEY (model_type, sha256, file_path)
                        );

                        CREATE TABLE IF NOT EXISTS excluded_models (
                            model_type TEXT NOT NULL,
                            file_path TEXT NOT NULL,
                            PRIMARY KEY (model_type, file_path)
                        );
                        """
                    )
                    self._ensure_additional_model_columns(conn)
                    conn.commit()
                self._schema_initialized = True
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Failed to initialize persistent cache schema: %s", exc)

    def _ensure_additional_model_columns(self, conn: sqlite3.Connection) -> None:
        try:
            existing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(models)").fetchall()
            }
        except Exception:  # pragma: no cover - defensive guard
            return

        required_columns = {
            "metadata_source": "TEXT",
            "civitai_creator_username": "TEXT",
            "civitai_deleted": "INTEGER DEFAULT 0",
        }

        for column, definition in required_columns.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE models ADD COLUMN {column} {definition}")

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

    def _prepare_model_row(self, model_type: str, item: Dict) -> Tuple:
        civitai = item.get("civitai") or {}
        trained_words = civitai.get("trainedWords")
        if isinstance(trained_words, str):
            trained_words_json = trained_words
        elif trained_words is None:
            trained_words_json = None
        else:
            trained_words_json = json.dumps(trained_words)

        metadata_source = item.get("metadata_source") or None
        creator_username = None
        creator_data = civitai.get("creator") if isinstance(civitai, dict) else None
        if isinstance(creator_data, dict):
            creator_username = creator_data.get("username") or None

        return (
            model_type,
            item.get("file_path"),
            item.get("file_name"),
            item.get("model_name"),
            item.get("folder"),
            int(item.get("size") or 0),
            float(item.get("modified") or 0.0),
            (item.get("sha256") or "").lower() or None,
            item.get("base_model"),
            item.get("preview_url"),
            int(item.get("preview_nsfw_level") or 0),
            1 if item.get("from_civitai", True) else 0,
            1 if item.get("favorite") else 0,
            item.get("notes"),
            item.get("usage_tips"),
            metadata_source,
            civitai.get("id"),
            civitai.get("modelId"),
            civitai.get("name"),
            creator_username,
            trained_words_json,
            1 if item.get("civitai_deleted") else 0,
            1 if item.get("exclude") else 0,
            1 if item.get("db_checked") else 0,
            float(item.get("last_checked_at") or 0.0),
        )

    def _insert_model_sql(self) -> str:
        columns = ", ".join(self._MODEL_COLUMNS)
        placeholders = ", ".join(["?"] * len(self._MODEL_COLUMNS))
        return f"INSERT INTO models ({columns}) VALUES ({placeholders})"

    def _load_tags(self, conn: sqlite3.Connection, model_type: str) -> Dict[str, List[str]]:
        tag_rows = conn.execute(
            "SELECT file_path, tag FROM model_tags WHERE model_type = ?",
            (model_type,),
        ).fetchall()
        result: Dict[str, List[str]] = {}
        for row in tag_rows:
            result.setdefault(row["file_path"], []).append(row["tag"])
        return result


def get_persistent_cache() -> PersistentModelCache:
    from .settings_manager import get_settings_manager  # Local import to avoid cycles

    library_name = get_settings_manager().get_active_library_name()
    return PersistentModelCache.get_default(library_name)
