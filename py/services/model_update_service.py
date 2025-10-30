"""Service for tracking remote model version updates."""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .errors import RateLimitError, ResourceNotFoundError
from .settings_manager import get_settings_manager
from ..utils.civitai_utils import rewrite_preview_url
from ..utils.preview_selection import select_preview_media

logger = logging.getLogger(__name__)


@dataclass
class ModelVersionRecord:
    """Persisted metadata for a single model version."""

    version_id: int
    name: Optional[str]
    base_model: Optional[str]
    released_at: Optional[str]
    size_bytes: Optional[int]
    preview_url: Optional[str]
    is_in_library: bool
    should_ignore: bool
    sort_index: int = 0


@dataclass
class ModelUpdateRecord:
    """Representation of a persisted update record."""

    model_type: str
    model_id: int
    versions: List[ModelVersionRecord]
    last_checked_at: Optional[float]
    should_ignore_model: bool

    @property
    def largest_version_id(self) -> Optional[int]:
        """Return the highest known version identifier for the model."""

        if not self.versions:
            return None
        return max(version.version_id for version in self.versions)

    @property
    def version_ids(self) -> List[int]:
        """Return all known version identifiers."""

        return [version.version_id for version in self.versions]

    @property
    def in_library_version_ids(self) -> List[int]:
        """Return the subset of version identifiers present in the local library."""

        return [version.version_id for version in self.versions if version.is_in_library]

    def has_update(self) -> bool:
        """Return True when a non-ignored remote version newer than the newest local copy is available."""

        if self.should_ignore_model:
            return False
        max_in_library = None
        for version in self.versions:
            if version.is_in_library:
                if max_in_library is None or version.version_id > max_in_library:
                    max_in_library = version.version_id

        if max_in_library is None:
            return any(
                not version.is_in_library and not version.should_ignore for version in self.versions
            )

        for version in self.versions:
            if version.is_in_library or version.should_ignore:
                continue
            if version.version_id > max_in_library:
                return True
        return False


