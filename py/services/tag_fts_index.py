"""SQLite FTS5-based full-text search index for tags.

This module provides fast tag search using SQLite's FTS5 extension,
enabling sub-100ms search times for 221k+ Danbooru/e621 tags.
"""

from __future__ import annotations

import csv
import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..utils.cache_paths import CacheType, resolve_cache_path_with_migration

logger = logging.getLogger(__name__)


# Category definitions for Danbooru and e621
CATEGORY_NAMES = {
    # Danbooru categories
    0: "general",
    1: "artist",
    3: "copyright",
    4: "character",
    5: "meta",
    # e621 categories
    7: "general",
    8: "artist",
    10: "copyright",
    11: "character",
    12: "species",
    14: "meta",
    15: "lore",
}

# Map category names to their IDs (for filtering)
CATEGORY_NAME_TO_IDS = {
    "general": [0, 7],
    "artist": [1, 8],
    "copyright": [3, 10],
    "character": [4, 11],
    "meta": [5, 14],
    "species": [12],
    "lore": [15],
}


class TagFTSIndex:
    """SQLite FTS5-based full-text search index for tags.

    Provides fast prefix-based search across the Danbooru/e621 tag database.
    Supports category-based filtering and returns enriched results with
    post counts and category information.
    """

    _DEFAULT_FILENAME = "tag_fts.sqlite"
    _CSV_FILENAME = "danbooru_e621_merged.csv"

    def __init__(self, db_path: Optional[str] = None, csv_path: Optional[str] = None) -> None:
        """Initialize the FTS index.

        Args:
            db_path: Optional path to the SQLite database file.
                     If not provided, uses the default location in settings directory.
            csv_path: Optional path to the CSV file containing tag data.
                      If not provided, looks in the refs/ directory.
        """
        self._db_path = db_path or self._resolve_default_db_path()
        self._csv_path = csv_path or self._resolve_default_csv_path()
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._indexing_in_progress = False
        self._schema_initialized = False
        self._warned_not_ready = False

        # Ensure directory exists
        try:
            directory = os.path.dirname(self._db_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create FTS index directory %s: %s", directory, exc)

    def _resolve_default_db_path(self) -> str:
        """Resolve the default database path."""
        env_override = os.environ.get("LORA_MANAGER_TAG_FTS_DB")
        return resolve_cache_path_with_migration(
            CacheType.TAG_FTS,
            env_override=env_override,
        )

    def _resolve_default_csv_path(self) -> str:
        """Resolve the default CSV file path."""
        # Look for the CSV in the refs/ directory relative to the package
        package_dir = Path(__file__).parent.parent.parent
        csv_path = package_dir / "refs" / self._CSV_FILENAME
        return str(csv_path)

    def get_database_path(self) -> str:
        """Return the resolved database path."""
        return self._db_path

    def get_csv_path(self) -> str:
        """Return the resolved CSV path."""
        return self._csv_path

    def is_ready(self) -> bool:
        """Check if the FTS index is ready for queries."""
        return self._ready.is_set()

    def is_indexing(self) -> bool:
        """Check if indexing is currently in progress."""
        return self._indexing_in_progress

    def initialize(self) -> None:
        """Initialize the database schema."""
        if self._schema_initialized:
            return

        with self._lock:
            if self._schema_initialized:
                return

            try:
                conn = self._connect()
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.executescript("""
                        -- FTS5 virtual table for full-text search
                        CREATE VIRTUAL TABLE IF NOT EXISTS tag_fts USING fts5(
                            tag_name,
                            tokenize='unicode61 remove_diacritics 2'
                        );

                        -- Tags table with metadata
                        CREATE TABLE IF NOT EXISTS tags (
                            rowid INTEGER PRIMARY KEY,
                            tag_name TEXT UNIQUE NOT NULL,
                            category INTEGER NOT NULL DEFAULT 0,
                            post_count INTEGER NOT NULL DEFAULT 0
                        );

                        -- Indexes for efficient filtering
                        CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category);
                        CREATE INDEX IF NOT EXISTS idx_tags_post_count ON tags(post_count DESC);

                        -- Index version tracking
                        CREATE TABLE IF NOT EXISTS fts_metadata (
                            key TEXT PRIMARY KEY,
                            value TEXT
                        );
                    """)
                    conn.commit()
                    self._schema_initialized = True
                    logger.debug("Tag FTS index schema initialized at %s", self._db_path)
                finally:
                    conn.close()
            except Exception as exc:
                logger.error("Failed to initialize tag FTS schema: %s", exc)

    def build_index(self) -> None:
        """Build the FTS index from the CSV file.

        This method parses the danbooru_e621_merged.csv file and creates
        the FTS index for fast searching.
        """
        if self._indexing_in_progress:
            logger.warning("Tag FTS indexing already in progress, skipping")
            return

        if not os.path.exists(self._csv_path):
            logger.warning("CSV file not found at %s, cannot build tag index", self._csv_path)
            return

        self._indexing_in_progress = True
        self._ready.clear()
        start_time = time.time()

        try:
            self.initialize()
            if not self._schema_initialized:
                logger.error("Cannot build tag FTS index: schema not initialized")
                return

            with self._lock:
                conn = self._connect()
                try:
                    conn.execute("BEGIN")

                    # Clear existing data
                    conn.execute("DELETE FROM tag_fts")
                    conn.execute("DELETE FROM tags")

                    # Parse CSV and insert in batches
                    batch_size = 500
                    rows = []
                    total_inserted = 0

                    with open(self._csv_path, "r", encoding="utf-8") as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if len(row) < 3:
                                continue

                            tag_name = row[0].strip()
                            if not tag_name:
                                continue

                            try:
                                category = int(row[1])
                            except (ValueError, IndexError):
                                category = 0

                            try:
                                post_count = int(row[2])
                            except (ValueError, IndexError):
                                post_count = 0

                            rows.append((tag_name, category, post_count))

                            if len(rows) >= batch_size:
                                self._insert_batch(conn, rows)
                                total_inserted += len(rows)
                                rows = []

                    # Insert remaining rows
                    if rows:
                        self._insert_batch(conn, rows)
                        total_inserted += len(rows)

                    # Update metadata
                    conn.execute(
                        "INSERT OR REPLACE INTO fts_metadata (key, value) VALUES (?, ?)",
                        ("last_build_time", str(time.time()))
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO fts_metadata (key, value) VALUES (?, ?)",
                        ("tag_count", str(total_inserted))
                    )

                    conn.commit()
                    elapsed = time.time() - start_time
                    logger.info("Tag FTS index built: %d tags indexed in %.2fs", total_inserted, elapsed)
                finally:
                    conn.close()

            self._ready.set()

        except Exception as exc:
            logger.error("Failed to build tag FTS index: %s", exc, exc_info=True)
        finally:
            self._indexing_in_progress = False

    def _insert_batch(self, conn: sqlite3.Connection, rows: List[tuple]) -> None:
        """Insert a batch of rows into the database."""
        # Insert into tags table
        conn.executemany(
            "INSERT OR IGNORE INTO tags (tag_name, category, post_count) VALUES (?, ?, ?)",
            rows
        )

        # Get rowids and insert into FTS table
        tag_names = [row[0] for row in rows]
        placeholders = ",".join("?" * len(tag_names))
        cursor = conn.execute(
            f"SELECT rowid, tag_name FROM tags WHERE tag_name IN ({placeholders})",
            tag_names
        )

        fts_rows = [(tag_name,) for rowid, tag_name in cursor.fetchall()]
        if fts_rows:
            conn.executemany("INSERT INTO tag_fts (tag_name) VALUES (?)", fts_rows)

    def ensure_ready(self) -> bool:
        """Ensure the index is ready, building if necessary.

        Returns:
            True if the index is ready, False otherwise.
        """
        if self.is_ready():
            return True

        # Check if index already exists and has data
        self.initialize()
        if self._schema_initialized:
            count = self.get_indexed_count()
            if count > 0:
                self._ready.set()
                logger.debug("Tag FTS index already populated with %d tags", count)
                return True

        # Build the index
        self.build_index()
        return self.is_ready()

    def search(
        self,
        query: str,
        categories: Optional[List[int]] = None,
        limit: int = 20
    ) -> List[Dict]:
        """Search tags using FTS5 with prefix matching.

        Args:
            query: The search query string.
            categories: Optional list of category IDs to filter by.
            limit: Maximum number of results to return.

        Returns:
            List of dictionaries with tag_name, category, and post_count.
        """
        # Ensure index is ready (lazy initialization)
        if not self.ensure_ready():
            if not self._warned_not_ready:
                logger.debug("Tag FTS index not ready, returning empty results")
                self._warned_not_ready = True
            return []

        if not query or not query.strip():
            return []

        fts_query = self._build_fts_query(query)
        if not fts_query:
            return []

        try:
            with self._lock:
                conn = self._connect(readonly=True)
                try:
                    # Build the SQL query
                    if categories:
                        placeholders = ",".join("?" * len(categories))
                        sql = f"""
                            SELECT t.tag_name, t.category, t.post_count
                            FROM tags t
                            WHERE t.tag_name IN (
                                SELECT tag_name FROM tag_fts WHERE tag_fts MATCH ?
                            )
                            AND t.category IN ({placeholders})
                            ORDER BY t.post_count DESC
                            LIMIT ?
                        """
                        params = [fts_query] + categories + [limit]
                    else:
                        sql = """
                            SELECT t.tag_name, t.category, t.post_count
                            FROM tags t
                            WHERE t.tag_name IN (
                                SELECT tag_name FROM tag_fts WHERE tag_fts MATCH ?
                            )
                            ORDER BY t.post_count DESC
                            LIMIT ?
                        """
                        params = [fts_query, limit]

                    cursor = conn.execute(sql, params)
                    results = []
                    for row in cursor.fetchall():
                        results.append({
                            "tag_name": row[0],
                            "category": row[1],
                            "post_count": row[2],
                        })
                    return results
                finally:
                    conn.close()
        except Exception as exc:
            logger.debug("Tag FTS search error for query '%s': %s", query, exc)
            return []

    def get_indexed_count(self) -> int:
        """Return the number of tags currently indexed."""
        if not self._schema_initialized:
            return 0

        try:
            with self._lock:
                conn = self._connect(readonly=True)
                try:
                    cursor = conn.execute("SELECT COUNT(*) FROM tags")
                    result = cursor.fetchone()
                    return result[0] if result else 0
                finally:
                    conn.close()
        except Exception:
            return 0

    def clear(self) -> bool:
        """Clear all data from the FTS index.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute("DELETE FROM tag_fts")
                    conn.execute("DELETE FROM tags")
                    conn.commit()
                    self._ready.clear()
                    return True
                finally:
                    conn.close()
        except Exception as exc:
            logger.error("Failed to clear tag FTS index: %s", exc)
            return False

    # Internal helpers

    def _connect(self, readonly: bool = False) -> sqlite3.Connection:
        """Create a database connection."""
        uri = False
        path = self._db_path
        if readonly:
            if not os.path.exists(path):
                raise FileNotFoundError(path)
            path = f"file:{path}?mode=ro"
            uri = True
        conn = sqlite3.connect(path, check_same_thread=False, uri=uri)
        conn.row_factory = sqlite3.Row
        return conn

    def _build_fts_query(self, query: str) -> str:
        """Build an FTS5 query string with prefix matching.

        Args:
            query: The user's search query.

        Returns:
            FTS5 query string.
        """
        # Split query into words and clean them
        words = query.lower().split()
        if not words:
            return ""

        # Escape and add prefix wildcard to each word
        prefix_terms = []
        for word in words:
            escaped = self._escape_fts_query(word)
            if escaped:
                # Add prefix wildcard for substring-like matching
                prefix_terms.append(f"{escaped}*")

        if not prefix_terms:
            return ""

        # Combine terms with implicit AND (all words must match)
        return " ".join(prefix_terms)

    def _escape_fts_query(self, text: str) -> str:
        """Escape special FTS5 characters.

        FTS5 special characters: " ( ) * : ^ -
        We keep * for prefix matching but escape others.
        """
        if not text:
            return ""

        # Replace FTS5 special characters with space
        special = ['"', "(", ")", "*", ":", "^", "-", "{", "}", "[", "]"]
        result = text
        for char in special:
            result = result.replace(char, " ")

        # Collapse multiple spaces and strip
        result = re.sub(r"\s+", " ", result).strip()
        return result


# Singleton instance
_tag_fts_index: Optional[TagFTSIndex] = None
_tag_fts_lock = threading.Lock()


def get_tag_fts_index() -> TagFTSIndex:
    """Get the singleton TagFTSIndex instance."""
    global _tag_fts_index
    if _tag_fts_index is None:
        with _tag_fts_lock:
            if _tag_fts_index is None:
                _tag_fts_index = TagFTSIndex()
    return _tag_fts_index


__all__ = [
    "TagFTSIndex",
    "get_tag_fts_index",
    "CATEGORY_NAMES",
    "CATEGORY_NAME_TO_IDS",
]
