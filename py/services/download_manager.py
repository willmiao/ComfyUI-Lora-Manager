import logging
import os
import asyncio
from collections import OrderedDict
import uuid
from typing import Dict, List
from urllib.parse import urlparse
from ..utils.models import LoraMetadata, CheckpointMetadata, EmbeddingMetadata
from ..utils.constants import CARD_PREVIEW_WIDTH, VALID_LORA_TYPES, CIVITAI_MODEL_TAGS
from ..utils.civitai_utils import rewrite_preview_url
from ..utils.exif_utils import ExifUtils
from ..utils.metadata_manager import MetadataManager
from .service_registry import ServiceRegistry
from .settings_manager import get_settings_manager
from .metadata_service import get_default_metadata_provider
from .downloader import get_downloader

# Download to temporary file first
import tempfile

logger = logging.getLogger(__name__)

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
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # Add download management
        self._active_downloads = OrderedDict()  # download_id -> download_info
        self._download_semaphore = asyncio.Semaphore(5)  # Limit concurrent downloads
        self._download_tasks = {}  # download_id -> asyncio.Task
    
    async def _get_lora_scanner(self):
        """Get the lora scanner from registry"""
        return await ServiceRegistry.get_lora_scanner()
        
    async def _get_checkpoint_scanner(self):
        """Get the checkpoint scanner from registry"""
        return await ServiceRegistry.get_checkpoint_scanner()
    
    async def download_from_civitai(self, model_id: int = None, model_version_id: int = None, 
                                  save_dir: str = None, relative_path: str = '', 
                                  progress_callback=None, use_default_paths: bool = False,
                                  download_id: str = None, source: str = None) -> Dict:
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
            
        Returns:
            Dict with download result
        """
        # Validate that at least one identifier is provided
        if not model_id and not model_version_id:
            return {'success': False, 'error': 'Either model_id or model_version_id must be provided'}
        
        # Use provided download_id or generate new one
        task_id = download_id or str(uuid.uuid4())
        
        # Register download task in tracking dict
        self._active_downloads[task_id] = {
            'model_id': model_id,
            'model_version_id': model_version_id,
            'progress': 0,
            'status': 'queued'
        }
        
        # Create tracking task
        download_task = asyncio.create_task(
            self._download_with_semaphore(
                task_id, model_id, model_version_id, save_dir, 
                relative_path, progress_callback, use_default_paths, source
            )
        )
        
        # Store task for tracking and cancellation
        self._download_tasks[task_id] = download_task
        
        try:
            # Wait for download to complete
            result = await download_task
            result['download_id'] = task_id  # Include download_id in result
            return result
        except asyncio.CancelledError:
            return {'success': False, 'error': 'Download was cancelled', 'download_id': task_id}
        finally:
            # Clean up task reference
            if task_id in self._download_tasks:
                del self._download_tasks[task_id]

    async def _download_with_semaphore(self, task_id: str, model_id: int, model_version_id: int,
                                     save_dir: str, relative_path: str, 
                                     progress_callback=None, use_default_paths: bool = False,
                                     source: str = None):
        """Execute download with semaphore to limit concurrency"""
        # Update status to waiting
        if task_id in self._active_downloads:
            self._active_downloads[task_id]['status'] = 'waiting'
        
        # Wrap progress callback to track progress in active_downloads
        original_callback = progress_callback
        async def tracking_callback(progress):
            if task_id in self._active_downloads:
                self._active_downloads[task_id]['progress'] = progress
            if original_callback:
                await original_callback(progress)
        
        # Acquire semaphore to limit concurrent downloads
        try:
            async with self._download_semaphore:
                # Update status to downloading
                if task_id in self._active_downloads:
                    self._active_downloads[task_id]['status'] = 'downloading'
                
                # Use original download implementation
                try:
                    # Check for cancellation before starting
                    if asyncio.current_task().cancelled():
                        raise asyncio.CancelledError()
                    
                    result = await self._execute_original_download(
                        model_id, model_version_id, save_dir,
                        relative_path, tracking_callback, use_default_paths,
                        task_id, source
                    )
                    
                    # Update status based on result
                    if task_id in self._active_downloads:
                        self._active_downloads[task_id]['status'] = 'completed' if result['success'] else 'failed'
                        if not result['success']:
                            self._active_downloads[task_id]['error'] = result.get('error', 'Unknown error')
                    
                    return result
                except asyncio.CancelledError:
                    # Handle cancellation
                    if task_id in self._active_downloads:
                        self._active_downloads[task_id]['status'] = 'cancelled'
                    logger.info(f"Download cancelled for task {task_id}")
                    raise
                except Exception as e:
                    # Handle other errors
                    logger.error(f"Download error for task {task_id}: {str(e)}", exc_info=True)
                    if task_id in self._active_downloads:
                        self._active_downloads[task_id]['status'] = 'failed'
                        self._active_downloads[task_id]['error'] = str(e)
                    return {'success': False, 'error': str(e)}
        finally:
            # Schedule cleanup of download record after delay
            asyncio.create_task(self._cleanup_download_record(task_id))

    async def _cleanup_download_record(self, task_id: str):
        """Keep completed downloads in history for a short time"""
        await asyncio.sleep(600)  # Keep for 10 minutes
        if task_id in self._active_downloads:
            del self._active_downloads[task_id]

    async def _execute_original_download(self, model_id, model_version_id, save_dir, 
                                     relative_path, progress_callback, use_default_paths,
                                     download_id=None, source=None):
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
                    return {'success': False, 'error': 'Model version already exists in lora library'}
                
                # Check checkpoint scanner
                if await checkpoint_scanner.check_model_version_exists(model_version_id):
                    return {'success': False, 'error': 'Model version already exists in checkpoint library'}
                
                # Check embedding scanner
                if await embedding_scanner.check_model_version_exists(model_version_id):
                    return {'success': False, 'error': 'Model version already exists in embedding library'}

            # Get metadata provider based on source parameter
            if source == 'civarchive':
                from .metadata_service import get_metadata_provider
                metadata_provider = await get_metadata_provider('civarchive')
            else:
                metadata_provider = await get_default_metadata_provider()

            # Get version info based on the provided identifier
            version_info = await metadata_provider.get_model_version(model_id, model_version_id)
            
            if not version_info:
                return {'success': False, 'error': 'Failed to fetch model metadata'}

            model_type_from_info = version_info.get('model', {}).get('type', '').lower()
            if model_type_from_info == 'checkpoint':
                model_type = 'checkpoint'
            elif model_type_from_info in VALID_LORA_TYPES:
                model_type = 'lora'
            elif model_type_from_info == 'textualinversion':
                model_type = 'embedding'
            else:
                return {'success': False, 'error': f'Model type "{model_type_from_info}" is not supported for download'}
            
            # Case 2: model_version_id was None, check after getting version_info
            if model_version_id is None:
                version_id = version_info.get('id')
                
                if model_type == 'lora':
                    # Check lora scanner
                    lora_scanner = await self._get_lora_scanner()
                    if await lora_scanner.check_model_version_exists(version_id):
                        return {'success': False, 'error': 'Model version already exists in lora library'}
                elif model_type == 'checkpoint':
                    # Check checkpoint scanner
                    checkpoint_scanner = await self._get_checkpoint_scanner()
                    if await checkpoint_scanner.check_model_version_exists(version_id):
                        return {'success': False, 'error': 'Model version already exists in checkpoint library'}
                elif model_type == 'embedding':
                    # Embeddings are not checked in scanners, but we can still check if it exists
                    embedding_scanner = await ServiceRegistry.get_embedding_scanner()
                    if await embedding_scanner.check_model_version_exists(version_id):
                        return {'success': False, 'error': 'Model version already exists in embedding library'}
            
            # Handle use_default_paths
            if use_default_paths:
                settings_manager = get_settings_manager()
                # Set save_dir based on model type
                if model_type == 'checkpoint':
                    default_path = settings_manager.get('default_checkpoint_root')
                    if not default_path:
                        return {'success': False, 'error': 'Default checkpoint root path not set in settings'}
                    save_dir = default_path
                elif model_type == 'lora':
                    default_path = settings_manager.get('default_lora_root')
                    if not default_path:
                        return {'success': False, 'error': 'Default lora root path not set in settings'}
                    save_dir = default_path
                elif model_type == 'embedding':
                    default_path = settings_manager.get('default_embedding_root')
                    if not default_path:
                        return {'success': False, 'error': 'Default embedding root path not set in settings'}
                    save_dir = default_path

                # Calculate relative path using template
                relative_path = self._calculate_relative_path(version_info, model_type)

            # Update save directory with relative path if provided
            if relative_path:
                save_dir = os.path.join(save_dir, relative_path)
                # Create directory if it doesn't exist
                os.makedirs(save_dir, exist_ok=True)

            # Check if this is an early access model
            if version_info.get('earlyAccessEndsAt'):
                early_access_date = version_info.get('earlyAccessEndsAt', '')
                # Convert to a readable date if possible
                try:
                    from datetime import datetime
                    date_obj = datetime.fromisoformat(early_access_date.replace('Z', '+00:00'))
                    formatted_date = date_obj.strftime('%Y-%m-%d')
                    early_access_msg = f"This model requires payment (until {formatted_date}). "
                except:
                    early_access_msg = "This model requires payment. "
                
                early_access_msg += "Please ensure you have purchased early access and are logged in to Civitai."
                logger.warning(f"Early access model detected: {version_info.get('name', 'Unknown')}")
                
                # We'll still try to download, but log a warning and prepare for potential failure
                if progress_callback:
                    await progress_callback(1)  # Show minimal progress to indicate we're trying

            # Report initial progress
            if progress_callback:
                await progress_callback(0)

            # 2. Get file information
            file_info = next((f for f in version_info.get('files', []) if f.get('primary')), None)
            if not file_info:
                return {'success': False, 'error': 'No primary file found in metadata'}
            mirrors = file_info.get('mirrors') or []
            download_urls = []
            if mirrors:
                for mirror in mirrors:
                    if mirror.get('deletedAt') is None and mirror.get('url'):
                        download_urls.append(mirror['url'])
            else:
                download_url = file_info.get('downloadUrl')
                if download_url:
                    download_urls.append(download_url)

            if not download_urls:
                return {'success': False, 'error': 'No download URL found for primary file'}

            # 3. Prepare download
            file_name = file_info['name']
            save_path = os.path.join(save_dir, file_name)

            # 5. Prepare metadata based on model type
            if model_type == "checkpoint":
                metadata = CheckpointMetadata.from_civitai_info(version_info, file_info, save_path)
                logger.info(f"Creating CheckpointMetadata for {file_name}")
            elif model_type == "lora":
                metadata = LoraMetadata.from_civitai_info(version_info, file_info, save_path)
                logger.info(f"Creating LoraMetadata for {file_name}")
            elif model_type == "embedding":
                metadata = EmbeddingMetadata.from_civitai_info(version_info, file_info, save_path)
                logger.info(f"Creating EmbeddingMetadata for {file_name}")
            
            # 6. Start download process
            result = await self._execute_download(
                download_urls=download_urls,
                save_dir=save_dir,
                metadata=metadata,
                version_info=version_info,
                relative_path=relative_path,
                progress_callback=progress_callback,
                model_type=model_type,
                download_id=download_id
            )

            # If early_access_msg exists and download failed, replace error message
            if 'early_access_msg' in locals() and not result.get('success', False):
                result['error'] = early_access_msg

            return result

        except Exception as e:
            logger.error(f"Error in download_from_civitai: {e}", exc_info=True)
            # Check if this might be an early access error
            error_str = str(e).lower()
            if "403" in error_str or "401" in error_str or "unauthorized" in error_str or "early access" in error_str:
                return {'success': False, 'error': f"Early access restriction: {str(e)}. Please ensure you have purchased early access and are logged in to Civitai."}
            return {'success': False, 'error': str(e)}

    def _calculate_relative_path(self, version_info: Dict, model_type: str = 'lora') -> str:
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
            return ''
        
        # Get base model name
        base_model = version_info.get('baseModel', '')
        
        # Get author from creator data
        creator_info = version_info.get('creator')
        if creator_info and isinstance(creator_info, dict):
            author = creator_info.get('username') or 'Anonymous'
        else:
            author = 'Anonymous'
        
        # Apply mapping if available
        base_model_mappings = settings_manager.get('base_model_path_mappings', {})
        mapped_base_model = base_model_mappings.get(base_model, base_model)
        
        # Get model tags
        model_tags = version_info.get('model', {}).get('tags', [])
        
        # Find the first Civitai model tag that exists in model_tags
        first_tag = ''
        for civitai_tag in CIVITAI_MODEL_TAGS:
            if civitai_tag in model_tags:
                first_tag = civitai_tag
                break
        
        # If no Civitai model tag found, fallback to first tag
        if not first_tag and model_tags:
            first_tag = model_tags[0]
        
        # Format the template with available data
        formatted_path = path_template
        formatted_path = formatted_path.replace('{base_model}', mapped_base_model)
        formatted_path = formatted_path.replace('{first_tag}', first_tag)
        formatted_path = formatted_path.replace('{author}', author)

        if model_type == 'embedding':
            formatted_path = formatted_path.replace(' ', '_')

        return formatted_path

    async def _execute_download(self, download_urls: List[str], save_dir: str,
                          metadata, version_info: Dict,
                          relative_path: str, progress_callback=None,
                          model_type: str = "lora", download_id: str = None) -> Dict:
        """Execute the actual download process including preview images and model files"""
        try:
            # Extract original filename details
            original_filename = os.path.basename(metadata.file_path)
            base_name, extension = os.path.splitext(original_filename)
            
            # Check for filename conflicts and generate unique filename if needed
            # Use the hash from metadata for conflict resolution
            def hash_provider():
                return metadata.sha256
            
            unique_filename = metadata.generate_unique_filename(
                save_dir, 
                base_name, 
                extension, 
                hash_provider=hash_provider
            )
            
            # Update paths if filename changed
            if unique_filename != original_filename:
                logger.info(f"Filename conflict detected. Changing '{original_filename}' to '{unique_filename}'")
                save_path = os.path.join(save_dir, unique_filename)
                # Update metadata with new file path and name
                metadata.file_path = save_path.replace(os.sep, '/')
                metadata.file_name = os.path.splitext(unique_filename)[0]
            else:
                save_path = metadata.file_path
                
            part_path = save_path + '.part'
            metadata_path = os.path.splitext(save_path)[0] + '.metadata.json'
            
            # Store file paths in active_downloads for potential cleanup
            if download_id and download_id in self._active_downloads:
                self._active_downloads[download_id]['file_path'] = save_path
                self._active_downloads[download_id]['part_path'] = part_path

            # Download preview image if available
            images = version_info.get('images', [])
            if images:
                if progress_callback:
                    await progress_callback(1)  # 1% progress for starting preview download

                first_image = images[0] if isinstance(images[0], dict) else None
                preview_url = first_image.get('url') if first_image else None
                media_type = (first_image.get('type') or '').lower() if first_image else ''
                nsfw_level = first_image.get('nsfwLevel', 0) if first_image else 0

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

                    if media_type == 'video':
                        preview_ext = _extension_from_url(preview_url, '.mp4')
                        preview_path = os.path.splitext(save_path)[0] + preview_ext
                        rewritten_url, rewritten = rewrite_preview_url(preview_url, media_type='video')
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
                                attempt,
                                preview_path,
                                use_auth=False
                            )
                            if success:
                                preview_downloaded = True
                                break
                    else:
                        rewritten_url, rewritten = rewrite_preview_url(preview_url, media_type='image')
                        if rewritten:
                            preview_ext = _extension_from_url(preview_url, '.png')
                            preview_path = os.path.splitext(save_path)[0] + preview_ext
                            success, _ = await downloader.download_file(
                                rewritten_url,
                                preview_path,
                                use_auth=False
                            )
                            if success:
                                preview_downloaded = True

                        if not preview_downloaded:
                            temp_path: str | None = None
                            try:
                                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                                    temp_path = temp_file.name

                                success, content, _ = await downloader.download_to_memory(
                                    preview_url,
                                    use_auth=False
                                )
                                if success:
                                    with open(temp_path, 'wb') as temp_file_handle:
                                        temp_file_handle.write(content)
                                    preview_path = os.path.splitext(save_path)[0] + '.webp'

                                    optimized_data, _ = ExifUtils.optimize_image(
                                        image_data=temp_path,
                                        target_width=CARD_PREVIEW_WIDTH,
                                        format='webp',
                                        quality=85,
                                        preserve_metadata=False
                                    )

                                    with open(preview_path, 'wb') as preview_file:
                                        preview_file.write(optimized_data)

                                    preview_downloaded = True
                            finally:
                                if temp_path and os.path.exists(temp_path):
                                    try:
                                        os.unlink(temp_path)
                                    except Exception as e:
                                        logger.warning(f"Failed to delete temp file: {e}")

                if preview_downloaded and preview_path:
                    metadata.preview_url = preview_path.replace(os.sep, '/')
                    metadata.preview_nsfw_level = nsfw_level
                    if download_id and download_id in self._active_downloads:
                        self._active_downloads[download_id]['preview_path'] = preview_path

                if progress_callback:
                    await progress_callback(3)  # 3% progress after preview download

            # Download model file with progress tracking using downloader
            downloader = await get_downloader()
            last_error = None
            for download_url in download_urls:
                use_auth = download_url.startswith("https://civitai.com/api/download/")
                success, result = await downloader.download_file(
                    download_url,
                    save_path,  # Use full path instead of separate dir and filename
                    progress_callback=lambda p: self._handle_download_progress(p, progress_callback),
                    use_auth=use_auth  # Only use authentication for Civitai downloads
                )

                if success:
                    break

                last_error = result
                if os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove incomplete file {save_path}: {e}")
            else:
                # Clean up files on failure, but preserve .part file for resume
                cleanup_files = [metadata_path]
                preview_path_value = getattr(metadata, 'preview_url', None)
                if preview_path_value and os.path.exists(preview_path_value):
                    cleanup_files.append(preview_path_value)

                for path in cleanup_files:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception as e:
                            logger.warning(f"Failed to cleanup file {path}: {e}")

                # Log but don't remove .part file to allow resume
                if os.path.exists(part_path):
                    logger.info(f"Preserving partial download for resume: {part_path}")

                return {'success': False, 'error': last_error or 'Failed to download file'}

            # 4. Update file information (size and modified time)
            metadata.update_file_info(save_path)

            # 5. Final metadata update
            await MetadataManager.save_metadata(save_path, metadata)

            # 6. Update cache based on model type
            if model_type == "checkpoint":
                scanner = await self._get_checkpoint_scanner()
                logger.info(f"Updating checkpoint cache for {save_path}")
            elif model_type == "lora":
                scanner = await self._get_lora_scanner()
                logger.info(f"Updating lora cache for {save_path}")
            elif model_type == "embedding":
                scanner = await ServiceRegistry.get_embedding_scanner()
                logger.info(f"Updating embedding cache for {save_path}")
                
            # Convert metadata to dictionary
            metadata_dict = metadata.to_dict()

            # Add model to cache and save to disk in a single operation
            await scanner.add_model_to_cache(metadata_dict, relative_path)

            # Report 100% completion
            if progress_callback:
                await progress_callback(100)

            return {
                'success': True
            }

        except Exception as e:
            logger.error(f"Error in _execute_download: {e}", exc_info=True)
            # Clean up partial downloads except .part file
            cleanup_files = [metadata_path]
            if hasattr(metadata, 'preview_url') and metadata.preview_url and os.path.exists(metadata.preview_url):
                cleanup_files.append(metadata.preview_url)
            
            for path in cleanup_files:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup file {path}: {e}")
            
            return {'success': False, 'error': str(e)}

    async def _handle_download_progress(self, file_progress: float, progress_callback):
        """Convert file download progress to overall progress
        
        Args:
            file_progress: Progress of file download (0-100)
            progress_callback: Callback function for progress updates
        """
        if progress_callback:
            # Scale file progress to 3-100 range (after preview download)
            overall_progress = 3 + (file_progress * 0.97)  # 97% of progress for file download
            await progress_callback(round(overall_progress))
            
    async def cancel_download(self, download_id: str) -> Dict:
        """Cancel an active download by download_id
        
        Args:
            download_id: The unique identifier of the download task
            
        Returns:
            Dict: Status of the cancellation operation
        """
        if download_id not in self._download_tasks:
            return {'success': False, 'error': 'Download task not found'}
        
        try:
            # Get the task and cancel it
            task = self._download_tasks[download_id]
            task.cancel()
            
            # Update status in active downloads
            if download_id in self._active_downloads:
                self._active_downloads[download_id]['status'] = 'cancelling'
            
            # Wait briefly for the task to acknowledge cancellation
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            
            # Clean up ALL files including .part when user cancels
            download_info = self._active_downloads.get(download_id)
            if download_info:
                # Delete the main file
                if 'file_path' in download_info:
                    file_path = download_info['file_path']
                    if os.path.exists(file_path):
                        try:
                            os.unlink(file_path)
                            logger.debug(f"Deleted cancelled download: {file_path}")
                        except Exception as e:
                            logger.error(f"Error deleting file: {e}")
                
                # Delete the .part file (only on user cancellation)
                if 'part_path' in download_info:
                    part_path = download_info['part_path']
                    if os.path.exists(part_path):
                        try:
                            os.unlink(part_path)
                            logger.debug(f"Deleted partial download: {part_path}")
                        except Exception as e:
                            logger.error(f"Error deleting part file: {e}")
                
                # Delete metadata file if exists
                if 'file_path' in download_info:
                    file_path = download_info['file_path']
                    metadata_path = os.path.splitext(file_path)[0] + '.metadata.json'
                    if os.path.exists(metadata_path):
                        try:
                            os.unlink(metadata_path)
                        except Exception as e:
                            logger.error(f"Error deleting metadata file: {e}")

                    preview_path_value = download_info.get('preview_path')
                    if preview_path_value and os.path.exists(preview_path_value):
                        try:
                            os.unlink(preview_path_value)
                            logger.debug(f"Deleted preview file: {preview_path_value}")
                        except Exception as e:
                            logger.error(f"Error deleting preview file: {e}")

                    # Delete preview file if exists (.webp or .mp4) for legacy paths
                    for preview_ext in ['.webp', '.mp4']:
                        preview_path = os.path.splitext(file_path)[0] + preview_ext
                        if os.path.exists(preview_path):
                            try:
                                os.unlink(preview_path)
                                logger.debug(f"Deleted preview file: {preview_path}")
                            except Exception as e:
                                logger.error(f"Error deleting preview file: {e}")
            
            return {'success': True, 'message': 'Download cancelled successfully'}
        except Exception as e:
            logger.error(f"Error cancelling download: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def get_active_downloads(self) -> Dict:
        """Get information about all active downloads
        
        Returns:
            Dict: List of active downloads and their status
        """
        return {
            'downloads': [
                {
                    'download_id': task_id,
                    'model_id': info.get('model_id'),
                    'model_version_id': info.get('model_version_id'),
                    'progress': info.get('progress', 0),
                    'status': info.get('status', 'unknown'),
                    'error': info.get('error', None)
                }
                for task_id, info in self._active_downloads.items()
            ]
        }
