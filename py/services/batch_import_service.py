"""Batch import service for importing multiple images as recipes."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from aiohttp import web

from .recipes import (
    RecipeAnalysisService,
    RecipePersistenceService,
    RecipeValidationError,
    RecipeDownloadError,
    RecipeNotFoundError,
)


class ImportItemType(Enum):
    """Type of import item."""

    URL = "url"
    LOCAL_PATH = "local_path"


class ImportStatus(Enum):
    """Status of an individual import item."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class BatchImportItem:
    """Represents a single item to import."""

    id: str
    source: str
    item_type: ImportItemType
    status: ImportStatus = ImportStatus.PENDING
    error_message: Optional[str] = None
    recipe_name: Optional[str] = None
    recipe_id: Optional[str] = None
    duration: float = 0.0


@dataclass
class BatchImportProgress:
    """Tracks progress of a batch import operation."""

    operation_id: str
    total: int
    completed: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    current_item: str = ""
    status: str = "pending"
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    items: List[BatchImportItem] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    skip_no_metadata: bool = False
    skip_duplicates: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "total": self.total,
            "completed": self.completed,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "current_item": self.current_item,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress_percent": round((self.completed / self.total) * 100, 1)
            if self.total > 0
            else 0,
            "items": [
                {
                    "id": item.id,
                    "source": item.source,
                    "item_type": item.item_type.value,
                    "status": item.status.value,
                    "error_message": item.error_message,
                    "recipe_name": item.recipe_name,
                    "recipe_id": item.recipe_id,
                    "duration": item.duration,
                }
                for item in self.items
            ],
        }


class AdaptiveConcurrencyController:
    """Adjusts concurrency based on task performance."""

    def __init__(
        self,
        min_concurrency: int = 1,
        max_concurrency: int = 5,
        initial_concurrency: int = 3,
    ) -> None:
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.current_concurrency = initial_concurrency
        self._task_durations: List[float] = []
        self._recent_errors = 0
        self._recent_successes = 0

    def record_result(self, duration: float, success: bool) -> None:
        self._task_durations.append(duration)
        if len(self._task_durations) > 10:
            self._task_durations.pop(0)

        if success:
            self._recent_successes += 1
            if duration < 1.0 and self.current_concurrency < self.max_concurrency:
                self.current_concurrency = min(
                    self.current_concurrency + 1, self.max_concurrency
                )
            elif duration > 10.0 and self.current_concurrency > self.min_concurrency:
                self.current_concurrency = max(
                    self.current_concurrency - 1, self.min_concurrency
                )
        else:
            self._recent_errors += 1
            if self.current_concurrency > self.min_concurrency:
                self.current_concurrency = max(
                    self.current_concurrency - 1, self.min_concurrency
                )

    def reset_counters(self) -> None:
        self._recent_errors = 0
        self._recent_successes = 0

    def get_semaphore(self) -> asyncio.Semaphore:
        return asyncio.Semaphore(self.current_concurrency)


