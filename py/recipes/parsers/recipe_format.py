"""Parser for dedicated recipe metadata format."""

import re
import json
import logging
from typing import Dict, Any
from ...config import config
from ..base import RecipeMetadataParser
from ..constants import GEN_PARAM_KEYS
from ...services.metadata_service import get_default_metadata_provider

logger = logging.getLogger(__name__)

class RecipeFormatParser(RecipeMetadataParser):
    """Parser for images with dedicated recipe metadata format"""
    
    # Regular expression pattern for extracting recipe metadata
    METADATA_MARKER = r'Recipe metadata: (\{.*\})'
    
    def is_metadata_matching(self, user_comment: str) -> bool:
        """Check if the user comment matches the metadata format"""
        return re.search(self.METADATA_MARKER, user_comment, re.IGNORECASE | re.DOTALL) is not None
    
    async def parse_metadata(self, user_comment: str, recipe_scanner=None, civitai_client=None) -> Dict[str, Any]:
        """Parse metadata from images with dedicated recipe metadata format"""
        try:
            # Get metadata provider instead of using civitai_client directly
            metadata_provider = await get_default_metadata_provider()
            
            # Extract recipe metadata from user comment
            try:
                # Look for recipe metadata section
                recipe_match = re.search(self.METADATA_MARKER, user_comment, re.IGNORECASE | re.DOTALL)
                if not recipe_match:
                    recipe_metadata = None
                else:
                    recipe_json = recipe_match.group(1)
                    recipe_metadata = json.loads(recipe_json)
            except Exception as e:
                logger.error(f"Error extracting recipe metadata: {e}")
                recipe_metadata = None
            if not recipe_metadata:
                return {"error": "No recipe metadata found", "loras": []}
                
            # Process the recipe metadata
            loras = []
            for lora in recipe_metadata.get('loras', []):
                # Convert recipe lora format to frontend format
                lora_entry = {
                    'id': int(lora.get('modelVersionId', 0)),
                    'name': lora.get('modelName', ''),
                    'version': lora.get('modelVersionName', ''),
                    'type': 'lora',
                    'weight': lora.get('strength', 1.0),
                    'file_name': lora.get('file_name', ''),
                    'hash': lora.get('hash', '')
                }
                
                # Check if this LoRA exists locally by SHA256 hash
                if lora.get('hash') and recipe_scanner:
                    lora_scanner = recipe_scanner._lora_scanner
                    exists_locally = lora_scanner.has_hash(lora['hash'])
                    if exists_locally:
                        lora_cache = await lora_scanner.get_cached_data()
                        lora_item = next((item for item in lora_cache.raw_data if item['sha256'].lower() == lora['hash'].lower()), None)
                        if lora_item:
                            lora_entry['existsLocally'] = True
                            lora_entry['localPath'] = lora_item['file_path']
                            lora_entry['file_name'] = lora_item['file_name']
                            lora_entry['size'] = lora_item['size']
                            lora_entry['thumbnailUrl'] = config.get_preview_static_url(lora_item['preview_url'])
                            
                    else:
                        lora_entry['existsLocally'] = False
                        lora_entry['localPath'] = None
                        
                        # Try to get additional info from Civitai if we have a model version ID
                        if lora.get('modelVersionId') and metadata_provider:
                            try:
                                civitai_info_tuple = await metadata_provider.get_model_version_info(lora['modelVersionId'])
                                # Populate lora entry with Civitai info
                                populated_entry = await self.populate_lora_from_civitai(
                                    lora_entry, 
                                    civitai_info_tuple, 
                                    recipe_scanner,
                                    None,  # No need to track base model counts
                                    lora['hash']
                                )
                                if populated_entry is None:
                                    continue  # Skip invalid LoRA types
                                lora_entry = populated_entry
                            except Exception as e:
                                logger.error(f"Error fetching Civitai info for LoRA: {e}")
                                lora_entry['thumbnailUrl'] = '/loras_static/images/no-preview.png'
                
                loras.append(lora_entry)
            
            logger.info(f"Found {len(loras)} loras in recipe metadata")

            # Process checkpoint information if present
            checkpoint = None
            checkpoint_data = recipe_metadata.get('checkpoint') or {}
            if isinstance(checkpoint_data, dict) and checkpoint_data:
                version_id = checkpoint_data.get('modelVersionId') or checkpoint_data.get('id')
                checkpoint_entry = {
                    'id': version_id or 0,
                    'modelId': checkpoint_data.get('modelId', 0),
                    'name': checkpoint_data.get('name', 'Unknown Checkpoint'),
                    'version': checkpoint_data.get('version', ''),
                    'type': checkpoint_data.get('type', 'checkpoint'),
                    'hash': checkpoint_data.get('hash', ''),
                    'existsLocally': False,
                    'localPath': None,
                    'file_name': checkpoint_data.get('file_name', ''),
                    'thumbnailUrl': '/loras_static/images/no-preview.png',
                    'baseModel': '',
                    'size': 0,
                    'downloadUrl': '',
                    'isDeleted': False
                }

                if metadata_provider:
                    try:
                        civitai_info = None
                        if version_id:
                            civitai_info = await metadata_provider.get_model_version_info(str(version_id))
                        elif checkpoint_entry.get('hash'):
                            civitai_info = await metadata_provider.get_model_by_hash(checkpoint_entry['hash'])

                        if civitai_info:
                            checkpoint_entry = await self.populate_checkpoint_from_civitai(checkpoint_entry, civitai_info)
                    except Exception as e:
                        logger.error(f"Error fetching Civitai info for checkpoint in recipe metadata: {e}")

                checkpoint = checkpoint_entry
            
            # Filter gen_params to only include recognized keys
            filtered_gen_params = {}
            if 'gen_params' in recipe_metadata:
                for key, value in recipe_metadata['gen_params'].items():
                    if key in GEN_PARAM_KEYS:
                        filtered_gen_params[key] = value
            
            return {
                'base_model': checkpoint['baseModel'] if checkpoint and checkpoint.get('baseModel') else recipe_metadata.get('base_model', ''),
                'loras': loras,
                'gen_params': filtered_gen_params,
                'tags': recipe_metadata.get('tags', []),
                'title': recipe_metadata.get('title', ''),
                'from_recipe_metadata': True,
                **({'checkpoint': checkpoint, 'model': checkpoint} if checkpoint else {})
            }
            
        except Exception as e:
            logger.error(f"Error parsing recipe format metadata: {e}", exc_info=True)
            return {"error": str(e), "loras": []}
