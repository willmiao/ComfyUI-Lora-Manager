"""Service for tracking remote model version updates."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .errors import RateLimitError

logger = logging.getLogger(__name__)


@dataclass
class ModelUpdateRecord:
    """Representation of a persisted update record."""

    model_type: str
    model_id: int
    largest_version_id: Optional[int]
    version_ids: List[int]
    in_library_version_ids: List[int]
    last_checked_at: Optional[float]
    should_ignore: bool

    def has_update(self) -> bool:
        """Return True when remote versions exceed the local library."""

        if self.should_ignore or not self.version_ids:
            return False
        local_versions = set(self.in_library_version_ids)
        return any(version_id not in local_versions for version_id in self.version_ids)


class ModelUpdateService:
    """Persist and query remote model version metadata."""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS model_update_status (
            model_type TEXT NOT NULL,
            model_id INTEGER NOT NULL,
            largest_version_id INTEGER,
            version_ids TEXT,
            in_library_version_ids TEXT,
            last_checked_at REAL,
            should_ignore INTEGER DEFAULT 0,
            PRIMARY KEY (model_type, model_id)
        )
    """

    def __init__(self, db_path: str, *, ttl_seconds: int = 24 * 60 * 60) -> None:
        self._db_path = db_path
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
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

    def _initialize_schema(self) -> None:
        if self._schema_initialized:
            return
        try:
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys = ON")
                conn.executescript(self._SCHEMA)
            self._schema_initialized = True
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.error("Failed to initialize update schema: %s", exc, exc_info=True)
            raise

    async def refresh_for_model_type(
        self,
        model_type: str,
        scanner,
        metadata_provider,
        *,
        force_refresh: bool = False,
    ) -> Dict[int, ModelUpdateRecord]:
        """Refresh update information for every model present in the cache."""

        local_versions = await self._collect_local_versions(scanner)
        results: Dict[int, ModelUpdateRecord] = {}
        for model_id, version_ids in local_versions.items():
            record = await self._refresh_single_model(
                model_type,
                model_id,
                version_ids,
                metadata_provider,
                force_refresh=force_refresh,
            )
            if record:
                results[model_id] = record
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
            record = ModelUpdateRecord(
                model_type=model_type,
                model_id=model_id,
                largest_version_id=existing.largest_version_id if existing else None,
                version_ids=list(existing.version_ids) if existing else [],
                in_library_version_ids=normalized_versions,
                last_checked_at=existing.last_checked_at if existing else None,
                should_ignore=existing.should_ignore if existing else False,
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
                    model_type=model_type,
                    model_id=model_id,
                    largest_version_id=existing.largest_version_id,
                    version_ids=list(existing.version_ids),
                    in_library_version_ids=list(existing.in_library_version_ids),
                    last_checked_at=existing.last_checked_at,
                    should_ignore=should_ignore,
                )
            else:
                record = ModelUpdateRecord(
                    model_type=model_type,
                    model_id=model_id,
                    largest_version_id=None,
                    version_ids=[],
                    in_library_version_ids=[],
                    last_checked_at=None,
                    should_ignore=should_ignore,
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

    async def _refresh_single_model(
        self,
        model_type: str,
        model_id: int,
        local_versions: Sequence[int],
        metadata_provider,
        *,
        force_refresh: bool = False,
    ) -> Optional[ModelUpdateRecord]:
        normalized_local = self._normalize_sequence(local_versions)
        now = time.time()
        async with self._lock:
            existing = self._get_record(model_type, model_id)
            if existing and existing.should_ignore and not force_refresh:
                record = ModelUpdateRecord(
                    model_type=model_type,
                    model_id=model_id,
                    largest_version_id=existing.largest_version_id,
                    version_ids=list(existing.version_ids),
                    in_library_version_ids=normalized_local,
                    last_checked_at=existing.last_checked_at,
                    should_ignore=True,
                )
                self._upsert_record(record)
                return record

            should_fetch = force_refresh or not existing or self._is_stale(existing, now)
        # release lock during network request
        fetched_versions: List[int] | None = None
        if metadata_provider and should_fetch:
            try:
                response = await metadata_provider.get_model_versions(model_id)
            except RateLimitError:
                raise
            except Exception as exc:  # pragma: no cover - defensive log
                logger.error(
                    "Failed to fetch versions for model %s (%s): %s",
                    model_id,
                    model_type,
                    exc,
                    exc_info=True,
                )
            else:
                fetched_versions = self._extract_version_ids(response)

        async with self._lock:
            existing = self._get_record(model_type, model_id)
            if existing and existing.should_ignore and not force_refresh:
                # Ignore state could have flipped while awaiting provider
                record = ModelUpdateRecord(
                    model_type=model_type,
                    model_id=model_id,
                    largest_version_id=existing.largest_version_id,
                    version_ids=list(existing.version_ids),
                    in_library_version_ids=normalized_local,
                    last_checked_at=existing.last_checked_at,
                    should_ignore=True,
                )
                self._upsert_record(record)
                return record

            version_ids = (
                fetched_versions
                if fetched_versions is not None
                else (list(existing.version_ids) if existing else [])
            )
            largest = max(version_ids) if version_ids else None
            last_checked = now if fetched_versions is not None else (
                existing.last_checked_at if existing else None
            )
            record = ModelUpdateRecord(
                model_type=model_type,
                model_id=model_id,
                largest_version_id=largest,
                version_ids=version_ids,
                in_library_version_ids=normalized_local,
                last_checked_at=last_checked,
                should_ignore=existing.should_ignore if existing else False,
            )
            self._upsert_record(record)
            return record

    async def _collect_local_versions(self, scanner) -> Dict[int, List[int]]:
        cache = await scanner.get_cached_data()
        mapping: Dict[int, set[int]] = {}
        if not cache or not getattr(cache, "raw_data", None):
            return {}

        for item in cache.raw_data:
            civitai = item.get("civitai") if isinstance(item, dict) else None
            if not isinstance(civitai, dict):
                continue
            model_id = self._normalize_int(civitai.get("modelId"))
            version_id = self._normalize_int(civitai.get("id"))
            if model_id is None or version_id is None:
                continue
            mapping.setdefault(model_id, set()).add(version_id)

        return {model_id: sorted(ids) for model_id, ids in mapping.items()}

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

    def _extract_version_ids(self, response) -> List[int]:
        if not isinstance(response, Mapping):
            return []
        versions = response.get("modelVersions")
        if not isinstance(versions, Iterable):
            return []
        normalized = []
        for entry in versions:
            if isinstance(entry, Mapping):
                normalized_id = self._normalize_int(entry.get("id"))
            else:
                normalized_id = self._normalize_int(entry)
            if normalized_id is not None:
                normalized.append(normalized_id)
        return sorted(dict.fromkeys(normalized))

    def _get_record(self, model_type: str, model_id: int) -> Optional[ModelUpdateRecord]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT model_type, model_id, largest_version_id, version_ids,
                       in_library_version_ids, last_checked_at, should_ignore
                FROM model_update_status
                WHERE model_type = ? AND model_id = ?
                """,
                (model_type, model_id),
            ).fetchone()
        if not row:
            return None
        return ModelUpdateRecord(
            model_type=row["model_type"],
            model_id=int(row["model_id"]),
            largest_version_id=self._normalize_int(row["largest_version_id"]),
            version_ids=self._deserialize_json_array(row["version_ids"]),
            in_library_version_ids=self._deserialize_json_array(
                row["in_library_version_ids"]
            ),
            last_checked_at=row["last_checked_at"],
            should_ignore=bool(row["should_ignore"]),
        )

    def _upsert_record(self, record: ModelUpdateRecord) -> None:
        payload = (
            record.model_type,
            record.model_id,
            record.largest_version_id,
            json.dumps(record.version_ids),
            json.dumps(record.in_library_version_ids),
            record.last_checked_at,
            1 if record.should_ignore else 0,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_update_status (
                    model_type, model_id, largest_version_id, version_ids,
                    in_library_version_ids, last_checked_at, should_ignore
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_type, model_id) DO UPDATE SET
                    largest_version_id = excluded.largest_version_id,
                    version_ids = excluded.version_ids,
                    in_library_version_ids = excluded.in_library_version_ids,
                    last_checked_at = excluded.last_checked_at,
                    should_ignore = excluded.should_ignore
                """,
                payload,
            )
            conn.commit()

    @staticmethod
    def _deserialize_json_array(value) -> List[int]:
        if not value:
            return []
        try:
            data = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        if isinstance(data, list):
            normalized = []
            for entry in data:
                try:
                    normalized.append(int(entry))
                except (TypeError, ValueError):
                    continue
            return sorted(dict.fromkeys(normalized))
        return []

