import os
import json
import logging
from typing import Dict, Optional, Callable, Awaitable

from ..utils.model_utils import determine_base_model
from ..utils.metadata_manager import MetadataManager
from ..services.metadata_service import get_default_metadata_provider
from ..config import config

logger = logging.getLogger(__name__)


class ModelMetadataService:
    """Service for handling model metadata operations"""
    
    def __init__(self):
        """Initialize the metadata service"""
        self.metadata_provider = None
    
    async def _get_metadata_provider(self):
        """Get metadata provider instance"""
        if not self.metadata_provider:
            self.metadata_provider = await get_default_metadata_provider()
        return self.metadata_provider
    
    async def load_local_metadata(self, metadata_path: str) -> Dict:
        """Load local metadata file
        
        Args:
            metadata_path: Path to the metadata file
            
        Returns:
            Dict: Loaded metadata or empty dict if file doesn't exist
        """
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading metadata from {metadata_path}: {e}")
                return {}
        return {}

    async def handle_not_found_on_civitai(self, metadata_path: str, local_metadata: Dict) -> None:
        """Handle case when model is not found on CivitAI
        
        Args:
            metadata_path: Path to save the metadata
            local_metadata: Local metadata to update
        """
        local_metadata['from_civitai'] = False
        await MetadataManager.save_metadata(metadata_path, local_metadata)

    def is_civitai_api_metadata(self, meta: dict) -> bool:
        """Determine if the given civitai metadata is from the civitai API
        
        Args:
            meta: Metadata dictionary to check
            
        Returns:
            bool: True if both 'files' and 'images' exist and are non-empty,
                 and the 'source' is not 'archive_db'
        """
        if not isinstance(meta, dict):
            return False
        files = meta.get('files')
        images = meta.get('images')
        source = meta.get('source')
        return bool(files) and bool(images) and source != 'archive_db'

    async def update_model_metadata(self, metadata_path: str, local_metadata: Dict, 
                                  civitai_metadata: Dict, metadata_provider=None) -> None:
        """Update local metadata with CivitAI data
        
        Args:
            metadata_path: Path to save the metadata
            local_metadata: Local metadata to update
            civitai_metadata: CivitAI metadata to merge
            metadata_provider: Optional metadata provider instance
        """
        # Save existing trainedWords and customImages if they exist
        existing_civitai = local_metadata.get('civitai') or {}  # Use empty dict if None

        # Check if we should skip the update to avoid overwriting richer data
        if civitai_metadata.get('source') == 'archive_db' and self.is_civitai_api_metadata(existing_civitai):
            logger.info(f"Skipping update from archive_db data to preserve richer API data for {metadata_path}")
            return
        else:
            # Preserve existing trained words and custom images if they exist
            preserved_trained_words = existing_civitai.get('trainedWords', [])
            preserved_custom_images = existing_civitai.get('customImages', [])
            
            # Update with new civitai metadata
            local_metadata['civitai'] = civitai_metadata
            
            # Restore preserved data if the new data doesn't have it
            if not civitai_metadata.get('trainedWords') and preserved_trained_words:
                local_metadata['civitai']['trainedWords'] = preserved_trained_words
            if not civitai_metadata.get('customImages') and preserved_custom_images:
                local_metadata['civitai']['customImages'] = preserved_custom_images
        
        # Update model-related metadata from civitai_metadata.model
        if 'model' in civitai_metadata and civitai_metadata['model']:
            model_info = civitai_metadata['model']
            if 'name' in model_info:
                local_metadata['model_name'] = model_info['name']
            if 'description' in model_info:
                local_metadata['description'] = model_info['description']
        
        # Update base model
        local_metadata['base_model'] = determine_base_model(civitai_metadata.get('baseModel'))
        
        # Update preview if needed
        if not local_metadata.get('preview_url') or not os.path.exists(local_metadata['preview_url']):
            images = civitai_metadata.get('images', [])
            if images:
                # Use the first image as preview
                local_metadata['preview_url'] = images[0].get('url')

        # Save updated metadata
        await MetadataManager.save_metadata(metadata_path, local_metadata)

    async def fetch_and_update_model(
        self, 
        sha256: str, 
        file_path: str, 
        model_data: dict,
        update_cache_func: Callable[[str, str, Dict], Awaitable[bool]]
    ) -> bool:
        """Fetch and update metadata for a single model
        
        Args:
            sha256: SHA256 hash of the model file
            file_path: Path to the model file
            model_data: The model object in cache to update
            update_cache_func: Function to update the cache with new metadata
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            metadata_provider = await self._get_metadata_provider()
            
            # Fetch CivitAI metadata by hash
            civitai_metadata = await metadata_provider.get_model_by_hash(sha256)
            
            if not civitai_metadata:
                logger.warning(f"No CivitAI metadata found for hash {sha256}")
                return False
            
            # Load existing local metadata
            metadata_path = file_path.replace('.safetensors', '.metadata.json')
            local_metadata = await self.load_local_metadata(metadata_path)
            
            # Update metadata
            await self.update_model_metadata(metadata_path, local_metadata, civitai_metadata)
            
            # Update cache
            success = await update_cache_func(sha256, file_path, local_metadata)
            
            if success:
                logger.info(f"Successfully updated metadata for {file_path}")
            else:
                logger.warning(f"Failed to update cache for {file_path}")
            
            return success

        except KeyError as e:
            logger.error(f"Missing required field in metadata: {e}")
            return False
        except Exception as e:
            logger.error(f"Error fetching metadata for {file_path}: {e}")
            return False
    
    def filter_civitai_data(self, data: Dict, minimal: bool = False) -> Dict:
        """Filter relevant fields from CivitAI data
        
        Args:
            data: CivitAI data dictionary
            minimal: If True, return only essential fields
            
        Returns:
            Dict: Filtered data
        """
        if not data:
            return {}

        fields = ["id", "modelId", "name", "trainedWords"] if minimal else [
            "id", "modelId", "name", "createdAt", "updatedAt",
            "publishedAt", "trainedWords", "baseModel", "description",
            "model", "images", "customImages", "creator"
        ]
        return {k: data[k] for k in fields if k in data}
