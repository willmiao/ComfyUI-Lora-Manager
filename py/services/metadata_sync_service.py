"""Services for synchronising metadata with remote providers."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from ..services.settings_manager import SettingsManager
from ..utils.model_utils import determine_base_model
from .errors import RateLimitError

logger = logging.getLogger(__name__)


class MetadataProviderProtocol:
    """Subset of metadata provider interface consumed by the sync service."""

    async def get_model_by_hash(self, sha256: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        ...

    async def get_model_version(
        self, model_id: int, model_version_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        ...


class MetadataSyncService:
    """High level orchestration for metadata synchronisation flows."""

    def __init__(
        self,
        *,
        metadata_manager,
        preview_service,
        settings: SettingsManager,
        default_metadata_provider_factory: Callable[[], Awaitable[MetadataProviderProtocol]],
        metadata_provider_selector: Callable[[str], Awaitable[MetadataProviderProtocol]],
    ) -> None:
        self._metadata_manager = metadata_manager
        self._preview_service = preview_service
        self._settings = settings
        self._get_default_provider = default_metadata_provider_factory
        self._get_provider = metadata_provider_selector

    async def load_local_metadata(self, metadata_path: str) -> Dict[str, Any]:
        """Load metadata JSON from disk, returning an empty structure when missing."""

        if not os.path.exists(metadata_path):
            return {}

        try:
            with open(metadata_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error loading metadata from %s: %s", metadata_path, exc)
            return {}

    async def mark_not_found_on_civitai(
        self, metadata_path: str, local_metadata: Dict[str, Any]
    ) -> None:
        """Persist the not-found flag for a metadata payload."""

        local_metadata["from_civitai"] = False
        await self._metadata_manager.save_metadata(metadata_path, local_metadata)

    @staticmethod
    def is_civitai_api_metadata(meta: Dict[str, Any]) -> bool:
        """Determine if the metadata originated from the CivitAI public API."""

        if not isinstance(meta, dict):
            return False
        files = meta.get("files")
        images = meta.get("images")
        source = meta.get("source")
        return bool(files) and bool(images) and source != "archive_db"

    async def update_model_metadata(
        self,
        metadata_path: str,
        local_metadata: Dict[str, Any],
        civitai_metadata: Dict[str, Any],
        metadata_provider: Optional[MetadataProviderProtocol] = None,
    ) -> Dict[str, Any]:
        """Merge remote metadata into the local record and persist the result."""

        existing_civitai = local_metadata.get("civitai") or {}

        if (
            civitai_metadata.get("source") == "archive_db"
            and self.is_civitai_api_metadata(existing_civitai)
        ):
            logger.info(
                "Skip civitai update for %s (%s)",
                local_metadata.get("model_name", ""),
                existing_civitai.get("name", ""),
            )
        else:
            merged_civitai = existing_civitai.copy()
            merged_civitai.update(civitai_metadata)

            if civitai_metadata.get("source") == "archive_db":
                model_name = civitai_metadata.get("model", {}).get("name", "")
                version_name = civitai_metadata.get("name", "")
                logger.info(
                    "Recovered metadata from archive_db for deleted model: %s (%s)",
                    model_name,
                    version_name,
                )

            if "trainedWords" in existing_civitai:
                existing_trained = existing_civitai.get("trainedWords", [])
                new_trained = civitai_metadata.get("trainedWords", [])
                merged_trained = list(set(existing_trained + new_trained))
                merged_civitai["trainedWords"] = merged_trained

            local_metadata["civitai"] = merged_civitai

        if "model" in civitai_metadata and civitai_metadata["model"]:
            model_data = civitai_metadata["model"]

            if model_data.get("name"):
                local_metadata["model_name"] = model_data["name"]

            if not local_metadata.get("modelDescription") and model_data.get("description"):
                local_metadata["modelDescription"] = model_data["description"]

            if not local_metadata.get("tags") and model_data.get("tags"):
                local_metadata["tags"] = model_data["tags"]

            if model_data.get("creator") and not local_metadata.get("civitai", {}).get(
                "creator"
            ):
                local_metadata.setdefault("civitai", {})["creator"] = model_data["creator"]

        local_metadata["base_model"] = determine_base_model(
            civitai_metadata.get("baseModel")
        )

        await self._preview_service.ensure_preview_for_metadata(
            metadata_path, local_metadata, civitai_metadata.get("images", [])
        )

        await self._metadata_manager.save_metadata(metadata_path, local_metadata)
        return local_metadata

    async def fetch_and_update_model(
        self,
        *,
        sha256: str,
        file_path: str,
        model_data: Dict[str, Any],
        update_cache_func: Callable[[str, str, Dict[str, Any]], Awaitable[bool]],
    ) -> tuple[bool, Optional[str]]:
        """Fetch metadata for a model and update both disk and cache state.

        Callers should hydrate ``model_data`` via ``MetadataManager.hydrate_model_data``
        before invoking this method so that the persisted payload retains all known
        metadata fields.
        """

        if not isinstance(model_data, dict):
            error = f"Invalid model_data type: {type(model_data)}"
            logger.error(error)
            return False, error

        metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
        enable_archive = self._settings.get("enable_metadata_archive_db", False)
        previous_source = model_data.get("metadata_source") or (model_data.get("civitai") or {}).get("source")

        try:
            provider_attempts: list[tuple[Optional[str], MetadataProviderProtocol]] = []
            sqlite_attempted = False

            if model_data.get("civitai_deleted") is True:
                if previous_source in (None, "civarchive"):
                    try:
                        provider_attempts.append(("civarchive_api", await self._get_provider("civarchive_api")))
                    except Exception as exc:  # pragma: no cover - provider resolution fault
                        logger.debug("Unable to resolve civarchive provider: %s", exc)

                if enable_archive and model_data.get("db_checked") is not True:
                    try:
                        provider_attempts.append(("sqlite", await self._get_provider("sqlite")))
                    except Exception as exc:  # pragma: no cover - provider resolution fault
                        logger.debug("Unable to resolve sqlite provider: %s", exc)

                if not provider_attempts:
                    if not enable_archive:
                        error_msg = "CivitAI model is deleted and metadata archive DB is not enabled"
                    elif model_data.get("db_checked") is True:
                        error_msg = "CivitAI model is deleted and not found in metadata archive DB"
                    else:
                        error_msg = "CivitAI model is deleted and no archive provider is available"
                    return False, error_msg
            else:
                provider_attempts.append((None, await self._get_default_provider()))

            civitai_metadata: Optional[Dict[str, Any]] = None
            metadata_provider: Optional[MetadataProviderProtocol] = None
            provider_used: Optional[str] = None
            last_error: Optional[str] = None

            for provider_name, provider in provider_attempts:
                try:
                    civitai_metadata_candidate, error = await provider.get_model_by_hash(sha256)
                except RateLimitError as exc:
                    exc.provider = exc.provider or (provider_name or provider.__class__.__name__)
                    raise
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error("Provider %s failed for hash %s: %s", provider_name, sha256, exc)
                    civitai_metadata_candidate, error = None, str(exc)

                if provider_name == "sqlite":
                    sqlite_attempted = True

                if civitai_metadata_candidate:
                    civitai_metadata = civitai_metadata_candidate
                    metadata_provider = provider
                    provider_used = provider_name
                    break

                last_error = error or last_error

            if civitai_metadata is None or metadata_provider is None:
                if sqlite_attempted:
                    model_data["db_checked"] = True

                if last_error == "Model not found":
                    model_data["from_civitai"] = False
                    model_data["civitai_deleted"] = True
                    model_data["db_checked"] = sqlite_attempted or (enable_archive and model_data.get("db_checked", False))
                    model_data["last_checked_at"] = datetime.now().timestamp()

                    data_to_save = model_data.copy()
                    data_to_save.pop("folder", None)
                    await self._metadata_manager.save_metadata(file_path, data_to_save)

                default_error = (
                    "CivitAI model is deleted and metadata archive DB is not enabled"
                    if model_data.get("civitai_deleted") and not enable_archive
                    else "CivitAI model is deleted and not found in metadata archive DB"
                    if model_data.get("civitai_deleted") and (model_data.get("db_checked") is True or sqlite_attempted)
                    else "No provider returned metadata"
                )

                error_msg = (
                    f"Error fetching metadata: {last_error or default_error} "
                    f"(model_name={model_data.get('model_name', '')})"
                )
                logger.error(error_msg)
                return False, error_msg

            model_data["from_civitai"] = True
            model_data["civitai_deleted"] = civitai_metadata.get("source") == "archive_db" or civitai_metadata.get("source") == "civarchive"
            model_data["db_checked"] = enable_archive and (
                civitai_metadata.get("source") == "archive_db" or sqlite_attempted
            )
            source = civitai_metadata.get("source") or "civitai_api"
            if source == "api":
                source = "civitai_api"
            elif provider_used == "civarchive_api" and source != "civarchive":
                source = "civarchive"
            elif provider_used == "sqlite":
                source = "archive_db"
            model_data["metadata_source"] = source
            model_data["last_checked_at"] = datetime.now().timestamp()

            readable_source = {
                "civitai_api": "CivitAI API",
                "civarchive": "CivArchive API",
                "archive_db": "Archive Database",
            }.get(source, source)

            logger.info(
                "Fetched metadata for %s via %s",
                model_data.get("model_name", ""),
                readable_source,
            )

            local_metadata = model_data.copy()
            local_metadata.pop("folder", None)

            await self.update_model_metadata(
                metadata_path,
                local_metadata,
                civitai_metadata,
                metadata_provider,
            )

            update_payload = {
                "model_name": local_metadata.get("model_name"),
                "preview_url": local_metadata.get("preview_url"),
                "civitai": local_metadata.get("civitai"),
            }
            model_data.update(update_payload)

            await update_cache_func(file_path, file_path, local_metadata)
            return True, None
        except KeyError as exc:
            error_msg = f"Error fetching metadata - Missing key: {exc} in model_data={model_data}"
            logger.error(error_msg)
            return False, error_msg
        except RateLimitError as exc:
            provider_label = exc.provider or "metadata provider"
            wait_hint = (
                f"; retry after approximately {int(exc.retry_after)}s"
                if exc.retry_after and exc.retry_after > 0
                else ""
            )
            error_msg = f"Rate limited by {provider_label}{wait_hint}"
            logger.warning(error_msg)
            return False, error_msg
        except Exception as exc:  # pragma: no cover - error path
            error_msg = f"Error fetching metadata: {exc}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    async def fetch_metadata_by_sha(
        self, sha256: str, metadata_provider: Optional[MetadataProviderProtocol] = None
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Fetch metadata for a SHA256 hash from the configured provider."""

        provider = metadata_provider or await self._get_default_provider()
        return await provider.get_model_by_hash(sha256)

    async def relink_metadata(
        self,
        *,
        file_path: str,
        metadata: Dict[str, Any],
        model_id: int,
        model_version_id: Optional[int],
    ) -> Dict[str, Any]:
        """Relink a local metadata record to a specific CivitAI model version."""

        provider = await self._get_default_provider()
        civitai_metadata = await provider.get_model_version(model_id, model_version_id)
        if not civitai_metadata:
            raise ValueError(
                f"Model version not found on CivitAI for ID: {model_id}"
                + (f" with version: {model_version_id}" if model_version_id else "")
            )

        metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
        await self.update_model_metadata(
            metadata_path,
            metadata,
            civitai_metadata,
            provider,
        )

        return metadata

    async def save_metadata_updates(
        self,
        *,
        file_path: str,
        updates: Dict[str, Any],
        metadata_loader: Callable[[str], Awaitable[Dict[str, Any]]],
        update_cache: Callable[[str, str, Dict[str, Any]], Awaitable[bool]],
    ) -> Dict[str, Any]:
        """Apply metadata updates and persist to disk and cache."""

        metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
        metadata = await metadata_loader(metadata_path)

        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(metadata.get(key), dict):
                metadata[key].update(value)
            else:
                metadata[key] = value

        await self._metadata_manager.save_metadata(file_path, metadata)
        await update_cache(file_path, file_path, metadata)

        if "model_name" in updates:
            logger.debug("Metadata update touched model_name; cache resort required")

        return metadata

    async def verify_duplicate_hashes(
        self,
        *,
        file_paths: Iterable[str],
        metadata_loader: Callable[[str], Awaitable[Dict[str, Any]]],
        hash_calculator: Callable[[str], Awaitable[str]],
        update_cache: Callable[[str, str, Dict[str, Any]], Awaitable[bool]],
    ) -> Dict[str, Any]:
        """Verify a collection of files share the same SHA256 hash."""

        file_paths = list(file_paths)
        if not file_paths:
            raise ValueError("No file paths provided for verification")

        results = {
            "verified_as_duplicates": True,
            "mismatched_files": [],
            "new_hash_map": {},
        }

        expected_hash: Optional[str] = None
        first_metadata_path = os.path.splitext(file_paths[0])[0] + ".metadata.json"
        first_metadata = await metadata_loader(first_metadata_path)
        if first_metadata and "sha256" in first_metadata:
            expected_hash = first_metadata["sha256"].lower()

        for path in file_paths:
            if not os.path.exists(path):
                continue

            try:
                actual_hash = await hash_calculator(path)
                metadata_path = os.path.splitext(path)[0] + ".metadata.json"
                metadata = await metadata_loader(metadata_path)
                stored_hash = metadata.get("sha256", "").lower()

                if not expected_hash:
                    expected_hash = stored_hash

                if actual_hash != expected_hash:
                    results["verified_as_duplicates"] = False
                    results["mismatched_files"].append(path)
                    results["new_hash_map"][path] = actual_hash

                if actual_hash != stored_hash:
                    metadata["sha256"] = actual_hash
                    await self._metadata_manager.save_metadata(path, metadata)
                    await update_cache(path, path, metadata)
            except Exception as exc:  # pragma: no cover - defensive path
                logger.error("Error verifying hash for %s: %s", path, exc)
                results["mismatched_files"].append(path)
                results["new_hash_map"][path] = "error_calculating_hash"
                results["verified_as_duplicates"] = False

        return results

