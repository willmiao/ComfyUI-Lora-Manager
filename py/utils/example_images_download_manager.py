from __future__ import annotations

import asyncio
import json
import time
import logging
import os
import re
import shutil
import uuid
from typing import Any, Dict, Iterable, List, Set, Tuple

from ..services.service_registry import ServiceRegistry
from ..utils.example_images_paths import (
    ExampleImagePathResolver,
    ensure_library_root_exists,
    uses_library_scoped_folders,
)
from ..utils.metadata_manager import MetadataManager
from .example_images_processor import ExampleImagesProcessor
from .example_images_metadata import MetadataUpdater
from ..services.downloader import get_downloader
from ..services.settings_manager import get_settings_manager


class ExampleImagesDownloadError(RuntimeError):
    """Base error for example image download operations."""


class DownloadInProgressError(ExampleImagesDownloadError):
    """Raised when a download is already running."""

    def __init__(self, progress_snapshot: dict) -> None:
        super().__init__("Download already in progress")
        self.progress_snapshot = progress_snapshot


class DownloadNotRunningError(ExampleImagesDownloadError):
    """Raised when pause/resume is requested without an active download."""

    def __init__(self, message: str = "No download in progress") -> None:
        super().__init__(message)


class DownloadConfigurationError(ExampleImagesDownloadError):
    """Raised when configuration prevents starting a download."""


logger = logging.getLogger(__name__)


class _DownloadProgress(dict):
    """Mutable mapping maintaining download progress with set-aware serialisation."""

    def __init__(self) -> None:
        super().__init__()
        self.reset()

    def reset(self) -> None:
        """Reset the progress dictionary to its initial state."""

        self.update(
            total=0,
            completed=0,
            current_model='',
            status='idle',
            errors=[],
            last_error=None,
            start_time=None,
            end_time=None,
            processed_models=set(),
            refreshed_models=set(),
            failed_models=set(),
        )

    def snapshot(self) -> dict:
        """Return a JSON-serialisable snapshot of the current progress."""

        snapshot = dict(self)
        snapshot['processed_models'] = list(self['processed_models'])
        snapshot['refreshed_models'] = list(self['refreshed_models'])
        snapshot['failed_models'] = list(self['failed_models'])
        return snapshot


def _model_directory_has_files(path: str) -> bool:
    """Return True when the provided directory exists and contains entries."""

    if not path or not os.path.isdir(path):
        return False

    try:
        with os.scandir(path) as entries:
            for _ in entries:
                return True
    except OSError:
        return False

    return False

