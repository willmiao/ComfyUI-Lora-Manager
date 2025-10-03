import json
import logging
import os
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
    _instance: Optional["PersistentModelCache"] = None
    _instance_lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or self._resolve_default_path()
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
    def get_default(cls) -> "PersistentModelCache":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_enabled(self) -> bool:
        return os.environ.get("LORA_MANAGER_DISABLE_PERSISTENT_CACHE", "0") != "1"

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
                    rows = conn.execute(
                        "SELECT file_path, file_name, model_name, folder, size, modified, sha256, base_model,"
                        " preview_url, preview_nsfw_level, from_civitai, favorite, notes, usage_tips,"
                        " civitai_id, civitai_model_id, civitai_name, trained_words, exclude, db_checked,"
                        " last_checked_at"
                        " FROM models WHERE model_type = ?",
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

            civitai: Optional[Dict] = None
            if any(row[col] is not None for col in ("civitai_id", "civitai_model_id", "civitai_name")):
                civitai = {}
                if row["civitai_id"] is not None:
                    civitai["id"] = row["civitai_id"]
                if row["civitai_model_id"] is not None:
                    civitai["modelId"] = row["civitai_model_id"]
                if row["civitai_name"]:
                    civitai["name"] = row["civitai_name"]
                if trained_words:
                    civitai["trainedWords"] = trained_words

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
                "exclude": bool(row["exclude"]),
                "db_checked": bool(row["db_checked"]),
                "last_checked_at": row["last_checked_at"] or 0.0,
                "tags": tags.get(file_path, []),
                "civitai": civitai,
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
                    conn.execute("DELETE FROM models WHERE model_type = ?", (model_type,))
                    conn.execute("DELETE FROM model_tags WHERE model_type = ?", (model_type,))
                    conn.execute("DELETE FROM hash_index WHERE model_type = ?", (model_type,))
                    conn.execute("DELETE FROM excluded_models WHERE model_type = ?", (model_type,))

                    model_rows = [self._prepare_model_row(model_type, item) for item in raw_data]
                    conn.executemany(self._insert_model_sql(), model_rows)

                    tag_rows = []
                    for item in raw_data:
                        file_path = item.get("file_path")
                        if not file_path:
                            continue
                        for tag in item.get("tags") or []:
                            tag_rows.append((model_type, file_path, tag))
                    if tag_rows:
                        conn.executemany(
                            "INSERT INTO model_tags (model_type, file_path, tag) VALUES (?, ?, ?)",
                            tag_rows,
                        )

                    hash_rows: List[Tuple[str, str, str]] = []
                    for sha_value, paths in hash_index.items():
                        for path in paths:
                            if not sha_value or not path:
                                continue
                            hash_rows.append((model_type, sha_value.lower(), path))
                    if hash_rows:
                        conn.executemany(
                            "INSERT OR IGNORE INTO hash_index (model_type, sha256, file_path) VALUES (?, ?, ?)",
                            hash_rows,
                        )

                    excluded_rows = [(model_type, path) for path in excluded_models]
                    if excluded_rows:
                        conn.executemany(
                            "INSERT OR IGNORE INTO excluded_models (model_type, file_path) VALUES (?, ?)",
                            excluded_rows,
                        )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as exc:
            logger.warning("Failed to persist cache for %s: %s", model_type, exc)

    # Internal helpers -------------------------------------------------

    def _resolve_default_path(self) -> str:
        override = os.environ.get("LORA_MANAGER_CACHE_DB")
        if override:
            return override
        try:
            settings_dir = get_settings_dir(create=True)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Falling back to project directory for cache: %s", exc)
            settings_dir = os.path.dirname(os.path.dirname(self._db_path)) if hasattr(self, "_db_path") else os.getcwd()
        return os.path.join(settings_dir, self._DEFAULT_FILENAME)

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
                            civitai_id INTEGER,
                            civitai_model_id INTEGER,
                            civitai_name TEXT,
                            trained_words TEXT,
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
                    conn.commit()
                self._schema_initialized = True
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Failed to initialize persistent cache schema: %s", exc)

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
            civitai.get("id"),
            civitai.get("modelId"),
            civitai.get("name"),
            trained_words_json,
            1 if item.get("exclude") else 0,
            1 if item.get("db_checked") else 0,
            float(item.get("last_checked_at") or 0.0),
        )

    def _insert_model_sql(self) -> str:
        return (
            "INSERT INTO models (model_type, file_path, file_name, model_name, folder, size, modified, sha256,"
            " base_model, preview_url, preview_nsfw_level, from_civitai, favorite, notes, usage_tips,"
            " civitai_id, civitai_model_id, civitai_name, trained_words, exclude, db_checked, last_checked_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )

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
    return PersistentModelCache.get_default()
