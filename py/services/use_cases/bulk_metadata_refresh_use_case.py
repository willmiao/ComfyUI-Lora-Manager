"""Use case encapsulating the bulk metadata refresh orchestration."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Protocol, Sequence

from ..metadata_sync_service import MetadataSyncService
from ..model_scanner import _normalized_root_prefix, _path_matches_prefix
from ..model_sources import has_external_source
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
        eligible: Sequence[Dict[str, Any]] = [
            model
            for model in cache.raw_data
            if not model.get("skip_metadata_refresh", False)
            and not self._is_in_skip_path(model.get("folder", ""), skip_paths)
            and (not model.get("civitai") or not model["civitai"].get("id"))
            # Skip models linked to an external model site (Hugging Face /
            # ModelScope / TensorArt) — they are not on CivitAI / CivArchive.
            # Users can still refresh them individually via the right-click
            # context menu.
            and not has_external_source(model)
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

        # Models on a drive that cannot be read right now stay in the cache
        # (scoped scan keeps them), but fetching their metadata would only
        # spend CivitAI rate limit on sidecar/preview writes that cannot land.
        offline_roots = self._offline_root_details()
        if offline_roots:
            to_process = [
                model
                for model in eligible
                if not self._is_under_offline_root(model.get("file_path", ""), offline_roots)
            ]
        else:
            to_process = list(eligible)
        offline_skipped = len(eligible) - len(to_process)
        if offline_skipped:
            self._logger.info(
                "Bulk metadata refresh: %d model(s) skipped, drive offline: %s",
                offline_skipped,
                ", ".join(root["label"] for root in offline_roots),
            )

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
            payload: Dict[str, Any] = {
                "status": status,
                "total": total_models,
                "processed": processed,
                "success": success,
                "failure_count": len(failures),
                "skipped_count": skipped_count,
                "offline_skipped": offline_skipped,
                "handled": handled_count,
                "elapsed_seconds": int(time.monotonic() - start_time),
            }
            # Only include full failure details in terminal emits (completed,
            # cancelled, rate_limited) to avoid serializing the list on every
            # per-model progress update.
            if status in ("completed", "cancelled", "rate_limited"):
                if failures:
                    payload["failures"] = failures
                if offline_roots:
                    payload["offline_roots"] = [
                        {"path": root["path"], "label": root["label"]}
                        for root in offline_roots
                    ]
            payload.update(extra)
            await progress_callback.on_progress(payload)

        await emit("started")

        RATE_LIMIT_ABORT_THRESHOLD = 3
        consecutive_rate_limits = 0

        for model in to_process:
            if self._service.scanner.is_cancelled():
                self._logger.info("Bulk metadata refresh cancelled by user")
                await emit("cancelled", processed=processed, success=success)
                return {"success": False, "message": "Operation cancelled", "processed": processed, "updated": success, "total": total_models, "failures": failures, "failure_count": len(failures), "skipped_count": skipped_count, "offline_skipped": offline_skipped, "elapsed_seconds": int(time.monotonic() - start_time)}
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
                            hash_status = "completed"
                        else:
                            self._logger.error(f"Failed to calculate hash for {file_path}")
                            failures.append({"name": model.get("model_name", file_path or "Unknown"), "error": "Failed to calculate hash"})
                            processed += 1
                            handled_count += 1
                            continue
                    else:
                        self._logger.warning(f"Scanner does not support lazy hash calculation for {file_path}")
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

                await MetadataManager.hydrate_model_data(model)

                # hydrate_model_data replaces model with .metadata.json content,
                # which may lack sha256. Restore from cache and persist the fix.
                if not model.get("sha256"):
                    model["sha256"] = sha256
                    model["hash_status"] = model.get("hash_status", hash_status)
                    data_to_save = model.copy()
                    data_to_save.pop("folder", None)
                    await MetadataManager.save_metadata(file_path, data_to_save)

                result, error_msg = await self._metadata_sync.fetch_and_update_model(
                    sha256=model["sha256"],
                    file_path=model["file_path"],
                    model_data=model,
                    update_cache_func=self._service.scanner.update_single_model_cache,
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
                        "offline_skipped": offline_skipped,
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
        if offline_skipped:
            message += (
                f"; {offline_skipped} skipped, drive offline ("
                + ", ".join(root["label"] for root in offline_roots)
                + ")"
            )

        return {"success": True, "message": message, "processed": processed, "updated": success, "total": total_models, "failures": failures, "failure_count": len(failures), "skipped_count": skipped_count, "offline_skipped": offline_skipped, "elapsed_seconds": int(time.monotonic() - start_time)}

    def _offline_root_details(self) -> List[Dict[str, str]]:
        """Configured roots whose directory cannot be read right now.

        Uses the scanner's root description (live ``os.path.exists`` per root),
        so both a drive switched off at startup and one unplugged mid-session
        are covered. Root probing must never break a fetch: any failure yields
        an empty list, which disables the offline filter.
        """
        describe = getattr(self._service.scanner, "describe_model_roots", None)
        if describe is None:
            return []
        try:
            details = describe()
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.debug("Failed to describe model roots: %s", exc)
            return []

        offline: List[Dict[str, str]] = []
        for detail in details:
            if not isinstance(detail, dict) or detail.get("reachable", True):
                continue
            path = detail.get("path") or ""
            if not path:
                continue
            offline.append(
                {
                    "path": path,
                    "label": detail.get("label") or path,
                    "prefix": _normalized_root_prefix(path),
                }
            )
        return offline

    @staticmethod
    def _is_under_offline_root(
        file_path: str, offline_roots: Sequence[Dict[str, str]]
    ) -> bool:
        """Match a cached business path against offline root prefixes."""
        if not file_path:
            return False
        return any(
            _path_matches_prefix(file_path, root["prefix"]) for root in offline_roots
        )

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