class DownloadManager:
    """Manages downloading example images for models."""

    def __init__(self, *, ws_manager, state_lock: asyncio.Lock | None = None) -> None:
        self._download_task: asyncio.Task | None = None
        self._is_downloading = False
        self._progress = _DownloadProgress()
        self._ws_manager = ws_manager
        self._state_lock = state_lock or asyncio.Lock()
        self._stop_requested = False

    def _resolve_output_dir(self, library_name: str | None = None) -> str:
        base_path = get_settings_manager().get('example_images_path')
        if not base_path:
            return ''
        return ensure_library_root_exists(library_name)

    async def start_download(self, options: dict):
        """Start downloading example images for models."""

        async with self._state_lock:
            if self._is_downloading:
                raise DownloadInProgressError(self._progress.snapshot())

            try:
                data = options or {}
                auto_mode = data.get('auto_mode', False)
                optimize = data.get('optimize', True)
                model_types = data.get('model_types', ['lora', 'checkpoint'])
                delay = float(data.get('delay', 0.2))

                settings_manager = get_settings_manager()
                base_path = settings_manager.get('example_images_path')

                if not base_path:
                    error_msg = 'Example images path not configured in settings'
                    if auto_mode:
                        logger.debug(error_msg)
                        return {
                            'success': True,
                            'message': 'Example images path not configured, skipping auto download'
                        }
                    raise DownloadConfigurationError(error_msg)

                active_library = get_settings_manager().get_active_library_name()
                output_dir = self._resolve_output_dir(active_library)
                if not output_dir:
                    raise DownloadConfigurationError('Example images path not configured in settings')

                self._progress.reset()
                self._stop_requested = False
                self._progress['status'] = 'running'
                self._progress['start_time'] = time.time()
                self._progress['end_time'] = None

                progress_file = os.path.join(output_dir, '.download_progress.json')
                progress_source = progress_file
                if uses_library_scoped_folders():
                    legacy_root = get_settings_manager().get('example_images_path') or ''
                    legacy_progress = os.path.join(legacy_root, '.download_progress.json') if legacy_root else ''
                    if legacy_progress and os.path.exists(legacy_progress) and not os.path.exists(progress_file):
                        try:
                            os.makedirs(output_dir, exist_ok=True)
                            shutil.move(legacy_progress, progress_file)
                            logger.info(
                                "Migrated legacy download progress file '%s' to '%s'",
                                legacy_progress,
                                progress_file,
                            )
                        except OSError as exc:
                            logger.warning(
                                "Failed to migrate download progress file from '%s' to '%s': %s",
                                legacy_progress,
                                progress_file,
                                exc,
                            )
                            progress_source = legacy_progress

                if os.path.exists(progress_source):
                    try:
                        with open(progress_source, 'r', encoding='utf-8') as f:
                            saved_progress = json.load(f)
                            self._progress['processed_models'] = set(saved_progress.get('processed_models', []))
                            self._progress['failed_models'] = set(saved_progress.get('failed_models', []))
                            logger.debug(
                                "Loaded previous progress, %s models already processed, %s models marked as failed",
                                len(self._progress['processed_models']),
                                len(self._progress['failed_models']),
                            )
                    except Exception as e:
                        logger.error(f"Failed to load progress file: {e}")
                        self._progress['processed_models'] = set()
                        self._progress['failed_models'] = set()
                else:
                    self._progress['processed_models'] = set()
                    self._progress['failed_models'] = set()

                self._is_downloading = True
                self._download_task = asyncio.create_task(
                    self._download_all_example_images(
                        output_dir,
                        optimize,
                        model_types,
                        delay,
                        active_library,
                    )
                )

                snapshot = self._progress.snapshot()
            except ExampleImagesDownloadError:
                # Re-raise our own exception types without wrapping
                self._is_downloading = False
                self._download_task = None
                raise
            except Exception as e:
                self._is_downloading = False
                self._download_task = None
                logger.error(f"Failed to start example images download: {e}", exc_info=True)
                raise ExampleImagesDownloadError(str(e)) from e

        await self._broadcast_progress(status='running')

        return {
            'success': True,
            'message': 'Download started',
            'status': snapshot
        }
            
    async def get_status(self, request):
        """Get the current status of example images download."""

        return {
            'success': True,
            'is_downloading': self._is_downloading,
            'status': self._progress.snapshot(),
        }

    async def pause_download(self, request):
        """Pause the example images download."""

        async with self._state_lock:
            if not self._is_downloading:
                raise DownloadNotRunningError()

            self._progress['status'] = 'paused'

        await self._broadcast_progress(status='paused')

        return {
            'success': True,
            'message': 'Download paused'
        }

    async def resume_download(self, request):
        """Resume the example images download."""

        async with self._state_lock:
            if not self._is_downloading:
                raise DownloadNotRunningError()

            if self._progress['status'] == 'paused':
                self._progress['status'] = 'running'
            else:
                raise DownloadNotRunningError(
                    f"Download is in '{self._progress['status']}' state, cannot resume"
                )

        await self._broadcast_progress(status='running')

        return {
            'success': True,
            'message': 'Download resumed'
        }

    async def stop_download(self, request):
        """Stop the example images download after the current model completes."""

        async with self._state_lock:
            if not self._is_downloading:
                raise DownloadNotRunningError()

            if self._progress['status'] in {'completed', 'error', 'stopped'}:
                raise DownloadNotRunningError()

            if self._progress['status'] != 'stopping':
                self._stop_requested = True
                self._progress['status'] = 'stopping'

        await self._broadcast_progress(status='stopping')

        return {
            'success': True,
            'message': 'Download stopping'
        }
    
    async def _download_all_example_images(
        self,
        output_dir,
        optimize,
        model_types,
        delay,
        library_name,
    ):
        """Download example images for all models."""

        downloader = await get_downloader()
        
        try:
            # Get scanners
            scanners = []
            if 'lora' in model_types:
                lora_scanner = await ServiceRegistry.get_lora_scanner()
                scanners.append(('lora', lora_scanner))
            
            if 'checkpoint' in model_types:
                checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
                scanners.append(('checkpoint', checkpoint_scanner))

            if 'embedding' in model_types:
                embedding_scanner = await ServiceRegistry.get_embedding_scanner()
                scanners.append(('embedding', embedding_scanner))
            
            # Get all models
            all_models = []
            for scanner_type, scanner in scanners:
                cache = await scanner.get_cached_data()
                if cache and cache.raw_data:
                    for model in cache.raw_data:
                        if model.get('sha256'):
                            all_models.append((scanner_type, model, scanner))
            
            # Update total count
            self._progress['total'] = len(all_models)
            logger.debug(f"Found {self._progress['total']} models to process")
            await self._broadcast_progress(status='running')
            
            # Process each model
            for i, (scanner_type, model, scanner) in enumerate(all_models):
                async with self._state_lock:
                    current_status = self._progress['status']

                if current_status not in {'running', 'paused', 'stopping'}:
                    break

                # Main logic for processing model is here, but actual operations are delegated to other classes
                was_remote_download = await self._process_model(
                    scanner_type,
                    model,
                    scanner,
                    output_dir,
                    optimize,
                    downloader,
                    library_name,
                )

                # Update progress
                self._progress['completed'] += 1

                async with self._state_lock:
                    current_status = self._progress['status']
                    should_stop = self._stop_requested and current_status == 'stopping'

                broadcast_status = 'running' if current_status == 'running' else current_status
                await self._broadcast_progress(status=broadcast_status)

                if should_stop:
                    break

                # Only add delay after remote download of models, and not after processing the last model
                if (
                    was_remote_download
                    and i < len(all_models) - 1
                    and current_status == 'running'
                ):
                    await asyncio.sleep(delay)

            async with self._state_lock:
                if self._stop_requested and self._progress['status'] == 'stopping':
                    self._progress['status'] = 'stopped'
                    self._progress['end_time'] = time.time()
                    self._stop_requested = False
                    final_status = 'stopped'
                elif self._progress['status'] not in {'error', 'stopped'}:
                    self._progress['status'] = 'completed'
                    self._progress['end_time'] = time.time()
                    self._stop_requested = False
                    final_status = 'completed'
                else:
                    final_status = self._progress['status']
                    self._stop_requested = False
                    if self._progress['end_time'] is None:
                        self._progress['end_time'] = time.time()

            if final_status == 'completed':
                logger.debug(
                    "Example images download completed: %s/%s models processed",
                    self._progress['completed'],
                    self._progress['total'],
                )
            elif final_status == 'stopped':
                logger.debug(
                    "Example images download stopped: %s/%s models processed",
                    self._progress['completed'],
                    self._progress['total'],
                )

            await self._broadcast_progress(status=final_status)

        except Exception as e:
            error_msg = f"Error during example images download: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._progress['errors'].append(error_msg)
            self._progress['last_error'] = error_msg
            self._progress['status'] = 'error'
            self._progress['end_time'] = time.time()
            await self._broadcast_progress(status='error', extra={'error': error_msg})

        finally:
            # Save final progress to file
            try:
                self._save_progress(output_dir)
            except Exception as e:
                logger.error(f"Failed to save progress file: {e}")

            # Set download status to not downloading
            async with self._state_lock:
                self._is_downloading = False
                self._download_task = None
                self._stop_requested = False
    
    async def _process_model(
        self,
        scanner_type,
        model,
        scanner,
        output_dir,
        optimize,
        downloader,
        library_name,
    ):
        """Process a single model download."""

        # Check if download is paused
        while self._progress['status'] == 'paused':
            await asyncio.sleep(1)

        # Check if download should continue
        if self._progress['status'] not in {'running', 'stopping'}:
            logger.info(f"Download stopped: {self._progress['status']}")
            return False  # Return False to indicate no remote download happened
        
        model_hash = model.get('sha256', '').lower()
        model_name = model.get('model_name', 'Unknown')
        model_file_path = model.get('file_path', '')
        model_file_name = model.get('file_name', '')
        
        try:
            # Update current model info
            self._progress['current_model'] = f"{model_name} ({model_hash[:8]})"
            await self._broadcast_progress(status='running')
            
            # Skip if already in failed models
            if model_hash in self._progress['failed_models']:
                logger.debug(f"Skipping known failed model: {model_name}")
                return False
            
            model_dir = ExampleImagePathResolver.get_model_folder(model_hash, library_name)
            existing_files = _model_directory_has_files(model_dir)

            # Skip if already processed AND directory exists with files
            if model_hash in self._progress['processed_models']:
                if existing_files:
                    logger.debug(f"Skipping already processed model: {model_name}")
                    return False
                logger.info(f"Model {model_name} marked as processed but folder empty or missing, reprocessing")
                # Remove from processed models since we need to reprocess
                self._progress['processed_models'].discard(model_hash)

            if existing_files and model_hash not in self._progress['processed_models']:
                logger.debug(
                    "Model folder already populated for %s, marking as processed without download",
                    model_name,
                )
                self._progress['processed_models'].add(model_hash)
                return False

            if not model_dir:
                logger.warning(
                    "Unable to resolve example images folder for model %s (%s)",
                    model_name,
                    model_hash,
                )
                return False

            # Create model directory
            os.makedirs(model_dir, exist_ok=True)
            
            # First check for local example images - local processing doesn't need delay
            local_images_processed = await ExampleImagesProcessor.process_local_examples(
                model_file_path, model_file_name, model_name, model_dir, optimize
            )
            
            # If we processed local images, update metadata
            if local_images_processed:
                await MetadataUpdater.update_metadata_from_local_examples(
                    model_hash, model, scanner_type, scanner, model_dir
                )
                self._progress['processed_models'].add(model_hash)
                return False  # Return False to indicate no remote download happened
            
            full_model = await MetadataUpdater.get_updated_model(
                model_hash, scanner
            )
            civitai_payload = (full_model or {}).get('civitai') if full_model else None
            civitai_payload = civitai_payload or {}

            # If no local images, try to download from remote
            if civitai_payload.get('images'):
                images = civitai_payload.get('images', [])

                success, is_stale, failed_images = await ExampleImagesProcessor.download_model_images_with_tracking(
                    model_hash, model_name, images, model_dir, optimize, downloader
                )

                failed_urls: Set[str] = set(failed_images)

                # If metadata is stale, try to refresh it
                if is_stale and model_hash not in self._progress['refreshed_models']:
                    await MetadataUpdater.refresh_model_metadata(
                        model_hash, model_name, scanner_type, scanner, self._progress
                    )

                    # Get the updated model data
                    updated_model = await MetadataUpdater.get_updated_model(
                        model_hash, scanner
                    )
                    updated_civitai = (updated_model or {}).get('civitai') if updated_model else None
                    updated_civitai = updated_civitai or {}

                    if updated_civitai.get('images'):
                        # Retry download with updated metadata
                        updated_images = updated_civitai.get('images', [])
                        success, _, additional_failed = await ExampleImagesProcessor.download_model_images_with_tracking(
                            model_hash, model_name, updated_images, model_dir, optimize, downloader
                        )

                        failed_urls.update(additional_failed)

                    self._progress['refreshed_models'].add(model_hash)

                if failed_urls:
                    await self._remove_failed_images_from_metadata(
                        model_hash,
                        model_name,
                        model_dir,
                        failed_urls,
                        scanner,
                    )

                if failed_urls:
                    self._progress['failed_models'].add(model_hash)
                    self._progress['processed_models'].add(model_hash)
                    logger.info(
                        "Removed %s failed example images for %s", len(failed_urls), model_name
                    )
                elif success:
                    self._progress['processed_models'].add(model_hash)
                else:
                    self._progress['failed_models'].add(model_hash)
                    logger.info(
                        "Example images download failed for %s despite metadata refresh", model_name
                    )

                return True  # Return True to indicate a remote download happened
            else:
                # No civitai data or images available, mark as failed to avoid future attempts
                self._progress['failed_models'].add(model_hash)
                logger.debug(f"No civitai images available for model {model_name}, marking as failed")

            # Save progress periodically
            if self._progress['completed'] % 10 == 0 or self._progress['completed'] == self._progress['total'] - 1:
                self._save_progress(output_dir)
                
            return False  # Default return if no conditions met
                
        except Exception as e:
            error_msg = f"Error processing model {model.get('model_name')}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._progress['errors'].append(error_msg)
            self._progress['last_error'] = error_msg
            return False  # Return False on exception
    
    def _save_progress(self, output_dir):
        """Save download progress to file."""
        try:
            progress_file = os.path.join(output_dir, '.download_progress.json')
            
            # Read existing progress file if it exists
            existing_data = {}
            if os.path.exists(progress_file):
                try:
                    with open(progress_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to read existing progress file: {e}")
            
            # Create new progress data
            progress_data = {
                'processed_models': list(self._progress['processed_models']),
                'refreshed_models': list(self._progress['refreshed_models']),
                'failed_models': list(self._progress['failed_models']),
                'completed': self._progress['completed'],
                'total': self._progress['total'],
                'last_update': time.time()
            }
            
            # Preserve existing fields (especially naming_version)
            for key, value in existing_data.items():
                if key not in progress_data:
                    progress_data[key] = value
            
            # Write updated progress data
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save progress file: {e}")
    
    async def start_force_download(self, options: dict):
        """Force download example images for specific models."""

        async with self._state_lock:
            if self._is_downloading:
                raise DownloadInProgressError(self._progress.snapshot())

            data = options or {}
            model_hashes = data.get('model_hashes', [])
            optimize = data.get('optimize', True)
            model_types = data.get('model_types', ['lora', 'checkpoint'])
            delay = float(data.get('delay', 0.2))

            if not model_hashes:
                raise DownloadConfigurationError('Missing model_hashes parameter')

            settings_manager = get_settings_manager()
            base_path = settings_manager.get('example_images_path')

            if not base_path:
                raise DownloadConfigurationError('Example images path not configured in settings')
            active_library = settings_manager.get_active_library_name()
            output_dir = self._resolve_output_dir(active_library)
            if not output_dir:
                raise DownloadConfigurationError('Example images path not configured in settings')

            self._progress.reset()
            self._stop_requested = False
            self._progress['total'] = len(model_hashes)
            self._progress['status'] = 'running'
            self._progress['start_time'] = time.time()
            self._progress['end_time'] = None

            self._is_downloading = True

        await self._broadcast_progress(status='running')

        try:
            result = await self._download_specific_models_example_images_sync(
                model_hashes,
                output_dir,
                optimize,
                model_types,
                delay,
                active_library,
            )

            async with self._state_lock:
                self._is_downloading = False
                final_status = self._progress['status']

            message = 'Force download completed'
            if final_status == 'stopped':
                message = 'Force download stopped'

            return {
                'success': True,
                'message': message,
                'result': result
            }

        except Exception as e:
            async with self._state_lock:
                self._is_downloading = False
            logger.error(f"Failed during forced example images download: {e}", exc_info=True)
            await self._broadcast_progress(status='error', extra={'error': str(e)})
            raise ExampleImagesDownloadError(str(e)) from e
    
    async def _download_specific_models_example_images_sync(
        self,
        model_hashes,
        output_dir,
        optimize,
        model_types,
        delay,
        library_name,
    ):
        """Download example images for specific models only - synchronous version."""

        downloader = await get_downloader()
        
        try:
            # Get scanners
            scanners = []
            if 'lora' in model_types:
                lora_scanner = await ServiceRegistry.get_lora_scanner()
                scanners.append(('lora', lora_scanner))
            
            if 'checkpoint' in model_types:
                checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
                scanners.append(('checkpoint', checkpoint_scanner))

            if 'embedding' in model_types:
                embedding_scanner = await ServiceRegistry.get_embedding_scanner()
                scanners.append(('embedding', embedding_scanner))
            
            # Find the specified models
            models_to_process = []
            for scanner_type, scanner in scanners:
                cache = await scanner.get_cached_data()
                if cache and cache.raw_data:
                    for model in cache.raw_data:
                        if model.get('sha256') in model_hashes:
                            models_to_process.append((scanner_type, model, scanner))
            
            # Update total count based on found models
            self._progress['total'] = len(models_to_process)
            logger.debug(f"Found {self._progress['total']} models to process")

            # Send initial progress via WebSocket
            await self._broadcast_progress(status='running')
            
            # Process each model
            success_count = 0
            for i, (scanner_type, model, scanner) in enumerate(models_to_process):
                async with self._state_lock:
                    current_status = self._progress['status']

                if current_status not in {'running', 'paused', 'stopping'}:
                    break

                # Force process this model regardless of previous status
                was_successful = await self._process_specific_model(
                    scanner_type,
                    model,
                    scanner,
                    output_dir,
                    optimize,
                    downloader,
                    library_name,
                )

                if was_successful:
                    success_count += 1

                # Update progress
                self._progress['completed'] += 1

                async with self._state_lock:
                    current_status = self._progress['status']
                    should_stop = self._stop_requested and current_status == 'stopping'

                broadcast_status = 'running' if current_status == 'running' else current_status
                # Send progress update via WebSocket
                await self._broadcast_progress(status=broadcast_status)

                if should_stop:
                    break

                # Only add delay after remote download, and not after processing the last model
                if (
                    was_successful
                    and i < len(models_to_process) - 1
                    and current_status == 'running'
                ):
                    await asyncio.sleep(delay)

            async with self._state_lock:
                if self._stop_requested and self._progress['status'] == 'stopping':
                    self._progress['status'] = 'stopped'
                    self._progress['end_time'] = time.time()
                    self._stop_requested = False
                    final_status = 'stopped'
                elif self._progress['status'] not in {'error', 'stopped'}:
                    self._progress['status'] = 'completed'
                    self._progress['end_time'] = time.time()
                    self._stop_requested = False
                    final_status = 'completed'
                else:
                    final_status = self._progress['status']
                    self._stop_requested = False
                    if self._progress['end_time'] is None:
                        self._progress['end_time'] = time.time()

            if final_status == 'completed':
                logger.debug(
                    "Forced example images download completed: %s/%s models processed",
                    self._progress['completed'],
                    self._progress['total'],
                )
            elif final_status == 'stopped':
                logger.debug(
                    "Forced example images download stopped: %s/%s models processed",
                    self._progress['completed'],
                    self._progress['total'],
                )

            # Send final progress via WebSocket
            await self._broadcast_progress(status=final_status)

            return {
                'total': self._progress['total'],
                'processed': self._progress['completed'],
                'successful': success_count,
                'errors': self._progress['errors']
            }
            
        except Exception as e:
            error_msg = f"Error during forced example images download: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._progress['errors'].append(error_msg)
            self._progress['last_error'] = error_msg
            self._progress['status'] = 'error'
            self._progress['end_time'] = time.time()

            # Send error status via WebSocket
            await self._broadcast_progress(status='error', extra={'error': error_msg})
            
            raise
        
        finally:
            # No need to close any sessions since we use the global downloader
            pass
    
    async def _process_specific_model(
        self,
        scanner_type,
        model,
        scanner,
        output_dir,
        optimize,
        downloader,
        library_name,
    ):
        """Process a specific model for forced download, ignoring previous download status."""

        # Check if download is paused
        while self._progress['status'] == 'paused':
            await asyncio.sleep(1)
        
        # Check if download should continue
        if self._progress['status'] not in {'running', 'stopping'}:
            logger.info(f"Download stopped: {self._progress['status']}")
            return False
        
        model_hash = model.get('sha256', '').lower()
        model_name = model.get('model_name', 'Unknown')
        model_file_path = model.get('file_path', '')
        model_file_name = model.get('file_name', '')
        
        try:
            # Update current model info
            self._progress['current_model'] = f"{model_name} ({model_hash[:8]})"
            await self._broadcast_progress(status='running')
            
            model_dir = ExampleImagePathResolver.get_model_folder(model_hash, library_name)
            if not model_dir:
                logger.warning(
                    "Unable to resolve example images folder for model %s (%s)",
                    model_name,
                    model_hash,
                )
                return False

            os.makedirs(model_dir, exist_ok=True)
            
            # First check for local example images - local processing doesn't need delay
            local_images_processed = await ExampleImagesProcessor.process_local_examples(
                model_file_path, model_file_name, model_name, model_dir, optimize
            )
            
            # If we processed local images, update metadata
            if local_images_processed:
                await MetadataUpdater.update_metadata_from_local_examples(
                    model_hash, model, scanner_type, scanner, model_dir
                )
                self._progress['processed_models'].add(model_hash)
                return False  # Return False to indicate no remote download happened
            
            full_model = await MetadataUpdater.get_updated_model(
                model_hash, scanner
            )
            civitai_payload = (full_model or {}).get('civitai') if full_model else None
            civitai_payload = civitai_payload or {}

            # If no local images, try to download from remote
            if civitai_payload.get('images'):
                images = civitai_payload.get('images', [])

                success, is_stale, failed_images = await ExampleImagesProcessor.download_model_images_with_tracking(
                    model_hash, model_name, images, model_dir, optimize, downloader
                )

                failed_urls: Set[str] = set(failed_images)

                # If metadata is stale, try to refresh it
                if is_stale and model_hash not in self._progress['refreshed_models']:
                    await MetadataUpdater.refresh_model_metadata(
                        model_hash, model_name, scanner_type, scanner, self._progress
                    )

                    # Get the updated model data
                    updated_model = await MetadataUpdater.get_updated_model(
                        model_hash, scanner
                    )
                    updated_civitai = (updated_model or {}).get('civitai') if updated_model else None
                    updated_civitai = updated_civitai or {}

                    if updated_civitai.get('images'):
                        # Retry download with updated metadata
                        updated_images = updated_civitai.get('images', [])
                        success, _, additional_failed_images = await ExampleImagesProcessor.download_model_images_with_tracking(
                            model_hash, model_name, updated_images, model_dir, optimize, downloader
                        )

                        # Combine failed images from both attempts
                        failed_urls.update(additional_failed_images)

                    self._progress['refreshed_models'].add(model_hash)

                # For forced downloads, remove failed images from metadata
                if failed_urls:
                    await self._remove_failed_images_from_metadata(
                        model_hash, model_name, model_dir, failed_urls, scanner
                    )

                # Mark as processed
                if success or failed_urls:  # Mark as processed if we successfully downloaded some images or removed failed ones
                    self._progress['processed_models'].add(model_hash)

                return True  # Return True to indicate a remote download happened
            else:
                logger.debug(f"No civitai images available for model {model_name}")


                return False
                
        except Exception as e:
            error_msg = f"Error processing model {model.get('model_name')}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._progress['errors'].append(error_msg)
            self._progress['last_error'] = error_msg
            return False  # Return False on exception

    async def _remove_failed_images_from_metadata(
        self,
        model_hash: str,
        model_name: str,
        model_dir: str,
        failed_images: Iterable[str],
        scanner,
    ) -> None:
        """Mark failed images in model metadata so they won't be retried."""

        failed_set: Set[str] = {url for url in failed_images if url}
        if not failed_set:
            return

        try:
            # Get current model data
            model_data = await MetadataUpdater.get_updated_model(model_hash, scanner)
            if not model_data:
                logger.warning(f"Could not find model data for {model_name} to remove failed images")
                return

            civitai_payload = model_data.get('civitai') or {}
            current_images = civitai_payload.get('images') or []
            if not current_images:
                logger.warning(f"No images in metadata for {model_name}")
                return

            updated = False

            for image in current_images:
                image_url = image.get('url')
                optimized_url = (
                    ExampleImagesProcessor.get_civitai_optimized_url(image_url)
                    if image_url and 'civitai.com' in image_url
                    else None
                )

                if image_url not in failed_set and optimized_url not in failed_set:
                    continue

                if image.get('downloadFailed'):
                    continue

                image['downloadFailed'] = True
                image.setdefault('downloadError', 'not_found')
                logger.debug(
                    "Marked example image %s for %s as failed due to missing remote asset",
                    image_url,
                    model_name,
                )
                updated = True

            if not updated:
                return

            file_path = model_data.get('file_path')
            if file_path:
                model_copy = model_data.copy()
                model_copy.pop('folder', None)
                await MetadataManager.save_metadata(file_path, model_copy)

                try:
                    await scanner.update_single_model_cache(file_path, file_path, model_data)
                except AttributeError:
                    logger.debug("Scanner does not expose cache update for %s", model_name)

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Error removing failed images from metadata for %s: %s", model_name, exc, exc_info=True
            )

    def _renumber_example_image_files(self, model_dir: str) -> None:
        if not model_dir or not os.path.isdir(model_dir):
            return

        pattern = re.compile(r'^image_(\d+)(\.[^.]+)$', re.IGNORECASE)
        matches: List[Tuple[int, str, str]] = []

        for entry in os.listdir(model_dir):
            match = pattern.match(entry)
            if match:
                matches.append((int(match.group(1)), entry, match.group(2)))

        if not matches:
            return

        matches.sort(key=lambda item: item[0])
        staged_paths: List[Tuple[str, str]] = []

        for _, original_name, extension in matches:
            source_path = os.path.join(model_dir, original_name)
            temp_name = f"tmp_{uuid.uuid4().hex}_{original_name}"
            temp_path = os.path.join(model_dir, temp_name)
            try:
                os.rename(source_path, temp_path)
                staged_paths.append((temp_path, extension))
            except OSError as exc:
                logger.warning("Failed to stage rename for %s: %s", source_path, exc)

        for new_index, (temp_path, extension) in enumerate(staged_paths):
            final_name = f"image_{new_index}{extension}"
            final_path = os.path.join(model_dir, final_name)
            try:
                os.rename(temp_path, final_path)
            except OSError as exc:
                logger.warning("Failed to finalise rename for %s: %s", final_path, exc)

    async def _broadcast_progress(
        self,
        *,
        status: str | None = None,
        extra: Dict[str, Any] | None = None,
    ) -> None:
        payload = self._build_progress_payload(status=status, extra=extra)
        try:
            await self._ws_manager.broadcast(payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to broadcast example image progress: %s", exc)

    def _build_progress_payload(
        self,
        *,
        status: str | None = None,
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            'type': 'example_images_progress',
            'processed': self._progress['completed'],
            'total': self._progress['total'],
            'status': status or self._progress['status'],
            'current_model': self._progress['current_model'],
        }

        if self._progress['errors']:
            payload['errors'] = list(self._progress['errors'])
        if self._progress['last_error']:
            payload['last_error'] = self._progress['last_error']

        if extra:
            payload.update(extra)

        return payload


_default_download_manager: DownloadManager | None = None


def get_default_download_manager(ws_manager) -> DownloadManager:
    """Return the singleton download manager used by default routes."""

    global _default_download_manager
    if (
        _default_download_manager is None
        or getattr(_default_download_manager, "_ws_manager", None) is not ws_manager
    ):
        _default_download_manager = DownloadManager(ws_manager=ws_manager)
    return _default_download_manager
