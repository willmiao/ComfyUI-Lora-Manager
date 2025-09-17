from datetime import datetime
import os
import logging
import asyncio
from typing import Optional, Dict, Tuple, List
from .model_metadata_provider import CivitaiModelMetadataProvider, ModelMetadataProviderManager
from .downloader import get_downloader

logger = logging.getLogger(__name__)

class CivitaiClient:
    _instance = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_instance(cls):
        """Get singleton instance of CivitaiClient"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                
                # Register this client as a metadata provider
                provider_manager = await ModelMetadataProviderManager.get_instance()
                provider_manager.register_provider('civitai', CivitaiModelMetadataProvider(cls._instance), True)
                
            return cls._instance

    def __init__(self):
        # Check if already initialized for singleton pattern
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.base_url = "https://civitai.com/api/v1"
    
    async def download_file(self, url: str, save_dir: str, default_filename: str, progress_callback=None) -> Tuple[bool, str]:
        """Download file with resumable downloads and retry mechanism

        Args:
            url: Download URL
            save_dir: Directory to save the file
            default_filename: Fallback filename if none provided in headers
            progress_callback: Optional async callback function for progress updates (0-100)

        Returns:
            Tuple[bool, str]: (success, save_path or error message)
        """
        downloader = await get_downloader()
        save_path = os.path.join(save_dir, default_filename)
        
        # Use unified downloader with CivitAI authentication
        success, result = await downloader.download_file(
            url=url,
            save_path=save_path,
            progress_callback=progress_callback,
            use_auth=True,  # Enable CivitAI authentication
            allow_resume=True
        )
        
        return success, result

    async def get_model_by_hash(self, model_hash: str) -> Optional[Dict]:
        try:
            downloader = await get_downloader()
            success, version = await downloader.make_request(
                'GET',
                f"{self.base_url}/model-versions/by-hash/{model_hash}",
                use_auth=True
            )
            if success:
                # Get model ID from version data
                model_id = version.get('modelId')
                if model_id:
                    # Fetch additional model metadata
                    success_model, data = await downloader.make_request(
                        'GET',
                        f"{self.base_url}/models/{model_id}",
                        use_auth=True
                    )
                    if success_model:
                        # Enrich version_info with model data
                        version['model']['description'] = data.get("description")
                        version['model']['tags'] = data.get("tags", [])
                        
                        # Add creator from model data
                        version['creator'] = data.get("creator")
                
                return version
            return None
        except Exception as e:
            logger.error(f"API Error: {str(e)}")
            return None

    async def download_preview_image(self, image_url: str, save_path: str):
        try:
            downloader = await get_downloader()
            success, content, headers = await downloader.download_to_memory(
                image_url,
                use_auth=False  # Preview images don't need auth
            )
            if success:
                # Ensure directory exists
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'wb') as f:
                    f.write(content)
                return True
            return False
        except Exception as e:
            logger.error(f"Download Error: {str(e)}")
            return False
            
    async def get_model_versions(self, model_id: str) -> List[Dict]:
        """Get all versions of a model with local availability info"""
        try:
            downloader = await get_downloader()
            success, result = await downloader.make_request(
                'GET',
                f"{self.base_url}/models/{model_id}",
                use_auth=True
            )
            if success:
                # Also return model type along with versions
                return {
                    'modelVersions': result.get('modelVersions', []),
                    'type': result.get('type', ''),
                    'name': result.get('name', '')
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching model versions: {e}")
            return None
            
    async def get_model_version(self, model_id: int = None, version_id: int = None) -> Optional[Dict]:
        """Get specific model version with additional metadata
        
        Args:
            model_id: The Civitai model ID (optional if version_id is provided)
            version_id: Optional specific version ID to retrieve
            
        Returns:
            Optional[Dict]: The model version data with additional fields or None if not found
        """
        try:
            downloader = await get_downloader()
            
            # Case 1: Only version_id is provided
            if model_id is None and version_id is not None:
                # First get the version info to extract model_id
                success, version = await downloader.make_request(
                    'GET',
                    f"{self.base_url}/model-versions/{version_id}",
                    use_auth=True
                )
                if not success:
                    return None
                
                model_id = version.get('modelId')
                if not model_id:
                    logger.error(f"No modelId found in version {version_id}")
                    return None
            
                # Now get the model data for additional metadata
                success, model_data = await downloader.make_request(
                    'GET',
                    f"{self.base_url}/models/{model_id}",
                    use_auth=True
                )
                if success:
                    # Enrich version with model data
                    version['model']['description'] = model_data.get("description")
                    version['model']['tags'] = model_data.get("tags", [])
                    version['creator'] = model_data.get("creator")
                
                return version
            
            # Case 2: model_id is provided (with or without version_id)
            elif model_id is not None:
                # Step 1: Get model data to find version_id if not provided and get additional metadata
                success, data = await downloader.make_request(
                    'GET',
                    f"{self.base_url}/models/{model_id}",
                    use_auth=True
                )
                if not success:
                    return None
                    
                model_versions = data.get('modelVersions', [])
                
                # Step 2: Determine the version_id to use
                target_version_id = version_id
                if target_version_id is None:
                    target_version_id = model_versions[0].get('id')
            
                # Step 3: Get detailed version info using the version_id
                success, version = await downloader.make_request(
                    'GET',
                    f"{self.base_url}/model-versions/{target_version_id}",
                    use_auth=True
                )
                if not success:
                    return None
                
                # Step 4: Enrich version_info with model data
                # Add description and tags from model data
                version['model']['description'] = data.get("description")
                version['model']['tags'] = data.get("tags", [])
                
                # Add creator from model data
                version['creator'] = data.get("creator")
                
                return version
            
            # Case 3: Neither model_id nor version_id provided
            else:
                logger.error("Either model_id or version_id must be provided")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching model version: {e}")
            return None

    async def get_model_version_info(self, version_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Fetch model version metadata from Civitai
        
        Args:
            version_id: The Civitai model version ID
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: A tuple containing:
                - The model version data or None if not found
                - An error message if there was an error, or None on success
        """
        try:
            downloader = await get_downloader()
            url = f"{self.base_url}/model-versions/{version_id}"
            
            logger.debug(f"Resolving DNS for model version info: {url}")
            success, result = await downloader.make_request(
                'GET',
                url,
                use_auth=True
            )
            
            if success:
                logger.debug(f"Successfully fetched model version info for: {version_id}")
                return result, None
            
            # Handle specific error cases
            if "404" in str(result):
                error_msg = f"Model not found (status 404)"
                logger.warning(f"Model version not found: {version_id} - {error_msg}")
                return None, error_msg
            
            # Other error cases
            logger.error(f"Failed to fetch model info for {version_id}: {result}")
            return None, str(result)
        except Exception as e:
            error_msg = f"Error fetching model version info: {e}"
            logger.error(error_msg)
            return None, error_msg

    async def get_model_metadata(self, model_id: str) -> Tuple[Optional[Dict], int]:
        """Fetch model metadata (description, tags, and creator info) from Civitai API
        
        Args:
            model_id: The Civitai model ID
            
        Returns:
            Tuple[Optional[Dict], int]: A tuple containing:
                - A dictionary with model metadata or None if not found
                - The HTTP status code from the request (0 for exceptions)
        """
        try:
            downloader = await get_downloader()
            url = f"{self.base_url}/models/{model_id}"
            
            success, result = await downloader.make_request(
                'GET',
                url,
                use_auth=True
            )
            
            if not success:
                # Try to extract status code from error message
                status_code = 0
                if "404" in str(result):
                    status_code = 404
                elif "401" in str(result):
                    status_code = 401
                elif "403" in str(result):
                    status_code = 403
                logger.warning(f"Failed to fetch model metadata: {result}")
                return None, status_code
            
            # Extract relevant metadata
            metadata = {
                "description": result.get("description") or "No model description available",
                "tags": result.get("tags", []),
                "creator": {
                    "username": result.get("creator", {}).get("username"),
                    "image": result.get("creator", {}).get("image")
                }
            }
            
            if metadata["description"] or metadata["tags"] or metadata["creator"]["username"]:
                return metadata, 200
            else:
                logger.warning(f"No metadata found for model {model_id}")
                return None, 200
                
        except Exception as e:
            logger.error(f"Error fetching model metadata: {e}", exc_info=True)
            return None, 0

    async def get_image_info(self, image_id: str) -> Optional[Dict]:
        """Fetch image information from Civitai API
        
        Args:
            image_id: The Civitai image ID
            
        Returns:
            Optional[Dict]: The image data or None if not found
        """
        try:
            downloader = await get_downloader()
            url = f"{self.base_url}/images?imageId={image_id}&nsfw=X"
            
            logger.debug(f"Fetching image info for ID: {image_id}")
            success, result = await downloader.make_request(
                'GET',
                url,
                use_auth=True
            )
            
            if success:
                if result and "items" in result and len(result["items"]) > 0:
                    logger.debug(f"Successfully fetched image info for ID: {image_id}")
                    return result["items"][0]
                logger.warning(f"No image found with ID: {image_id}")
                return None
            
            logger.error(f"Failed to fetch image info for ID: {image_id}: {result}")
            return None
        except Exception as e:
            error_msg = f"Error fetching image info: {e}"
            logger.error(error_msg)
            return None
