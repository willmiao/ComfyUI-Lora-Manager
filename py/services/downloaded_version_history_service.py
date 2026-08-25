# pyright: reportImportCycles=false
# Lazy (function-local) imports still count as static edges in basedpyright's
# reportImportCycles, so the ServiceRegistry singleton pattern necessarily forms
# import cycles. Breaking them would require an architectural refactor.
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from typing import Iterable, Mapping, Optional, Sequence

from ..utils.cache_paths import get_cache_base_dir
from .settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


def _normalize_model_type(model_type: str | None) -> Optional[str]:
    if not isinstance(model_type, str):
        return None
    normalized = model_type.strip().lower()
    if normalized in {"lora", "locon", "dora"}:
        return "lora"
    if normalized == "checkpoint":
        return "checkpoint"
    if normalized in {"embedding", "textualinversion"}:
        return "embedding"
    return None


def _normalize_int(value) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_database_path() -> str:
    base_dir = get_cache_base_dir(create=True)
    history_dir = os.path.join(base_dir, "download_history")
    os.makedirs(history_dir, exist_ok=True)
    return os.path.join(history_dir, "downloaded_versions.sqlite")


class DownloadedVersionHistoryService:
    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS downloaded_model_versions (
            model_type TEXT NOT NULL,
            version_id INTEGER NOT NULL,
            model_id INTEGER,
            first_seen_at REAL NOT NULL,
            last_seen_at REAL NOT NULL,
            source TEXT NOT NULL,
            last_file_path TEXT,
            last_library_name TEXT,
            is_deleted_override INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (model_type, version_id)
        );
        CREATE INDEX IF NOT EXISTS idx_downloaded_model_versions_model
            ON downloaded_model_versions(model_type, model_id);
        CREATE TABLE IF NOT EXISTS downloaded_version_files (
            model_type TEXT NOT NULL,
            version_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            file_name TEXT,
            downloaded_at REAL NOT NULL,
            PRIMARY KEY (model_type, version_id, file_id)
        );
    """

    def __init__(self, db_path: str | None = None, *, settings_manager=None) -> None:
        self._db_path = db_path or _resolve_database_path()
        self._settings = settings_manager or get_settings_manager()
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None
        self._schema_initialized = False
        self._ensure_directory()
        self._initialize_schema()

    def _ensure_directory(self) -> None:
        directory = os.path.dirname(self._db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _initialize_schema(self) -> None:
        if self._schema_initialized:
            return
        with self._connect() as conn:
            conn.executescript(self._SCHEMA)
            conn.commit()
        self._schema_initialized = True

    def get_database_path(self) -> str:
        return self._db_path

    def close(self) -> None:
        """Close the persistent SQLite connection, if open.

        This is called before plugin update operations to release the
        database file lock on Windows, allowing ``shutil.rmtree()`` to
        succeed when the cache resides inside the plugin directory.
        """
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None

    def _get_active_library_name(self) -> str | None:
        try:
            value = self._settings.get_active_library_name()
        except Exception:
            return None
        return value or None

    async def mark_downloaded(
        self,
        model_type: str,
        version_id: int,
        *,
        model_id: int | None = None,
        source: str = "manual",
        file_path: str | None = None,
        library_name: str | None = None,
        file_id: int | None = None,
        file_name: str | None = None,
    ) -> None:
        normalized_type = _normalize_model_type(model_type)
        normalized_version_id = _normalize_int(version_id)
        normalized_model_id = _normalize_int(model_id)
        normalized_file_id = _normalize_int(file_id)
        if normalized_type is None or normalized_version_id is None:
            return

        active_library_name = library_name or self._get_active_library_name()
        timestamp = time.time()

        async with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO downloaded_model_versions (
                    model_type, version_id, model_id, first_seen_at, last_seen_at,
                    source, last_file_path, last_library_name, is_deleted_override
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(model_type, version_id) DO UPDATE SET
                    model_id = COALESCE(excluded.model_id, downloaded_model_versions.model_id),
                    last_seen_at = excluded.last_seen_at,
                    source = excluded.source,
                    last_file_path = COALESCE(excluded.last_file_path, downloaded_model_versions.last_file_path),
                    last_library_name = COALESCE(excluded.last_library_name, downloaded_model_versions.last_library_name),
                    is_deleted_override = 0
                """,
                (
                    normalized_type,
                    normalized_version_id,
                    normalized_model_id,
                    timestamp,
                    timestamp,
                    source,
                    file_path,
                    active_library_name,
                ),
            )
            if normalized_file_id is not None:
                # Per-file history for multi-file versions (#1058)
                conn.execute(
                    """
                    INSERT INTO downloaded_version_files (
                        model_type, version_id, file_id, file_name, downloaded_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(model_type, version_id, file_id) DO UPDATE SET
                        file_name = COALESCE(excluded.file_name, downloaded_version_files.file_name),
                        downloaded_at = excluded.downloaded_at
                    """,
                    (
                        normalized_type,
                        normalized_version_id,
                        normalized_file_id,
                        file_name,
                        timestamp,
                    ),
                )
            conn.commit()

    async def mark_downloaded_bulk(
        self,
        model_type: str,
        records: Sequence[Mapping[str, object]],
        *,
        source: str = "scan",
        library_name: str | None = None,
    ) -> None:
        normalized_type = _normalize_model_type(model_type)
        if normalized_type is None or not records:
            return

        timestamp = time.time()
        active_library_name = library_name or self._get_active_library_name()
        payload: list[tuple[object, ...]] = []
        for record in records:
            version_id = _normalize_int(record.get("version_id"))
            if version_id is None:
                continue
            payload.append(
                (
                    normalized_type,
                    version_id,
                    _normalize_int(record.get("model_id")),
                    timestamp,
                    timestamp,
                    source,
                    record.get("file_path"),
                    active_library_name,
                )
            )

        if not payload:
            return

        async with self._lock:
            # The connection is created with check_same_thread=False and all
            # access is serialized by self._lock, so the executemany upsert +
            # commit can run in the default executor without blocking the
            # event loop on large hydration payloads.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._mark_downloaded_bulk_sync, payload)

    def _mark_downloaded_bulk_sync(self, payload: Sequence[tuple[object, ...]]) -> None:
        """Synchronous executemany upsert + commit; runs in a worker thread."""
        conn = self._get_conn()
        conn.executemany(
            """
            INSERT INTO downloaded_model_versions (
                model_type, version_id, model_id, first_seen_at, last_seen_at,
                source, last_file_path, last_library_name, is_deleted_override
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(model_type, version_id) DO UPDATE SET
                model_id = COALESCE(excluded.model_id, downloaded_model_versions.model_id),
                last_seen_at = excluded.last_seen_at,
                source = excluded.source,
                last_file_path = COALESCE(excluded.last_file_path, downloaded_model_versions.last_file_path),
                last_library_name = COALESCE(excluded.last_library_name, downloaded_model_versions.last_library_name),
                is_deleted_override = 0
            """,
            payload,
        )
        conn.commit()

    async def mark_as_deleted(self, model_type: str, version_id: int) -> None:
        normalized_type = _normalize_model_type(model_type)
        normalized_version_id = _normalize_int(version_id)
        if normalized_type is None or normalized_version_id is None:
            return

        timestamp = time.time()

        async with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO downloaded_model_versions (
                    model_type, version_id, model_id, first_seen_at, last_seen_at,
                    source, last_file_path, last_library_name, is_deleted_override
                ) VALUES (?, ?, NULL, ?, ?, 'manual', NULL, ?, 1)
                ON CONFLICT(model_type, version_id) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    source = excluded.source,
                    last_library_name = COALESCE(excluded.last_library_name, downloaded_model_versions.last_library_name),
                    is_deleted_override = 1
                """,
                (
                    normalized_type,
                    normalized_version_id,
                    timestamp,
                    timestamp,
                    self._get_active_library_name(),
                ),
            )
            # Whole-version deletion also clears the per-file records (#1058)
            conn.execute(
                """
                DELETE FROM downloaded_version_files
                WHERE model_type = ? AND version_id = ?
                """,
                (normalized_type, normalized_version_id),
            )
            conn.commit()

    async def mark_file_deleted(
        self, model_type: str, version_id: int, file_id: int
    ) -> None:
        """Drop a single file record of a version, keeping siblings (#1058)."""
        normalized_type = _normalize_model_type(model_type)
        normalized_version_id = _normalize_int(version_id)
        normalized_file_id = _normalize_int(file_id)
        if (
            normalized_type is None
            or normalized_version_id is None
            or normalized_file_id is None
        ):
            return

        async with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                DELETE FROM downloaded_version_files
                WHERE model_type = ? AND version_id = ? AND file_id = ?
                """,
                (normalized_type, normalized_version_id, normalized_file_id),
            )
            conn.commit()

    async def get_downloaded_file_ids(
        self, model_type: str, version_id: int
    ) -> list[int]:
        """Return the CivitAI file ids recorded as downloaded for a version."""
        normalized_type = _normalize_model_type(model_type)
        normalized_version_id = _normalize_int(version_id)
        if normalized_type is None or normalized_version_id is None:
            return []

        async with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT file_id
                FROM downloaded_version_files
                WHERE model_type = ? AND version_id = ?
                ORDER BY file_id ASC
                """,
                (normalized_type, normalized_version_id),
            ).fetchall()
        return [int(row["file_id"]) for row in rows]

    async def has_been_downloaded(self, model_type: str, version_id: int) -> bool:
        normalized_type = _normalize_model_type(model_type)
        normalized_version_id = _normalize_int(version_id)
        if normalized_type is None or normalized_version_id is None:
            return False

        async with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                """
                SELECT is_deleted_override
                FROM downloaded_model_versions
                WHERE model_type = ? AND version_id = ?
                """,
                (normalized_type, normalized_version_id),
            ).fetchone()
        return bool(row) and not bool(row["is_deleted_override"])

    async def get_downloaded_version_ids(
        self, model_type: str, model_id: int
    ) -> list[int]:
        normalized_type = _normalize_model_type(model_type)
        normalized_model_id = _normalize_int(model_id)
        if normalized_type is None or normalized_model_id is None:
            return []

        async with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT version_id
                FROM downloaded_model_versions
                WHERE model_type = ? AND model_id = ? AND is_deleted_override = 0
                ORDER BY version_id ASC
                """,
                (normalized_type, normalized_model_id),
            ).fetchall()
        return [int(row["version_id"]) for row in rows]

    async def get_downloaded_version_ids_bulk(
        self, model_type: str, model_ids: Iterable[int]
    ) -> dict[int, set[int]]:
        normalized_type = _normalize_model_type(model_type)
        if normalized_type is None:
            return {}

        normalized_model_ids = sorted(
            {
                value
                for value in (_normalize_int(model_id) for model_id in model_ids)
                if value is not None
            }
        )
        if not normalized_model_ids:
            return {}

        placeholders = ", ".join(["?"] * len(normalized_model_ids))
        params: list[object] = [normalized_type, *normalized_model_ids]

        async with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                f"""
                SELECT model_id, version_id
                FROM downloaded_model_versions
                WHERE model_type = ?
                  AND model_id IN ({placeholders})
                  AND is_deleted_override = 0
                """,
                params,
            ).fetchall()

        result: dict[int, set[int]] = {}
        for row in rows:
            model_id = _normalize_int(row["model_id"])
            version_id = _normalize_int(row["version_id"])
            if model_id is None or version_id is None:
                continue
            result.setdefault(model_id, set()).add(version_id)
        return result
