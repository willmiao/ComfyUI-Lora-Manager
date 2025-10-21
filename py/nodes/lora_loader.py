import logging
import re
from nodes import LoraLoader
from ..utils.utils import get_lora_info
from .utils import FlexibleOptionalInputType, any_type, extract_lora_name, get_loras_list, nunchaku_load_lora

logger = logging.getLogger(__name__)

class LoraManagerLoader:
    NAME = "Lora Loader (LoraManager)"
    CATEGORY = "Lora Manager/loaders"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                # "clip": ("CLIP",),
                "text": ("STRING", {
                    "multiline": True,
                    "pysssss.autocomplete": False, 
                    "dynamicPrompts": True, 
                    "tooltip": "Format: <lora:lora_name:strength> separated by spaces or punctuation",
                    "placeholder": "LoRA syntax input: <lora:name:strength>"
                }),
            },
            "optional": FlexibleOptionalInputType(any_type),
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "trigger_words", "loaded_loras")
    FUNCTION = "load_loras"
    
    def load_loras(self, model, text, **kwargs):
        """Loads multiple LoRAs based on the kwargs input and lora_stack."""
        loaded_loras = []
        all_trigger_words = []
        
        clip = kwargs.get('clip', None)
        lora_stack = kwargs.get('lora_stack', None)
        
        # Check if model is a Nunchaku Flux model - simplified approach
        is_nunchaku_model = False
        
        try:
            model_wrapper = model.model.diffusion_model
            # Check if model is a Nunchaku Flux model using only class name
            if model_wrapper.__class__.__name__ == "ComfyFluxWrapper":
                is_nunchaku_model = True
                logger.info("Detected Nunchaku Flux model")
        except (AttributeError, TypeError):
            # Not a model with the expected structure
            pass
        
        # First process lora_stack if available
        if lora_stack:
            for lora_path, model_strength, clip_strength in lora_stack:
                # Apply the LoRA using the appropriate loader
                if is_nunchaku_model:
                    # Use our custom function for Flux models
                    model = nunchaku_load_lora(model, lora_path, model_strength)
                    # clip remains unchanged for Nunchaku models
                else:
                    # Use default loader for standard models
                    model, clip = LoraLoader().load_lora(model, clip, lora_path, model_strength, clip_strength)
                
                # Extract lora name for trigger words lookup
                lora_name = extract_lora_name(lora_path)
                _, trigger_words = get_lora_info(lora_name)
                
                all_trigger_words.extend(trigger_words)
                # Add clip strength to output if different from model strength (except for Nunchaku models)
                if not is_nunchaku_model and abs(model_strength - clip_strength) > 0.001:
                    loaded_loras.append(f"{lora_name}: {model_strength},{clip_strength}")
                else:
                    loaded_loras.append(f"{lora_name}: {model_strength}")
        
        # Then process loras from kwargs with support for both old and new formats
        loras_list = get_loras_list(kwargs)
        for lora in loras_list:
            if not lora.get('active', False):
                continue
                
            lora_name = lora['name']
            model_strength = float(lora['strength'])
            # Get clip strength - use model strength as default if not specified
            clip_strength = float(lora.get('clipStrength', model_strength))
            
            # Get lora path and trigger words
            lora_path, trigger_words = get_lora_info(lora_name)
            
            # Apply the LoRA using the appropriate loader
            if is_nunchaku_model:
                # For Nunchaku models, use our custom function
                model = nunchaku_load_lora(model, lora_path, model_strength)
                # clip remains unchanged
            else:
                # Use default loader for standard models
                model, clip = LoraLoader().load_lora(model, clip, lora_path, model_strength, clip_strength)
            
            # Include clip strength in output if different from model strength and not a Nunchaku model
            if not is_nunchaku_model and abs(model_strength - clip_strength) > 0.001:
                loaded_loras.append(f"{lora_name}: {model_strength},{clip_strength}")
            else:
                loaded_loras.append(f"{lora_name}: {model_strength}")
            
            # Add trigger words to collection
            all_trigger_words.extend(trigger_words)
        
        # use ',, ' to separate trigger words for group mode
        trigger_words_text = ",, ".join(all_trigger_words) if all_trigger_words else ""
        
        # Format loaded_loras with support for both formats
        formatted_loras = []
        for item in loaded_loras:
            parts = item.split(":")
            lora_name = parts[0]
            strength_parts = parts[1].strip().split(",")
            
            if len(strength_parts) > 1:
                # Different model and clip strengths
                model_str = strength_parts[0].strip()
                clip_str = strength_parts[1].strip()
                formatted_loras.append(f"<lora:{lora_name}:{model_str}:{clip_str}>")
            else:
                # Same strength for both
                model_str = strength_parts[0].strip()
                formatted_loras.append(f"<lora:{lora_name}:{model_str}>")
                
        formatted_loras_text = " ".join(formatted_loras)

        return (model, clip, trigger_words_text, formatted_loras_text)

