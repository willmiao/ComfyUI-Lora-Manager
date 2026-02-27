"""Use case encapsulating the bulk metadata refresh orchestration."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol, Sequence

from ..metadata_sync_service import MetadataSyncService
from ...utils.metadata_manager import MetadataManager


class MetadataRefreshProgressReporter(Protocol):
    """Protocol for progress reporters used during metadata refresh."""

    async def on_progress(self, payload: Dict[str, Any]) -> None:
        """Handle a metadata refresh progress update."""


class BulkMetadataRefreshUseCase:
    """Coordinate bulk metadata refreshes with progress emission."""

    def __init__(
        self,
        *,
        service,
        metadata_sync: MetadataSyncService,
        settings_service,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._service = service
        self._metadata_sync = metadata_sync
        self._settings = settings_service
        self._logger = logger or logging.getLogger(__name__)

    async def execute(
        self,
        *,
        progress_callback: Optional[MetadataRefreshProgressReporter] = None,
    ) -> Dict[str, Any]:
        """Refresh metadata for all qualifying models."""

        cache = await self._service.scanner.get_cached_data()
        total_models = len(cache.raw_data)

        enable_metadata_archive_db = self._settings.get("enable_metadata_archive_db", False)
        skip_paths = self._settings.get("metadata_refresh_skip_paths", [])
        to_process: Sequence[Dict[str, Any]] = [
            model
            for model in cache.raw_data
            if not model.get("skip_metadata_refresh", False)
            and not self._is_in_skip_path(model.get("folder", ""), skip_paths)
            and (not model.get("civitai") or not model["civitai"].get("id"))
            and not (
                # Skip models confirmed not on CivitAI when no need to retry
                model.get("from_civitai") is False
                and model.get("civitai_deleted") is True
                and (
                    not enable_metadata_archive_db
                    or model.get("db_checked", False)
                )
            )
        ]

        total_to_process = len(to_process)
        processed = 0
        success = 0
        needs_resort = False

        self._service.scanner.reset_cancellation()

        async def emit(status: str, **extra: Any) -> None:
            if progress_callback is None:
                return
            payload = {"status": status, "total": total_to_process, "processed": processed, "success": success}
            payload.update(extra)
            await progress_callback.on_progress(payload)

        await emit("started")

        for model in to_process:
            if self._service.scanner.is_cancelled():
                self._logger.info("Bulk metadata refresh cancelled by user")
                await emit("cancelled", processed=processed, success=success)
                return {"success": False, "message": "Operation cancelled", "processed": processed, "updated": success, "total": total_models}
            try:
                original_name = model.get("model_name")

                # Handle lazy hash calculation for models with pending hash status
                sha256 = model.get("sha256", "")
                hash_status = model.get("hash_status", "completed")
                file_path = model.get("file_path")

                if not sha256 and hash_status == "pending" and file_path:
                    self._logger.info(f"Calculating pending hash for {file_path}")
                    # Check if scanner has calculate_hash_for_model method (CheckpointScanner)
                    calculate_hash_method = getattr(self._service.scanner, "calculate_hash_for_model", None)
                    if calculate_hash_method:
                        sha256 = await calculate_hash_method(file_path)
                        if sha256:
                            model["sha256"] = sha256
                            model["hash_status"] = "completed"
                        else:
                            self._logger.error(f"Failed to calculate hash for {file_path}")
                            processed += 1
                            continue
                    else:
                        self._logger.warning(f"Scanner does not support lazy hash calculation for {file_path}")
                        processed += 1
                        continue

                # Skip models without valid hash
                if not model.get("sha256"):
                    self._logger.warning(f"Skipping model without hash: {file_path}")
                    processed += 1
                    continue

                await MetadataManager.hydrate_model_data(model)
                result, _ = await self._metadata_sync.fetch_and_update_model(
                    sha256=model["sha256"],
                    file_path=model["file_path"],
                    model_data=model,
                    update_cache_func=self._service.scanner.update_single_model_cache,
                )
                if result:
                    success += 1
                    if original_name != model.get("model_name"):
                        needs_resort = True
                processed += 1
                await emit(
                    "processing",
                    processed=processed,
                    success=success,
                    current_name=model.get("model_name", "Unknown"),
                )
            except Exception as exc:  # pragma: no cover - logging path
                processed += 1
                self._logger.error(
                    "Error fetching CivitAI data for %s: %s",
                    model.get("file_path"),
                    exc,
                )

        if needs_resort:
            await cache.resort()

        await emit("completed", processed=processed, success=success)

        message = (
            "Successfully updated "
            f"{success} of {processed} processed {self._service.model_type}s (total: {total_models})"
        )

        return {"success": True, "message": message, "processed": processed, "updated": success, "total": total_models}

    @staticmethod
    def _is_in_skip_path(folder: str, skip_paths: List[str]) -> bool:
        if not skip_paths or not folder:
            return False
        normalized = folder.replace("\\", "/").strip("/")
        if not normalized:
            return False
        for sp in skip_paths:
            nsp = sp.replace("\\", "/").strip("/")
            if not nsp:
                continue
            if normalized == nsp or normalized.startswith(nsp + "/"):
                return True
        return False

    async def execute_with_error_handling(
        self,
        *,
        progress_callback: Optional[MetadataRefreshProgressReporter] = None,
    ) -> Dict[str, Any]:
        """Wrapper providing progress notification on unexpected failures."""

        try:
            return await self.execute(progress_callback=progress_callback)
        except Exception as exc:
            if progress_callback is not None:
                await progress_callback.on_progress({"status": "error", "error": str(exc)})
            raise
