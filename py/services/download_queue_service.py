from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from typing import Any, Optional

from ..utils.cache_paths import get_cache_base_dir

logger = logging.getLogger(__name__)


def _resolve_database_path() -> str:
    base_dir = get_cache_base_dir(create=True)
    history_dir = os.path.join(base_dir, "download_history")
    os.makedirs(history_dir, exist_ok=True)
    return os.path.join(history_dir, "download_queue.sqlite")


class DownloadQueueService:
    """Persistent download queue and history manager backed by SQLite.

    Provides a singleton interface for managing a download queue and
    corresponding history table, both stored in a single SQLite database
    under the cache directory.
    """

    _instance: Optional[DownloadQueueService] = None
    _class_lock: asyncio.Lock = asyncio.Lock()

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS download_queue (
            download_id TEXT PRIMARY KEY,
            model_id INTEGER,
            model_version_id INTEGER,
            model_name TEXT NOT NULL DEFAULT '',
            version_name TEXT DEFAULT '',
            thumbnail_url TEXT DEFAULT '',
            source TEXT,
            file_params TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            priority INTEGER DEFAULT 0,
            progress INTEGER DEFAULT 0,
            bytes_downloaded INTEGER DEFAULT 0,
            total_bytes INTEGER,
            bytes_per_second REAL DEFAULT 0.0,
            error TEXT,
            file_path TEXT,
            added_at REAL NOT NULL,
            started_at REAL,
            completed_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_dq_status ON download_queue(status);
        CREATE INDEX IF NOT EXISTS idx_dq_added ON download_queue(added_at);

        CREATE TABLE IF NOT EXISTS download_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            download_id TEXT,
            model_id INTEGER,
            model_version_id INTEGER,
            model_name TEXT NOT NULL DEFAULT '',
            version_name TEXT DEFAULT '',
            thumbnail_url TEXT DEFAULT '',
            status TEXT NOT NULL,
            error TEXT,
            file_path TEXT,
            bytes_downloaded INTEGER DEFAULT 0,
            total_bytes INTEGER,
            completed_at REAL NOT NULL,
            is_already_exists INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_dh_completed ON download_history(completed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_dh_status ON download_history(status);
    """

    @classmethod
    async def get_instance(cls) -> DownloadQueueService:
        """Return the singleton instance, creating it if necessary."""
        async with cls._class_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or _resolve_database_path()
        self._lock = asyncio.Lock()
        self._conn: Optional[sqlite3.Connection] = None
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
        """Return the resolved database file path."""
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

    # ------------------------------------------------------------------
    # Queue methods
    # ------------------------------------------------------------------

    async def add_to_queue(
        self,
        download_id: str,
        model_id: Optional[int] = None,
        model_version_id: Optional[int] = None,
        model_name: str = "",
        version_name: str = "",
        thumbnail_url: str = "",
        source: Optional[str] = None,
        file_params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Insert a new download into the queue.

        Returns the inserted row as a dict (or an empty dict if the
        download_id already exists).
        """
        now = time.time()
        file_params_json = json.dumps(file_params) if file_params is not None else None

        async with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT OR IGNORE INTO download_queue (
                    download_id, model_id, model_version_id, model_name,
                    version_name, thumbnail_url, source, file_params,
                    status, priority, added_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?)
                """,
                (
                    download_id,
                    model_id,
                    model_version_id,
                    model_name,
                    version_name,
                    thumbnail_url,
                    source,
                    file_params_json,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM download_queue WHERE download_id = ?",
                (download_id,),
            ).fetchone()

        return dict(row) if row else {}

    async def get_queue(self) -> list[dict[str, Any]]:
        """Return all items in the queue ordered by priority then added time."""
        async with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM download_queue ORDER BY priority DESC, added_at ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    async def get_queued_count(self) -> int:
        """Return the number of items with status ``'queued'``."""
        async with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM download_queue WHERE status = 'queued'"
            ).fetchone()
        return row["cnt"] if row else 0

    async def update_status(
        self,
        download_id: str,
        status: str,
        **extra: Any,
    ) -> bool:
        """Update the status and/or extra fields of a queue item.

        Accepted extra keyword arguments:
        ``progress``, ``error``, ``file_path``, ``bytes_downloaded``,
        ``total_bytes``, ``bytes_per_second``.

        Returns ``True`` if a row was updated.
        """
        allowed_extra = {
            "progress",
            "error",
            "file_path",
            "bytes_downloaded",
            "total_bytes",
            "bytes_per_second",
        }

        set_clauses: list[str] = ["status = ?"]
        params: list[Any] = [status]
        now = time.time()

        if status in ("downloading",):
            set_clauses.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
        if status in ("completed", "failed", "canceled"):
            set_clauses.append("completed_at = ?")
            params.append(now)

        for key, value in extra.items():
            if key in allowed_extra:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        params.append(download_id)

        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                f"UPDATE download_queue SET {', '.join(set_clauses)} "
                "WHERE download_id = ?",
                params,
            )
            conn.commit()
        return cursor.rowcount > 0

    async def remove_from_queue(self, download_id: str) -> bool:
        """Remove a single item from the queue by download_id.

        Returns ``True`` if a row was deleted.
        """
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM download_queue WHERE download_id = ?",
                (download_id,),
            )
            conn.commit()
        return cursor.rowcount > 0

    async def move_to_top(self, download_id: str) -> bool:
        """Move an item to the front of the queue (highest priority).

        Returns ``True`` if the item was found and updated.
        """
        async with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT priority FROM download_queue WHERE download_id = ?",
                (download_id,),
            ).fetchone()
            if row is None:
                return False

            max_row = conn.execute(
                "SELECT MAX(priority) AS mx FROM download_queue"
            ).fetchone()
            max_priority: int = max_row["mx"] if max_row["mx"] is not None else 0

            conn.execute(
                "UPDATE download_queue SET priority = ? WHERE download_id = ?",
                (max_priority + 1, download_id),
            )
            conn.commit()
        return True

    async def move_to_end(self, download_id: str) -> bool:
        """Move an item to the end of the queue (lowest priority).

        Returns ``True`` if the item was found and updated.
        """
        async with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT priority FROM download_queue WHERE download_id = ?",
                (download_id,),
            ).fetchone()
            if row is None:
                return False

            min_row = conn.execute(
                "SELECT MIN(priority) AS mn FROM download_queue"
            ).fetchone()
            min_priority: int = min_row["mn"] if min_row["mn"] is not None else 0

            conn.execute(
                "UPDATE download_queue SET priority = ? WHERE download_id = ?",
                (min_priority - 1, download_id),
            )
            conn.commit()
        return True

    async def clear_queue(self, status_filter: Optional[str] = None) -> int:
        """Remove items from the queue.

        When *status_filter* is provided only items with that status are
        deleted.  Returns the number of deleted rows.
        """
        async with self._lock:
            conn = self._get_conn()
            if status_filter is not None:
                cursor = conn.execute(
                    "DELETE FROM download_queue WHERE status = ?",
                    (status_filter,),
                )
            else:
                cursor = conn.execute("DELETE FROM download_queue")
            conn.commit()
        return cursor.rowcount

    async def complete_download(
        self,
        download_id: str,
        status: str = "completed",
        error: Optional[str] = None,
        file_path: Optional[str] = None,
        bytes_downloaded: int = 0,
        total_bytes: Optional[int] = None,
        completed_at: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """Atomically move a download from the queue into the history table.

        Looks up the queue record by ``download_id``, deletes it from the
        queue, and inserts a corresponding history entry with the given
        terminal status (``completed``, ``failed``, or ``canceled``).

        When *completed_at* is provided it is used as the completion
        timestamp; otherwise ``time.time()`` is used.

        Returns the original queue record (before deletion) on success,
        or ``None`` if the download was not found in the queue.
        """
        async with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM download_queue WHERE download_id = ?",
                (download_id,),
            ).fetchone()
            if row is None:
                return None

            now = completed_at if completed_at is not None else time.time()
            conn.execute(
                "DELETE FROM download_queue WHERE download_id = ?",
                (download_id,),
            )
            conn.execute(
                """
                INSERT INTO download_history (
                    download_id, model_id, model_version_id, model_name,
                    version_name, thumbnail_url, status, error, file_path,
                    bytes_downloaded, total_bytes, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["download_id"],
                    row["model_id"],
                    row["model_version_id"],
                    row["model_name"],
                    row["version_name"],
                    row["thumbnail_url"],
                    status,
                    error,
                    file_path,
                    bytes_downloaded,
                    total_bytes,
                    now,
                ),
            )
            conn.commit()
        return dict(row)

    async def pop_next_download(self) -> Optional[dict[str, Any]]:
        """Atomically fetch and mark the next queued item as ``downloading``.

        The item with the highest priority (and earliest ``added_at``
        among ties) whose status is ``'queued'`` is selected, set to
        ``'downloading'``, and returned as a dict.  Returns ``None`` if
        the queue is empty.
        """
        async with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                """
                SELECT * FROM download_queue
                WHERE status = 'queued'
                ORDER BY priority DESC, added_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None

            download_id = row["download_id"]
            now = time.time()
            conn.execute(
                "UPDATE download_queue SET status = 'downloading', "
                "started_at = COALESCE(started_at, ?) "
                "WHERE download_id = ?",
                (now, download_id),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM download_queue WHERE download_id = ?",
                (download_id,),
            ).fetchone()

        return dict(updated) if updated else None

    # ------------------------------------------------------------------
    # History methods
    # ------------------------------------------------------------------

    async def add_to_history(
        self,
        download_id: Optional[str] = None,
        model_id: Optional[int] = None,
        model_version_id: Optional[int] = None,
        model_name: str = "",
        version_name: str = "",
        thumbnail_url: str = "",
        status: str = "completed",
        error: Optional[str] = None,
        file_path: Optional[str] = None,
        bytes_downloaded: int = 0,
        total_bytes: Optional[int] = None,
        is_already_exists: int = 0,
    ) -> int:
        """Insert a record into the download history.

        Returns the ``id`` (AUTOINCREMENT primary key) of the newly
        inserted row.
        """
        now = time.time()

        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                """
                INSERT INTO download_history (
                    download_id, model_id, model_version_id, model_name,
                    version_name, thumbnail_url, status, error, file_path,
                    bytes_downloaded, total_bytes, completed_at, is_already_exists
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    download_id,
                    model_id,
                    model_version_id,
                    model_name,
                    version_name,
                    thumbnail_url,
                    status,
                    error,
                    file_path,
                    bytes_downloaded,
                    total_bytes,
                    now,
                    is_already_exists,
                ),
            )
            conn.commit()
        return cursor.lastrowid or 0

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return a page of download history entries.

        Returns a dict with keys ``items``, ``total``, ``limit``, and
        ``offset``.
        """
        async with self._lock:
            conn = self._get_conn()

            if status_filter is not None:
                count_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM download_history WHERE status = ?",
                    (status_filter,),
                ).fetchone()
                rows = conn.execute(
                    "SELECT * FROM download_history WHERE status = ? "
                    "ORDER BY completed_at DESC LIMIT ? OFFSET ?",
                    (status_filter, limit, offset),
                ).fetchall()
            else:
                count_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM download_history"
                ).fetchone()
                rows = conn.execute(
                    "SELECT * FROM download_history "
                    "ORDER BY completed_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()

        return {
            "items": [dict(row) for row in rows],
            "total": count_row["cnt"] if count_row else 0,
            "limit": limit,
            "offset": offset,
        }

    async def delete_history_item(self, id: int) -> bool:
        """Delete a single history entry by its *id*.

        Returns ``True`` if a row was deleted.
        """
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM download_history WHERE id = ?",
                (id,),
            )
            conn.commit()
        return cursor.rowcount > 0

    async def clear_history(
        self,
        status_filter: Optional[str] = None,
        before_timestamp: Optional[float] = None,
    ) -> int:
        """Remove history entries matching the optional filters.

        Both ``status_filter`` and ``before_timestamp`` can be combined
        (AND logic).  Returns the number of deleted rows.
        """
        async with self._lock:
            conn = self._get_conn()

            clauses: list[str] = []
            params: list[Any] = []

            if status_filter is not None:
                clauses.append("status = ?")
                params.append(status_filter)
            if before_timestamp is not None:
                clauses.append("completed_at < ?")
                params.append(before_timestamp)

            where = ""
            if clauses:
                where = " WHERE " + " AND ".join(clauses)

            cursor = conn.execute(
                f"DELETE FROM download_history{where}",
                params,
            )
            conn.commit()
        return cursor.rowcount

    async def get_history_count(self, status_filter: Optional[str] = None) -> int:
        """Return the number of history entries, optionally filtered by status."""
        async with self._lock:
            conn = self._get_conn()
            if status_filter is not None:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM download_history WHERE status = ?",
                    (status_filter,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM download_history"
                ).fetchone()
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # Retry
    # ------------------------------------------------------------------

    async def retry_from_history(self, item_id: int) -> Optional[dict[str, Any]]:
        """Re-queue a failed or canceled download from history.

        Looks up the history record by its primary key.  If the status is
        ``failed`` or ``canceled`` a new queue entry is created with the
        same model metadata and a fresh download id.
        """
        async with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM download_history WHERE id = ?",
                (item_id,),
            ).fetchone()
            if row is None:
                return None
            status = str(row["status"])
            if status not in ("failed", "canceled"):
                return None

            import uuid

            new_id = str(uuid.uuid4())
            now = time.time()
            conn.execute(
                """
                INSERT INTO download_queue (
                    download_id, model_id, model_version_id, model_name,
                    version_name, thumbnail_url, source, file_params,
                    status, priority, added_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'queued', 0, ?)
                """,
                (
                    new_id,
                    row["model_id"],
                    row["model_version_id"],
                    row["model_name"],
                    row["version_name"],
                    row["thumbnail_url"],
                    "retry",
                    now,
                ),
            )
            conn.commit()
            queued = conn.execute(
                "SELECT * FROM download_queue WHERE download_id = ?",
                (new_id,),
            ).fetchone()

        return dict(queued) if queued else None

    async def retry_all_failed(self) -> int:
        """Re-queue all failed and canceled downloads from history.

        Returns the number of items that were re-queued.
        """
        async with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM download_history WHERE status IN ('failed', 'canceled')"
            ).fetchall()
            if not rows:
                return 0

            import uuid

            now = time.time()
            count = 0
            for row in rows:
                new_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO download_queue (
                        download_id, model_id, model_version_id, model_name,
                        version_name, thumbnail_url, source, file_params,
                        status, priority, added_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'queued', 0, ?)
                    """,
                    (
                        new_id,
                        row["model_id"],
                        row["model_version_id"],
                        row["model_name"],
                        row["version_name"],
                        row["thumbnail_url"],
                        "retry",
                        now,
                    ),
                )
                count += 1
            conn.commit()

        return count

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict[str, int]:
        """Return aggregate counts across both tables.

        Returns a dict with keys ``queued``, ``downloading``, ``paused``
        (all from the queue table) and ``completed``, ``failed``,
        ``canceled`` (all from the history table).
        """
        async with self._lock:
            conn = self._get_conn()

            queue_rows = conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM download_queue GROUP BY status"
            ).fetchall()
            queue_stats: dict[str, int] = {}
            for row in queue_rows:
                queue_stats[str(row["status"])] = row["cnt"]

            history_rows = conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM download_history GROUP BY status"
            ).fetchall()
            history_stats: dict[str, int] = {}
            for row in history_rows:
                history_stats[str(row["status"])] = row["cnt"]

        return {
            "queued": queue_stats.get("queued", 0),
            "downloading": queue_stats.get("downloading", 0),
            "paused": queue_stats.get("paused", 0),
            "completed": history_stats.get("completed", 0),
            "failed": history_stats.get("failed", 0),
            "canceled": history_stats.get("canceled", 0),
        }
