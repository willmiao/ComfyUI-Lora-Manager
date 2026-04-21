import copy
import logging
import os
import asyncio
import inspect
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
import uuid
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from ..utils.models import LoraMetadata, CheckpointMetadata, EmbeddingMetadata
from ..utils.constants import (
    CARD_PREVIEW_WIDTH,
    DIFFUSION_MODEL_BASE_MODELS,
    SUPPORTED_DOWNLOAD_SKIP_BASE_MODELS,
    VALID_LORA_TYPES,
)
from ..utils.civitai_utils import normalize_civitai_download_url, rewrite_preview_url
from ..utils.preview_selection import resolve_mature_threshold, select_preview_media
from ..utils.utils import sanitize_folder_name
from ..utils.exif_utils import ExifUtils
from ..utils.metadata_manager import MetadataManager
from .service_registry import ServiceRegistry
from .settings_manager import get_settings_manager
from .metadata_service import get_default_metadata_provider, get_metadata_provider
from .downloader import get_downloader, DownloadProgress, DownloadStreamControl
from .aria2_downloader import Aria2Error, get_aria2_downloader
from .aria2_transfer_state import Aria2TransferStateStore

# Download to temporary file first
import tempfile

logger = logging.getLogger(__name__)

CIVITAI_DOWNLOAD_URL_PREFIXES = (
    "https://civitai.com/api/download/",
    "https://civitai.red/api/download/",
)


