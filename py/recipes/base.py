"""Base classes for recipe parsers."""

import json
import logging
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from abc import ABC, abstractmethod
from ..config import config
from ..utils.constants import VALID_LORA_TYPES, VALID_CHECKPOINT_SUB_TYPES
from ..utils.civitai_utils import rewrite_preview_url

logger = logging.getLogger(__name__)

class RecipeMetadataParser(ABC):
    """Interface for parsing recipe metadata from image user comments"""

    METADATA_MARKER = None

    @abstractmethod
    def is_metadata_matching(self, user_comment: str) -> bool:
        """Check if the user comment matches the metadata format"""
        pass
    
    @abstractmethod
    async def parse_metadata(self, user_comment: str, recipe_scanner=None, civitai_client=None) -> Dict[str, Any]:
        """
        Parse metadata from user comment and return structured recipe data
        
        Args:
            user_comment: The EXIF UserComment string from the image
            recipe_scanner: Optional recipe scanner instance for local LoRA lookup
            civitai_client: Optional Civitai client for fetching model information
            
        Returns:
            Dict containing parsed recipe data with standardized format
        """
        pass
    
    @staticmethod
    async def populate_lora_from_civitai(lora_entry: Dict[str, Any], civitai_info_tuple: Tuple[Dict[str, Any], Optional[str]], 
                                         recipe_scanner=None, base_model_counts=None, hash_value=None) -> Optional[Dict[str, Any]]:
        """
        Populate a lora entry with information from Civitai API response
        
        Args:
            lora_entry: The lora entry to populate
            civitai_info_tuple: The response tuple from Civitai API (data, error_msg)
            recipe_scanner: Optional recipe scanner for local file lookup
            base_model_counts: Optional dict to track base model counts
            hash_value: Optional hash value to use if not available in civitai_info
            
        Returns:
            The populated lora_entry dict if type is valid, None otherwise
        """
        try:
            # Unpack the tuple to get the actual data
            civitai_info, error_msg = civitai_info_tuple if isinstance(civitai_info_tuple, tuple) else (civitai_info_tuple, None)
            
            if not civitai_info or error_msg == "Model not found":
                # CivitAI may fail to resolve a hash that is still being
                # computed (known CivitAI issue). Before marking as deleted,
                # try to reconcile with a local model that has the same
                # filename and matching AutoV3 hash.
                reconciled = False
                file_name = lora_entry.get("file_name")
                if file_name and recipe_scanner and hash_value:
                    lora_scanner = getattr(recipe_scanner, "_lora_scanner", None)
                    if lora_scanner:
                        try:
                            # Local import to avoid circular dependency:
                            # base.py → file_utils → settings_manager → ...
                            #  → recipe_scanner → enrichment → base.py
                            from ..utils.file_utils import calculate_autov3  # fmt: skip
                            cache = await lora_scanner.get_cached_data()
                            for item in getattr(cache, "raw_data", []):
                                if item.get("file_name") == file_name:
                                    local_path = item.get("file_path")
                                    if local_path and os.path.exists(local_path):
                                        local_autov3 = calculate_autov3(local_path)
                                        if local_autov3 and local_autov3 == hash_value:
                                            lora_entry["existsLocally"] = True
                                            lora_entry["localPath"] = local_path
                                            lora_entry["hash"] = item.get("sha256", hash_value)
                                            if "preview_url" in item:
                                                lora_entry["thumbnailUrl"] = config.get_preview_static_url(item["preview_url"])
                                            civ = item.get("civitai") or {}
                                            if isinstance(civ, dict):
                                                if civ.get("id") is not None:
                                                    lora_entry["id"] = civ["id"]
                                                if civ.get("modelId") is not None:
                                                    lora_entry["modelId"] = civ["modelId"]
                                                if civ.get("name"):
                                                    lora_entry["version"] = civ["name"]
                                                # model_name is the CivitAI model display
                                                # name stored directly in the cache column.
                                                cached_model_name = item.get("model_name")
                                                if cached_model_name:
                                                    lora_entry["name"] = cached_model_name
                                            reconciled = True
                                            break
                        except Exception:
                            pass
                if not reconciled:
                    lora_entry['isDeleted'] = True
                    lora_entry['thumbnailUrl'] = '/loras_static/images/no-preview.png'
                return lora_entry
                
            # Get model type and validate
            model_type = civitai_info.get('model', {}).get('type', '').lower()
            lora_entry['type'] = model_type
            if model_type not in VALID_LORA_TYPES:
                logger.debug(f"Skipping non-LoRA model type: {model_type}")
                return None

            # Check if this is an early access lora
            if civitai_info.get('earlyAccessEndsAt'):
                # Convert earlyAccessEndsAt to a human-readable date
                early_access_date = civitai_info.get('earlyAccessEndsAt', '')
                lora_entry['isEarlyAccess'] = True
                lora_entry['earlyAccessEndsAt'] = early_access_date
                
            # Update model name if available
            if 'model' in civitai_info and 'name' in civitai_info['model']:
                lora_entry['name'] = civitai_info['model']['name']

            lora_entry['id'] = civitai_info.get('id')
            lora_entry['modelId'] = civitai_info.get('modelId')
            
            # Update version if available
            if 'name' in civitai_info:
                lora_entry['version'] = civitai_info.get('name', '')
            
            # Get thumbnail URL from first image
            if 'images' in civitai_info and civitai_info['images']:
                image_url = civitai_info['images'][0].get('url')
                if image_url:
                    rewritten_image_url, _ = rewrite_preview_url(image_url, media_type='image')
                    lora_entry['thumbnailUrl'] = rewritten_image_url or image_url
            
            # Get base model
            current_base_model = civitai_info.get('baseModel', '')
            lora_entry['baseModel'] = current_base_model
            
            # Update base model counts if tracking them
            if base_model_counts is not None and current_base_model:
                base_model_counts[current_base_model] = base_model_counts.get(current_base_model, 0) + 1
            
            # Get download URL
            lora_entry['downloadUrl'] = civitai_info.get('downloadUrl', '')
            
            # Process file information if available
            if 'files' in civitai_info:
                # Find the primary model file (type="Model" and primary=true) in the files list
                model_file = next((file for file in civitai_info.get('files', []) 
                                    if file.get('type') == 'Model' and file.get('primary') == True), None)
                
                if model_file:
                    # Get size
                    lora_entry['size'] = model_file.get('sizeKB', 0) * 1024
                    
                    # Get SHA256 hash
                    sha256 = model_file.get('hashes', {}).get('SHA256', hash_value)
                    if sha256:
                        lora_entry['hash'] = sha256.lower()
                    
                    # Check if exists locally
                    if recipe_scanner and lora_entry['hash']:
                        lora_scanner = recipe_scanner._lora_scanner
                        exists_locally = lora_scanner.has_hash(lora_entry['hash'])
                        if exists_locally:
                            try:
                                local_path = lora_scanner.get_path_by_hash(lora_entry['hash'])
                                lora_entry['existsLocally'] = True
                                lora_entry['localPath'] = local_path
                                lora_entry['file_name'] = os.path.splitext(os.path.basename(local_path))[0]
                                
                                # Get thumbnail from local preview if available
                                lora_cache = await lora_scanner.get_cached_data()
                                lora_item = next((item for item in lora_cache.raw_data 
                                                    if item['sha256'].lower() == lora_entry['hash'].lower()), None)
                                if lora_item and 'preview_url' in lora_item:
                                    lora_entry['thumbnailUrl'] = config.get_preview_static_url(lora_item['preview_url'])
                            except Exception as e:
                                logger.error(f"Error getting local lora path: {e}")
                        else:
                            # For missing LoRAs, get file_name from model_file.name
                            file_name = model_file.get('name', '')
                            lora_entry['file_name'] = os.path.splitext(file_name)[0] if file_name else ''
                
        except Exception as e:
            logger.error(f"Error populating lora from Civitai info: {e}")
            
        return lora_entry
    
    @staticmethod
    async def populate_checkpoint_from_civitai(checkpoint: Dict[str, Any], civitai_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Populate checkpoint information from Civitai API response
        
        Args:
            checkpoint: The checkpoint entry to populate
            civitai_info: The response from Civitai API or a (data, error_msg) tuple
            
        Returns:
            The populated checkpoint dict
        """
        try:
            civitai_data, error_msg = (
                (civitai_info, None)
                if not isinstance(civitai_info, tuple)
                else civitai_info
            )

            if not civitai_data or error_msg == "Model not found":
                checkpoint['isDeleted'] = True
                return checkpoint

            # Validate that the model type is actually a checkpoint.
            # Unlike populate_lora_from_civitai which has this check,
            # this function was missing type validation — allowing LoRA
            # version data to be saved as the recipe's checkpoint when the
            # wrong version ID was passed downstream (fixed in v2.7+).
            model_type = civitai_data.get('model', {}).get('type', '').lower()
            if model_type not in VALID_CHECKPOINT_SUB_TYPES:
                logger.warning(
                    f"Cannot populate checkpoint: model version {civitai_data.get('id')} "
                    f"has type '{model_type}', expected one of {VALID_CHECKPOINT_SUB_TYPES}. "
                    f"Skipping checkpoint enrichment."
                )
                return checkpoint

            if 'model' in civitai_data and 'name' in civitai_data['model']:
                checkpoint['name'] = civitai_data['model']['name']

            if 'name' in civitai_data:
                checkpoint['version'] = civitai_data.get('name', '')

            if 'images' in civitai_data and civitai_data['images']:
                image_url = civitai_data['images'][0].get('url')
                if image_url:
                    rewritten_image_url, _ = rewrite_preview_url(image_url, media_type='image')
                    checkpoint['thumbnailUrl'] = rewritten_image_url or image_url

            checkpoint['baseModel'] = civitai_data.get('baseModel', '')
            checkpoint['downloadUrl'] = civitai_data.get('downloadUrl', '')

            checkpoint['modelId'] = civitai_data.get('modelId', checkpoint.get('modelId', 0))
            checkpoint['id'] = civitai_data.get('id', 0)

            if 'files' in civitai_data:
                model_file = next(
                    (
                        file
                        for file in civitai_data.get('files', [])
                        if file.get('type') == 'Model'
                    ),
                    None,
                )

                if model_file:
                    checkpoint['size'] = model_file.get('sizeKB', 0) * 1024

                    sha256 = model_file.get('hashes', {}).get('SHA256')
                    if sha256:
                        checkpoint['hash'] = sha256.lower()

                    file_name = model_file.get('name', '')
                    if file_name:
                        checkpoint['file_name'] = os.path.splitext(file_name)[0]
        except Exception as e:
            logger.error(f"Error populating checkpoint from Civitai info: {e}")
            
        return checkpoint
