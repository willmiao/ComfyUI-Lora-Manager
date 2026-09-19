"""Filename template use case: bulk-rename library models per the configured template.

An empty template reverts previously renamed models to the original filename
recorded in their ``.metadata.json`` sidecar (``original_file_name``).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from ...utils.constants import AUTO_ORGANIZE_BATCH_SIZE
from ...utils.utils import calculate_filename_for_model
from ..model_file_service import AutoOrganizeResult, ProgressCallback
from ..model_lifecycle_service import ModelLifecycleService, load_local_metadata
from ..settings_manager import get_settings_manager
from .auto_organize_use_case import (
    AutoOrganizeInProgressError,
    AutoOrganizeLockProvider,
)

logger = logging.getLogger(__name__)

_PROGRESS_TYPE = "filename_template_progress"


class FilenameTemplateUseCase:
    """Apply the download filename template to existing library models.

    An empty template restores the recorded original filename instead of
    rendering a template. Shares the auto-organize lock (and its in-progress
    error) so a bulk rename never runs concurrently with an auto-organize
    operation.
    """

    def __init__(
        self,
        *,
        scanner,
        lifecycle_service: ModelLifecycleService,
        lock_provider: AutoOrganizeLockProvider,
        model_type: str,
        metadata_loader: Callable[[str], Awaitable[Dict[str, Any]]] = load_local_metadata,
    ) -> None:
        self._scanner = scanner
        self._lifecycle_service = lifecycle_service
        self._lock_provider = lock_provider
        self._model_type = model_type
        self._metadata_loader = metadata_loader

    async def execute(
        self,
        *,
        file_paths: Optional[Sequence[str]] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AutoOrganizeResult:
        """Run the bulk rename guarded by the shared library-operation lock."""

        is_running = getattr(self._lock_provider, "is_filename_template_running", None)
        if callable(is_running) and is_running():
            raise AutoOrganizeInProgressError(
                "A filename template operation is already running"
            )
        if self._lock_provider.is_auto_organize_running():
            raise AutoOrganizeInProgressError("Auto-organize is already running")

        lock = await self._lock_provider.get_auto_organize_lock()
        if lock.locked():
            raise AutoOrganizeInProgressError(
                "Another library operation is already running"
            )

        async with lock:
            return await self._run(
                file_paths=file_paths, progress_callback=progress_callback
            )

    async def _run(
        self,
        *,
        file_paths: Optional[Sequence[str]],
        progress_callback: Optional[ProgressCallback],
    ) -> AutoOrganizeResult:
        result = AutoOrganizeResult()
        result.operation_type = "filename_template"

        self._scanner.reset_cancellation()

        try:
            template = get_settings_manager().get_download_filename_template(
                self._model_type
            )

            cache = await self._scanner.get_cached_data()
            models = list(cache.raw_data)
            if file_paths:
                wanted = set(file_paths)
                models = [
                    model for model in models if model.get("file_path") in wanted
                ]

            result.total = len(models)

            await self._emit_progress(progress_callback, result, "started")

            for index in range(0, result.total, AUTO_ORGANIZE_BATCH_SIZE):
                if self._scanner.is_cancelled():
                    logger.info(
                        "Filename template apply cancelled for %s", self._model_type
                    )
                    break

                batch = models[index : index + AUTO_ORGANIZE_BATCH_SIZE]
                for model in batch:
                    if self._scanner.is_cancelled():
                        break
                    await self._process_model(model, template, result)
                    result.processed += 1

                await self._emit_progress(progress_callback, result, "processing")
                # Yield between batches so the server stays responsive.
                await asyncio.sleep(0.1)

            if self._scanner.is_cancelled():
                result.status = "cancelled"
                await self._emit_progress(progress_callback, result, "cancelled")
                return result

            await self._emit_progress(progress_callback, result, "completed")
            return result

        except Exception as exc:
            logger.error("Error in filename template apply: %s", exc, exc_info=True)
            if progress_callback:
                await progress_callback.on_progress(
                    {
                        "type": _PROGRESS_TYPE,
                        "status": "error",
                        "error": str(exc),
                        "operation_type": result.operation_type,
                    }
                )
            raise

    async def _process_model(
        self,
        model: Dict[str, Any],
        template: str,
        result: AutoOrganizeResult,
    ) -> None:
        model_name = model.get("model_name", "Unknown")
        try:
            file_path = model.get("file_path")
            if not file_path:
                self._add_result(result, model_name, False, "No file path found")
                result.failure_count += 1
                return

            if not template:
                # Empty template = revert to the original filename recorded
                # by the first rename; models without a record are skipped.
                new_stem = await self._resolve_recorded_original(file_path)
            else:
                new_stem = calculate_filename_for_model(model, self._model_type)
            if not new_stem:
                result.skipped_count += 1
                return

            current_stem = os.path.splitext(os.path.basename(file_path))[0]
            if new_stem == current_stem or os.path.normcase(
                new_stem
            ) == os.path.normcase(current_stem):
                result.skipped_count += 1
                return

            await self._lifecycle_service.rename_model(
                file_path=file_path, new_file_name=new_stem
            )
            result.success_count += 1

        except ValueError as exc:
            # Conflicts (e.g. target name already exists) count as failures
            # without aborting the batch.
            self._add_result(result, model_name, False, str(exc))
            result.failure_count += 1
        except Exception as exc:
            logger.error(
                "Error applying filename template to %s: %s", model_name, exc,
                exc_info=True,
            )
            self._add_result(result, model_name, False, f"Error: {exc}")
            result.failure_count += 1

    async def _resolve_recorded_original(self, file_path: str) -> str:
        """Return the original filename stem recorded at the first rename.

        Reads the ``.metadata.json`` sidecar; returns an empty string when no
        sidecar or no ``original_file_name`` entry exists (models never
        renamed, or renamed before the recording shipped).
        """
        metadata_path = f"{os.path.splitext(file_path)[0]}.metadata.json"
        metadata = await self._metadata_loader(metadata_path)
        original = metadata.get("original_file_name")
        if not isinstance(original, str):
            return ""
        return original.strip()

    async def _emit_progress(
        self,
        progress_callback: Optional[ProgressCallback],
        result: AutoOrganizeResult,
        status: str,
    ) -> None:
        if not progress_callback:
            return
        await progress_callback.on_progress(
            {
                "type": _PROGRESS_TYPE,
                "status": status,
                "total": result.total,
                "processed": result.processed,
                "success": result.success_count,
                "failures": result.failure_count,
                "skipped": result.skipped_count,
                "operation_type": result.operation_type,
            }
        )

    @staticmethod
    def _add_result(
        result: AutoOrganizeResult,
        model_name: str,
        success: bool,
        message: str,
    ) -> None:
        """Add a result entry if under the limit (mirrors ModelFileService)."""
        if len(result.results) < 100:
            result.results.append(
                {"model": model_name, "success": success, "message": message}
            )
        elif len(result.results) == 100:
            result.results_truncated = True
            result.sample_results = result.results[:50]
