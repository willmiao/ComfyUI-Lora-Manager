"""SQLite FTS5-based full-text search index for recipes.

This module provides fast recipe search using SQLite's FTS5 extension,
enabling sub-100ms search times even with 20k+ recipes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Set

from ..utils.settings_paths import get_settings_dir

logger = logging.getLogger(__name__)


class RecipeFTSIndex:
    """SQLite FTS5-based full-text search index for recipes.

    Provides fast prefix-based search across multiple recipe fields:
    - title
    - tags
    - lora_names (file names)
    - lora_models (model names)
    - prompt
    - negative_prompt
    """

    _DEFAULT_FILENAME = "recipe_fts.sqlite"

    # Map of search option keys to FTS column names
    FIELD_MAP = {
        'title': ['title'],
        'tags': ['tags'],
        'lora_name': ['lora_names'],
        'lora_model': ['lora_models'],
        'prompt': ['prompt', 'negative_prompt'],
    }

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the FTS index.

        Args:
            db_path: Optional path to the SQLite database file.
                     If not provided, uses the default location in settings directory.
        """
        self._db_path = db_path or self._resolve_default_path()
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

    def _resolve_default_path(self) -> str:
        """Resolve the default database path."""
        override = os.environ.get("LORA_MANAGER_RECIPE_FTS_DB")
        if override:
            return override

        try:
            settings_dir = get_settings_dir(create=True)
        except Exception as exc:
            logger.warning("Falling back to current directory for FTS index: %s", exc)
            settings_dir = "."

        return os.path.join(settings_dir, self._DEFAULT_FILENAME)

    def get_database_path(self) -> str:
        """Return the resolved database path."""
        return self._db_path

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
                        -- Note: We use a regular FTS5 table (not contentless) so we can retrieve recipe_id
                        CREATE VIRTUAL TABLE IF NOT EXISTS recipe_fts USING fts5(
                            recipe_id,
                            title,
                            tags,
                            lora_names,
                            lora_models,
                            prompt,
                            negative_prompt,
                            tokenize='unicode61 remove_diacritics 2'
                        );

                        -- Recipe ID to rowid mapping for fast lookups and deletions
                        CREATE TABLE IF NOT EXISTS recipe_rowid (
                            recipe_id TEXT PRIMARY KEY,
                            fts_rowid INTEGER UNIQUE
                        );

                        -- Index version tracking
                        CREATE TABLE IF NOT EXISTS fts_metadata (
                            key TEXT PRIMARY KEY,
                            value TEXT
                        );
                    """)
                    conn.commit()
                    self._schema_initialized = True
                    logger.debug("FTS index schema initialized at %s", self._db_path)
                finally:
                    conn.close()
            except Exception as exc:
                logger.error("Failed to initialize FTS schema: %s", exc)

    def build_index(self, recipes: List[Dict[str, Any]]) -> None:
        """Build or rebuild the entire FTS index from recipe data.

        Args:
            recipes: List of recipe dictionaries to index.
        """
        if self._indexing_in_progress:
            logger.warning("FTS indexing already in progress, skipping")
            return

        self._indexing_in_progress = True
        self._ready.clear()
        start_time = time.time()

        try:
            self.initialize()
            if not self._schema_initialized:
                logger.error("Cannot build FTS index: schema not initialized")
                return

            with self._lock:
                conn = self._connect()
                try:
                    conn.execute("BEGIN")

                    # Clear existing data
                    conn.execute("DELETE FROM recipe_fts")
                    conn.execute("DELETE FROM recipe_rowid")

                    # Batch insert for performance
                    batch_size = 500
                    total = len(recipes)
                    inserted = 0

                    for i in range(0, total, batch_size):
                        batch = recipes[i:i + batch_size]
                        rows = []
                        rowid_mappings = []

                        for recipe in batch:
                            recipe_id = str(recipe.get('id', ''))
                            if not recipe_id:
                                continue

                            row = self._prepare_fts_row(recipe)
                            rows.append(row)
                            inserted += 1

                        if rows:
                            # Insert into FTS table
                            conn.executemany(
                                """INSERT INTO recipe_fts (recipe_id, title, tags, lora_names,
                                   lora_models, prompt, negative_prompt)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                rows
                            )

                            # Build rowid mappings
                            for row in rows:
                                recipe_id = row[0]
                                cursor = conn.execute(
                                    "SELECT rowid FROM recipe_fts WHERE recipe_id = ?",
                                    (recipe_id,)
                                )
                                result = cursor.fetchone()
                                if result:
                                    rowid_mappings.append((recipe_id, result[0]))

                            if rowid_mappings:
                                conn.executemany(
                                    "INSERT OR REPLACE INTO recipe_rowid (recipe_id, fts_rowid) VALUES (?, ?)",
                                    rowid_mappings
                                )

                    # Update metadata
                    conn.execute(
                        "INSERT OR REPLACE INTO fts_metadata (key, value) VALUES (?, ?)",
                        ('last_build_time', str(time.time()))
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO fts_metadata (key, value) VALUES (?, ?)",
                        ('recipe_count', str(inserted))
                    )

                    conn.commit()
                    elapsed = time.time() - start_time
                    logger.info("FTS index built: %d recipes indexed in %.2fs", inserted, elapsed)
                finally:
                    conn.close()

            self._ready.set()

        except Exception as exc:
            logger.error("Failed to build FTS index: %s", exc, exc_info=True)
        finally:
            self._indexing_in_progress = False

    def search(self, query: str, fields: Optional[Set[str]] = None) -> Set[str]:
        """Search recipes using FTS5 with prefix matching.

        Args:
            query: The search query string.
            fields: Optional set of field names to search. If None, searches all fields.
                    Valid fields: 'title', 'tags', 'lora_name', 'lora_model', 'prompt'

        Returns:
            Set of matching recipe IDs.
        """
        if not self.is_ready():
            if not self._warned_not_ready:
                logger.debug("FTS index not ready, returning empty results")
                self._warned_not_ready = True
            return set()

        if not query or not query.strip():
            return set()

        fts_query = self._build_fts_query(query, fields)
        if not fts_query:
            return set()

        try:
            with self._lock:
                conn = self._connect(readonly=True)
                try:
                    cursor = conn.execute(
                        "SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH ?",
                        (fts_query,)
                    )
                    return {row[0] for row in cursor.fetchall()}
                finally:
                    conn.close()
        except Exception as exc:
            logger.debug("FTS search error for query '%s': %s", query, exc)
            return set()

    def add_recipe(self, recipe: Dict[str, Any]) -> bool:
        """Add a single recipe to the FTS index.

        Args:
            recipe: The recipe dictionary to add.

        Returns:
            True if successful, False otherwise.
        """
        if not self.is_ready():
            return False

        recipe_id = str(recipe.get('id', ''))
        if not recipe_id:
            return False

        try:
            with self._lock:
                conn = self._connect()
                try:
                    # Remove existing entry if present
                    self._remove_recipe_locked(conn, recipe_id)

                    # Insert new entry
                    row = self._prepare_fts_row(recipe)
                    conn.execute(
                        """INSERT INTO recipe_fts (recipe_id, title, tags, lora_names,
                           lora_models, prompt, negative_prompt)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        row
                    )

                    # Update rowid mapping
                    cursor = conn.execute(
                        "SELECT rowid FROM recipe_fts WHERE recipe_id = ?",
                        (recipe_id,)
                    )
                    result = cursor.fetchone()
                    if result:
                        conn.execute(
                            "INSERT OR REPLACE INTO recipe_rowid (recipe_id, fts_rowid) VALUES (?, ?)",
                            (recipe_id, result[0])
                        )

                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception as exc:
            logger.debug("Failed to add recipe %s to FTS index: %s", recipe_id, exc)
            return False

    def remove_recipe(self, recipe_id: str) -> bool:
        """Remove a recipe from the FTS index.

        Args:
            recipe_id: The ID of the recipe to remove.

        Returns:
            True if successful, False otherwise.
        """
        if not self.is_ready():
            return False

        if not recipe_id:
            return False

        try:
            with self._lock:
                conn = self._connect()
                try:
                    self._remove_recipe_locked(conn, recipe_id)
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception as exc:
            logger.debug("Failed to remove recipe %s from FTS index: %s", recipe_id, exc)
            return False

    def update_recipe(self, recipe: Dict[str, Any]) -> bool:
        """Update a recipe in the FTS index.

        Args:
            recipe: The updated recipe dictionary.

        Returns:
            True if successful, False otherwise.
        """
        return self.add_recipe(recipe)  # add_recipe handles removal and re-insertion

    def clear(self) -> bool:
        """Clear all data from the FTS index.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute("DELETE FROM recipe_fts")
                    conn.execute("DELETE FROM recipe_rowid")
                    conn.commit()
                    self._ready.clear()
                    return True
                finally:
                    conn.close()
        except Exception as exc:
            logger.error("Failed to clear FTS index: %s", exc)
            return False

    def get_indexed_count(self) -> int:
        """Return the number of recipes currently indexed."""
        if not self._schema_initialized:
            return 0

        try:
            with self._lock:
                conn = self._connect(readonly=True)
                try:
                    cursor = conn.execute("SELECT COUNT(*) FROM recipe_fts")
                    result = cursor.fetchone()
                    return result[0] if result else 0
                finally:
                    conn.close()
        except Exception:
            return 0

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

    def _remove_recipe_locked(self, conn: sqlite3.Connection, recipe_id: str) -> None:
        """Remove a recipe entry. Caller must hold the lock."""
        # Get the rowid for deletion
        cursor = conn.execute(
            "SELECT fts_rowid FROM recipe_rowid WHERE recipe_id = ?",
            (recipe_id,)
        )
        result = cursor.fetchone()
        if result:
            fts_rowid = result[0]
            # Delete from FTS using rowid
            conn.execute(
                "DELETE FROM recipe_fts WHERE rowid = ?",
                (fts_rowid,)
            )
        # Also try direct delete by recipe_id (handles edge cases)
        conn.execute(
            "DELETE FROM recipe_fts WHERE recipe_id = ?",
            (recipe_id,)
        )
        conn.execute(
            "DELETE FROM recipe_rowid WHERE recipe_id = ?",
            (recipe_id,)
        )

    def _prepare_fts_row(self, recipe: Dict[str, Any]) -> tuple:
        """Prepare a row tuple for FTS insertion."""
        recipe_id = str(recipe.get('id', ''))
        title = str(recipe.get('title', ''))

        # Extract tags as space-separated string
        tags_list = recipe.get('tags', [])
        tags = ' '.join(str(t) for t in tags_list if t) if tags_list else ''

        # Extract LoRA file names and model names
        loras = recipe.get('loras', [])
        lora_names = []
        lora_models = []
        for lora in loras:
            if isinstance(lora, dict):
                file_name = lora.get('file_name', '')
                if file_name:
                    lora_names.append(str(file_name))
                model_name = lora.get('modelName', '')
                if model_name:
                    lora_models.append(str(model_name))

        lora_names_str = ' '.join(lora_names)
        lora_models_str = ' '.join(lora_models)

        # Extract prompts from gen_params
        gen_params = recipe.get('gen_params', {})
        prompt = str(gen_params.get('prompt', '')) if gen_params else ''
        negative_prompt = str(gen_params.get('negative_prompt', '')) if gen_params else ''

        return (recipe_id, title, tags, lora_names_str, lora_models_str, prompt, negative_prompt)

    def _build_fts_query(self, query: str, fields: Optional[Set[str]] = None) -> str:
        """Build an FTS5 query string with prefix matching and field restrictions.

        Args:
            query: The user's search query.
            fields: Optional set of field names to restrict search to.

        Returns:
            FTS5 query string.
        """
        # Split query into words and clean them
        words = query.lower().split()
        if not words:
            return ''

        # Escape and add prefix wildcard to each word
        prefix_terms = []
        for word in words:
            escaped = self._escape_fts_query(word)
            if escaped:
                # Add prefix wildcard for substring-like matching
                # FTS5 prefix queries: word* matches words starting with "word"
                prefix_terms.append(f'{escaped}*')

        if not prefix_terms:
            return ''

        # Combine terms with implicit AND (all words must match)
        term_expr = ' '.join(prefix_terms)

        # If no field restriction, search all indexed fields (not recipe_id)
        if not fields:
            return term_expr

        # Build field-restricted query with OR between fields
        field_clauses = []
        for field in fields:
            if field in self.FIELD_MAP:
                cols = self.FIELD_MAP[field]
                for col in cols:
                    # FTS5 column filter syntax: column:term
                    # Need to handle multiple terms properly
                    for term in prefix_terms:
                        field_clauses.append(f'{col}:{term}')

        if not field_clauses:
            return term_expr

        # Combine field clauses with OR
        return ' OR '.join(field_clauses)

    def _escape_fts_query(self, text: str) -> str:
        """Escape special FTS5 characters.

        FTS5 special characters: " ( ) * : ^ -
        We keep * for prefix matching but escape others.
        """
        if not text:
            return ''

        # Replace FTS5 special characters with space
        # Keep alphanumeric, CJK characters, and common punctuation
        special = ['"', '(', ')', '*', ':', '^', '-', '{', '}', '[', ']']
        result = text
        for char in special:
            result = result.replace(char, ' ')

        # Collapse multiple spaces and strip
        result = re.sub(r'\s+', ' ', result).strip()
        return result