class DownloadManager:
    _instance = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls):
        """Get singleton instance of DownloadManager"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        # Check if already initialized for singleton pattern
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # Add download management
        self._active_downloads = OrderedDict()  # download_id -> download_info
        self._download_semaphore = asyncio.Semaphore(5)  # Limit concurrent downloads
        self._download_tasks = {}  # download_id -> asyncio.Task
        self._pause_events: Dict[str, DownloadStreamControl] = {}
        self._archive_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="lm-archive"
        )
        self._aria2_state_store = Aria2TransferStateStore()
        self._restored_persisted_downloads = False
        self._restore_lock = asyncio.Lock()

    @staticmethod
    def _get_model_download_backend() -> str:
        backend = (get_settings_manager().get("download_backend") or "python").strip()
        return backend.lower() or "python"

    async def _schedule_auto_example_images_download(
        self,
        *,
        metadata,
        model_type: str,
    ) -> None:
        settings_manager = get_settings_manager()
        if not settings_manager.get("auto_download_example_images", False):
            return

        if not settings_manager.get("example_images_path"):
            logger.debug(
                "Skipping automatic example images download; example_images_path is not configured"
            )
            return

        raw_hash = getattr(metadata, "sha256", "") or ""
        model_hash = str(raw_hash).strip().lower()
        if not model_hash:
            logger.debug(
                "Skipping automatic example images download for %s; missing sha256",
                getattr(metadata, "file_path", ""),
            )
            return

        optimize = bool(settings_manager.get("optimize_example_images", True))

        async def _run_auto_example_images_download() -> None:
            try:
                from ..utils.example_images_download_manager import (
                    DownloadInProgressError,
                    get_default_download_manager,
                )

                ws_manager = await ServiceRegistry.get_websocket_manager()
                example_images_manager = get_default_download_manager(ws_manager)
                await example_images_manager.start_force_download(
                    {
                        "model_hashes": [model_hash],
                        "optimize": optimize,
                        "model_types": [model_type],
                        "delay": 0,
                    }
                )
            except DownloadInProgressError:
                logger.info(
                    "Skipping automatic example images download for %s; another example images download is already running",
                    model_hash,
                )
            except Exception as exc:
                logger.warning(
                    "Automatic example images download failed for %s: %s",
                    model_hash,
                    exc,
                    exc_info=True,
                )

        asyncio.create_task(_run_auto_example_images_download())

    async def _download_model_file(
        self,
        download_url: str,
        save_path: str,
        *,
        backend: str,
        progress_callback,
        use_auth: bool,
        download_id: Optional[str],
        pause_control: Optional[DownloadStreamControl],
    ) -> Tuple[bool, str]:
        if backend == "aria2":
            if not download_id:
                return False, "aria2 downloads require a tracked download_id"

            headers: Dict[str, str] = {}
            if use_auth:
                api_key = (get_settings_manager().get("civitai_api_key") or "").strip()
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

            try:
                aria2_downloader = await get_aria2_downloader()
                return await aria2_downloader.download_file(
                    download_url,
                    save_path,
                    download_id=download_id,
                    progress_callback=progress_callback,
                    headers=headers or None,
                )
            except Aria2Error as exc:
                logger.error("aria2 download failed for %s: %s", download_url, exc)
                return False, str(exc)

        download_kwargs = {
            "progress_callback": progress_callback,
            "use_auth": use_auth,
        }

        if pause_control is not None:
            download_kwargs["pause_event"] = pause_control

        downloader = await get_downloader()
        return await downloader.download_file(download_url, save_path, **download_kwargs)

    async def _get_lora_scanner(self):
        """Get the lora scanner from registry"""
        return await ServiceRegistry.get_lora_scanner()

    async def _get_checkpoint_scanner(self):
        """Get the checkpoint scanner from registry"""
        return await ServiceRegistry.get_checkpoint_scanner()

    async def _has_been_downloaded(self, model_type: str, model_version_id: int) -> bool:
        try:
            history_service = await ServiceRegistry.get_downloaded_version_history_service()
            return await history_service.has_been_downloaded(model_type, model_version_id)
        except Exception as exc:
            logger.debug(
                "Failed to read download history for %s version %s: %s",
                model_type,
                model_version_id,
                exc,
            )
            return False

    async def download_from_civitai(
        self,
        model_id: int = None,
        model_version_id: int = None,
        save_dir: str = None,
        relative_path: str = "",
        progress_callback=None,
        use_default_paths: bool = False,
        download_id: str = None,
        source: str = None,
        file_params: Dict = None,
    ) -> Dict:
        """Download model from Civitai with task tracking and concurrency control

        Args:
            model_id: Civitai model ID (optional if model_version_id is provided)
            model_version_id: Civitai model version ID (optional if model_id is provided)
            save_dir: Directory to save the model
            relative_path: Relative path within save_dir
            progress_callback: Callback function for progress updates
            use_default_paths: Flag to use default paths
            download_id: Unique identifier for this download task
            source: Optional source parameter to specify metadata provider
            file_params: Optional dict with file selection params (type, format, size, fp, isPrimary)

        Returns:
            Dict with download result
        """
        # Validate that at least one identifier is provided
        if not model_id and not model_version_id:
            return {
                "success": False,
                "error": "Either model_id or model_version_id must be provided",
            }

        # Use provided download_id or generate new one
        task_id = download_id or str(uuid.uuid4())

        # Register download task in tracking dict
        self._active_downloads[task_id] = {
            "model_id": model_id,
            "model_version_id": model_version_id,
            "save_dir": save_dir,
            "relative_path": relative_path,
            "use_default_paths": bool(use_default_paths),
            "source": source,
            "file_params": copy.deepcopy(file_params) if file_params is not None else None,
            "progress": 0,
            "status": "queued",
            "transfer_backend": self._get_model_download_backend(),
            "bytes_downloaded": 0,
            "total_bytes": None,
            "bytes_per_second": 0.0,
            "last_progress_timestamp": None,
        }

        pause_control = DownloadStreamControl()
        self._pause_events[task_id] = pause_control

        if self._active_downloads[task_id]["transfer_backend"] == "aria2":
            await self._persist_aria2_state(task_id)

        # Create tracking task
        download_task = asyncio.create_task(
            self._download_with_semaphore(
                task_id,
                model_id,
                model_version_id,
                save_dir,
                relative_path,
                progress_callback,
                use_default_paths,
                source,
                file_params,
            )
        )

        # Store task for tracking and cancellation
        self._download_tasks[task_id] = download_task

        try:
            # Wait for download to complete
            result = await download_task
            result["download_id"] = task_id  # Include download_id in result
            return result
        except asyncio.CancelledError:
            return {
                "success": False,
                "error": "Download was cancelled",
                "download_id": task_id,
            }
        finally:
            # Clean up task reference
            if task_id in self._download_tasks:
                del self._download_tasks[task_id]
            self._pause_events.pop(task_id, None)

    async def _download_with_semaphore(
        self,
        task_id: str,
        model_id: int,
        model_version_id: int,
        save_dir: str,
        relative_path: str,
        progress_callback=None,
        use_default_paths: bool = False,
        source: str = None,
        file_params: Dict = None,
    ):
        """Execute download with semaphore to limit concurrency"""
        # Update status to waiting
        if task_id in self._active_downloads:
            self._active_downloads[task_id]["status"] = "waiting"
            if self._active_downloads[task_id].get("transfer_backend") == "aria2":
                await self._persist_aria2_state(task_id)

        # Wrap progress callback to track progress in active_downloads
        original_callback = progress_callback

        async def tracking_callback(progress, metrics=None):
            progress_value, snapshot = self._normalize_progress(progress, metrics)

            if task_id in self._active_downloads:
                info = self._active_downloads[task_id]
                info["progress"] = round(progress_value)
                if snapshot is not None:
                    info["bytes_downloaded"] = snapshot.bytes_downloaded
                    info["total_bytes"] = snapshot.total_bytes
                    info["bytes_per_second"] = snapshot.bytes_per_second
                    pause_control = self._pause_events.get(task_id)
                    if isinstance(pause_control, DownloadStreamControl):
                        pause_control.mark_progress(snapshot.timestamp)
                        info["last_progress_timestamp"] = (
                            pause_control.last_progress_timestamp
                        )

            if original_callback:
                await self._dispatch_progress(
                    original_callback, snapshot, progress_value
                )

        # Acquire semaphore to limit concurrent downloads
        try:
            async with self._download_semaphore:
                pause_control = self._pause_events.get(task_id)
                if pause_control is not None and pause_control.is_paused():
                    if task_id in self._active_downloads:
                        self._active_downloads[task_id]["status"] = "paused"
                        self._active_downloads[task_id]["bytes_per_second"] = 0.0
                        if self._active_downloads[task_id].get("transfer_backend") == "aria2":
                            await self._persist_aria2_state(task_id)
                    await pause_control.wait()

                # Update status to downloading
                if task_id in self._active_downloads:
                    self._active_downloads[task_id]["status"] = "downloading"
                    if self._active_downloads[task_id].get("transfer_backend") == "aria2":
                        await self._persist_aria2_state(task_id)

                # Use original download implementation
                try:
                    # Check for cancellation before starting
                    if asyncio.current_task().cancelled():
                        raise asyncio.CancelledError()

                    result = await self._execute_original_download(
                        model_id,
                        model_version_id,
                        save_dir,
                        relative_path,
                        tracking_callback,
                        use_default_paths,
                        task_id,
                        self._active_downloads.get(task_id, {}).get(
                            "transfer_backend", "python"
                        ),
                        source,
                        file_params,
                    )

                    # Update status based on result
                    if task_id in self._active_downloads:
                        self._active_downloads[task_id]["status"] = (
                            result.get("status", "completed")
                            if result["success"]
                            else "failed"
                        )
                        if not result["success"]:
                            self._active_downloads[task_id]["error"] = result.get(
                                "error", "Unknown error"
                            )
                        self._active_downloads[task_id]["bytes_per_second"] = 0.0
                        if self._active_downloads[task_id].get("transfer_backend") == "aria2":
                            await self._persist_aria2_state(task_id)

                    return result
                except asyncio.CancelledError:
                    # Handle cancellation
                    if task_id in self._active_downloads:
                        self._active_downloads[task_id]["status"] = "cancelled"
                        self._active_downloads[task_id]["bytes_per_second"] = 0.0
                        if self._active_downloads[task_id].get("transfer_backend") == "aria2":
                            await self._persist_aria2_state(task_id)
                    logger.info(f"Download cancelled for task {task_id}")
                    raise
                except Exception as e:
                    # Handle other errors
                    logger.error(
                        f"Download error for task {task_id}: {str(e)}", exc_info=True
                    )
                    if task_id in self._active_downloads:
                        self._active_downloads[task_id]["status"] = "failed"
                        self._active_downloads[task_id]["error"] = str(e)
                        self._active_downloads[task_id]["bytes_per_second"] = 0.0
                        if self._active_downloads[task_id].get("transfer_backend") == "aria2":
                            await self._persist_aria2_state(task_id)
                    return {"success": False, "error": str(e)}
        finally:
            # Schedule cleanup of download record after delay
            asyncio.create_task(self._cleanup_download_record(task_id))

    def _start_background_download_task(self, download_id: str, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self._download_tasks[download_id] = task

        def _cleanup_done_task(done_task: asyncio.Task) -> None:
            current_task = self._download_tasks.get(download_id)
            if current_task is done_task:
                self._download_tasks.pop(download_id, None)
                self._pause_events.pop(download_id, None)

        task.add_done_callback(_cleanup_done_task)
        return task

    async def _cleanup_download_record(self, task_id: str):
        """Keep completed downloads in history for a short time"""
        await asyncio.sleep(600)  # Keep for 10 minutes
        if task_id in self._active_downloads:
            del self._active_downloads[task_id]

    async def _delete_file_with_retries(
        self,
        path: Optional[str],
        *,
        retries: int = 5,
        delay: float = 0.1,
    ) -> bool:
        if not path:
            return False

        for attempt in range(retries):
            if not os.path.exists(path):
                return True
            try:
                os.unlink(path)
                return True
            except FileNotFoundError:
                return True
            except Exception:
                if attempt == retries - 1:
                    return False
                await asyncio.sleep(delay)
        return False

    async def _cleanup_cancelled_download_files(
        self,
        download_id: str,
        download_info: Optional[Dict],
    ) -> None:
        target_files = set()
        persisted = await self._aria2_state_store.get(download_id)

        primary_path = None
        if isinstance(download_info, dict):
            primary_path = download_info.get("file_path")
        if not primary_path and isinstance(persisted, dict):
            primary_path = persisted.get("save_path") or persisted.get("file_path")
        if primary_path:
            target_files.add(primary_path)

        if isinstance(download_info, dict):
            for extra_path in download_info.get("extracted_paths", []):
                if extra_path:
                    target_files.add(extra_path)

        for file_path in target_files:
            deleted = await self._delete_file_with_retries(file_path)
            if deleted:
                logger.debug(f"Deleted cancelled download: {file_path}")
            elif os.path.exists(file_path):
                logger.error(f"Error deleting file: {file_path}")

        part_path = None
        if isinstance(download_info, dict):
            part_path = download_info.get("part_path")
        if part_path:
            deleted = await self._delete_file_with_retries(part_path)
            if deleted:
                logger.debug(f"Deleted partial download: {part_path}")
            elif os.path.exists(part_path):
                logger.error(f"Error deleting part file: {part_path}")

        aria2_control_path = None
        if isinstance(download_info, dict):
            aria2_control_path = download_info.get("aria2_control_path")
        if not aria2_control_path and primary_path:
            aria2_control_path = f"{primary_path}.aria2"
        if aria2_control_path:
            deleted = await self._delete_file_with_retries(aria2_control_path)
            if deleted:
                logger.debug(f"Deleted aria2 control file: {aria2_control_path}")
            elif os.path.exists(aria2_control_path):
                logger.warning(
                    "Failed to delete aria2 control file after retries: %s",
                    aria2_control_path,
                )

        for file_path in target_files:
            metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
            deleted = await self._delete_file_with_retries(metadata_path)
            if not deleted and os.path.exists(metadata_path):
                logger.error(f"Error deleting metadata file: {metadata_path}")

        preview_candidates = set()
        if isinstance(download_info, dict):
            preview_path_value = download_info.get("preview_path")
            if preview_path_value:
                preview_candidates.add(preview_path_value)

        for preview_path in preview_candidates:
            deleted = await self._delete_file_with_retries(preview_path)
            if deleted and not os.path.exists(preview_path):
                logger.debug(f"Deleted preview file: {preview_path}")
            elif os.path.exists(preview_path):
                logger.error(f"Error deleting preview file: {preview_path}")

    async def _persist_aria2_state(
        self,
        download_id: str,
        *,
        extra: Optional[Dict] = None,
    ) -> None:
        info = self._active_downloads.get(download_id)
        if not info:
            return

        payload = {
            "download_id": download_id,
            "model_id": info.get("model_id"),
            "model_version_id": info.get("model_version_id"),
            "save_dir": info.get("save_dir"),
            "relative_path": info.get("relative_path", ""),
            "use_default_paths": bool(info.get("use_default_paths", False)),
            "source": info.get("source"),
            "file_params": copy.deepcopy(info.get("file_params")),
            "transfer_backend": info.get("transfer_backend", "aria2"),
            "status": info.get("status", "queued"),
            "progress": info.get("progress", 0),
            "bytes_downloaded": info.get("bytes_downloaded", 0),
            "total_bytes": info.get("total_bytes"),
            "bytes_per_second": info.get("bytes_per_second", 0.0),
            "file_path": info.get("file_path"),
        }
        if extra:
            payload.update(extra)

        await self._aria2_state_store.upsert(download_id, payload)

    def _build_restored_download_info(self, record: Dict, save_path: str) -> Dict:
        return {
            "model_id": record.get("model_id"),
            "model_version_id": record.get("model_version_id"),
            "save_dir": record.get("save_dir"),
            "relative_path": record.get("relative_path", ""),
            "use_default_paths": bool(record.get("use_default_paths", False)),
            "source": record.get("source"),
            "file_params": copy.deepcopy(record.get("file_params")),
            "progress": record.get("progress", 0),
            "status": record.get("status", "paused"),
            "transfer_backend": "aria2",
            "bytes_downloaded": record.get("bytes_downloaded", 0),
            "total_bytes": record.get("total_bytes"),
            "bytes_per_second": record.get("bytes_per_second", 0.0),
            "last_progress_timestamp": None,
            "file_path": save_path,
            "aria2_control_path": f"{save_path}.aria2",
        }

    def _is_same_aria2_download_request(
        self,
        current_info: Optional[Dict],
        persisted_record: Dict,
    ) -> bool:
        if not isinstance(current_info, dict):
            return False

        current_version_id = current_info.get("model_version_id")
        persisted_version_id = persisted_record.get("model_version_id")
        if current_version_id is None or persisted_version_id is None:
            return False

        return current_version_id == persisted_version_id

    def _build_download_urls_from_file_info(self, file_info: Dict, source: str = None) -> List[str]:
        mirrors = file_info.get("mirrors") or []
        download_urls: List[str] = []
        if mirrors:
            for mirror in mirrors:
                if mirror.get("deletedAt") is None and mirror.get("url"):
                    download_urls.append(normalize_civitai_download_url(mirror["url"]))

            if source == "civarchive" and len(download_urls) > 1:
                civitai_urls = [
                    u for u in download_urls if u.startswith(CIVITAI_DOWNLOAD_URL_PREFIXES)
                ]
                non_civitai_urls = [
                    u for u in download_urls if not u.startswith(CIVITAI_DOWNLOAD_URL_PREFIXES)
                ]
                download_urls = non_civitai_urls + civitai_urls
        else:
            download_url = file_info.get("downloadUrl")
            if download_url:
                download_urls.append(normalize_civitai_download_url(download_url))

        return download_urls

    def _build_metadata_for_resume(
        self,
        *,
        model_type: str,
        version_info: Dict,
        file_info: Dict,
        save_path: str,
    ):
        if model_type == "checkpoint":
            return CheckpointMetadata.from_civitai_info(version_info, file_info, save_path)
        if model_type == "embedding":
            return EmbeddingMetadata.from_civitai_info(version_info, file_info, save_path)
        return LoraMetadata.from_civitai_info(version_info, file_info, save_path)

    def _resolve_save_path_from_persisted_record(self, record: Dict) -> Optional[str]:
        save_path = record.get("save_path") or record.get("file_path")
        if isinstance(save_path, str) and save_path:
            return os.path.abspath(save_path)

        resume_context = record.get("resume_context")
        if not isinstance(resume_context, dict):
            return None

        save_dir = resume_context.get("save_dir")
        file_info = resume_context.get("file_info")
        if not isinstance(save_dir, str) or not save_dir:
            return None
        if not isinstance(file_info, dict):
            return None

        file_name = file_info.get("name")
        if not isinstance(file_name, str) or not file_name:
            return None

        return os.path.abspath(os.path.join(save_dir, file_name))

    async def _resume_restored_aria2_download(self, download_id: str, record: Dict) -> Dict:
        try:
            if download_id in self._active_downloads:
                self._active_downloads[download_id]["status"] = "downloading"
                self._active_downloads[download_id]["bytes_per_second"] = 0.0
                if self._active_downloads[download_id].get("transfer_backend") == "aria2":
                    await self._persist_aria2_state(download_id)

            resume_context = record.get("resume_context")
            if not isinstance(resume_context, dict):
                result = {"success": False, "error": "Missing aria2 resume context"}
            else:
                version_info = copy.deepcopy(resume_context.get("version_info") or {})
                file_info = copy.deepcopy(resume_context.get("file_info") or {})
                model_type = (resume_context.get("model_type") or "").lower()
                relative_path = resume_context.get("relative_path", "")
                save_dir = resume_context.get("save_dir")
                source = record.get("source")

                if not version_info or not file_info or not model_type or not save_dir:
                    result = {"success": False, "error": "Incomplete aria2 resume context"}
                else:
                    save_path = (
                        record.get("save_path")
                        or record.get("file_path")
                        or os.path.join(save_dir, file_info.get("name", ""))
                    )
                    metadata = self._build_metadata_for_resume(
                        model_type=model_type,
                        version_info=version_info,
                        file_info=file_info,
                        save_path=save_path,
                    )
                    download_urls = resume_context.get("download_urls")
                    if not isinstance(download_urls, list) or not download_urls:
                        download_urls = self._build_download_urls_from_file_info(
                            file_info, source=source
                        )
                    if not download_urls:
                        result = {"success": False, "error": "No mirror URL found"}
                    else:
                        result = await self._execute_download(
                            download_urls=download_urls,
                            save_dir=save_dir,
                            metadata=metadata,
                            version_info=version_info,
                            relative_path=relative_path,
                            progress_callback=None,
                            model_type=model_type,
                            download_id=download_id,
                            transfer_backend="aria2",
                        )

                        if result.get("success", False):
                            resolved_model_id = (
                                record.get("model_id")
                                or version_info.get("modelId")
                                or (version_info.get("model") or {}).get("id")
                            )
                            await self._record_downloaded_version_history(
                                model_type,
                                resolved_model_id,
                                version_info,
                                record.get("model_version_id"),
                                record.get("save_path") or record.get("file_path"),
                            )
                            await self._sync_downloaded_version(
                                model_type,
                                resolved_model_id,
                                version_info,
                                record.get("model_version_id"),
                            )

            if download_id in self._active_downloads:
                self._active_downloads[download_id]["status"] = (
                    result.get("status", "completed")
                    if result["success"]
                    else "failed"
                )
                if not result["success"]:
                    self._active_downloads[download_id]["error"] = result.get(
                        "error", "Unknown error"
                    )
                self._active_downloads[download_id]["bytes_per_second"] = 0.0
                if self._active_downloads[download_id].get("transfer_backend") == "aria2":
                    await self._persist_aria2_state(download_id)

            return result
        except asyncio.CancelledError:
            if download_id in self._active_downloads:
                self._active_downloads[download_id]["status"] = "cancelled"
                self._active_downloads[download_id]["bytes_per_second"] = 0.0
                if self._active_downloads[download_id].get("transfer_backend") == "aria2":
                    await self._persist_aria2_state(download_id)
            logger.info(f"Download cancelled for task {download_id}")
            raise
        except Exception as exc:
            logger.error(
                f"Download error for task {download_id}: {str(exc)}", exc_info=True
            )
            if download_id in self._active_downloads:
                self._active_downloads[download_id]["status"] = "failed"
                self._active_downloads[download_id]["error"] = str(exc)
                self._active_downloads[download_id]["bytes_per_second"] = 0.0
                if self._active_downloads[download_id].get("transfer_backend") == "aria2":
                    await self._persist_aria2_state(download_id)
            return {"success": False, "error": str(exc)}
        finally:
            asyncio.create_task(self._cleanup_download_record(download_id))

    async def _adopt_existing_aria2_download(
        self,
        previous_download_id: str,
        new_download_id: str,
        persisted_record: Dict,
        save_path: str,
    ) -> None:
        aria2_downloader = await get_aria2_downloader()
        await aria2_downloader.reassign_transfer(previous_download_id, new_download_id)

        old_task = self._download_tasks.get(previous_download_id)
        if old_task is not None and not old_task.done():
            old_task.cancel()
            old_pause_control = self._pause_events.get(previous_download_id)
            if old_pause_control is not None:
                old_pause_control.resume()
            try:
                await asyncio.wait_for(asyncio.shield(old_task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if previous_download_id != new_download_id:
            self._active_downloads.pop(previous_download_id, None)
            self._pause_events.pop(previous_download_id, None)
            self._download_tasks.pop(previous_download_id, None)

        reassigned = await self._aria2_state_store.reassign(
            previous_download_id, new_download_id
        )
        merged_record = dict(persisted_record)
        if reassigned:
            merged_record.update(reassigned)

        current_info = self._active_downloads.get(new_download_id)
        if current_info is not None:
            current_info.update(
                {
                    "model_id": merged_record.get("model_id", current_info.get("model_id")),
                    "model_version_id": merged_record.get(
                        "model_version_id", current_info.get("model_version_id")
                    ),
                    "save_dir": merged_record.get("save_dir", current_info.get("save_dir")),
                    "relative_path": merged_record.get(
                        "relative_path", current_info.get("relative_path", "")
                    ),
                    "source": merged_record.get("source", current_info.get("source")),
                    "file_params": copy.deepcopy(
                        merged_record.get("file_params", current_info.get("file_params"))
                    ),
                    "file_path": save_path,
                    "aria2_control_path": f"{save_path}.aria2",
                }
            )
        else:
            self._active_downloads[new_download_id] = self._build_restored_download_info(
                merged_record, save_path
            )

    async def _restore_persisted_downloads(self) -> None:
        if self._restored_persisted_downloads:
            return

        async with self._restore_lock:
            if self._restored_persisted_downloads:
                return

            persisted = await self._aria2_state_store.load_all()
            if not persisted:
                self._restored_persisted_downloads = True
                return

            aria2_downloader = await get_aria2_downloader()
            for download_id, record in persisted.items():
                if record.get("transfer_backend") != "aria2":
                    continue

                save_path = self._resolve_save_path_from_persisted_record(record)
                if save_path is None:
                    continue

                if (
                    record.get("save_path") != save_path
                    or record.get("file_path") != save_path
                ):
                    await self._aria2_state_store.upsert(
                        download_id,
                        {
                            "save_path": save_path,
                            "file_path": save_path,
                        },
                    )
                control_path = f"{save_path}.aria2"
                gid = record.get("gid")
                status_payload = None
                if isinstance(gid, str) and gid:
                    try:
                        status_payload = await aria2_downloader.get_status_by_gid(gid)
                    except Exception:
                        status_payload = None

                if status_payload is not None:
                    remote_status = status_payload.get("status", "")
                    if remote_status in {"active", "waiting", "paused"}:
                        await aria2_downloader.restore_transfer(download_id, gid, save_path)
                        restored = self._active_downloads.setdefault(
                            download_id,
                            self._build_restored_download_info(record, save_path),
                        )
                        restored["status"] = (
                            "paused" if remote_status == "paused" else "downloading"
                        )
                        pause_control = self._pause_events.get(download_id)
                        if pause_control is None:
                            pause_control = DownloadStreamControl()
                            self._pause_events[download_id] = pause_control
                        if remote_status == "paused":
                            pause_control.pause()
                        else:
                            pause_control.resume()
                        await self._aria2_state_store.upsert(
                            download_id,
                            {
                                "gid": gid,
                                "save_path": save_path,
                                "file_path": save_path,
                                "status": restored["status"],
                            },
                        )
                        if (
                            remote_status in {"active", "waiting"}
                            and download_id not in self._download_tasks
                        ):
                            resume_context = record.get("resume_context")
                            if isinstance(resume_context, dict):
                                self._start_background_download_task(
                                    download_id,
                                    self._resume_restored_aria2_download(
                                        download_id,
                                        dict(record),
                                    )
                                )
                            else:
                                self._start_background_download_task(
                                    download_id,
                                    self._download_with_semaphore(
                                        download_id,
                                        restored.get("model_id"),
                                        restored.get("model_version_id"),
                                        restored.get("save_dir"),
                                        restored.get("relative_path", ""),
                                        None,
                                        bool(restored.get("use_default_paths", False)),
                                        restored.get("source"),
                                        restored.get("file_params"),
                                    )
                                )
                        continue

                    if remote_status == "complete" and not os.path.exists(control_path):
                        await self._aria2_state_store.remove(download_id)
                        continue

                if os.path.exists(save_path) and os.path.exists(control_path):
                    restored = self._active_downloads.setdefault(
                        download_id,
                        self._build_restored_download_info(record, save_path),
                    )
                    pause_control = self._pause_events.get(download_id)
                    if pause_control is None:
                        pause_control = DownloadStreamControl()
                        self._pause_events[download_id] = pause_control

                    # No live aria2 gid was found, so restore this partial as resumable-but-paused.
                    pause_control.pause()
                    restored["status"] = "paused"
                    await self._aria2_state_store.upsert(
                        download_id,
                        {
                            "save_path": save_path,
                            "file_path": save_path,
                            "status": "paused",
                        },
                    )
                    continue

                await self._aria2_state_store.remove(download_id)

            self._restored_persisted_downloads = True

    async def _resolve_download_target_path(
        self,
        save_dir: str,
        metadata,
        *,
        transfer_backend: str,
        download_id: Optional[str],
    ) -> Tuple[bool, str]:
        original_filename = os.path.basename(metadata.file_path)
        base_name, extension = os.path.splitext(original_filename)
        original_path = os.path.join(save_dir, original_filename)

        if transfer_backend == "aria2":
            control_path = f"{original_path}.aria2"
            if os.path.exists(original_path) and os.path.exists(control_path):
                persisted_record = None
                if download_id:
                    persisted_record = await self._aria2_state_store.get(download_id)
                    if persisted_record:
                        persisted_path = (
                            persisted_record.get("save_path")
                            or persisted_record.get("file_path")
                        )
                        if isinstance(persisted_path, str) and os.path.abspath(
                            persisted_path
                        ) == os.path.abspath(original_path):
                            logger.info(
                                "Reusing aria2 partial target %s for %s",
                                original_path,
                                download_id,
                            )
                            return True, original_path

                conflict_record = await self._aria2_state_store.find_by_save_path(
                    original_path, exclude_download_id=download_id
                )
                if conflict_record is not None:
                    current_info = self._active_downloads.get(download_id) if download_id else None
                    if download_id and self._is_same_aria2_download_request(
                        current_info, conflict_record
                    ):
                        logger.info(
                            "Reassigning aria2 partial target %s from %s to %s",
                            original_path,
                            conflict_record.get("download_id"),
                            download_id,
                        )
                        await self._adopt_existing_aria2_download(
                            conflict_record["download_id"],
                            download_id,
                            conflict_record,
                            original_path,
                        )
                        return True, original_path

                    return (
                        False,
                        f"Another aria2 download is already using '{original_filename}' for resume",
                    )

                if download_id:
                    logger.info(
                        "Reusing aria2 partial target %s for %s",
                        original_path,
                        download_id,
                    )
                    return True, original_path

        def hash_provider():
            return metadata.sha256

        unique_filename = metadata.generate_unique_filename(
            save_dir, base_name, extension, hash_provider=hash_provider
        )

        if unique_filename != original_filename:
            logger.info(
                f"Filename conflict detected. Changing '{original_filename}' to '{unique_filename}'"
            )
            save_path = os.path.join(save_dir, unique_filename)
            metadata.file_path = save_path.replace(os.sep, "/")
            metadata.file_name = os.path.splitext(unique_filename)[0]
            return True, save_path

        return True, metadata.file_path

    async def _execute_original_download(
        self,
        model_id,
        model_version_id,
        save_dir,
        relative_path,
        progress_callback,
        use_default_paths,
        download_id=None,
        transfer_backend="python",
        source=None,
        file_params=None,
    ):
        """Wrapper for original download_from_civitai implementation"""
        try:
            # Check if model version already exists in library
            if model_version_id is not None:
                # Check both scanners
                lora_scanner = await self._get_lora_scanner()
                checkpoint_scanner = await self._get_checkpoint_scanner()
                embedding_scanner = await ServiceRegistry.get_embedding_scanner()

                # Check lora scanner first
                if await lora_scanner.check_model_version_exists(model_version_id):
                    return {
                        "success": False,
                        "error": "Model version already exists in lora library",
                    }

                # Check checkpoint scanner
                if await checkpoint_scanner.check_model_version_exists(
                    model_version_id
                ):
                    return {
                        "success": False,
                        "error": "Model version already exists in checkpoint library",
                    }

                # Check embedding scanner
                if await embedding_scanner.check_model_version_exists(model_version_id):
                    return {
                        "success": False,
                        "error": "Model version already exists in embedding library",
                    }

            # Use CivArchive provider directly when source is 'civarchive'
            # This prioritizes CivArchive metadata (with mirror availability info) over Civitai
            if source == "civarchive":
                metadata_provider = await get_metadata_provider("civarchive_api")
                if not metadata_provider:
                    logger.warning(
                        "CivArchive provider not available, falling back to default provider"
                    )
                    metadata_provider = await get_default_metadata_provider()
            else:
                metadata_provider = await get_default_metadata_provider()

            # Get version info based on the provided identifier
            version_info = await metadata_provider.get_model_version(
                model_id, model_version_id
            )

            if not version_info:
                # If CivArchive provider failed and source was 'civarchive', try default provider as fallback
                if source == "civarchive":
                    logger.info(
                        "CivArchive metadata fetch failed, trying default provider"
                    )
                    metadata_provider = await get_default_metadata_provider()
                    version_info = await metadata_provider.get_model_version(
                        model_id, model_version_id
                    )

            if not version_info:
                return {"success": False, "error": "Failed to fetch model metadata"}

            model_type_from_info = version_info.get("model", {}).get("type", "").lower()
            if model_type_from_info == "checkpoint":
                model_type = "checkpoint"
            elif model_type_from_info in VALID_LORA_TYPES:
                model_type = "lora"
            elif model_type_from_info == "textualinversion":
                model_type = "embedding"
            else:
                return {
                    "success": False,
                    "error": f'Model type "{model_type_from_info}" is not supported for download',
                }

            resolved_version_id = model_version_id
            raw_version_id = version_info.get("id")
            if resolved_version_id is None and raw_version_id is not None:
                try:
                    resolved_version_id = int(raw_version_id)
                except (TypeError, ValueError):
                    resolved_version_id = None

            if (
                get_settings_manager().get_skip_previously_downloaded_model_versions()
                and resolved_version_id is not None
                and await self._has_been_downloaded(model_type, resolved_version_id)
            ):
                file_name = ""
                files = version_info.get("files")
                if isinstance(files, list):
                    primary_file = next(
                        (
                            file_info
                            for file_info in files
                            if isinstance(file_info, dict) and file_info.get("primary")
                        ),
                        None,
                    )
                    selected_file = primary_file
                    if selected_file is None:
                        selected_file = next(
                            (file_info for file_info in files if isinstance(file_info, dict)),
                            None,
                        )
                    if isinstance(selected_file, dict):
                        raw_file_name = selected_file.get("name", "")
                        if isinstance(raw_file_name, str):
                            file_name = raw_file_name.strip()

                message = (
                    f"Skipped download for '{file_name or version_info.get('name') or f'model_version:{resolved_version_id}'}' "
                    f"because version {resolved_version_id} was already downloaded before"
                )
                logger.info(message)
                return {
                    "success": True,
                    "skipped": True,
                    "status": "skipped",
                    "reason": "previously_downloaded_version",
                    "message": message,
                    "model_version_id": resolved_version_id,
                    "file_name": file_name,
                    "download_id": download_id,
                }

            excluded_base_models = get_settings_manager().get_download_skip_base_models()
            base_model_value = version_info.get("baseModel", "")
            if (
                isinstance(base_model_value, str)
                and base_model_value in SUPPORTED_DOWNLOAD_SKIP_BASE_MODELS
                and base_model_value in excluded_base_models
            ):
                file_name = ""
                files = version_info.get("files")
                if isinstance(files, list):
                    primary_file = next(
                        (
                            file_info
                            for file_info in files
                            if isinstance(file_info, dict) and file_info.get("primary")
                        ),
                        None,
                    )
                    selected_file = primary_file
                    if selected_file is None:
                        selected_file = next(
                            (file_info for file_info in files if isinstance(file_info, dict)),
                            None,
                        )
                    if isinstance(selected_file, dict):
                        raw_file_name = selected_file.get("name", "")
                        if isinstance(raw_file_name, str):
                            file_name = raw_file_name.strip()

                message = (
                    f"Skipped download for '{file_name or version_info.get('name') or f'model_version:{model_version_id or model_id}'}' "
                    f"because base model '{base_model_value}' is excluded in settings"
                )
                logger.info(message)
                return {
                    "success": True,
                    "skipped": True,
                    "status": "skipped",
                    "reason": "base_model_excluded",
                    "message": message,
                    "base_model": base_model_value,
                    "file_name": file_name,
                    "download_id": download_id,
                }

            # Check if this checkpoint should be treated as a diffusion model based on baseModel
            is_diffusion_model = False
            if model_type == "checkpoint":
                if base_model_value in DIFFUSION_MODEL_BASE_MODELS:
                    is_diffusion_model = True
                    logger.info(
                        f"baseModel '{base_model_value}' is a known diffusion model, routing to unet folder"
                    )

            # Case 2: model_version_id was None, check after getting version_info
            if model_version_id is None:
                version_id = version_info.get("id")

                if model_type == "lora":
                    # Check lora scanner
                    lora_scanner = await self._get_lora_scanner()
                    if await lora_scanner.check_model_version_exists(version_id):
                        return {
                            "success": False,
                            "error": "Model version already exists in lora library",
                        }
                elif model_type == "checkpoint":
                    # Check checkpoint scanner
                    checkpoint_scanner = await self._get_checkpoint_scanner()
                    if await checkpoint_scanner.check_model_version_exists(version_id):
                        return {
                            "success": False,
                            "error": "Model version already exists in checkpoint library",
                        }
                elif model_type == "embedding":
                    # Embeddings are not checked in scanners, but we can still check if it exists
                    embedding_scanner = await ServiceRegistry.get_embedding_scanner()
                    if await embedding_scanner.check_model_version_exists(version_id):
                        return {
                            "success": False,
                            "error": "Model version already exists in embedding library",
                        }

            # Handle use_default_paths
            if use_default_paths:
                settings_manager = get_settings_manager()
                # Set save_dir based on model type
                if model_type == "checkpoint":
                    if is_diffusion_model:
                        default_path = settings_manager.get("default_unet_root")
                        error_msg = "Default unet root path not set in settings"
                    else:
                        default_path = settings_manager.get("default_checkpoint_root")
                        error_msg = "Default checkpoint root path not set in settings"
                    if not default_path:
                        return {
                            "success": False,
                            "error": error_msg,
                        }
                    save_dir = default_path
                elif model_type == "lora":
                    default_path = settings_manager.get("default_lora_root")
                    if not default_path:
                        return {
                            "success": False,
                            "error": "Default lora root path not set in settings",
                        }
                    save_dir = default_path
                elif model_type == "embedding":
                    default_path = settings_manager.get("default_embedding_root")
                    if not default_path:
                        return {
                            "success": False,
                            "error": "Default embedding root path not set in settings",
                        }
                    save_dir = default_path

                # Calculate relative path using template
                relative_path = self._calculate_relative_path(version_info, model_type)

            # Update save directory with relative path if provided
            if relative_path:
                save_dir = os.path.join(save_dir, relative_path)
                # Create directory if it doesn't exist
                os.makedirs(save_dir, exist_ok=True)

            # Check if this is an early access model
            if version_info.get("earlyAccessEndsAt"):
                early_access_date = version_info.get("earlyAccessEndsAt", "")
                # Convert to a readable date if possible
                try:
                    from datetime import datetime

                    date_obj = datetime.fromisoformat(
                        early_access_date.replace("Z", "+00:00")
                    )
                    formatted_date = date_obj.strftime("%Y-%m-%d")
                    early_access_msg = (
                        f"This model requires payment (until {formatted_date}). "
                    )
                except:
                    early_access_msg = "This model requires payment. "

                early_access_msg += "Please ensure you have purchased early access and are logged in to Civitai."
                logger.warning(
                    f"Early access model detected: {version_info.get('name', 'Unknown')}"
                )

                # We'll still try to download, but log a warning and prepare for potential failure
                if progress_callback:
                    await progress_callback(
                        1
                    )  # Show minimal progress to indicate we're trying

            # Report initial progress
            if progress_callback:
                await progress_callback(0)

            # 2. Get file information
            files = version_info.get("files", [])
            file_info = None

            # If file_params is provided, try to find matching file
            if file_params and model_version_id:
                target_type = file_params.get("type", "Model")
                target_format = file_params.get("format", "SafeTensor")
                target_size = file_params.get("size", "full")
                target_fp = file_params.get("fp")
                is_primary = file_params.get("isPrimary", False)

                if is_primary:
                    # Find primary file
                    file_info = next(
                        (
                            f
                            for f in files
                            if f.get("primary")
                            and f.get("type") in ("Model", "Negative")
                        ),
                        None,
                    )
                else:
                    # Match by metadata
                    for f in files:
                        f_type = f.get("type", "")
                        f_meta = f.get("metadata", {})

                        # Check type match
                        if f_type != target_type:
                            continue

                        # Check metadata match
                        if f_meta.get("format") != target_format:
                            continue
                        if f_meta.get("size") != target_size:
                            continue
                        if target_fp and f_meta.get("fp") != target_fp:
                            continue

                        file_info = f
                        break

            # Fallback to primary file if no match found
            if not file_info:
                file_info = next(
                    (
                        f
                        for f in files
                        if f.get("primary") and f.get("type") in ("Model", "Negative")
                    ),
                    None,
                )

            if not file_info:
                return {"success": False, "error": "No suitable file found in metadata"}
            mirrors = file_info.get("mirrors") or []
            download_urls = []
            if mirrors:
                for mirror in mirrors:
                    if mirror.get("deletedAt") is None and mirror.get("url"):
                        download_urls.append(
                            normalize_civitai_download_url(mirror["url"])
                        )

                # When source is 'civarchive', prioritize non-Civitai URLs
                # This avoids failed downloads from deleted Civitai models
                if source == "civarchive" and len(download_urls) > 1:
                    civitai_urls = [
                        u
                        for u in download_urls
                        if u.startswith(CIVITAI_DOWNLOAD_URL_PREFIXES)
                    ]
                    non_civitai_urls = [
                        u
                        for u in download_urls
                        if not u.startswith(CIVITAI_DOWNLOAD_URL_PREFIXES)
                    ]
                    download_urls = non_civitai_urls + civitai_urls
            else:
                download_url = file_info.get("downloadUrl")
                if download_url:
                    download_urls.append(
                        normalize_civitai_download_url(download_url)
                    )

            if not download_urls:
                return {"success": False, "error": "No mirror URL found"}

            # 3. Prepare download
            file_name = file_info.get("name", "")
            if not file_name:
                return {"success": False, "error": "No filename found in file info"}
            save_path = os.path.join(save_dir, file_name)

            # 5. Prepare metadata based on model type
            if model_type == "checkpoint":
                metadata = CheckpointMetadata.from_civitai_info(
                    version_info, file_info, save_path
                )
                logger.info(f"Creating CheckpointMetadata for {file_name}")
            elif model_type == "lora":
                metadata = LoraMetadata.from_civitai_info(
                    version_info, file_info, save_path
                )
                logger.info(f"Creating LoraMetadata for {file_name}")
            elif model_type == "embedding":
                metadata = EmbeddingMetadata.from_civitai_info(
                    version_info, file_info, save_path
                )
                logger.info(f"Creating EmbeddingMetadata for {file_name}")

            # 6. Start download process
            if transfer_backend == "aria2" and download_id:
                await self._persist_aria2_state(
                    download_id,
                    extra={
                        "save_dir": save_dir,
                        "relative_path": relative_path,
                        "resume_context": {
                            "version_info": copy.deepcopy(version_info),
                            "file_info": copy.deepcopy(file_info),
                            "model_type": model_type,
                            "relative_path": relative_path,
                            "save_dir": save_dir,
                            "download_urls": copy.deepcopy(download_urls),
                        },
                    },
                )

            execute_kwargs = {
                "download_urls": download_urls,
                "save_dir": save_dir,
                "metadata": metadata,
                "version_info": version_info,
                "relative_path": relative_path,
                "progress_callback": progress_callback,
                "model_type": model_type,
                "download_id": download_id,
            }
            execute_signature = inspect.signature(self._execute_download)
            if (
                "transfer_backend" in execute_signature.parameters
                or any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in execute_signature.parameters.values()
                )
            ):
                execute_kwargs["transfer_backend"] = transfer_backend

            result = await self._execute_download(**execute_kwargs)

            if result.get("success", False):
                resolved_model_id = (
                    model_id
                    or version_info.get("modelId")
                    or (version_info.get("model") or {}).get("id")
                )
                await self._record_downloaded_version_history(
                    model_type,
                    resolved_model_id,
                    version_info,
                    model_version_id,
                    save_path,
                )
                await self._sync_downloaded_version(
                    model_type,
                    resolved_model_id,
                    version_info,
                    model_version_id,
                )
                await self._schedule_auto_example_images_download(
                    metadata=metadata,
                    model_type=model_type,
                )

            # If early_access_msg exists and download failed, replace error message
            if "early_access_msg" in locals() and not result.get("success", False):
                result["error"] = early_access_msg

            return result

        except Exception as e:
            logger.error(f"Error in download_from_civitai: {e}", exc_info=True)
            # Check if this might be an early access error
            error_str = str(e).lower()
            if (
                "403" in error_str
                or "401" in error_str
                or "unauthorized" in error_str
                or "early access" in error_str
            ):
                return {
                    "success": False,
                    "error": f"Early access restriction: {str(e)}. Please ensure you have purchased early access and are logged in to Civitai.",
                }
            return {"success": False, "error": str(e)}

    async def _record_downloaded_version_history(
        self,
        model_type: str,
        model_id_value,
        version_info: Dict,
        fallback_version_id=None,
        file_path: str | None = None,
    ) -> None:
        try:
            history_service = await ServiceRegistry.get_downloaded_version_history_service()
        except Exception as exc:
            logger.debug(
                "Skipping download history sync; failed to acquire history service: %s",
                exc,
            )
            return

        if history_service is None:
            return

        resolved_model_id = model_id_value
        if resolved_model_id is None:
            resolved_model_id = version_info.get("modelId")
        if resolved_model_id is None:
            model_info = version_info.get("model")
            if isinstance(model_info, dict):
                resolved_model_id = model_info.get("id")

        version_id = version_info.get("id")
        if version_id is None:
            version_id = fallback_version_id

        try:
            await history_service.mark_downloaded(
                model_type,
                int(version_id),
                model_id=int(resolved_model_id) if resolved_model_id is not None else None,
                source="download",
                file_path=file_path,
            )
        except (TypeError, ValueError):
            logger.debug(
                "Skipping download history sync; invalid identifiers model=%s version=%s",
                resolved_model_id,
                version_id,
            )
        except Exception as exc:
            logger.debug("Failed to sync download history for %s: %s", model_type, exc)

    async def _sync_downloaded_version(
        self,
        model_type: str,
        model_id_value,
        version_info: Dict,
        fallback_version_id=None,
    ) -> None:
        """Ensure update tracking reflects a newly downloaded version."""

        try:
            update_service = await ServiceRegistry.get_model_update_service()
        except Exception as exc:
            logger.debug(
                "Skipping update sync; failed to acquire update service: %s", exc
            )
            return

        if update_service is None:
            return

        resolved_model_id = model_id_value
        if resolved_model_id is None:
            resolved_model_id = version_info.get("modelId")
        if resolved_model_id is None:
            model_info = version_info.get("model")
            if isinstance(model_info, dict):
                resolved_model_id = model_info.get("id")
        try:
            resolved_model_id = int(resolved_model_id)
        except (TypeError, ValueError):
            logger.debug(
                "Skipping update sync; invalid model id: %s", resolved_model_id
            )
            return

        version_id = version_info.get("id")
        if version_id is None:
            version_id = fallback_version_id
        try:
            version_id = int(version_id)
        except (TypeError, ValueError):
            logger.debug(
                "Skipping update sync; invalid version id for model %s: %s",
                resolved_model_id,
                version_id,
            )
            return

        version_ids = set()
        scanner = None
        try:
            if model_type == "lora":
                scanner = await self._get_lora_scanner()
            elif model_type == "checkpoint":
                scanner = await self._get_checkpoint_scanner()
            elif model_type == "embedding":
                scanner = await ServiceRegistry.get_embedding_scanner()
        except Exception as exc:
            logger.debug("Failed to acquire scanner for %s models: %s", model_type, exc)

        if scanner is not None:
            try:
                local_versions = await scanner.get_model_versions_by_id(
                    resolved_model_id
                )
            except Exception as exc:
                logger.debug(
                    "Failed to collect local versions for %s model %s: %s",
                    model_type,
                    resolved_model_id,
                    exc,
                )
            else:
                for entry in local_versions or []:
                    vid = entry.get("versionId")
                    try:
                        version_ids.add(int(vid))
                    except (TypeError, ValueError):
                        continue

        version_ids.add(version_id)

        try:
            await update_service.update_in_library_versions(
                model_type,
                resolved_model_id,
                sorted(version_ids),
                version_info=version_info,
            )
        except Exception as exc:
            logger.debug(
                "Failed to update in-library versions for %s model %s: %s",
                model_type,
                resolved_model_id,
                exc,
            )

    def _calculate_relative_path(
        self, version_info: Dict, model_type: str = "lora"
    ) -> str:
        """Calculate relative path using template from settings

        Args:
            version_info: Version info from Civitai API
            model_type: Type of model ('lora', 'checkpoint', 'embedding')

        Returns:
            Relative path string
        """
        # Get path template from settings for specific model type
        settings_manager = get_settings_manager()
        path_template = settings_manager.get_download_path_template(model_type)

        # If template is empty, return empty path (flat structure)
        if not path_template:
            return ""

        # Get base model name
        base_model = version_info.get("baseModel", "")

        # Get author from creator data
        creator_info = version_info.get("creator")
        if creator_info and isinstance(creator_info, dict):
            author = creator_info.get("username") or "Anonymous"
        else:
            author = "Anonymous"

        # Apply mapping if available
        base_model_mappings = settings_manager.get("base_model_path_mappings", {})
        mapped_base_model = base_model_mappings.get(base_model, base_model)

        model_info = version_info.get("model") or {}

        # Get model tags
        model_tags = model_info.get("tags", [])

        first_tag = settings_manager.resolve_priority_tag_for_model(
            model_tags, model_type
        )

        # Format the template with available data
        formatted_path = path_template
        formatted_path = formatted_path.replace("{base_model}", mapped_base_model)
        formatted_path = formatted_path.replace("{first_tag}", first_tag)
        formatted_path = formatted_path.replace("{author}", author)
        formatted_path = formatted_path.replace(
            "{model_name}", sanitize_folder_name(model_info.get("name", ""))
        )
        formatted_path = formatted_path.replace(
            "{version_name}", sanitize_folder_name(version_info.get("name", ""))
        )

        if model_type == "embedding":
            formatted_path = formatted_path.replace(" ", "_")

        return formatted_path

    async def _execute_download(
        self,
        download_urls: List[str],
        save_dir: str,
        metadata,
        version_info: Dict,
        relative_path: str,
        progress_callback=None,
        model_type: str = "lora",
        download_id: str = None,
        transfer_backend: Optional[str] = None,
    ) -> Dict:
        """Execute the actual download process including preview images and model files"""
        metadata_entries: List = []
        metadata_files_for_cleanup: List[str] = []
        extracted_paths: List[str] = []
        metadata_path = ""
        preview_targets: List[str] = []
        preview_path: str | None = None
        preview_nsfw_level = 0
        transfer_backend = (transfer_backend or self._get_model_download_backend()).lower()
        try:
            resolved, save_path = await self._resolve_download_target_path(
                save_dir,
                metadata,
                transfer_backend=transfer_backend,
                download_id=download_id,
            )
            if not resolved:
                return {"success": False, "error": save_path}

            part_path = save_path + ".part"
            metadata_path = os.path.splitext(save_path)[0] + ".metadata.json"

            pause_control = self._pause_events.get(download_id) if download_id else None

            # Store file paths in active_downloads for potential cleanup
            if download_id and download_id in self._active_downloads:
                self._active_downloads[download_id]["file_path"] = save_path
                if transfer_backend == "python":
                    self._active_downloads[download_id]["part_path"] = part_path
                if transfer_backend == "aria2":
                    self._active_downloads[download_id]["aria2_control_path"] = (
                        f"{save_path}.aria2"
                    )

            # Download preview image if available
            images = version_info.get("images", [])
            if images:
                if progress_callback:
                    await progress_callback(
                        1
                    )  # 1% progress for starting preview download

                settings_manager = get_settings_manager()
                blur_mature_content = bool(
                    settings_manager.get("blur_mature_content", True)
                )
                mature_threshold = resolve_mature_threshold(
                    {"mature_blur_level": settings_manager.get("mature_blur_level", "R")}
                )
                selected_image, nsfw_level = select_preview_media(
                    images,
                    blur_mature_content=blur_mature_content,
                    mature_threshold=mature_threshold,
                )

                preview_url = selected_image.get("url") if selected_image else None
                media_type = (
                    (selected_image.get("type") or "").lower() if selected_image else ""
                )

                def _extension_from_url(url: str, fallback: str) -> str:
                    try:
                        parsed = urlparse(url)
                    except ValueError:
                        return fallback
                    ext = os.path.splitext(parsed.path)[1]
                    return ext or fallback

                preview_downloaded = False
                preview_path = None

                if preview_url:
                    downloader = await get_downloader()

                    if media_type == "video":
                        preview_ext = _extension_from_url(preview_url, ".mp4")
                        preview_path = os.path.splitext(save_path)[0] + preview_ext
                        rewritten_url, rewritten = rewrite_preview_url(
                            preview_url, media_type="video"
                        )
                        attempt_urls: List[str] = []
                        if rewritten:
                            attempt_urls.append(rewritten_url)
                        attempt_urls.append(preview_url)

                        seen_attempts = set()
                        for attempt in attempt_urls:
                            if not attempt or attempt in seen_attempts:
                                continue
                            seen_attempts.add(attempt)
                            success, _ = await downloader.download_file(
                                attempt, preview_path, use_auth=False
                            )
                            if success:
                                preview_downloaded = True
                                break
                    else:
                        rewritten_url, rewritten = rewrite_preview_url(
                            preview_url, media_type="image"
                        )
                        if rewritten:
                            preview_ext = _extension_from_url(preview_url, ".png")
                            preview_path = os.path.splitext(save_path)[0] + preview_ext
                            success, _ = await downloader.download_file(
                                rewritten_url, preview_path, use_auth=False
                            )
                            if success:
                                preview_downloaded = True

                        if not preview_downloaded:
                            temp_path: str | None = None
                            try:
                                with tempfile.NamedTemporaryFile(
                                    suffix=".png", delete=False
                                ) as temp_file:
                                    temp_path = temp_file.name

                                (
                                    success,
                                    content,
                                    _,
                                ) = await downloader.download_to_memory(
                                    preview_url, use_auth=False
                                )
                                if success:
                                    with open(temp_path, "wb") as temp_file_handle:
                                        temp_file_handle.write(content)
                                    preview_path = (
                                        os.path.splitext(save_path)[0] + ".webp"
                                    )

                                    optimized_data, _ = ExifUtils.optimize_image(
                                        image_data=temp_path,
                                        target_width=CARD_PREVIEW_WIDTH,
                                        format="webp",
                                        quality=85,
                                        preserve_metadata=False,
                                    )

                                    with open(preview_path, "wb") as preview_file:
                                        preview_file.write(optimized_data)

                                    preview_downloaded = True
                            finally:
                                if temp_path and os.path.exists(temp_path):
                                    try:
                                        os.unlink(temp_path)
                                    except Exception as e:
                                        logger.warning(
                                            f"Failed to delete temp file: {e}"
                                        )

                if preview_downloaded and preview_path:
                    preview_nsfw_level = nsfw_level
                    metadata.preview_url = preview_path.replace(os.sep, "/")
                    metadata.preview_nsfw_level = nsfw_level
                    if download_id and download_id in self._active_downloads:
                        self._active_downloads[download_id]["preview_path"] = preview_path

                if progress_callback:
                    await progress_callback(3)  # 3% progress after preview download

            # Download model file with progress tracking using the configured backend
            downloader = None
            if transfer_backend == "python":
                downloader = await get_downloader()
                if pause_control is not None:
                    pause_control.update_stall_timeout(downloader.stall_timeout)
            if pause_control is not None and pause_control.is_paused():
                if download_id and download_id in self._active_downloads:
                    self._active_downloads[download_id]["status"] = "paused"
                    self._active_downloads[download_id]["bytes_per_second"] = 0.0
                await pause_control.wait()
                if download_id and download_id in self._active_downloads:
                    self._active_downloads[download_id]["status"] = "downloading"
            last_error = None
            for download_url in download_urls:
                download_url = normalize_civitai_download_url(download_url)
                use_auth = download_url.startswith(CIVITAI_DOWNLOAD_URL_PREFIXES)
                if transfer_backend == "aria2" and download_id:
                    await self._persist_aria2_state(
                        download_id,
                        extra={
                            "status": self._active_downloads.get(download_id, {}).get(
                                "status", "downloading"
                            ),
                            "save_path": save_path,
                            "file_path": save_path,
                            "url": download_url,
                        },
                    )
                success, result = await self._download_model_file(
                    download_url,
                    save_path,
                    backend=transfer_backend,
                    progress_callback=lambda progress, snapshot=None: (
                        self._handle_download_progress(
                            progress,
                            progress_callback,
                            snapshot,
                        )
                    ),
                    use_auth=use_auth,
                    download_id=download_id,
                    pause_control=pause_control,
                )

                if success:
                    break

                last_error = result
                if os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except Exception as e:
                        logger.warning(
                            f"Failed to remove incomplete file {save_path}: {e}"
                        )
            else:
                # Clean up files on failure, but preserve .part file for resume
                cleanup_files = [metadata_path]
                preview_path_value = getattr(metadata, "preview_url", None)
                if preview_path_value and os.path.exists(preview_path_value):
                    cleanup_files.append(preview_path_value)

                for path in cleanup_files:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception as e:
                            logger.warning(f"Failed to cleanup file {path}: {e}")

                # Keep resumable partial state for the matching backend.
                if transfer_backend == "python" and os.path.exists(part_path):
                    logger.info(f"Preserving partial download for resume: {part_path}")
                elif transfer_backend == "aria2" and os.path.exists(f"{save_path}.aria2"):
                    logger.info("Preserving aria2 partial download for resume: %s", save_path)
                    if download_id:
                        await self._persist_aria2_state(
                            download_id,
                            extra={
                                "status": "failed",
                                "save_path": save_path,
                                "file_path": save_path,
                            },
                        )

                return {
                    "success": False,
                    "error": last_error or "Failed to download file",
                }

            # 4. Handle archive extraction and prepare per-file metadata
            actual_file_paths = [save_path]
            if zipfile.is_zipfile(save_path):
                supported_extensions = self._get_supported_extensions_for_type(
                    model_type
                )
                extracted_paths = await self._extract_model_files_from_archive(
                    save_path, supported_extensions
                )
                if not extracted_paths:
                    supported_text = ", ".join(sorted(supported_extensions))
                    return {
                        "success": False,
                        "error": f"Zip archive does not contain any supported model files ({supported_text})",
                    }
                actual_file_paths = extracted_paths
                try:
                    os.remove(save_path)
                except OSError as exc:
                    logger.warning(
                        f"Unable to delete temporary archive {save_path}: {exc}"
                    )
                if download_id and download_id in self._active_downloads:
                    self._active_downloads[download_id]["file_path"] = extracted_paths[
                        0
                    ]
                    self._active_downloads[download_id]["extracted_paths"] = (
                        extracted_paths
                    )

            metadata_entries = await self._build_metadata_entries(
                metadata, actual_file_paths
            )
            if preview_path:
                preview_targets = self._distribute_preview_to_entries(
                    preview_path, metadata_entries
                )
                for entry, target in zip(metadata_entries, preview_targets):
                    entry.preview_url = target.replace(os.sep, "/")
                    entry.preview_nsfw_level = preview_nsfw_level
                if (
                    download_id
                    and download_id in self._active_downloads
                    and preview_targets
                ):
                    self._active_downloads[download_id]["preview_path"] = (
                        preview_targets[0]
                    )

            scanner = None
            if model_type == "checkpoint":
                scanner = await self._get_checkpoint_scanner()
                logger.info(f"Updating checkpoint cache for {actual_file_paths[0]}")
            elif model_type == "lora":
                scanner = await self._get_lora_scanner()
                logger.info(f"Updating lora cache for {actual_file_paths[0]}")
            elif model_type == "embedding":
                scanner = await ServiceRegistry.get_embedding_scanner()
                logger.info(f"Updating embedding cache for {actual_file_paths[0]}")

            adjust_cached_entry = (
                getattr(scanner, "adjust_cached_entry", None)
                if scanner is not None
                else None
            )

            for index, entry in enumerate(metadata_entries):
                file_path_for_adjust = getattr(
                    entry, "file_path", actual_file_paths[index]
                )
                normalized_file_path = (
                    file_path_for_adjust.replace(os.sep, "/")
                    if isinstance(file_path_for_adjust, str)
                    else str(file_path_for_adjust)
                )

                if scanner is not None:
                    find_root = getattr(scanner, "_find_root_for_file", None)
                    adjust_root = None
                    if callable(find_root):
                        try:
                            adjust_root = find_root(normalized_file_path)
                        except TypeError:
                            adjust_root = None

                    adjust_metadata = getattr(scanner, "adjust_metadata", None)
                    if callable(adjust_metadata):
                        adjusted_entry = adjust_metadata(
                            entry, normalized_file_path, adjust_root
                        )
                        if adjusted_entry is not None:
                            entry = adjusted_entry
                            metadata_entries[index] = entry

                metadata_file_path = (
                    os.path.splitext(entry.file_path)[0] + ".metadata.json"
                )
                metadata_files_for_cleanup.append(metadata_file_path)

                await MetadataManager.save_metadata(entry.file_path, entry)

                metadata_dict = entry.to_dict()
                if callable(adjust_cached_entry):
                    metadata_dict = adjust_cached_entry(metadata_dict)

                if scanner is not None:
                    await scanner.add_model_to_cache(metadata_dict, relative_path)

            if transfer_backend == "aria2" and download_id:
                await self._aria2_state_store.remove(download_id)

            # Report 100% completion
            if progress_callback:
                await progress_callback(100)

            return {"success": True}

        except Exception as e:
            logger.error(f"Error in _execute_download: {e}", exc_info=True)
            cleanup_targets = {
                path
                for path in [
                    save_path,
                    metadata_path,
                    *metadata_files_for_cleanup,
                    *extracted_paths,
                ]
                if path
            }
            preview_candidate = (
                metadata_entries[0].preview_url
                if metadata_entries
                else getattr(metadata, "preview_url", None)
            )
            if preview_candidate:
                cleanup_targets.add(preview_candidate)

            cleanup_targets.update(preview_targets)
            for path in cleanup_targets:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as exc:
                        logger.warning(f"Failed to cleanup file {path}: {exc}")

            return {"success": False, "error": str(e)}

    def _get_supported_extensions_for_type(self, model_type: str) -> Set[str]:
        if model_type == "checkpoint":
            return {
                ".ckpt",
                ".pt",
                ".pt2",
                ".bin",
                ".pth",
                ".safetensors",
                ".pkl",
                ".sft",
                ".gguf",
            }
        if model_type == "embedding":
            return {
                ".ckpt",
                ".pt",
                ".pt2",
                ".bin",
                ".pth",
                ".safetensors",
                ".pkl",
                ".sft",
            }
        return {".safetensors"}

    async def _extract_model_files_from_archive(
        self,
        archive_path: str,
        allowed_extensions: Optional[Set[str]] = None,
    ) -> List[str]:
        if not zipfile.is_zipfile(archive_path):
            return []

        target_dir = os.path.dirname(archive_path)
        normalized_extensions = {
            ext.lower() for ext in allowed_extensions or {".safetensors"}
        }

        def _extract_sync() -> List[str]:
            extracted_files: List[str] = []
            with zipfile.ZipFile(archive_path, "r") as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    extension = os.path.splitext(info.filename)[1].lower()
                    if extension not in normalized_extensions:
                        continue
                    file_name = os.path.basename(info.filename)
                    if not file_name:
                        continue
                    dest_path = self._resolve_extracted_destination(
                        target_dir, file_name
                    )
                    with archive.open(info) as source, open(dest_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    extracted_files.append(dest_path)
            return extracted_files

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._archive_executor, _extract_sync)

    async def _build_metadata_entries(
        self, base_metadata, file_paths: List[str]
    ) -> List:
        if not file_paths:
            return []

        entries: List = []
        for index, file_path in enumerate(file_paths):
            entry = base_metadata if index == 0 else copy.deepcopy(base_metadata)
            # Update file paths without modifying size and modified timestamps
            # modified should remain as the download start time (import time)
            # size will be updated below to reflect actual downloaded file size
            entry.file_path = file_path.replace(os.sep, "/")
            entry.file_name = os.path.splitext(os.path.basename(file_path))[0]
            # Update size to actual downloaded file size
            entry.size = os.path.getsize(file_path)
            # Use SHA256 from API metadata (already set in from_civitai_info)
            # Do not recalculate to avoid blocking during ComfyUI execution
            entries.append(entry)

        return entries

    def _resolve_extracted_destination(self, target_dir: str, filename: str) -> str:
        base_name, extension = os.path.splitext(filename)
        candidate = filename
        destination = os.path.join(target_dir, candidate)
        counter = 1

        while os.path.exists(destination):
            candidate = f"{base_name}-{counter}{extension}"
            destination = os.path.join(target_dir, candidate)
            counter += 1

        return destination

    def _distribute_preview_to_entries(
        self, preview_path: str, entries: List
    ) -> List[str]:
        if not preview_path or not entries:
            return []

        if not os.path.exists(preview_path):
            return []

        extension = os.path.splitext(preview_path)[1] or ".webp"

        targets = [
            os.path.splitext(entry.file_path)[0] + extension for entry in entries
        ]

        if not targets:
            return []

        first_target = targets[0]
        if preview_path != first_target:
            os.replace(preview_path, first_target)
        source_path = first_target

        for target in targets[1:]:
            shutil.copyfile(source_path, target)

        return targets

    async def _handle_download_progress(
        self,
        progress_update,
        progress_callback,
        snapshot=None,
    ):
        """Convert file download progress to overall progress."""

        if not progress_callback:
            return

        file_progress, original_snapshot = self._normalize_progress(
            progress_update, snapshot
        )
        overall_progress = 3 + (file_progress * 0.97)
        overall_progress = max(0.0, min(overall_progress, 100.0))
        rounded_progress = round(overall_progress)

        normalized_snapshot: Optional[DownloadProgress] = None
        if original_snapshot is not None:
            normalized_snapshot = DownloadProgress(
                percent_complete=overall_progress,
                bytes_downloaded=original_snapshot.bytes_downloaded,
                total_bytes=original_snapshot.total_bytes,
                bytes_per_second=original_snapshot.bytes_per_second,
                timestamp=original_snapshot.timestamp,
            )

        await self._dispatch_progress(
            progress_callback, normalized_snapshot, rounded_progress
        )

    async def cancel_download(self, download_id: str) -> Dict:
        """Cancel an active download by download_id

        Args:
            download_id: The unique identifier of the download task

        Returns:
            Dict: Status of the cancellation operation
        """
        await self._restore_persisted_downloads()

        if download_id not in self._download_tasks and download_id not in self._active_downloads:
            return {"success": False, "error": "Download task not found"}

        download_info = self._active_downloads.get(download_id)
        task = self._download_tasks.get(download_id)
        active_statuses = {"queued", "waiting", "downloading", "paused", "cancelling"}
        if task is None and (
            not isinstance(download_info, dict)
            or download_info.get("status") not in active_statuses
        ):
            return {"success": False, "error": "Download task not found"}

        should_cleanup_local_tracking = False
        try:
            backend = (
                self._active_downloads.get(download_id, {}).get("transfer_backend")
                or "python"
            )

            if backend == "aria2":
                try:
                    aria2_downloader = await get_aria2_downloader()
                    cancel_result = await aria2_downloader.cancel_download(download_id)
                    if (
                        not cancel_result.get("success")
                        and cancel_result.get("error") != "Download task not found"
                    ):
                        return cancel_result
                    should_cleanup_local_tracking = True
                except Exception as exc:
                    logger.warning(
                        "Failed to cancel aria2 transfer for %s, continuing with local task cancellation: %s",
                        download_id,
                        exc,
                    )
                    should_cleanup_local_tracking = True
            else:
                should_cleanup_local_tracking = True

            if task is not None:
                task.cancel()

            pause_control = self._pause_events.get(download_id)
            if pause_control is not None:
                pause_control.resume()

            # Update status in active downloads
            if download_id in self._active_downloads:
                self._active_downloads[download_id]["status"] = "cancelling"
                self._active_downloads[download_id]["bytes_per_second"] = 0.0

            # Wait briefly for the task to acknowledge cancellation
            if task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            # Clean up ALL files including .part when user cancels
            download_info = self._active_downloads.get(download_id)
            await self._cleanup_cancelled_download_files(download_id, download_info)
            return {"success": True, "message": "Download cancelled successfully"}
        except Exception as e:
            logger.error(f"Error cancelling download: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            if should_cleanup_local_tracking:
                self._pause_events.pop(download_id, None)
                self._download_tasks.pop(download_id, None)
                await self._aria2_state_store.remove(download_id)

    async def pause_download(self, download_id: str) -> Dict:
        """Pause an active download without losing progress."""

        await self._restore_persisted_downloads()

        if download_id not in self._download_tasks and download_id not in self._active_downloads:
            return {"success": False, "error": "Download task not found"}

        pause_control = self._pause_events.get(download_id)
        if pause_control is None:
            return {"success": False, "error": "Download task not found"}

        if pause_control.is_paused():
            return {"success": False, "error": "Download is already paused"}

        pause_control.pause()

        backend = (
            self._active_downloads.get(download_id, {}).get("transfer_backend")
            or "python"
        )
        if backend == "aria2":
            try:
                aria2_downloader = await get_aria2_downloader()
                if await aria2_downloader.has_transfer(download_id):
                    result = await aria2_downloader.pause_download(download_id)
                    if not result.get("success"):
                        pause_control.resume()
                        return result
            except Exception as exc:
                pause_control.resume()
                return {"success": False, "error": str(exc)}

            download_info = self._active_downloads.get(download_id)
            if download_info is not None:
                download_info["status"] = "paused"
                download_info["bytes_per_second"] = 0.0
                await self._persist_aria2_state(download_id)
            return {"success": True, "message": "Download paused successfully"}

        download_info = self._active_downloads.get(download_id)
        if download_info is not None:
            download_info["status"] = "paused"
            download_info["bytes_per_second"] = 0.0

        return {"success": True, "message": "Download paused successfully"}

    async def resume_download(self, download_id: str) -> Dict:
        """Resume a previously paused download."""

        await self._restore_persisted_downloads()

        pause_control = self._pause_events.get(download_id)
        if pause_control is None:
            persisted = await self._aria2_state_store.get(download_id)
            if not persisted or persisted.get("transfer_backend") != "aria2":
                return {"success": False, "error": "Download task not found"}

            save_path = persisted.get("save_path") or persisted.get("file_path")
            pause_control = DownloadStreamControl()
            pause_control.pause()
            self._pause_events[download_id] = pause_control
            self._active_downloads[download_id] = self._build_restored_download_info(
                persisted,
                os.path.abspath(save_path),
            )

        if pause_control.is_set():
            return {"success": False, "error": "Download is not paused"}

        download_info = self._active_downloads.get(download_id)
        backend = (
            self._active_downloads.get(download_id, {}).get("transfer_backend")
            or "python"
        )
        if backend == "aria2":
            try:
                persisted = None
                if download_id not in self._download_tasks:
                    persisted = await self._aria2_state_store.get(download_id)
                aria2_downloader = await get_aria2_downloader()
                if await aria2_downloader.has_transfer(download_id):
                    result = await aria2_downloader.resume_download(download_id)
                    if not result.get("success"):
                        return result
                if download_id not in self._download_tasks and persisted:
                    resume_context = persisted.get("resume_context")
                    if isinstance(resume_context, dict):
                        self._start_background_download_task(
                            download_id,
                            self._resume_restored_aria2_download(
                                download_id,
                                dict(persisted),
                            ),
                        )
                    else:
                        self._start_background_download_task(
                            download_id,
                            self._download_with_semaphore(
                                download_id,
                                persisted.get("model_id"),
                                persisted.get("model_version_id"),
                                persisted.get("save_dir"),
                                persisted.get("relative_path", ""),
                                None,
                                bool(persisted.get("use_default_paths", False)),
                                persisted.get("source"),
                                persisted.get("file_params"),
                            ),
                        )
            except Exception as exc:
                return {"success": False, "error": str(exc)}

            pause_control.resume()

            if download_info is not None:
                if download_info.get("status") == "paused":
                    download_info["status"] = "downloading"
                download_info.setdefault("bytes_per_second", 0.0)
                await self._persist_aria2_state(download_id)
            return {"success": True, "message": "Download resumed successfully"}

        force_reconnect = False
        if pause_control is not None:
            elapsed = pause_control.time_since_last_progress()
            threshold = max(30.0, pause_control.stall_timeout / 2.0)
            if elapsed is not None and elapsed >= threshold:
                force_reconnect = True
                logger.info(
                    "Forcing reconnect for download %s after %.1f seconds without progress",
                    download_id,
                    elapsed,
                )

        pause_control.resume(force_reconnect=force_reconnect)

        if download_info is not None:
            if download_info.get("status") == "paused":
                download_info["status"] = "downloading"
            download_info.setdefault("bytes_per_second", 0.0)

        return {"success": True, "message": "Download resumed successfully"}

    @staticmethod
    def _coerce_progress_value(progress) -> float:
        try:
            return float(progress)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _normalize_progress(
        cls,
        progress,
        snapshot: Optional[DownloadProgress] = None,
    ) -> Tuple[float, Optional[DownloadProgress]]:
        if isinstance(progress, DownloadProgress):
            return progress.percent_complete, progress

        if isinstance(snapshot, DownloadProgress):
            return snapshot.percent_complete, snapshot

        if isinstance(progress, dict):
            if "percent_complete" in progress:
                return cls._coerce_progress_value(
                    progress["percent_complete"]
                ), snapshot
            if "progress" in progress:
                return cls._coerce_progress_value(progress["progress"]), snapshot

        return cls._coerce_progress_value(progress), None

    async def _dispatch_progress(
        self,
        callback,
        snapshot: Optional[DownloadProgress],
        progress_value: float,
    ) -> None:
        try:
            if snapshot is not None:
                result = callback(snapshot, snapshot)
            else:
                result = callback(progress_value)
        except TypeError:
            result = callback(progress_value)

        if inspect.isawaitable(result):
            await result
        elif asyncio.iscoroutine(result):
            await result

    async def get_active_downloads(self) -> Dict:
        """Get information about all active downloads

        Returns:
            Dict: List of active downloads and their status
        """
        await self._restore_persisted_downloads()
        return {
            "downloads": [
                {
                    "download_id": task_id,
                    "model_id": info.get("model_id"),
                    "model_version_id": info.get("model_version_id"),
                    "progress": info.get("progress", 0),
                    "status": info.get("status", "unknown"),
                    "error": info.get("error", None),
                    "bytes_downloaded": info.get("bytes_downloaded", 0),
                    "total_bytes": info.get("total_bytes"),
                    "bytes_per_second": info.get("bytes_per_second", 0.0),
                }
                for task_id, info in self._active_downloads.items()
            ]
        }
