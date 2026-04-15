"""SQLite FTS5-based full-text search index for tags.

This module provides fast tag search using SQLite's FTS5 extension,
enabling sub-100ms search times for 221k+ Danbooru/e621 tags.

Supports alias search: when a user searches for an alias (e.g., "miku"),
the system returns the canonical tag (e.g., "hatsune_miku") and indicates
which alias was matched.
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

# Schema version for tracking migrations
SCHEMA_VERSION = 2  # Version 2: Added aliases support


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

    def __init__(
        self, db_path: Optional[str] = None, csv_path: Optional[str] = None
    ) -> None:
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
            logger.warning(
                "Could not create FTS index directory %s: %s", directory, exc
            )

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

                    # Check if we need to migrate from old schema
                    needs_rebuild = self._check_and_migrate_schema(conn)

                    conn.executescript("""
                        -- FTS5 virtual table for full-text search
                        -- searchable_text contains "tag_name alias1 alias2 ..." for alias matching
                        CREATE VIRTUAL TABLE IF NOT EXISTS tag_fts USING fts5(
                            searchable_text,
                            tokenize='unicode61 remove_diacritics 2'
                        );

                        -- Tags table with metadata and aliases
                        CREATE TABLE IF NOT EXISTS tags (
                            rowid INTEGER PRIMARY KEY,
                            tag_name TEXT UNIQUE NOT NULL,
                            category INTEGER NOT NULL DEFAULT 0,
                            post_count INTEGER NOT NULL DEFAULT 0,
                            aliases TEXT DEFAULT ''
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

                    # Set schema version
                    conn.execute(
                        "INSERT OR REPLACE INTO fts_metadata (key, value) VALUES (?, ?)",
                        ("schema_version", str(SCHEMA_VERSION)),
                    )
                    conn.commit()

                    self._schema_initialized = True
                    self._needs_rebuild = needs_rebuild
                    logger.debug(
                        "Tag FTS index schema initialized at %s", self._db_path
                    )
                finally:
                    conn.close()
            except Exception as exc:
                logger.error("Failed to initialize tag FTS schema: %s", exc)

    def _check_and_migrate_schema(self, conn: sqlite3.Connection) -> bool:
        """Check schema version and migrate if necessary.

        Returns:
            True if the index needs to be rebuilt, False otherwise.
        """
        try:
            # Check if fts_metadata table exists
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fts_metadata'"
            )
            if not cursor.fetchone():
                return False  # Fresh database, no migration needed

            # Check schema version
            cursor = conn.execute(
                "SELECT value FROM fts_metadata WHERE key='schema_version'"
            )
            row = cursor.fetchone()
            if not row:
                # Old schema without version, needs rebuild
                logger.info(
                    "Migrating tag FTS index to schema version %d (adding alias support)",
                    SCHEMA_VERSION,
                )
                self._drop_old_tables(conn)
                return True

            current_version = int(row[0])
            if current_version < SCHEMA_VERSION:
                logger.info(
                    "Migrating tag FTS index from version %d to %d",
                    current_version,
                    SCHEMA_VERSION,
                )
                self._drop_old_tables(conn)
                return True

            return False
        except Exception as exc:
            logger.warning("Error checking schema version: %s", exc)
            return False

    def _drop_old_tables(self, conn: sqlite3.Connection) -> None:
        """Drop old tables for schema migration."""
        try:
            conn.executescript("""
                DROP TABLE IF EXISTS tag_fts;
                DROP TABLE IF EXISTS tags;
            """)
            conn.commit()
        except Exception as exc:
            logger.warning("Error dropping old tables: %s", exc)

    def build_index(self) -> None:
        """Build the FTS index from the CSV file.

        This method parses the danbooru_e621_merged.csv file and creates
        the FTS index for fast searching. The CSV format is:
        tag_name,category,post_count,aliases

        Where aliases is a comma-separated string (e.g., "miku,vocaloid_miku,39").
        """
        if self._indexing_in_progress:
            logger.warning("Tag FTS indexing already in progress, skipping")
            return

        if not os.path.exists(self._csv_path):
            logger.warning(
                "CSV file not found at %s, cannot build tag index", self._csv_path
            )
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
                    tags_with_aliases = 0

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

                            # Parse aliases from column 4 (if present)
                            aliases = row[3].strip() if len(row) >= 4 else ""
                            if aliases:
                                tags_with_aliases += 1

                            rows.append((tag_name, category, post_count, aliases))

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
                        ("last_build_time", str(time.time())),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO fts_metadata (key, value) VALUES (?, ?)",
                        ("tag_count", str(total_inserted)),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO fts_metadata (key, value) VALUES (?, ?)",
                        ("schema_version", str(SCHEMA_VERSION)),
                    )

                    conn.commit()
                    elapsed = time.time() - start_time
                    logger.info(
                        "Tag FTS index built: %d tags indexed (%d with aliases) in %.2fs",
                        total_inserted,
                        tags_with_aliases,
                        elapsed,
                    )
                finally:
                    conn.close()

            self._ready.set()

        except Exception as exc:
            logger.error("Failed to build tag FTS index: %s", exc, exc_info=True)
        finally:
            self._indexing_in_progress = False

    def _insert_batch(self, conn: sqlite3.Connection, rows: List[tuple]) -> None:
        """Insert a batch of rows into the database.

        Each row is a tuple of (tag_name, category, post_count, aliases).
        The FTS searchable_text is built as "tag_name alias1 alias2 ..." for alias matching.
        """
        # Insert into tags table (with aliases)
        conn.executemany(
            "INSERT OR IGNORE INTO tags (tag_name, category, post_count, aliases) VALUES (?, ?, ?, ?)",
            rows,
        )

        # Build a map of tag_name -> aliases for FTS insertion
        aliases_map = {row[0]: row[3] for row in rows}

        # Get rowids and insert into FTS table with explicit rowid
        # to ensure tags.rowid matches tag_fts.rowid for JOINs
        tag_names = [row[0] for row in rows]
        placeholders = ",".join("?" * len(tag_names))
        cursor = conn.execute(
            f"SELECT rowid, tag_name FROM tags WHERE tag_name IN ({placeholders})",
            tag_names,
        )

        # Build FTS rows with (rowid, searchable_text) = (tags.rowid, "tag_name alias1 alias2 ...")
        fts_rows = []
        for rowid, tag_name in cursor.fetchall():
            aliases = aliases_map.get(tag_name, "")
            if aliases:
                # Replace commas with spaces to create searchable text
                # Strip "/" prefix from aliases as it's an FTS5 special character
                alias_parts = []
                for alias in aliases.split(","):
                    alias = alias.strip()
                    if alias.startswith("/"):
                        alias = alias[1:]  # Remove leading slash
                    if alias:
                        alias_parts.append(alias)
                searchable_text = (
                    f"{tag_name} {' '.join(alias_parts)}" if alias_parts else tag_name
                )
            else:
                searchable_text = tag_name
            fts_rows.append((rowid, searchable_text))

        if fts_rows:
            conn.executemany(
                "INSERT INTO tag_fts (rowid, searchable_text) VALUES (?, ?)", fts_rows
            )

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
            # Check if schema migration requires rebuild
            if getattr(self, "_needs_rebuild", False):
                logger.info("Schema migration requires index rebuild")
                self._needs_rebuild = False
                self.build_index()
                return self.is_ready()

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
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict]:
        """Search tags using FTS5 with prefix matching.

        Supports alias search: if the query matches an alias rather than
        the tag_name, the result will include a "matched_alias" field.

        Ranking is based on a combination of:
        1. Exact prefix match boost (tag_name starts with query)
        2. Post count to preserve expected autocomplete ordering
        3. FTS5 bm25 relevance score as a deterministic tie-breaker

        Args:
            query: The search query string.
            categories: Optional list of category IDs to filter by.
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            List of dictionaries with tag_name, category, post_count,
            rank_score, and optionally matched_alias.
        """
        search_started_at = time.perf_counter()
        logger.info(
            "LM tag FTS search start query=%r categories=%s limit=%s offset=%s ready=%s indexing=%s",
            query,
            categories,
            limit,
            offset,
            self.is_ready(),
            self.is_indexing(),
        )

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

        logger.info(
            "LM tag FTS search built query=%r fts_query=%r",
            query,
            fts_query,
        )

        query_lower = query.lower().strip()

        try:
            logger.info("LM tag FTS search waiting_for_lock query=%r", query)
            with self._lock:
                logger.info("LM tag FTS search acquired_lock query=%r", query)
                conn = self._connect(readonly=True)
                try:
                    sql, params = self._build_search_statement(
                        query_lower=query_lower,
                        fts_query=fts_query,
                        categories=categories,
                        limit=limit,
                        offset=offset,
                    )

                    logger.info(
                        "LM tag FTS search executing_sql query=%r query_len=%s category_count=%s",
                        query,
                        len(query_lower),
                        len(categories) if categories else 0,
                    )
                    cursor = conn.execute(sql, params)
                    logger.info("LM tag FTS search execute_returned query=%r", query)
                    rows = cursor.fetchall()
                    logger.info(
                        "LM tag FTS search fetchall_returned query=%r row_count=%s",
                        query,
                        len(rows),
                    )
                    results = []
                    for row in rows:
                        result = {
                            "tag_name": row[0],
                            "category": row[1],
                            "post_count": row[2],
                            "is_tag_name_match": row[4] == 1,
                            "rank_score": row[5],
                        }

                        # Set is_exact_prefix based on tag_name match
                        tag_name = row[0]
                        if tag_name.lower().startswith(query_lower.lstrip("/")):
                            result["is_exact_prefix"] = True
                        else:
                            result["is_exact_prefix"] = result["is_tag_name_match"]

                        # Check if search matched an alias rather than the tag_name
                        matched_alias = self._find_matched_alias(query, row[0], row[3])
                        if matched_alias:
                            result["matched_alias"] = matched_alias

                        results.append(result)
                    elapsed_ms = (time.perf_counter() - search_started_at) * 1000
                    logger.info(
                        "LM tag FTS search done query=%r result_count=%s elapsed_ms=%.2f",
                        query,
                        len(results),
                        elapsed_ms,
                    )
                    return results
                finally:
                    conn.close()
        except Exception as exc:
            logger.debug("Tag FTS search error for query '%s': %s", query, exc)
            return []

    def _build_search_statement(
        self,
        query_lower: str,
        fts_query: str,
        categories: Optional[List[int]],
        limit: int,
        offset: int,
    ) -> tuple[str, list[object]]:
        """Build the SQL statement and params for a tag search."""
        # Escape special LIKE characters and add wildcard
        query_escaped = (
            query_lower.lstrip("/")
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

        # FTS5 bm25() returns negative scores, lower is better.
        # We use -bm25() to get higher=better scores, but keep post_count as the
        # primary sort within tag-name prefix matches so autocomplete ordering
        # remains aligned with the existing popularity-first behavior.
        if categories:
            placeholders = ",".join("?" * len(categories))
            sql = f"""
                SELECT t.tag_name, t.category, t.post_count, t.aliases,
                       CASE
                           WHEN t.tag_name LIKE ? ESCAPE '\\' THEN 1
                           ELSE 0
                       END AS is_tag_name_match,
                       bm25(tag_fts, -100.0, 1.0, 1.0) AS rank_score
                FROM tag_fts
                CROSS JOIN tags t ON t.rowid = tag_fts.rowid
                WHERE tag_fts.searchable_text MATCH ?
                  AND t.category IN ({placeholders})
                ORDER BY is_tag_name_match DESC, t.post_count DESC, rank_score DESC
                LIMIT ? OFFSET ?
            """
            params = [query_escaped + "%", fts_query] + categories + [limit, offset]
        else:
            sql = """
                SELECT t.tag_name, t.category, t.post_count, t.aliases,
                       CASE
                           WHEN t.tag_name LIKE ? ESCAPE '\\' THEN 1
                           ELSE 0
                       END AS is_tag_name_match,
                       bm25(tag_fts, -100.0, 1.0, 1.0) AS rank_score
                FROM tag_fts
                JOIN tags t ON tag_fts.rowid = t.rowid
                WHERE tag_fts.searchable_text MATCH ?
                ORDER BY is_tag_name_match DESC, t.post_count DESC, rank_score DESC
                LIMIT ? OFFSET ?
            """
            params = [query_escaped + "%", fts_query, limit, offset]

        return sql, params

    def _find_matched_alias(
        self, query: str, tag_name: str, aliases_str: str
    ) -> Optional[str]:
        """Find which alias matched the query, if any.

        Args:
            query: The original search query.
            tag_name: The canonical tag name.
            aliases_str: Comma-separated string of aliases.

        Returns:
            The matched alias string, or None if the query matched the tag_name directly.
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return None

        # Strip leading "/" from query if present (FTS index strips these)
        query_normalized = query_lower.lstrip("/")

        # Check if query matches tag_name prefix (direct match, no alias needed)
        if tag_name.lower().startswith(query_normalized):
            return None

        # Check aliases first - if query matches an alias or a word within an alias, return it
        if aliases_str:
            for alias in aliases_str.split(","):
                alias = alias.strip()
                if not alias:
                    continue
                # Normalize alias for comparison (strip leading slash)
                alias_normalized = alias.lower().lstrip("/")

                # Check if alias starts with query
                if alias_normalized.startswith(query_normalized):
                    return alias  # Return original alias (with "/" if present)

                # Check if any word within the alias starts with query
                # (mirrors FTS5 tokenization which splits on underscores)
                alias_words = alias_normalized.replace("_", " ").split()
                for word in alias_words:
                    if word.startswith(query_normalized):
                        return alias

        # If no alias matched, check if query matches a word in tag_name
        # (handles cases like "long_hair" matching "long" - no alias indicator needed)
        tag_words = tag_name.lower().replace("_", " ").split()
        for word in tag_words:
            if word.startswith(query_normalized):
                return None

        # Query matched via FTS but not tag_name words or aliases
        # This shouldn't normally happen, but return None for safety
        return None

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

        FTS5 special characters: " ( ) * : ^ - /
        We keep * for prefix matching but escape others.
        """
        if not text:
            return ""

        # Replace FTS5 special characters with space
        # Note: "/" is special in FTS5 (column filter syntax), so we strip it
        special = ['"', "(", ")", "*", ":", "^", "-", "{", "}", "[", "]", "/"]
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