class ModelUpdateService:
    """Persist and query remote model version metadata."""

    _SCHEMA = """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS model_update_status (
            model_id INTEGER PRIMARY KEY,
            model_type TEXT NOT NULL,
            last_checked_at REAL,
            should_ignore_model INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS model_update_versions (
            model_id INTEGER NOT NULL,
            version_id INTEGER NOT NULL,
            sort_index INTEGER NOT NULL DEFAULT 0,
            name TEXT,
            base_model TEXT,
            released_at TEXT,
            size_bytes INTEGER,
            preview_url TEXT,
            is_in_library INTEGER NOT NULL DEFAULT 0,
            should_ignore INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (model_id, version_id),
            FOREIGN KEY(model_id) REFERENCES model_update_status(model_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_model_update_versions_model_id
            ON model_update_versions(model_id);
    """

    def __init__(self, db_path: str, *, ttl_seconds: int = 24 * 60 * 60, settings_manager=None) -> None:
        self._db_path = db_path
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._schema_initialized = False
        self._settings = settings_manager or get_settings_manager()
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

    def _initialize_schema(self) -> None:
        if self._schema_initialized:
            return
        try:
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys = ON")
                conn.executescript(self._SCHEMA)
                self._apply_migrations(conn)
            self._schema_initialized = True
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.error("Failed to initialize update schema: %s", exc, exc_info=True)
            raise

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        """Ensure legacy databases match the current schema without dropping data."""

        status_columns = self._get_table_columns(conn, "model_update_status")
        if "should_ignore_model" not in status_columns:
            conn.execute(
                "ALTER TABLE model_update_status "
                "ADD COLUMN should_ignore_model INTEGER NOT NULL DEFAULT 0"
            )

        version_columns = self._get_table_columns(conn, "model_update_versions")
        migrations = {
            "sort_index": (
                "ALTER TABLE model_update_versions "
                "ADD COLUMN sort_index INTEGER NOT NULL DEFAULT 0"
            ),
            "name": (
                "ALTER TABLE model_update_versions "
                "ADD COLUMN name TEXT"
            ),
            "base_model": (
                "ALTER TABLE model_update_versions "
                "ADD COLUMN base_model TEXT"
            ),
            "released_at": (
                "ALTER TABLE model_update_versions "
                "ADD COLUMN released_at TEXT"
            ),
            "size_bytes": (
                "ALTER TABLE model_update_versions "
                "ADD COLUMN size_bytes INTEGER"
            ),
            "preview_url": (
                "ALTER TABLE model_update_versions "
                "ADD COLUMN preview_url TEXT"
            ),
            "is_in_library": (
                "ALTER TABLE model_update_versions "
                "ADD COLUMN is_in_library INTEGER NOT NULL DEFAULT 0"
            ),
            "should_ignore": (
                "ALTER TABLE model_update_versions "
                "ADD COLUMN should_ignore INTEGER NOT NULL DEFAULT 0"
            ),
        }

        for column, statement in migrations.items():
            if column not in version_columns:
                conn.execute(statement)

        # Refresh column metadata after applying additive migrations.
        version_columns = self._get_table_columns(conn, "model_update_versions")

        if self._requires_model_update_versions_pk_migration(conn):
            self._migrate_model_update_versions_primary_key(
                conn, version_columns
            )
            version_columns = self._get_table_columns(conn, "model_update_versions")

        if not self._has_unique_constraint(conn, "model_update_status", "model_id"):
            self._deduplicate_model_update_status(conn)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_model_update_status_model_id ON model_update_status(model_id)"
            )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_update_versions_model_id "
            "ON model_update_versions(model_id)"
        )


    def _get_table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        """Return the set of existing columns for a table."""

        cursor = conn.execute(f"PRAGMA table_info({table})")
        return {row["name"] for row in cursor.fetchall()}

    def _has_unique_constraint(
        self, conn: sqlite3.Connection, table: str, column: str
    ) -> bool:
        """Return True when the column already enforces uniqueness."""

        cursor = conn.execute(f"PRAGMA table_info({table})")
        rows = cursor.fetchall()
        column_info = next((row for row in rows if row["name"] == column), None)
        if column_info is None:
            return False

        if column_info["pk"] == 1 and all(
            other["pk"] == 0 for other in rows if other["name"] != column
        ):
            return True

        index_list = conn.execute(f"PRAGMA index_list({table})").fetchall()
        for index in index_list:
            if not index["unique"]:
                continue
            index_name = index["name"]
            index_info = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
            if len(index_info) == 1 and index_info[0]["name"] == column:
                return True
        return False

    def _requires_model_update_versions_pk_migration(
        self, conn: sqlite3.Connection
    ) -> bool:
        """Detect legacy schemas where version_id is the sole primary key."""

        info = conn.execute("PRAGMA table_info(model_update_versions)").fetchall()
        pk_columns = [row for row in info if row["pk"]]
        if not pk_columns:
            return True

        if len(pk_columns) == 1:
            return pk_columns[0]["name"] == "version_id"

        ordered = sorted(pk_columns, key=lambda row: row["pk"])
        expected = ["model_id", "version_id"]
        return [row["name"] for row in ordered] != expected

    def _migrate_model_update_versions_primary_key(
        self, conn: sqlite3.Connection, legacy_columns: set[str]
    ) -> None:
        """Upgrade the versions table to use a composite primary key."""

        logger.info("Migrating model_update_versions table to composite primary key")
        conn.execute(
            "ALTER TABLE model_update_versions RENAME TO model_update_versions_legacy"
        )
        conn.execute(
            """
            CREATE TABLE model_update_versions_new (
                model_id INTEGER NOT NULL,
                version_id INTEGER NOT NULL,
                sort_index INTEGER NOT NULL DEFAULT 0,
                name TEXT,
                base_model TEXT,
                released_at TEXT,
                size_bytes INTEGER,
                preview_url TEXT,
                is_in_library INTEGER NOT NULL DEFAULT 0,
                should_ignore INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (model_id, version_id),
                FOREIGN KEY(model_id) REFERENCES model_update_status(model_id) ON DELETE CASCADE
            )
            """
        )

        target_columns = [
            "model_id",
            "version_id",
            "sort_index",
            "name",
            "base_model",
            "released_at",
            "size_bytes",
            "preview_url",
            "is_in_library",
            "should_ignore",
        ]
        defaults = {
            "sort_index": "0",
            "name": "NULL",
            "base_model": "NULL",
            "released_at": "NULL",
            "size_bytes": "NULL",
            "preview_url": "NULL",
            "is_in_library": "0",
            "should_ignore": "0",
        }

        select_parts = []
        for column in target_columns:
            if column in legacy_columns:
                if column in {"sort_index", "is_in_library", "should_ignore"}:
                    select_parts.append(f"COALESCE({column}, {defaults[column]})")
                else:
                    select_parts.append(column)
            else:
                select_parts.append(defaults.get(column, "NULL"))

        conn.execute(
            """
            INSERT INTO model_update_versions_new ({columns})
            SELECT {select_clause}
            FROM model_update_versions_legacy
            """.format(
                columns=", ".join(target_columns),
                select_clause=", ".join(select_parts),
            )
        )

        conn.execute("DROP TABLE model_update_versions_legacy")
        conn.execute(
            "ALTER TABLE model_update_versions_new RENAME TO model_update_versions"
        )

    def _deduplicate_model_update_status(self, conn: sqlite3.Connection) -> None:
        """Remove duplicate status rows before applying uniqueness constraints."""

        duplicates = conn.execute(
            """
            SELECT model_id
            FROM model_update_status
            GROUP BY model_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        if not duplicates:
            return

        for row in duplicates:
            model_id = row["model_id"]
            conn.execute(
                """
                DELETE FROM model_update_status
                WHERE model_id = ?
                  AND rowid NOT IN (
                    SELECT rowid
                    FROM model_update_status
                    WHERE model_id = ?
                    ORDER BY
                        CASE WHEN last_checked_at IS NULL THEN 0 ELSE 1 END DESC,
                        last_checked_at DESC,
                        rowid DESC
                    LIMIT 1
                )
                """,
                (model_id, model_id),
            )

    async def refresh_for_model_type(
        self,
        model_type: str,
        scanner,
        metadata_provider,
        *,
        force_refresh: bool = False,
        target_model_ids: Optional[Sequence[int]] = None,
    ) -> Dict[int, ModelUpdateRecord]:
        """Refresh update information for every model present in the cache."""

        normalized_targets = (
            self._normalize_sequence(target_model_ids)
            if target_model_ids is not None
            else []
        )
        target_filter = normalized_targets or None

        local_versions = await self._collect_local_versions(
            scanner,
            target_model_ids=target_filter,
        )
        total_models = len(local_versions)
        if total_models == 0:
            if target_filter:
                logger.info(
                    "No %s models matched requested ids %s while refreshing update metadata",
                    model_type,
                    target_filter,
                )
            else:
                logger.info(
                    "No %s models found while refreshing update metadata", model_type
                )
            return {}

        logger.info(
            "Refreshing update metadata for %d %s models", total_models, model_type
        )

        results: Dict[int, ModelUpdateRecord] = {}
        prefetched: Dict[int, Mapping] = {}

        fetch_targets: List[int] = []
        if metadata_provider and local_versions:
            now = time.time()
            async with self._lock:
                for model_id in local_versions.keys():
                    existing = self._get_record(model_type, model_id)
                    if existing and existing.should_ignore_model and not force_refresh:
                        continue
                    if force_refresh or not existing or self._is_stale(existing, now):
                        fetch_targets.append(model_id)

            if fetch_targets:
                provider_name = (
                    metadata_provider.__class__.__name__
                    if metadata_provider is not None
                    else "unknown"
                )
                logger.info(
                    "Fetching remote metadata for %d %s models via bulk API using %s",
                    len(fetch_targets),
                    model_type,
                    provider_name,
                )
                try:
                    prefetched = await self._fetch_model_versions_bulk(
                        metadata_provider,
                        fetch_targets,
                    )
                except NotImplementedError:
                    prefetched = {}

        progress_interval = max(1, total_models // 10)
        for index, (model_id, version_ids) in enumerate(
            local_versions.items(), start=1
        ):
            record = await self._refresh_single_model(
                model_type,
                model_id,
                version_ids,
                metadata_provider,
                force_refresh=force_refresh,
                prefetched_response=prefetched.get(model_id),
            )
            if record:
                results[model_id] = record
            if index % progress_interval == 0 or index == total_models:
                logger.info(
                    "Refreshed update metadata for %d/%d %s models",
                    index,
                    total_models,
                    model_type,
                )
        logger.info(
            "Completed update refresh for %d %s models; %d records stored",
            total_models,
            model_type,
            len(results),
        )
        return results

    async def refresh_single_model(
        self,
        model_type: str,
        model_id: int,
        scanner,
        metadata_provider,
        *,
        force_refresh: bool = False,
    ) -> Optional[ModelUpdateRecord]:
        """Refresh update information for a specific model id."""

        local_versions = await self._collect_local_versions(scanner)
        version_ids = local_versions.get(model_id, [])
        return await self._refresh_single_model(
            model_type,
            model_id,
            version_ids,
            metadata_provider,
            force_refresh=force_refresh,
        )

    async def update_in_library_versions(
        self,
        model_type: str,
        model_id: int,
        version_ids: Sequence[int],
    ) -> ModelUpdateRecord:
        """Persist a new set of in-library version identifiers."""

        normalized_versions = self._normalize_sequence(version_ids)
        async with self._lock:
            existing = self._get_record(model_type, model_id)
            record = self._merge_with_local_versions(
                existing,
                normalized_versions,
                model_type=model_type,
                model_id=model_id,
            )
            self._upsert_record(record)
            return record

    async def set_should_ignore(
        self, model_type: str, model_id: int, should_ignore: bool
    ) -> ModelUpdateRecord:
        """Toggle the ignore flag for a model."""

        async with self._lock:
            existing = self._get_record(model_type, model_id)
            if existing:
                record = ModelUpdateRecord(
                    model_type=existing.model_type,
                    model_id=existing.model_id,
                    versions=list(existing.versions),
                    last_checked_at=existing.last_checked_at,
                    should_ignore_model=should_ignore,
                )
            else:
                record = ModelUpdateRecord(
                    model_type=model_type,
                    model_id=model_id,
                    versions=[],
                    last_checked_at=None,
                    should_ignore_model=should_ignore,
                )
            self._upsert_record(record)
            return record

    async def set_version_should_ignore(
        self,
        model_type: str,
        model_id: int,
        version_id: int,
        should_ignore: bool,
    ) -> ModelUpdateRecord:
        """Toggle the ignore flag for an individual version."""

        async with self._lock:
            existing = self._get_record(model_type, model_id)
            versions: List[ModelVersionRecord] = []
            found = False
            if existing:
                for record_version in existing.versions:
                    if record_version.version_id == version_id:
                        versions.append(
                            replace(record_version, should_ignore=should_ignore)
                        )
                        found = True
                    else:
                        versions.append(record_version)
            if not found:
                versions.append(
                    ModelVersionRecord(
                        version_id=version_id,
                        name=None,
                        base_model=None,
                        released_at=None,
                        size_bytes=None,
                        preview_url=None,
                        is_in_library=False,
                        should_ignore=should_ignore,
                        sort_index=len(versions),
                    )
                )

            record = ModelUpdateRecord(
                model_type=existing.model_type if existing else model_type,
                model_id=existing.model_id if existing else model_id,
                versions=self._sorted_versions(versions),
                last_checked_at=existing.last_checked_at if existing else None,
                should_ignore_model=existing.should_ignore_model if existing else False,
            )
            self._upsert_record(record)
            return record

    async def get_record(self, model_type: str, model_id: int) -> Optional[ModelUpdateRecord]:
        """Return a cached record without triggering remote fetches."""

        async with self._lock:
            return self._get_record(model_type, model_id)

    async def has_update(self, model_type: str, model_id: int) -> bool:
        """Determine if a model has updates pending."""

        record = await self.get_record(model_type, model_id)
        return record.has_update() if record else False

    async def has_updates_bulk(
        self,
        model_type: str,
        model_ids: Sequence[int],
    ) -> Dict[int, bool]:
        """Return update availability for each model id in a single database pass."""

        normalized_ids = self._normalize_sequence(model_ids)
        if not normalized_ids:
            return {}

        async with self._lock:
            records = self._get_records_bulk(model_type, normalized_ids)

        return {
            model_id: records.get(model_id).has_update() if records.get(model_id) else False
            for model_id in normalized_ids
        }

    async def _refresh_single_model(
        self,
        model_type: str,
        model_id: int,
        local_versions: Sequence[int],
        metadata_provider,
        *,
        force_refresh: bool = False,
        prefetched_response: Optional[Mapping] = None,
    ) -> Optional[ModelUpdateRecord]:
        normalized_local = self._normalize_sequence(local_versions)
        now = time.time()
        async with self._lock:
            existing = self._get_record(model_type, model_id)
            if existing and existing.should_ignore_model and not force_refresh:
                record = self._merge_with_local_versions(
                    existing,
                    normalized_local,
                )
                self._upsert_record(record)
                return record

            should_fetch = force_refresh or not existing or self._is_stale(existing, now)
        # release lock during network request
        fetched_versions: List[ModelVersionRecord] | None = None
        refresh_succeeded = False
        fallback_attempted = False
        fallback_error_message: Optional[str] = None
        mark_model_as_ignored = False
        response: Optional[Mapping] = None
        if metadata_provider and should_fetch:
            response = prefetched_response
            if response is None:
                fallback_attempted = True
                try:
                    response = await metadata_provider.get_model_versions(model_id)
                except RateLimitError:
                    raise
                except ResourceNotFoundError as exc:
                    fallback_error_message = str(exc) or "resource not found"
                    mark_model_as_ignored = True
                except Exception as exc:  # pragma: no cover - defensive log
                    logger.error(
                        "Failed to fetch versions for model %s (%s): %s",
                        model_id,
                        model_type,
                        exc,
                        exc_info=True,
                    )
                    fallback_error_message = str(exc)
            if response is not None:
                extracted = self._extract_versions(response)
                if extracted is not None:
                    fetched_versions = extracted
                    refresh_succeeded = True
                elif fallback_attempted and fallback_error_message is None:
                    fallback_error_message = "no versions returned"
            elif fallback_attempted and fallback_error_message is None:
                fallback_error_message = "no response"

        if fallback_attempted:
            if refresh_succeeded and isinstance(fetched_versions, list):
                logger.info(
                    "Fetched metadata via single lookup for model %s (%s); received %d versions",
                    model_id,
                    model_type,
                    len(fetched_versions),
                )
            elif mark_model_as_ignored:
                logger.info(
                    "Single lookup for model %s (%s) reported missing remote resource: %s",
                    model_id,
                    model_type,
                    fallback_error_message or "resource not found",
                )
            else:
                logger.warning(
                    "Single lookup for model %s (%s) failed: %s",
                    model_id,
                    model_type,
                    fallback_error_message or "unknown error",
                )

        async with self._lock:
            existing = self._get_record(model_type, model_id)
            if existing and existing.should_ignore_model and not force_refresh:
                record = self._merge_with_local_versions(
                    existing,
                    normalized_local,
                )
                self._upsert_record(record)
                return record

            if mark_model_as_ignored:
                record = self._merge_with_local_versions(
                    existing,
                    normalized_local,
                    model_type=model_type,
                    model_id=model_id,
                    last_checked_at=now,
                )
                record = replace(record, should_ignore_model=True)
                self._upsert_record(record)
                logger.info(
                    "Marked model %s (%s) as ignored after remote resource was not found",
                    model_id,
                    model_type,
                )
                return record

            if refresh_succeeded and isinstance(fetched_versions, list):
                record = self._build_record_from_remote(
                    model_type,
                    model_id,
                    normalized_local,
                    fetched_versions,
                    existing,
                    now,
                )
            else:
                record = self._merge_with_local_versions(
                    existing,
                    normalized_local,
                    model_type=model_type,
                    model_id=model_id,
                    last_checked_at=existing.last_checked_at if existing else None,
                )
            self._upsert_record(record)
            return record

    async def _fetch_model_versions_bulk(
        self,
        metadata_provider,
        model_ids: Sequence[int],
    ) -> Dict[int, Mapping]:
        """Fetch model metadata in batches of up to 100 ids."""

        BATCH_SIZE = 100
        normalized = self._normalize_sequence(model_ids)
        if not normalized:
            return {}

        aggregated: Dict[int, Mapping] = {}
        total_ids = len(normalized)
        total_batches = (total_ids + BATCH_SIZE - 1) // BATCH_SIZE
        provider_name = (
            metadata_provider.__class__.__name__
            if metadata_provider is not None
            else "unknown"
        )
        for batch_index, start in enumerate(range(0, total_ids, BATCH_SIZE), start=1):
            chunk = normalized[start : start + BATCH_SIZE]
            logger.info(
                "Requesting bulk metadata for %d models (batch %d/%d) from %s",
                len(chunk),
                batch_index,
                total_batches,
                provider_name,
            )
            try:
                response = await metadata_provider.get_model_versions_bulk(chunk)
            except RateLimitError:
                raise
            if response is None:
                continue
            if not isinstance(response, Mapping):
                logger.debug(
                    "Unexpected bulk response type %s from provider %s", type(response), metadata_provider
                )
                continue
            for key, value in response.items():
                normalized_key = self._normalize_int(key)
                if normalized_key is None:
                    continue
                if isinstance(value, Mapping):
                    aggregated[normalized_key] = value
        logger.info(
            "Completed bulk metadata fetch for %d models using %s",
            len(aggregated),
            provider_name,
        )
        return aggregated

    async def _collect_local_versions(
        self,
        scanner,
        *,
        target_model_ids: Optional[Sequence[int]] = None,
    ) -> Dict[int, List[int]]:
        cache = await scanner.get_cached_data()
        mapping: Dict[int, set[int]] = {}
        if not cache or not getattr(cache, "raw_data", None):
            return {}

        target_set = None
        if target_model_ids:
            target_set = set(target_model_ids)
            if not target_set:
                return {}

        for item in cache.raw_data:
            civitai = item.get("civitai") if isinstance(item, dict) else None
            if not isinstance(civitai, dict):
                continue
            model_id = self._normalize_int(civitai.get("modelId"))
            version_id = self._normalize_int(civitai.get("id"))
            if model_id is None or version_id is None:
                continue
            if target_set is not None and model_id not in target_set:
                continue
            mapping.setdefault(model_id, set()).add(version_id)

        return {model_id: sorted(ids) for model_id, ids in mapping.items()}

    def _merge_with_local_versions(
        self,
        existing: Optional[ModelUpdateRecord],
        normalized_local: Sequence[int],
        *,
        model_type: Optional[str] = None,
        model_id: Optional[int] = None,
        last_checked_at: Optional[float] = None,
    ) -> ModelUpdateRecord:
        local_set = set(normalized_local)
        versions: List[ModelVersionRecord] = []
        ignore_map: Dict[int, bool] = {}
        if existing:
            model_type = existing.model_type
            model_id = existing.model_id
            last_checked_at = existing.last_checked_at if last_checked_at is None else last_checked_at
            ignore_map = {version.version_id: version.should_ignore for version in existing.versions}
            for version in existing.versions:
                versions.append(
                    replace(
                        version,
                        is_in_library=version.version_id in local_set,
                    )
                )
        elif model_type is None or model_id is None:
            raise ValueError("model_type and model_id are required when creating a new record")

        seen_ids = {version.version_id for version in versions}
        for missing_id in sorted(local_set - seen_ids):
            versions.append(
                ModelVersionRecord(
                    version_id=missing_id,
                    name=None,
                    base_model=None,
                    released_at=None,
                    size_bytes=None,
                    preview_url=None,
                    is_in_library=True,
                    should_ignore=ignore_map.get(missing_id, False),
                    sort_index=len(versions),
                )
            )

        return ModelUpdateRecord(
            model_type=model_type,
            model_id=model_id,
            versions=self._sorted_versions(versions),
            last_checked_at=last_checked_at,
            should_ignore_model=existing.should_ignore_model if existing else False,
        )

    def _build_record_from_remote(
        self,
        model_type: str,
        model_id: int,
        local_versions: Sequence[int],
        remote_versions: Sequence[ModelVersionRecord],
        existing: Optional[ModelUpdateRecord],
        timestamp: float,
    ) -> ModelUpdateRecord:
        local_set = set(local_versions)
        ignore_map = {version.version_id: version.should_ignore for version in existing.versions} if existing else {}
        preview_map = {version.version_id: version.preview_url for version in existing.versions} if existing else {}
        sort_map = {version.version_id: version.sort_index for version in existing.versions} if existing else {}
        existing_map = {version.version_id: version for version in existing.versions} if existing else {}

        versions: List[ModelVersionRecord] = []
        seen_ids: set[int] = set()
        for index, remote_version in enumerate(remote_versions):
            version_id = remote_version.version_id
            seen_ids.add(version_id)
            versions.append(
                ModelVersionRecord(
                    version_id=version_id,
                    name=remote_version.name,
                    base_model=remote_version.base_model,
                    released_at=remote_version.released_at,
                    size_bytes=remote_version.size_bytes,
                    preview_url=remote_version.preview_url or preview_map.get(version_id),
                    is_in_library=version_id in local_set,
                    should_ignore=ignore_map.get(version_id, remote_version.should_ignore),
                    sort_index=sort_map.get(version_id, index),
                )
            )

        missing_local = local_set - seen_ids
        if missing_local:
            for version_id in sorted(missing_local):
                existing_version = existing_map.get(version_id)
                if existing_version:
                    versions.append(
                        replace(
                            existing_version,
                            is_in_library=True,
                        )
                    )
                else:
                    versions.append(
                        ModelVersionRecord(
                            version_id=version_id,
                            name=None,
                            base_model=None,
                            released_at=None,
                            size_bytes=None,
                            preview_url=None,
                            is_in_library=True,
                            should_ignore=ignore_map.get(version_id, False),
                            sort_index=len(versions),
                        )
                    )

        return ModelUpdateRecord(
            model_type=model_type,
            model_id=model_id,
            versions=self._sorted_versions(versions),
            last_checked_at=timestamp,
            should_ignore_model=existing.should_ignore_model if existing else False,
        )

    def _sorted_versions(self, versions: Sequence[ModelVersionRecord]) -> List[ModelVersionRecord]:
        ordered = sorted(versions, key=lambda version: (version.sort_index, version.version_id))
        normalized: List[ModelVersionRecord] = []
        for index, version in enumerate(ordered):
            normalized.append(replace(version, sort_index=index))
        return normalized

    def _is_stale(self, record: ModelUpdateRecord, now: float) -> bool:
        if record.last_checked_at is None:
            return True
        return (now - record.last_checked_at) >= self._ttl_seconds

    @staticmethod
    def _normalize_int(value) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _normalize_sequence(self, values: Sequence[int]) -> List[int]:
        normalized = [
            item
            for item in (self._normalize_int(value) for value in values)
            if item is not None
        ]
        return sorted(dict.fromkeys(normalized))

    @staticmethod
    def _normalize_string(value) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        try:
            return str(value)
        except Exception:  # pragma: no cover - defensive conversion
            return None

    def _extract_versions(self, response) -> Optional[List[ModelVersionRecord]]:
        if not isinstance(response, Mapping):
            return None
        versions = response.get("modelVersions")
        if versions is None:
            return []
        if not isinstance(versions, Iterable):
            return None
        extracted: List[ModelVersionRecord] = []
        for index, entry in enumerate(versions):
            if not isinstance(entry, Mapping):
                continue
            version_id = self._normalize_int(entry.get("id"))
            if version_id is None:
                continue
            name = self._normalize_string(entry.get("name"))
            base_model = self._normalize_string(entry.get("baseModel"))
            released_at = self._normalize_string(entry.get("publishedAt") or entry.get("createdAt"))
            size_bytes = self._extract_size_bytes(entry.get("files"))
            preview_url = self._extract_preview_url(entry.get("images"))
            extracted.append(
                ModelVersionRecord(
                    version_id=version_id,
                    name=name,
                    base_model=base_model,
                    released_at=released_at,
                    size_bytes=size_bytes,
                    preview_url=preview_url,
                    is_in_library=False,
                    should_ignore=False,
                    sort_index=index,
                )
            )
        return extracted

    def _extract_size_bytes(self, files) -> Optional[int]:
        if not isinstance(files, Iterable):
            return None

        def parse_size(entry: Mapping) -> Optional[int]:
            size_kb = entry.get("sizeKB")
            if size_kb is None:
                return None
            try:
                return int(float(size_kb) * 1024)
            except (TypeError, ValueError):
                return None

        preferred_size: Optional[int] = None
        fallback_size: Optional[int] = None
        for entry in files:
            if not isinstance(entry, Mapping):
                continue
            size_bytes = parse_size(entry)
            if size_bytes is None:
                continue

            entry_type = entry.get("type")
            is_model_type = isinstance(entry_type, str) and entry_type.lower() == "model"
            primary_flag = entry.get("primary")
            is_primary = primary_flag is True or (
                isinstance(primary_flag, str) and primary_flag.strip().lower() == "true"
            )

            if is_model_type and is_primary:
                preferred_size = size_bytes
                break
            if fallback_size is None:
                fallback_size = size_bytes

        return preferred_size if preferred_size is not None else fallback_size

    def _extract_preview_url(self, images) -> Optional[str]:
        if not isinstance(images, Iterable):
            return None

        candidates = [entry for entry in images if isinstance(entry, Mapping)]
        if not candidates:
            return None

        blur_mature_content = True
        settings = getattr(self, "_settings", None)
        if settings is not None and hasattr(settings, "get"):
            try:
                blur_mature_content = bool(settings.get("blur_mature_content", True))
            except Exception:  # pragma: no cover - defensive guard
                blur_mature_content = True

        selected, _ = select_preview_media(candidates, blur_mature_content=blur_mature_content)
        if not selected:
            return None

        url = selected.get("url")
        if not isinstance(url, str) or not url:
            return None

        media_type = selected.get("type")
        if not isinstance(media_type, str):
            media_type = None

        rewritten, _ = rewrite_preview_url(url, media_type)
        return rewritten or url

    def _get_record(self, model_type: str, model_id: int) -> Optional[ModelUpdateRecord]:
        records = self._get_records_bulk(model_type, [model_id])
        return records.get(model_id)

    def _get_records_bulk(
        self,
        model_type: str,
        model_ids: Sequence[int],
    ) -> Dict[int, ModelUpdateRecord]:
        if not model_ids:
            return {}

        params = tuple(model_ids)
        placeholders = ",".join("?" for _ in params)

        with self._connect() as conn:
            status_rows = conn.execute(
                f"""
                SELECT model_id, model_type, last_checked_at, should_ignore_model
                FROM model_update_status
                WHERE model_id IN ({placeholders})
                """,
                params,
            ).fetchall()
            if not status_rows:
                return {}

            version_rows = conn.execute(
                f"""
                SELECT model_id, version_id, sort_index, name, base_model, released_at,
                       size_bytes, preview_url, is_in_library, should_ignore
                FROM model_update_versions
                WHERE model_id IN ({placeholders})
                ORDER BY model_id ASC, sort_index ASC, version_id ASC
                """,
                params,
            ).fetchall()

        versions_by_model: Dict[int, List[ModelVersionRecord]] = {}
        for row in version_rows:
            model_id = int(row["model_id"])
            versions_by_model.setdefault(model_id, []).append(
                ModelVersionRecord(
                    version_id=int(row["version_id"]),
                    name=row["name"],
                    base_model=row["base_model"],
                    released_at=row["released_at"],
                    size_bytes=self._normalize_int(row["size_bytes"]),
                    preview_url=row["preview_url"],
                    is_in_library=bool(row["is_in_library"]),
                    should_ignore=bool(row["should_ignore"]),
                    sort_index=self._normalize_int(row["sort_index"]) or 0,
                )
            )

        records: Dict[int, ModelUpdateRecord] = {}
        for status in status_rows:
            model_id = int(status["model_id"])
            stored_type = status["model_type"]
            if stored_type and stored_type != model_type:
                logger.debug(
                    "Model id %s requested as %s but stored as %s",
                    model_id,
                    model_type,
                    stored_type,
                )

            record = ModelUpdateRecord(
                model_type=stored_type or model_type,
                model_id=model_id,
                versions=self._sorted_versions(versions_by_model.get(model_id, [])),
                last_checked_at=status["last_checked_at"],
                should_ignore_model=bool(status["should_ignore_model"]),
            )
            records[model_id] = record

        return records

    def _upsert_record(self, record: ModelUpdateRecord) -> None:
        payload = (
            record.model_id,
            record.model_type,
            record.last_checked_at,
            1 if record.should_ignore_model else 0,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_update_status (
                    model_id, model_type, last_checked_at, should_ignore_model
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    model_type = excluded.model_type,
                    last_checked_at = excluded.last_checked_at,
                    should_ignore_model = excluded.should_ignore_model
                """,
                payload,
            )
            conn.execute(
                "DELETE FROM model_update_versions WHERE model_id = ?",
                (record.model_id,),
            )
            for version in record.versions:
                conn.execute(
                    """
                    INSERT INTO model_update_versions (
                        version_id, model_id, sort_index, name, base_model, released_at,
                        size_bytes, preview_url, is_in_library, should_ignore
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version.version_id,
                        record.model_id,
                        version.sort_index,
                        version.name,
                        version.base_model,
                        version.released_at,
                        version.size_bytes,
                        version.preview_url,
                        1 if version.is_in_library else 0,
                        1 if version.should_ignore else 0,
                    ),
                )
            conn.commit()
