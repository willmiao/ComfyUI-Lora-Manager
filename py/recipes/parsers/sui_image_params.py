"""Parser for SuiImage (Stable Diffusion WebUI) metadata format."""

import json
import logging
from typing import Dict, Any, Optional, List
from ..base import RecipeMetadataParser
from ...services.metadata_service import get_default_metadata_provider

logger = logging.getLogger(__name__)


class SuiImageParamsParser(RecipeMetadataParser):
    """Parser for SuiImage metadata JSON format.

    This format is used by some Stable Diffusion WebUI variants.
    Structure:
    {
        "sui_image_params": {
            "prompt": "...",
            "negativeprompt": "...",
            "model": "...",
            "seed": ...,
            "steps": ...,
            ...
        },
        "sui_models": [
            {"name": "...", "param": "model", "hash": "..."},
            ...
        ],
        "sui_extra_data": {...}
    }
    """

    def is_metadata_matching(self, user_comment: str) -> bool:
        """Check if the user comment matches the SuiImage metadata format"""
        try:
            data = json.loads(user_comment)
            return isinstance(data, dict) and 'sui_image_params' in data
        except (json.JSONDecodeError, TypeError):
            return False

    async def parse_metadata(self, user_comment: str, recipe_scanner=None, civitai_client=None) -> Dict[str, Any]:
        """Parse metadata from SuiImage metadata format"""
        try:
            metadata_provider = await get_default_metadata_provider()

            data = json.loads(user_comment)
            params = data.get('sui_image_params', {})
            models = data.get('sui_models', [])

            # Extract prompt and negative prompt
            prompt = params.get('prompt', '')
            negative_prompt = params.get('negativeprompt', '') or params.get('negative_prompt', '')

            # Extract generation parameters
            gen_params = {}
            if prompt:
                gen_params['prompt'] = prompt
            if negative_prompt:
                gen_params['negative_prompt'] = negative_prompt

            # Map standard parameters
            param_mapping = {
                'steps': 'steps',
                'seed': 'seed',
                'cfgscale': 'cfg_scale',
                'cfg_scale': 'cfg_scale',
                'width': 'width',
                'height': 'height',
                'sampler': 'sampler',
                'scheduler': 'scheduler',
                'model': 'model',
                'vae': 'vae',
            }

            for src_key, dest_key in param_mapping.items():
                if src_key in params and params[src_key] is not None:
                    gen_params[dest_key] = params[src_key]

            # Add size info if available
            if 'width' in gen_params and 'height' in gen_params:
                gen_params['size'] = f"{gen_params['width']}x{gen_params['height']}"

            # Process models - extract checkpoint and loras
            loras: List[Dict[str, Any]] = []
            checkpoint: Optional[Dict[str, Any]] = None

            for model in models:
                model_name = model.get('name', '')
                param_type = model.get('param', '')
                model_hash = model.get('hash', '')

                # Remove .safetensors extension for cleaner name
                clean_name = model_name.replace('.safetensors', '') if model_name else ''

                # Check if this is a LoRA by looking at the name or param type
                is_lora = 'lora' in model_name.lower() or param_type.lower().startswith('lora')

                if is_lora:
                    lora_entry = {
                        'id': 0,
                        'modelId': 0,
                        'name': clean_name,
                        'version': '',
                        'type': 'lora',
                        'weight': 1.0,
                        'existsLocally': False,
                        'localPath': None,
                        'file_name': model_name,
                        'hash': model_hash.replace('0x', '') if model_hash.startswith('0x') else model_hash,
                        'thumbnailUrl': '/loras_static/images/no-preview.png',
                        'baseModel': '',
                        'size': 0,
                        'downloadUrl': '',
                        'isDeleted': False
                    }

                    # Try to get additional info from metadata provider
                    if metadata_provider and model_hash:
                        try:
                            civitai_info = await metadata_provider.get_model_by_hash(
                                model_hash.replace('0x', '') if model_hash.startswith('0x') else model_hash
                            )
                            if civitai_info:
                                lora_entry = await self.populate_lora_from_civitai(
                                    lora_entry, civitai_info, recipe_scanner
                                )
                        except Exception as e:
                            logger.debug(f"Error fetching info for LoRA {clean_name}: {e}")

                    if lora_entry:
                        loras.append(lora_entry)
                elif param_type == 'model' or 'lora' not in model_name.lower():
                    # This is likely a checkpoint
                    checkpoint_entry = {
                        'id': 0,
                        'modelId': 0,
                        'name': clean_name,
                        'version': '',
                        'type': 'checkpoint',
                        'hash': model_hash.replace('0x', '') if model_hash.startswith('0x') else model_hash,
                        'existsLocally': False,
                        'localPath': None,
                        'file_name': model_name,
                        'thumbnailUrl': '/loras_static/images/no-preview.png',
                        'baseModel': '',
                        'size': 0,
                        'downloadUrl': '',
                        'isDeleted': False
                    }

                    # Try to get additional info from metadata provider
                    if metadata_provider and model_hash:
                        try:
                            civitai_info = await metadata_provider.get_model_by_hash(
                                model_hash.replace('0x', '') if model_hash.startswith('0x') else model_hash
                            )
                            if civitai_info:
                                checkpoint_entry = await self.populate_checkpoint_from_civitai(
                                    checkpoint_entry, civitai_info
                                )
                        except Exception as e:
                            logger.debug(f"Error fetching info for checkpoint {clean_name}: {e}")

                    checkpoint = checkpoint_entry

            # Determine base model from loras or checkpoint
            base_model = None
            if loras:
                base_models = [lora.get('baseModel') for lora in loras if lora.get('baseModel')]
                if base_models:
                    from collections import Counter
                    base_model_counts = Counter(base_models)
                    base_model = base_model_counts.most_common(1)[0][0]
            elif checkpoint and checkpoint.get('baseModel'):
                base_model = checkpoint['baseModel']

            return {
                'base_model': base_model,
                'loras': loras,
                'checkpoint': checkpoint,
                'gen_params': gen_params,
                'from_sui_image_params': True
            }

        except Exception as e:
            logger.error(f"Error parsing SuiImage metadata: {e}", exc_info=True)
            return {"error": str(e), "loras": []}
