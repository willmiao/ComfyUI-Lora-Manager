"""Use case encapsulating the bulk metadata refresh orchestration."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Protocol

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
        retry_not_found_only: bool = False,
    ) -> Dict[str, Any]:
        """Refresh normal candidates or only previously negative-cached models."""

        cache = await self._service.scanner.get_cached_data()
        total_models = len(cache.raw_data)

        enable_metadata_archive_db = self._settings.get("enable_metadata_archive_db", False)
        skip_paths = self._settings.get("metadata_refresh_skip_paths", [])
        to_process: List[Dict[str, Any]] = []
        for model in cache.raw_data:
            if model.get("skip_metadata_refresh", False):
                continue
            if self._is_in_skip_path(model.get("folder", ""), skip_paths):
                continue
            metadata_missing = self._metadata_sidecar_missing(model)
            civitai = model.get("civitai") or {}
            has_civitai_id = bool(civitai.get("id"))
            confirmed_not_found = (
                model.get("from_civitai") is False
                and model.get("civitai_deleted") is True
                and (
                    not enable_metadata_archive_db
                    or model.get("db_checked", False)
                )
            )

            if retry_not_found_only:
                if confirmed_not_found:
                    to_process.append(model)
                continue

            # Keep intact Hugging Face-only records out of normal bulk CivitAI
            # fetches.  The explicit retry mode above is allowed to retry them.
            if model.get("hf_url", "") and not metadata_missing:
                continue

            # A deleted sidecar must invalidate the cached "already fetched"
            # decision.  Reuse the cached SHA256 in the processing loop so this
            # repair does not read and hash the model file again.
            if metadata_missing or (not has_civitai_id and not confirmed_not_found):
                to_process.append(model)

        total_to_process = len(to_process)
        initial_skipped = total_models - total_to_process  # models excluded from fetch queue
        processed = 0
        success = 0
        skipped_count = initial_skipped
        handled_count = initial_skipped
        needs_resort = False
        start_time = time.monotonic()
        failures: List[Dict[str, str]] = []

        self._service.scanner.reset_cancellation()

        async def emit(status: str, **extra: Any) -> None:
            if progress_callback is None:
                return
            payload = {
                "status": status,
                "total": total_models,
                "processed": processed,
                "success": success,
                "failure_count": len(failures),
                "skipped_count": skipped_count,
                "handled": handled_count,
                "candidate_total": total_to_process,
                "retry_not_found_only": retry_not_found_only,
                "elapsed_seconds": int(time.monotonic() - start_time),
            }
            # Only include full failure details in terminal emits (completed,
            # cancelled, rate_limited) to avoid serializing the list on every
            # per-model progress update.
            if failures and status in ("completed", "cancelled", "rate_limited"):
                payload["failures"] = failures
            payload.update(extra)
            await progress_callback.on_progress(payload)

        await emit("started")

        RATE_LIMIT_ABORT_THRESHOLD = 3
        consecutive_rate_limits = 0

        for model in to_process:
            if self._service.scanner.is_cancelled():
                self._logger.info("Bulk metadata refresh cancelled by user")
                await emit("cancelled", processed=processed, success=success)
                return {"success": False, "message": "Operation cancelled", "processed": processed, "updated": success, "total": total_models, "failures": failures, "failure_count": len(failures), "skipped_count": skipped_count, "elapsed_seconds": int(time.monotonic() - start_time)}
            try:
                original_name = model.get("model_name")

                # Recover a missing hash whenever the scanner supports on-demand
                # calculation.  A previous failed hydration may have removed the
                # hash even when hash_status was formerly "completed".
                sha256 = model.get("sha256", "")
                hash_status = model.get("hash_status", "completed")
                file_path = model.get("file_path")

                if not sha256 and file_path:
                    self._logger.info(f"Calculating missing hash for {file_path}")
                    # Check if scanner has calculate_hash_for_model method (CheckpointScanner)
                    calculate_hash_method = getattr(self._service.scanner, "calculate_hash_for_model", None)
                    if calculate_hash_method:
                        sha256 = await calculate_hash_method(file_path)
                        if sha256:
                            model["sha256"] = sha256
                            model["hash_status"] = "completed"
                        else:
                            self._logger.error(f"Failed to calculate hash for {file_path}")
                            failures.append({"name": model.get("model_name", file_path or "Unknown"), "error": "Failed to calculate hash"})
                            processed += 1
                            handled_count += 1
                            continue
                    else:
                        self._logger.warning(f"Scanner does not support hash calculation for {file_path}")
                        skipped_count += 1
                        processed += 1
                        handled_count += 1
                        continue

                # Skip models without valid hash
                if not model.get("sha256"):
                    self._logger.warning(f"Skipping model without hash: {file_path}")
                    skipped_count += 1
                    processed += 1
                    handled_count += 1
                    continue

                # hydrate_model_data replaces the dictionary with the sidecar
                # payload.  When the sidecar is missing, that payload contains
                # only file_path/folder and used to erase the cached SHA256,
                # causing model["sha256"] to raise and all later retries to skip.
                cached_local_fields = {
                    key: model.get(key)
                    for key in (
                        "file_path",
                        "file_name",
                        "model_name",
                        "folder",
                        "size",
                        "modified",
                        "sha256",
                        "hash_status",
                        "base_model",
                        "preview_url",
                        "favorite",
                        "notes",
                        "usage_tips",
                        "tags",
                        "hf_url",
                    )
                }
                await MetadataManager.hydrate_model_data(model)
                for key, value in cached_local_fields.items():
                    if value in (None, "", []):
                        continue
                    if model.get(key) in (None, "", []):
                        model[key] = value

                # Use the already recovered/calculated value even if hydration
                # did not provide one, and keep it in the mutable cache entry.
                if not model.get("sha256") and sha256:
                    model["sha256"] = sha256
                if not model.get("hash_status") and hash_status:
                    model["hash_status"] = hash_status

                resolved_sha256 = model.get("sha256")
                resolved_file_path = model.get("file_path") or file_path
                if not resolved_sha256 or not resolved_file_path:
                    raise ValueError("Model identity is incomplete after metadata hydration")

                result, error_msg = await self._metadata_sync.fetch_and_update_model(
                    sha256=resolved_sha256,
                    file_path=resolved_file_path,
                    model_data=model,
                    update_cache_func=self._service.scanner.update_single_model_cache,
                    force_civitai_retry=retry_not_found_only,
                )

                if not result and error_msg and "Rate limited" in error_msg:
                    consecutive_rate_limits += 1
                else:
                    consecutive_rate_limits = 0

                if not result:
                    current_name = model.get("model_name", file_path or "Unknown")
                    failures.append({"name": current_name, "error": error_msg or "Unknown error"})
                    self._logger.warning("Failed to fetch metadata for %s: %s", current_name, error_msg)

                if consecutive_rate_limits >= RATE_LIMIT_ABORT_THRESHOLD:
                    # The current model was attempted and failed due to rate limiting;
                    # count it before aborting so the summary is consistent.
                    processed += 1
                    handled_count += 1
                    self._logger.warning(
                        "Bulk metadata refresh aborted: %d consecutive rate limits detected. "
                        "Processed %d/%d models.",
                        consecutive_rate_limits,
                        processed,
                        total_to_process,
                    )
                    await emit(
                        "rate_limited",
                    )
                    return {
                        "success": False,
                        "message": f"Rate limit detected; {total_to_process - processed} models skipped",
                        "processed": processed,
                        "updated": success,
                        "total": total_models,
                        "failures": failures,
                        "failure_count": len(failures),
                        "skipped_count": skipped_count,
                        "elapsed_seconds": int(time.monotonic() - start_time),
                    }

                if result:
                    success += 1
                    if original_name != model.get("model_name"):
                        needs_resort = True
                processed += 1
                handled_count += 1
                await emit(
                    "processing",
                    processed=processed,
                    success=success,
                    current_name=model.get("model_name", "Unknown"),
                )
            except Exception as exc:  # pragma: no cover - logging path
                processed += 1
                handled_count += 1
                current_name = model.get("model_name", model.get("file_path", "Unknown"))
                failures.append({"name": current_name, "error": str(exc)})
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

        return {"success": True, "message": message, "processed": processed, "updated": success, "total": total_models, "failures": failures, "failure_count": len(failures), "skipped_count": skipped_count, "elapsed_seconds": int(time.monotonic() - start_time)}

    @staticmethod
    def _metadata_sidecar_missing(model: Dict[str, Any]) -> bool:
        """Return True when a present model file has lost its metadata sidecar."""
        file_path = model.get("file_path")
        if not isinstance(file_path, str) or not file_path or not os.path.isfile(file_path):
            return False
        metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
        return not os.path.exists(metadata_path)

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
        retry_not_found_only: bool = False,
    ) -> Dict[str, Any]:
        """Wrapper providing progress notification on unexpected failures."""

        try:
            return await self.execute(
                progress_callback=progress_callback,
                retry_not_found_only=retry_not_found_only,
            )
        except Exception as exc:
            if progress_callback is not None:
                await progress_callback.on_progress({"status": "error", "error": str(exc)})
            raise
