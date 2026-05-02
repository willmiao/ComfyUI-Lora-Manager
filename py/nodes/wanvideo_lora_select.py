import os
from ..utils.utils import get_lora_info_absolute
from ..config import config
from .utils import FlexibleOptionalInputType, any_type, get_loras_list
import logging

logger = logging.getLogger(__name__)


def _relpath_within_loras(abs_path):
    """Return abs_path relative to the first matching lora root, or basename as fallback."""
    all_roots = list(config.loras_roots or []) + list(config.extra_loras_roots or [])
    for root in all_roots:
        try:
            return os.path.relpath(abs_path, root)
        except ValueError:
            continue
    return os.path.basename(abs_path)

class WanVideoLoraSelectLM:
    NAME = "WanVideo Lora Select (LoraManager)"
    CATEGORY = "Lora Manager/stackers"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "low_mem_load": ("BOOLEAN", {"default": False, "tooltip": "Load LORA models with less VRAM usage, slower loading. This affects ALL LoRAs, not just the current ones. No effect if merge_loras is False"}),
                "merge_loras": ("BOOLEAN", {"default": True, "tooltip": "Merge LoRAs into the model, otherwise they are loaded on the fly. Always disabled for GGUF and scaled fp8 models. This affects ALL LoRAs, not just the current one"}),
                "text": ("AUTOCOMPLETE_TEXT_LORAS", {
                    "placeholder": "Search LoRAs to add...",
                    "tooltip": "Format: <lora:lora_name:strength> separated by spaces or punctuation",
                }),
            },
            "optional": FlexibleOptionalInputType(any_type),
        }

    RETURN_TYPES = ("WANVIDLORA", "STRING", "STRING")
    RETURN_NAMES = ("lora", "trigger_words", "active_loras")
    FUNCTION = "process_loras"
    
    def process_loras(self, text, low_mem_load=False, merge_loras=True, **kwargs):
        loras_list = []
        all_trigger_words = []
        active_loras = []
        
        # Process existing prev_lora if available
        prev_lora = kwargs.get('prev_lora', None)
        if prev_lora is not None:
            loras_list.extend(prev_lora)

        if not merge_loras:
            low_mem_load = False  # Unmerged LoRAs don't need low_mem_load
        
        # Get blocks if available
        blocks = kwargs.get('blocks', {})
        selected_blocks = blocks.get("selected_blocks", {})
        layer_filter = blocks.get("layer_filter", "")
        
        # Process loras from kwargs with support for both old and new formats
        loras_from_widget = get_loras_list(kwargs)
        for lora in loras_from_widget:
            if not lora.get('active', False):
                continue
                
            lora_name = lora['name']
            model_strength = float(lora['strength'])
            clip_strength = float(lora.get('clipStrength', model_strength))
            
            # Get lora path and trigger words
            lora_path, trigger_words = get_lora_info_absolute(lora_name)
            
            # Create lora item for WanVideo format
            lora_item = {
                "path": lora_path,
                "strength": model_strength,
                "name": os.path.splitext(_relpath_within_loras(lora_path))[0],
                "blocks": selected_blocks,
                "layer_filter": layer_filter,
                "low_mem_load": low_mem_load,
                "merge_loras": merge_loras,
            }
            
            # Add to list and collect active loras
            loras_list.append(lora_item)
            active_loras.append((lora_name, model_strength, clip_strength))
            
            # Add trigger words to collection
            all_trigger_words.extend(trigger_words)
        
        # Format trigger_words for output
        trigger_words_text = ",, ".join(all_trigger_words) if all_trigger_words else ""
        
        # Format active_loras for output
        formatted_loras = []
        for name, model_strength, clip_strength in active_loras:
            if abs(model_strength - clip_strength) > 0.001:
                # Different model and clip strengths
                formatted_loras.append(f"<lora:{name}:{str(model_strength).strip()}:{str(clip_strength).strip()}>")
            else:
                # Same strength for both
                formatted_loras.append(f"<lora:{name}:{str(model_strength).strip()}>")
                
        active_loras_text = " ".join(formatted_loras)

        return (loras_list, trigger_words_text, active_loras_text)