class BatchImportService:
    """Service for batch importing images as recipes."""

    SUPPORTED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

    def __init__(
        self,
        *,
        analysis_service: RecipeAnalysisService,
        persistence_service: RecipePersistenceService,
        ws_manager: Any,
        logger: logging.Logger,
    ) -> None:
        self._analysis_service = analysis_service
        self._persistence_service = persistence_service
        self._ws_manager = ws_manager
        self._logger = logger
        self._active_operations: Dict[str, BatchImportProgress] = {}
        self._cancellation_flags: Dict[str, bool] = {}
        self._concurrency_controller = AdaptiveConcurrencyController()

    def is_import_running(self, operation_id: Optional[str] = None) -> bool:
        if operation_id:
            progress = self._active_operations.get(operation_id)
            return progress is not None and progress.status in ("pending", "running")
        return any(
            p.status in ("pending", "running") for p in self._active_operations.values()
        )

    def get_progress(self, operation_id: str) -> Optional[BatchImportProgress]:
        return self._active_operations.get(operation_id)

    def cancel_import(self, operation_id: str) -> bool:
        if operation_id in self._active_operations:
            self._cancellation_flags[operation_id] = True
            return True
        return False

    def _validate_url(self, url: str) -> bool:
        import re

        url_pattern = re.compile(
            r"^https?://"
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
            r"localhost|"
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
            r"(?::\d+)?"
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )
        return url_pattern.match(url) is not None

    def _validate_local_path(self, path: str) -> bool:
        try:
            normalized = os.path.normpath(path)
            if not os.path.isabs(normalized):
                return False
            if ".." in normalized:
                return False
            return True
        except Exception:
            return False

    def _is_duplicate_source(
        self,
        source: str,
        item_type: ImportItemType,
        recipe_scanner: Any,
    ) -> bool:
        try:
            cache = recipe_scanner.get_cached_data_sync()
            if not cache:
                return False

            for recipe in getattr(cache, "raw_data", []):
                source_path = recipe.get("source_path") or recipe.get("source_url")
                if source_path and source_path == source:
                    return True
            return False
        except Exception:
            self._logger.warning("Failed to check for duplicates", exc_info=True)
            return False

    async def start_batch_import(
        self,
        *,
        recipe_scanner_getter: Callable[[], Any],
        civitai_client_getter: Callable[[], Any],
        items: List[Dict[str, str]],
        tags: Optional[List[str]] = None,
        skip_no_metadata: bool = False,
        skip_duplicates: bool = False,
    ) -> str:
        operation_id = str(uuid.uuid4())

        import_items = []
        for idx, item in enumerate(items):
            source = item.get("source", "")
            item_type_str = item.get("type", "url")

            if item_type_str == "url" or source.startswith(("http://", "https://")):
                item_type = ImportItemType.URL
            else:
                item_type = ImportItemType.LOCAL_PATH

            batch_import_item = BatchImportItem(
                id=f"{operation_id}_{idx}",
                source=source,
                item_type=item_type,
            )
            import_items.append(batch_import_item)

        progress = BatchImportProgress(
            operation_id=operation_id,
            total=len(import_items),
            items=import_items,
            tags=tags or [],
            skip_no_metadata=skip_no_metadata,
            skip_duplicates=skip_duplicates,
        )

        self._active_operations[operation_id] = progress
        self._cancellation_flags[operation_id] = False

        asyncio.create_task(
            self._run_batch_import(
                operation_id=operation_id,
                recipe_scanner_getter=recipe_scanner_getter,
                civitai_client_getter=civitai_client_getter,
            )
        )

        return operation_id

    async def start_directory_import(
        self,
        *,
        recipe_scanner_getter: Callable[[], Any],
        civitai_client_getter: Callable[[], Any],
        directory: str,
        recursive: bool = True,
        tags: Optional[List[str]] = None,
        skip_no_metadata: bool = False,
        skip_duplicates: bool = False,
    ) -> str:
        image_paths = await self._discover_images(directory, recursive)

        items = [{"source": path, "type": "local_path"} for path in image_paths]

        return await self.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=items,
            tags=tags,
            skip_no_metadata=skip_no_metadata,
            skip_duplicates=skip_duplicates,
        )

    async def _discover_images(
        self,
        directory: str,
        recursive: bool = True,
    ) -> List[str]:
        if not os.path.isdir(directory):
            raise RecipeValidationError(f"Directory not found: {directory}")

        image_paths: List[str] = []

        if recursive:
            for root, _, files in os.walk(directory):
                for filename in files:
                    if self._is_supported_image(filename):
                        image_paths.append(os.path.join(root, filename))
        else:
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                if os.path.isfile(filepath) and self._is_supported_image(filename):
                    image_paths.append(filepath)

        return sorted(image_paths)

    def _is_supported_image(self, filename: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        return ext in self.SUPPORTED_EXTENSIONS

    async def _run_batch_import(
        self,
        *,
        operation_id: str,
        recipe_scanner_getter: Callable[[], Any],
        civitai_client_getter: Callable[[], Any],
    ) -> None:
        progress = self._active_operations.get(operation_id)
        if not progress:
            return

        progress.status = "running"
        await self._broadcast_progress(progress)

        self._concurrency_controller = AdaptiveConcurrencyController()

        async def process_item(item: BatchImportItem) -> None:
            if self._cancellation_flags.get(operation_id, False):
                return

            progress.current_item = (
                os.path.basename(item.source)
                if item.item_type == ImportItemType.LOCAL_PATH
                else item.source[:50]
            )
            item.status = ImportStatus.PROCESSING
            await self._broadcast_progress(progress)

            start_time = time.time()
            try:
                result = await self._import_single_item(
                    item=item,
                    recipe_scanner_getter=recipe_scanner_getter,
                    civitai_client_getter=civitai_client_getter,
                    tags=progress.tags,
                    skip_no_metadata=progress.skip_no_metadata,
                    skip_duplicates=progress.skip_duplicates,
                    semaphore=self._concurrency_controller.get_semaphore(),
                )

                duration = time.time() - start_time
                item.duration = duration
                self._concurrency_controller.record_result(
                    duration, result.get("success", False)
                )

                if result.get("success"):
                    item.status = ImportStatus.SUCCESS
                    item.recipe_name = result.get("recipe_name")
                    item.recipe_id = result.get("recipe_id")
                    progress.success += 1
                elif result.get("skipped"):
                    item.status = ImportStatus.SKIPPED
                    item.error_message = result.get("error")
                    progress.skipped += 1
                else:
                    item.status = ImportStatus.FAILED
                    item.error_message = result.get("error")
                    progress.failed += 1

            except Exception as e:
                self._logger.error(f"Error importing {item.source}: {e}")
                item.status = ImportStatus.FAILED
                item.error_message = str(e)
                item.duration = time.time() - start_time
                progress.failed += 1
                self._concurrency_controller.record_result(item.duration, False)

            progress.completed += 1
            await self._broadcast_progress(progress)

        tasks = [process_item(item) for item in progress.items]
        await asyncio.gather(*tasks, return_exceptions=True)

        if self._cancellation_flags.get(operation_id, False):
            progress.status = "cancelled"
        else:
            progress.status = "completed"

        progress.finished_at = time.time()
        progress.current_item = ""
        await self._broadcast_progress(progress)

        await asyncio.sleep(5)
        self._cleanup_operation(operation_id)

    async def _import_single_item(
        self,
        *,
        item: BatchImportItem,
        recipe_scanner_getter: Callable[[], Any],
        civitai_client_getter: Callable[[], Any],
        tags: List[str],
        skip_no_metadata: bool,
        skip_duplicates: bool,
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        async with semaphore:
            recipe_scanner = recipe_scanner_getter()
            if recipe_scanner is None:
                return {"success": False, "error": "Recipe scanner unavailable"}

            try:
                if item.item_type == ImportItemType.URL:
                    if not self._validate_url(item.source):
                        return {
                            "success": False,
                            "error": f"Invalid URL format: {item.source}",
                        }

                    if skip_duplicates:
                        if self._is_duplicate_source(
                            item.source, item.item_type, recipe_scanner
                        ):
                            return {
                                "success": False,
                                "skipped": True,
                                "error": "Duplicate source URL",
                            }

                    civitai_client = civitai_client_getter()
                    analysis_result = await self._analysis_service.analyze_remote_image(
                        url=item.source,
                        recipe_scanner=recipe_scanner,
                        civitai_client=civitai_client,
                    )
                else:
                    if not self._validate_local_path(item.source):
                        return {
                            "success": False,
                            "error": f"Invalid or unsafe path: {item.source}",
                        }

                    if not os.path.exists(item.source):
                        return {
                            "success": False,
                            "error": f"File not found: {item.source}",
                        }

                    if skip_duplicates:
                        if self._is_duplicate_source(
                            item.source, item.item_type, recipe_scanner
                        ):
                            return {
                                "success": False,
                                "skipped": True,
                                "error": "Duplicate source path",
                            }

                    analysis_result = await self._analysis_service.analyze_local_image(
                        file_path=item.source,
                        recipe_scanner=recipe_scanner,
                    )

                payload = analysis_result.payload

                if payload.get("error"):
                    if skip_no_metadata and "No metadata" in payload.get("error", ""):
                        return {
                            "success": False,
                            "skipped": True,
                            "error": payload["error"],
                        }
                    return {"success": False, "error": payload["error"]}

                loras = payload.get("loras", [])
                if not loras:
                    if skip_no_metadata:
                        return {
                            "success": False,
                            "skipped": True,
                            "error": "No LoRAs found in image",
                        }
                    # When skip_no_metadata is False, allow importing images without LoRAs
                    # Continue with empty loras list

                recipe_name = self._generate_recipe_name(item, payload)
                all_tags = list(set(tags + (payload.get("tags", []) or [])))

                metadata = {
                    "base_model": payload.get("base_model", ""),
                    "loras": loras,
                    "gen_params": payload.get("gen_params", {}),
                    "source_path": item.source,
                }

                if payload.get("checkpoint"):
                    metadata["checkpoint"] = payload["checkpoint"]

                image_bytes = None
                image_base64 = payload.get("image_base64")

                if item.item_type == ImportItemType.LOCAL_PATH:
                    with open(item.source, "rb") as f:
                        image_bytes = f.read()
                    image_base64 = None

                save_result = await self._persistence_service.save_recipe(
                    recipe_scanner=recipe_scanner,
                    image_bytes=image_bytes,
                    image_base64=image_base64,
                    name=recipe_name,
                    tags=all_tags,
                    metadata=metadata,
                    extension=payload.get("extension"),
                )

                if save_result.status == 200:
                    return {
                        "success": True,
                        "recipe_name": recipe_name,
                        "recipe_id": save_result.payload.get("id"),
                    }
                else:
                    return {
                        "success": False,
                        "error": save_result.payload.get(
                            "error", "Failed to save recipe"
                        ),
                    }

            except RecipeValidationError as e:
                return {"success": False, "error": str(e)}
            except RecipeDownloadError as e:
                return {"success": False, "error": str(e)}
            except RecipeNotFoundError as e:
                return {"success": False, "skipped": True, "error": str(e)}
            except Exception as e:
                self._logger.error(
                    f"Unexpected error importing {item.source}: {e}", exc_info=True
                )
                return {"success": False, "error": str(e)}

    def _generate_recipe_name(
        self, item: BatchImportItem, payload: Dict[str, Any]
    ) -> str:
        if item.item_type == ImportItemType.LOCAL_PATH:
            base_name = os.path.splitext(os.path.basename(item.source))[0]
            return base_name[:100]
        else:
            loras = payload.get("loras", [])
            if loras:
                first_lora = loras[0].get("name", "Recipe")
                return f"Import - {first_lora}"[:100]
            return f"Imported Recipe {item.id[:8]}"

    async def _broadcast_progress(self, progress: BatchImportProgress) -> None:
        await self._ws_manager.broadcast(
            {
                "type": "batch_import_progress",
                **progress.to_dict(),
            }
        )

    def _cleanup_operation(self, operation_id: str) -> None:
        if operation_id in self._cancellation_flags:
            del self._cancellation_flags[operation_id]