class LoraManagerTextLoader:
    NAME = "LoRA Text Loader (LoraManager)"
    CATEGORY = "Lora Manager/loaders"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "lora_syntax": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Format: <lora:lora_name:strength> separated by spaces or punctuation"
                }),
            },
            "optional": {
                "clip": ("CLIP",),
                "lora_stack": ("LORA_STACK",),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "trigger_words", "loaded_loras")
    FUNCTION = "load_loras_from_text"
    
    def parse_lora_syntax(self, text):
        """Parse LoRA syntax from text input."""
        # Pattern to match <lora:name:strength> or <lora:name:model_strength:clip_strength>
        pattern = r'<lora:([^:>]+):([^:>]+)(?::([^:>]+))?>'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        loras = []
        for match in matches:
            lora_name = match[0]
            model_strength = float(match[1])
            clip_strength = float(match[2]) if match[2] else model_strength
            
            loras.append({
                'name': lora_name,
                'model_strength': model_strength,
                'clip_strength': clip_strength
            })
        
        return loras
    
    def load_loras_from_text(self, model, lora_syntax, clip=None, lora_stack=None):
        """Load LoRAs based on text syntax input."""
        loaded_loras = []
        all_trigger_words = []
        
        # Check if model is a Nunchaku Flux model - simplified approach
        is_nunchaku_model = False
        
        try:
            model_wrapper = model.model.diffusion_model
            # Check if model is a Nunchaku Flux model using only class name
            if model_wrapper.__class__.__name__ == "ComfyFluxWrapper":
                is_nunchaku_model = True
                logger.info("Detected Nunchaku Flux model")
        except (AttributeError, TypeError):
            # Not a model with the expected structure
            pass
        
        # First process lora_stack if available
        if lora_stack:
            for lora_path, model_strength, clip_strength in lora_stack:
                # Apply the LoRA using the appropriate loader
                if is_nunchaku_model:
                    # Use our custom function for Flux models
                    model = nunchaku_load_lora(model, lora_path, model_strength)
                    # clip remains unchanged for Nunchaku models
                else:
                    # Use default loader for standard models
                    model, clip = LoraLoader().load_lora(model, clip, lora_path, model_strength, clip_strength)
                
                # Extract lora name for trigger words lookup
                lora_name = extract_lora_name(lora_path)
                _, trigger_words = get_lora_info(lora_name)
                
                all_trigger_words.extend(trigger_words)
                # Add clip strength to output if different from model strength (except for Nunchaku models)
                if not is_nunchaku_model and abs(model_strength - clip_strength) > 0.001:
                    loaded_loras.append(f"{lora_name}: {model_strength},{clip_strength}")
                else:
                    loaded_loras.append(f"{lora_name}: {model_strength}")
        
        # Parse and process LoRAs from text syntax
        parsed_loras = self.parse_lora_syntax(lora_syntax)
        for lora in parsed_loras:
            lora_name = lora['name']
            model_strength = lora['model_strength']
            clip_strength = lora['clip_strength']
            
            # Get lora path and trigger words
            lora_path, trigger_words = get_lora_info(lora_name)
            
            # Apply the LoRA using the appropriate loader
            if is_nunchaku_model:
                # For Nunchaku models, use our custom function
                model = nunchaku_load_lora(model, lora_path, model_strength)
                # clip remains unchanged
            else:
                # Use default loader for standard models
                model, clip = LoraLoader().load_lora(model, clip, lora_path, model_strength, clip_strength)
            
            # Include clip strength in output if different from model strength and not a Nunchaku model
            if not is_nunchaku_model and abs(model_strength - clip_strength) > 0.001:
                loaded_loras.append(f"{lora_name}: {model_strength},{clip_strength}")
            else:
                loaded_loras.append(f"{lora_name}: {model_strength}")
            
            # Add trigger words to collection
            all_trigger_words.extend(trigger_words)
        
        # use ',, ' to separate trigger words for group mode
        trigger_words_text = ",, ".join(all_trigger_words) if all_trigger_words else ""

        # Format loaded_loras with support for both formats
        formatted_loras = []
        for item in loaded_loras:
            parts = item.split(":")
            lora_name = parts[0].strip()
            strength_parts = parts[1].strip().split(",")
            
            if len(strength_parts) > 1:
                # Different model and clip strengths
                model_str = strength_parts[0].strip()
                clip_str = strength_parts[1].strip()
                formatted_loras.append(f"<lora:{lora_name}:{model_str}:{clip_str}>")
            else:
                # Same strength for both
                model_str = strength_parts[0].strip()
                formatted_loras.append(f"<lora:{lora_name}:{model_str}>")
                
        formatted_loras_text = " ".join(formatted_loras)

        return (model, clip, trigger_words_text, formatted_loras_text)