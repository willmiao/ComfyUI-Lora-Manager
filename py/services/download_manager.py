import logging
import os
import asyncio
import yaml
from typing import Dict
from ..utils.models import LoraMetadata, CheckpointMetadata
from ..utils.constants import CARD_PREVIEW_WIDTH, VALID_LORA_TYPES, CIVITAI_MODEL_TAGS
from ..utils.exif_utils import ExifUtils
from ..utils.metadata_manager import MetadataManager
from .service_registry import ServiceRegistry
from .settings_manager import settings

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
        
        self._civitai_client = None  # Will be lazily initialized
        self._path_mappings = self._load_path_mappings()

    def _load_path_mappings(self):
        """Load path mappings from YAML configuration"""
        path_mappings = {
            'base_models': {},
            'model_tags': {}
        }
        
        # Path to the configuration file
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'path_mappings.yaml')
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    mappings = yaml.safe_load(f)
                    
                if mappings and isinstance(mappings, dict):
                    if 'base_models' in mappings and isinstance(mappings['base_models'], dict):
                        path_mappings['base_models'] = mappings['base_models']
                    if 'model_tags' in mappings and isinstance(mappings['model_tags'], dict):
                        path_mappings['model_tags'] = mappings['model_tags']
                
                logger.info(f"Loaded path mappings from {config_path}")
            else:
                logger.info(f"Path mappings configuration file not found at {config_path}, using default mappings")
        except Exception as e:
            logger.error(f"Error loading path mappings: {e}", exc_info=True)
            
        return path_mappings

    async def _get_civitai_client(self):
        """Lazily initialize CivitaiClient from registry"""
        if self._civitai_client is None:
            self._civitai_client = await ServiceRegistry.get_civitai_client()
        return self._civitai_client
    
    async def _get_lora_scanner(self):
        """Get the lora scanner from registry"""
        return await ServiceRegistry.get_lora_scanner()
        
    async def _get_checkpoint_scanner(self):
        """Get the checkpoint scanner from registry"""
        return await ServiceRegistry.get_checkpoint_scanner()

    async def download_from_civitai(self, model_id: int, 
                                  model_version_id: int, save_dir: str = None, 
                                  relative_path: str = '', progress_callback=None, use_default_paths: bool = False) -> Dict:
        """Download model from Civitai
        
        Args:
            model_id: Civitai model ID
            model_version_id: Civitai model version ID (optional, if not provided, will download the latest version)
            save_dir: Directory to save the model to
            relative_path: Relative path within save_dir
            progress_callback: Callback function for progress updates
            use_default_paths: Flag to indicate whether to use default paths
            
        Returns:
            Dict with download result
        """
        try:
            # Check if model version already exists in library
            if model_version_id is not None:
                # Case 1: model_version_id is provided, check both scanners
                lora_scanner = await self._get_lora_scanner()
                checkpoint_scanner = await self._get_checkpoint_scanner()
                
                # Check lora scanner first
                if await lora_scanner.check_model_version_exists(model_id, model_version_id):
                    return {'success': False, 'error': 'Model version already exists in lora library'}
                
                # Check checkpoint scanner
                if await checkpoint_scanner.check_model_version_exists(model_id, model_version_id):
                    return {'success': False, 'error': 'Model version already exists in checkpoint library'}

            # Get civitai client
            civitai_client = await self._get_civitai_client()

            # Get version info based on the provided identifier
            version_info = await civitai_client.get_model_version(model_id, model_version_id)
            
            if not version_info:
                return {'success': False, 'error': 'Failed to fetch model metadata'}

            model_type_from_info = version_info.get('model', {}).get('type', '').lower()
            if model_type_from_info == 'checkpoint':
                model_type = 'checkpoint'
            elif model_type_from_info in VALID_LORA_TYPES:
                model_type = 'lora'
            else:
                return {'success': False, 'error': f'Model type "{model_type_from_info}" is not supported for download'}
            
            # Case 2: model_version_id was None, check after getting version_info
            if model_version_id is None:
                version_model_id = version_info.get('modelId')
                version_id = version_info.get('id')
                
                if model_type == 'lora':
                    # Check lora scanner
                    lora_scanner = await self._get_lora_scanner()
                    if await lora_scanner.check_model_version_exists(version_model_id, version_id):
                        return {'success': False, 'error': 'Model version already exists in lora library'}
                elif model_type == 'checkpoint':
                    # Check checkpoint scanner
                    checkpoint_scanner = await self._get_checkpoint_scanner()
                    if await checkpoint_scanner.check_model_version_exists(version_model_id, version_id):
                        return {'success': False, 'error': 'Model version already exists in checkpoint library'}
            
            # Handle use_default_paths
            if use_default_paths:
                # Set save_dir based on model type
                if model_type == 'checkpoint':
                    default_path = settings.get('default_checkpoint_root')
                    if not default_path:
                        return {'success': False, 'error': 'Default checkpoint root path not set in settings'}
                    save_dir = default_path
                else:  # model_type == 'lora'
                    default_path = settings.get('default_lora_root')
                    if not default_path:
                        return {'success': False, 'error': 'Default lora root path not set in settings'}
                    save_dir = default_path
                    
                # Set relative_path to version_info.baseModel/prioritized_tag
                base_model = version_info.get('baseModel', '')
                model_tags = version_info.get('model', {}).get('tags', [])
                
                if base_model:
                    # Apply base model mapping if available
                    mapped_base_model = self._path_mappings['base_models'].get(base_model, base_model)
                    
                    # Find the first Civitai model tag that exists in model_tags
                    prioritized_tag = None
                    for civitai_tag in CIVITAI_MODEL_TAGS:
                        if civitai_tag in model_tags:
                            prioritized_tag = civitai_tag
                            break
                    
                    # If no Civitai model tag found, fallback to first tag
                    if prioritized_tag is None and model_tags:
                        prioritized_tag = model_tags[0]
                    
                    if prioritized_tag:
                        # Apply tag mapping if available
                        mapped_tag = self._path_mappings['model_tags'].get(prioritized_tag, prioritized_tag)
                        relative_path = os.path.join(mapped_base_model, mapped_tag)
                    else:
                        relative_path = mapped_base_model

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
                    early_access_msg = f"This model requires early access payment (until {formatted_date}). "
                except:
                    early_access_msg = "This model requires early access payment. "
                
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

            # 3. Prepare download
            file_name = file_info['name']
            save_path = os.path.join(save_dir, file_name)

            # 5. Prepare metadata based on model type
            if model_type == "checkpoint":
                metadata = CheckpointMetadata.from_civitai_info(version_info, file_info, save_path)
                logger.info(f"Creating CheckpointMetadata for {file_name}")
            else:
                metadata = LoraMetadata.from_civitai_info(version_info, file_info, save_path)
                logger.info(f"Creating LoraMetadata for {file_name}")
            
            # 6. Start download process
            result = await self._execute_download(
                download_url=file_info.get('downloadUrl', ''),
                save_dir=save_dir,
                metadata=metadata,
                version_info=version_info,
                relative_path=relative_path,
                progress_callback=progress_callback,
                model_type=model_type
            )

            return result

        except Exception as e:
            logger.error(f"Error in download_from_civitai: {e}", exc_info=True)
            # Check if this might be an early access error
            error_str = str(e).lower()
            if "403" in error_str or "401" in error_str or "unauthorized" in error_str or "early access" in error_str:
                return {'success': False, 'error': f"Early access restriction: {str(e)}. Please ensure you have purchased early access and are logged in to Civitai."}
            return {'success': False, 'error': str(e)}

    async def _execute_download(self, download_url: str, save_dir: str, 
                              metadata, version_info: Dict, 
                              relative_path: str, progress_callback=None,
                              model_type: str = "lora") -> Dict:
        """Execute the actual download process including preview images and model files"""
        try:
            civitai_client = await self._get_civitai_client()
            save_path = metadata.file_path
            metadata_path = os.path.splitext(save_path)[0] + '.metadata.json'

            # Download preview image if available
            images = version_info.get('images', [])
            if images:
                # Report preview download progress
                if progress_callback:
                    await progress_callback(1)  # 1% progress for starting preview download

                # Check if it's a video or an image
                is_video = images[0].get('type') == 'video'
                
                if (is_video):
                    # For videos, use .mp4 extension
                    preview_ext = '.mp4'
                    preview_path = os.path.splitext(save_path)[0] + preview_ext
                    
                    # Download video directly
                    if await civitai_client.download_preview_image(images[0]['url'], preview_path):
                        metadata.preview_url = preview_path.replace(os.sep, '/')
                        metadata.preview_nsfw_level = images[0].get('nsfwLevel', 0)
                else:
                    # For images, use WebP format for better performance
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                        temp_path = temp_file.name
                    
                    # Download the original image to temp path
                    if await civitai_client.download_preview_image(images[0]['url'], temp_path):
                        # Optimize and convert to WebP
                        preview_path = os.path.splitext(save_path)[0] + '.webp'
                        
                        # Use ExifUtils to optimize and convert the image
                        optimized_data, _ = ExifUtils.optimize_image(
                            image_data=temp_path,
                            target_width=CARD_PREVIEW_WIDTH,
                            format='webp',
                            quality=85,
                            preserve_metadata=False
                        )
                        
                        # Save the optimized image
                        with open(preview_path, 'wb') as f:
                            f.write(optimized_data)
                            
                        # Update metadata
                        metadata.preview_url = preview_path.replace(os.sep, '/')
                        metadata.preview_nsfw_level = images[0].get('nsfwLevel', 0)
                        
                        # Remove temporary file
                        try:
                            os.unlink(temp_path)
                        except Exception as e:
                            logger.warning(f"Failed to delete temp file: {e}")

                # Report preview download completion
                if progress_callback:
                    await progress_callback(3)  # 3% progress after preview download

            # Download model file with progress tracking
            success, result = await civitai_client._download_file(
                download_url, 
                save_dir,
                os.path.basename(save_path),
                progress_callback=lambda p: self._handle_download_progress(p, progress_callback)
            )

            if not success:
                # Clean up files on failure
                for path in [save_path, metadata_path, metadata.preview_url]:
                    if path and os.path.exists(path):
                        os.remove(path)
                return {'success': False, 'error': result}

            # 4. Update file information (size and modified time)
            metadata.update_file_info(save_path)

            # 5. Final metadata update
            await MetadataManager.save_metadata(save_path, metadata, True)

            # 6. Update cache based on model type
            if model_type == "checkpoint":
                scanner = await self._get_checkpoint_scanner()
                logger.info(f"Updating checkpoint cache for {save_path}")
            else:
                scanner = await self._get_lora_scanner()
                logger.info(f"Updating lora cache for {save_path}")
                
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
            # Clean up partial downloads
            for path in [save_path, metadata_path]:
                if path and os.path.exists(path):
                    os.remove(path)
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