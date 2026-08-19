"""Parser for ComfyUI metadata format."""

import re
import json
import logging
from typing import Dict, Any
from ..base import RecipeMetadataParser
from ..constants import GEN_PARAM_KEYS
from ...services.metadata_service import get_default_metadata_provider

logger = logging.getLogger(__name__)

class ComfyMetadataParser(RecipeMetadataParser):
    """Parser for Civitai ComfyUI metadata JSON format"""
    
    METADATA_MARKER = r"class_type"
    
    def is_metadata_matching(self, user_comment: str) -> bool:
        """Check if the user comment matches the ComfyUI metadata format"""
        try:
            data = json.loads(user_comment)
            # Check if it contains class_type nodes typical of ComfyUI workflow
            return isinstance(data, dict) and any(isinstance(v, dict) and 'class_type' in v for v in data.values())
        except (json.JSONDecodeError, TypeError):
            return False
    
    async def parse_metadata(self, user_comment: str, recipe_scanner=None, civitai_client=None) -> Dict[str, Any]:
        """Parse metadata from Civitai ComfyUI metadata format"""
        try:
            # Get metadata provider instead of using civitai_client directly
            metadata_provider = await get_default_metadata_provider()
            
            data = json.loads(user_comment)

            checkpoint_nodes = {k: v for k, v in data.items() if isinstance(v, dict) and v.get('class_type') == 'CheckpointLoaderSimple'}
            checkpoint = None
            checkpoint_id = None
            checkpoint_version_id = None
            if checkpoint_nodes:
                checkpoint_node = next(iter(checkpoint_nodes.values()))
                if 'inputs' in checkpoint_node and 'ckpt_name' in checkpoint_node['inputs']:
                    checkpoint_name = checkpoint_node['inputs']['ckpt_name']
                    checkpoint_match = re.search(r'civitai:(\d+)@(\d+)', checkpoint_name)
                    if checkpoint_match:
                        checkpoint_id = checkpoint_match.group(1)
                        checkpoint_version_id = checkpoint_match.group(2)
                        checkpoint = {
                            'id': checkpoint_version_id,
                            'modelId': checkpoint_id,
                            'name': f"Checkpoint {checkpoint_id}",
                            'version': '',
                            'type': 'checkpoint'
                        }
                        if metadata_provider:
                            try:
                                civitai_info_tuple = await metadata_provider.get_model_version_info(checkpoint_version_id)
                                civitai_info, _ = civitai_info_tuple if isinstance(civitai_info_tuple, tuple) else (civitai_info_tuple, None)
                                checkpoint = await self.populate_checkpoint_from_civitai(checkpoint, civitai_info)
                            except Exception as e:
                                logger.error(f"Error fetching Civitai info for checkpoint: {e}")

            recipe_base_model = checkpoint.get('baseModel') if checkpoint else None
            loras = []
            lora_candidates = []
            for node in data.values():
                if not isinstance(node, dict):
                    continue

                inputs = node.get('inputs')
                if not isinstance(inputs, dict):
                    continue

                if node.get('class_type') == 'LoraLoader':
                    lora_name = inputs.get('lora_name', '')
                    if isinstance(lora_name, str) and lora_name:
                        lora_candidates.append((lora_name, inputs.get('strength_model', 1.0)))
                    continue

                if node.get('class_type') != 'LoraLoaderLM':
                    continue

                loras_data = inputs.get('loras', [])
                if isinstance(loras_data, dict):
                    loras_data = loras_data.get('__value__', [])
                if isinstance(loras_data, list) and len(loras_data) == 1 and isinstance(loras_data[0], list):
                    loras_data = loras_data[0]
                if not isinstance(loras_data, list):
                    continue

                for lora in loras_data:
                    if not isinstance(lora, dict) or not lora.get('active', False) or lora.get('_isDummy', False):
                        continue
                    lora_name = lora.get('name', '')
                    if isinstance(lora_name, str) and lora_name:
                        lora_candidates.append((lora_name, lora.get('strength', 1.0)))

            for lora_name, weight in lora_candidates:
                if isinstance(weight, str):
                    try:
                        weight = float(weight)
                    except ValueError:
                        weight = 1.0
                lora_id_match = re.search(r'civitai:(\d+)@(\d+)', lora_name)
                if lora_id_match:
                    model_id = lora_id_match.group(1)
                    model_version_id = lora_id_match.group(2)
                    entry_name = f"Lora {model_id}"
                else:
                    model_id = 0
                    model_version_id = 0
                    entry_name = re.split(r'[\\/]', lora_name)[-1]
                    entry_name = re.sub(r'\.[^.]+$', '', entry_name)

                lora_entry = {
                    'id': model_version_id,
                    'modelId': model_id,
                    'name': entry_name,
                    'version': '',
                    'type': 'lora',
                    'weight': weight,
                    'existsLocally': False,
                    'localPath': None,
                    'file_name': entry_name,
                    'hash': '',
                    'thumbnailUrl': '/loras_static/images/no-preview.png',
                    'baseModel': '',
                    'size': 0,
                    'downloadUrl': '',
                    'isDeleted': False
                }

                if lora_id_match:
                    if metadata_provider:
                        try:
                            civitai_info_tuple = await metadata_provider.get_model_version_info(model_version_id)
                            populated_entry = await self.populate_lora_from_civitai(
                                lora_entry,
                                civitai_info_tuple,
                                recipe_scanner
                            )
                            if populated_entry is None:
                                continue
                            lora_entry = populated_entry
                        except Exception as e:
                            logger.error(f"Error fetching Civitai info for LoRA: {e}")
                else:
                    if not recipe_scanner:
                        continue
                    local_lora = await recipe_scanner.get_local_lora(lora_name, recipe_base_model)
                    if not local_lora:
                        continue
                    lora_entry = self.populate_lora_from_local(lora_entry, local_lora)

                loras.append(lora_entry)
            
            # Extract generation parameters
            gen_params = {}
            
            # First try to get from extraMetadata
            if 'extraMetadata' in data:
                try:
                    # extraMetadata is a JSON string that needs to be parsed
                    extra_metadata = json.loads(data['extraMetadata'])
                    
                    # Map fields from extraMetadata to our standard format
                    mapping = {
                        'prompt': 'prompt',
                        'negativePrompt': 'negative_prompt',
                        'steps': 'steps',
                        'sampler': 'sampler',
                        'cfgScale': 'cfg_scale',
                        'seed': 'seed'
                    }
                    
                    for src_key, dest_key in mapping.items():
                        if src_key in extra_metadata:
                            gen_params[dest_key] = extra_metadata[src_key]
                    
                    # If size info is available, format as "width x height"
                    if 'width' in extra_metadata and 'height' in extra_metadata:
                        gen_params['size'] = f"{extra_metadata['width']}x{extra_metadata['height']}"
                    
                except Exception as e:
                    logger.error(f"Error parsing extraMetadata: {e}")
            
            # If extraMetadata doesn't have all the info, try to get from nodes
            if not gen_params or len(gen_params) < 3:  # At least we want prompt, negative_prompt, and steps
                # Find positive prompt node
                positive_nodes = {k: v for k, v in data.items() if isinstance(v, dict) and 
                                v.get('class_type', '').endswith('CLIPTextEncode') and 
                                v.get('_meta', {}).get('title') == 'Positive'}
                
                if positive_nodes:
                    positive_node = next(iter(positive_nodes.values()))
                    if 'inputs' in positive_node and 'text' in positive_node['inputs']:
                        gen_params['prompt'] = positive_node['inputs']['text']
                
                # Find negative prompt node
                negative_nodes = {k: v for k, v in data.items() if isinstance(v, dict) and 
                                v.get('class_type', '').endswith('CLIPTextEncode') and 
                                v.get('_meta', {}).get('title') == 'Negative'}
                
                if negative_nodes:
                    negative_node = next(iter(negative_nodes.values()))
                    if 'inputs' in negative_node and 'text' in negative_node['inputs']:
                        gen_params['negative_prompt'] = negative_node['inputs']['text']
                
                # Find KSampler node for other parameters
                ksampler_nodes = {k: v for k, v in data.items() if isinstance(v, dict) and v.get('class_type') == 'KSampler'}
                
                if ksampler_nodes:
                    ksampler_node = next(iter(ksampler_nodes.values()))
                    if 'inputs' in ksampler_node:
                        inputs = ksampler_node['inputs']
                        if 'sampler_name' in inputs:
                            gen_params['sampler'] = inputs['sampler_name']
                        if 'steps' in inputs:
                            gen_params['steps'] = inputs['steps']
                        if 'cfg' in inputs:
                            gen_params['cfg_scale'] = inputs['cfg']
                        if 'seed' in inputs:
                            gen_params['seed'] = inputs['seed']
            
            # Determine base model from loras info
            base_model = None
            if loras:
                # Use the most common base model from loras
                base_models = [lora['baseModel'] for lora in loras if lora.get('baseModel')]
                if base_models:
                    from collections import Counter
                    base_model_counts = Counter(base_models)
                    base_model = base_model_counts.most_common(1)[0][0]
            
            return {
                'base_model': base_model,
                'loras': loras,
                'checkpoint': checkpoint,
                'gen_params': gen_params,
                'from_comfy_metadata': True
            }
            
        except Exception as e:
            logger.error(f"Error parsing ComfyUI metadata: {e}", exc_info=True)
            return {"error": str(e), "loras": []}
