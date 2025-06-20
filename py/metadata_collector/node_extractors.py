import os

from .constants import MODELS, PROMPTS, SAMPLING, LORAS, SIZE, IMAGES, IS_SAMPLER


class NodeMetadataExtractor:
    """Base class for node-specific metadata extraction"""
    
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        """Extract metadata from node inputs/outputs"""
        pass
        
    @staticmethod
    def update(node_id, outputs, metadata):
        """Update metadata with node outputs after execution"""
        pass
        
class GenericNodeExtractor(NodeMetadataExtractor):
    """Default extractor for nodes without specific handling"""
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        pass
        
class CheckpointLoaderExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs or "ckpt_name" not in inputs:
            return
            
        model_name = inputs.get("ckpt_name")
        if model_name:
            metadata[MODELS][node_id] = {
                "name": model_name,
                "type": "checkpoint",
                "node_id": node_id
            }
        
class CLIPTextEncodeExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs or "text" not in inputs:
            return
            
        text = inputs.get("text", "")
        metadata[PROMPTS][node_id] = {
            "text": text,
            "node_id": node_id
        }

    @staticmethod
    def update(node_id, outputs, metadata):
        if outputs and isinstance(outputs, list) and len(outputs) > 0:
            if isinstance(outputs[0], tuple) and len(outputs[0]) > 0:
                conditioning = outputs[0][0]
                metadata[PROMPTS][node_id]["conditioning"] = conditioning
        
class SamplerExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs:
            return
            
        sampling_params = {}
        for key in ["seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"]:
            if key in inputs:
                sampling_params[key] = inputs[key]
                
        metadata[SAMPLING][node_id] = {
            "parameters": sampling_params,
            "node_id": node_id,
            IS_SAMPLER: True  # Add sampler flag
        }

        # Store the conditioning objects directly in metadata for later matching
        pos_conditioning = inputs.get("positive", None)
        neg_conditioning = inputs.get("negative", None)

        # Save conditioning objects in metadata for later matching
        if pos_conditioning is not None or neg_conditioning is not None:
            if node_id not in metadata[PROMPTS]:
                metadata[PROMPTS][node_id] = {"node_id": node_id}
            
            metadata[PROMPTS][node_id]["pos_conditioning"] = pos_conditioning
            metadata[PROMPTS][node_id]["neg_conditioning"] = neg_conditioning
        
        # Extract latent image dimensions if available
        if "latent_image" in inputs and inputs["latent_image"] is not None:
            latent = inputs["latent_image"]
            if isinstance(latent, dict) and "samples" in latent:
                # Extract dimensions from latent tensor
                samples = latent["samples"]
                if hasattr(samples, "shape") and len(samples.shape) >= 3:
                    # Correct shape interpretation: [batch_size, channels, height/8, width/8]
                    # Multiply by 8 to get actual pixel dimensions
                    height = int(samples.shape[2] * 8)
                    width = int(samples.shape[3] * 8)
                    
                    if SIZE not in metadata:
                        metadata[SIZE] = {}
                        
                    metadata[SIZE][node_id] = {
                        "width": width,
                        "height": height,
                        "node_id": node_id
                    }

class KSamplerAdvancedExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs:
            return
            
        sampling_params = {}
        for key in ["noise_seed", "steps", "cfg", "sampler_name", "scheduler", "add_noise"]:
            if key in inputs:
                sampling_params[key] = inputs[key]
                
        metadata[SAMPLING][node_id] = {
            "parameters": sampling_params,
            "node_id": node_id,
            IS_SAMPLER: True  # Add sampler flag
        }
        
        # Store the conditioning objects directly in metadata for later matching
        pos_conditioning = inputs.get("positive", None)
        neg_conditioning = inputs.get("negative", None)

        # Save conditioning objects in metadata for later matching
        if pos_conditioning is not None or neg_conditioning is not None:
            if node_id not in metadata[PROMPTS]:
                metadata[PROMPTS][node_id] = {"node_id": node_id}
            
            metadata[PROMPTS][node_id]["pos_conditioning"] = pos_conditioning
            metadata[PROMPTS][node_id]["neg_conditioning"] = neg_conditioning
        
        # Extract latent image dimensions if available
        if "latent_image" in inputs and inputs["latent_image"] is not None:
            latent = inputs["latent_image"]
            if isinstance(latent, dict) and "samples" in latent:
                # Extract dimensions from latent tensor
                samples = latent["samples"]
                if hasattr(samples, "shape") and len(samples.shape) >= 3:
                    # Correct shape interpretation: [batch_size, channels, height/8, width/8]
                    # Multiply by 8 to get actual pixel dimensions
                    height = int(samples.shape[2] * 8)
                    width = int(samples.shape[3] * 8)
                    
                    if SIZE not in metadata:
                        metadata[SIZE] = {}
                        
                    metadata[SIZE][node_id] = {
                        "width": width,
                        "height": height,
                        "node_id": node_id
                    }

class LoraLoaderExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs or "lora_name" not in inputs:
            return
            
        lora_name = inputs.get("lora_name")
        # Extract base filename without extension from path
        lora_name = os.path.splitext(os.path.basename(lora_name))[0]
        strength_model = round(float(inputs.get("strength_model", 1.0)), 2)
        
        # Use the standardized format with lora_list
        metadata[LORAS][node_id] = {
            "lora_list": [
                {
                    "name": lora_name,
                    "strength": strength_model
                }
            ],
            "node_id": node_id
        }

class ImageSizeExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs:
            return
        
        width = inputs.get("width", 512)
        height = inputs.get("height", 512)
        
        if SIZE not in metadata:
            metadata[SIZE] = {}
            
        metadata[SIZE][node_id] = {
            "width": width,
            "height": height,
            "node_id": node_id
        }

class LoraLoaderManagerExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs:
            return
        
        active_loras = []
        
        # Process lora_stack if available
        if "lora_stack" in inputs:
            lora_stack = inputs.get("lora_stack", [])
            for lora_path, model_strength, clip_strength in lora_stack:
                # Extract lora name from path (following the format in lora_loader.py)
                lora_name = os.path.splitext(os.path.basename(lora_path))[0]
                active_loras.append({
                    "name": lora_name,
                    "strength": model_strength
                })
        
        # Process loras from inputs
        if "loras" in inputs:
            loras_data = inputs.get("loras", [])
            
            # Handle new format: {'loras': {'__value__': [...]}} 
            if isinstance(loras_data, dict) and '__value__' in loras_data:
                loras_list = loras_data['__value__']
            # Handle old format: {'loras': [...]}
            elif isinstance(loras_data, list):
                loras_list = loras_data
            else:
                loras_list = []
                
            # Filter for active loras
            for lora in loras_list:
                if isinstance(lora, dict) and lora.get("active", True) and not lora.get("_isDummy", False):
                    active_loras.append({
                        "name": lora.get("name", ""),
                        "strength": float(lora.get("strength", 1.0))
                    })
        
        if active_loras:
            metadata[LORAS][node_id] = {
                "lora_list": active_loras,
                "node_id": node_id
            }

class FluxGuidanceExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs or "guidance" not in inputs:
            return
            
        guidance_value = inputs.get("guidance")
        
        # Store the guidance value in SAMPLING category
        if node_id not in metadata[SAMPLING]:
            metadata[SAMPLING][node_id] = {"parameters": {}, "node_id": node_id}
            
        metadata[SAMPLING][node_id]["parameters"]["guidance"] = guidance_value

class UNETLoaderExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs or "unet_name" not in inputs:
            return
            
        model_name = inputs.get("unet_name")
        if model_name:
            metadata[MODELS][node_id] = {
                "name": model_name,
                "type": "checkpoint",
                "node_id": node_id
            }

class VAEDecodeExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        pass
        
    @staticmethod
    def update(node_id, outputs, metadata):
        # Ensure IMAGES category exists
        if IMAGES not in metadata:
            metadata[IMAGES] = {}
            
        # Save image data under node ID index to be captured by caching mechanism
        metadata[IMAGES][node_id] = {
            "node_id": node_id,
            "image": outputs
        }
        
        # Only set first_decode if it hasn't been recorded yet
        if "first_decode" not in metadata[IMAGES]:
            metadata[IMAGES]["first_decode"] = metadata[IMAGES][node_id]

class KSamplerSelectExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs or "sampler_name" not in inputs:
            return
            
        sampling_params = {}
        if "sampler_name" in inputs:
            sampling_params["sampler_name"] = inputs["sampler_name"]
                
        metadata[SAMPLING][node_id] = {
            "parameters": sampling_params,
            "node_id": node_id,
            IS_SAMPLER: False  # Mark as non-primary sampler
        }

class BasicSchedulerExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs:
            return
            
        sampling_params = {}
        for key in ["scheduler", "steps", "denoise"]:
            if key in inputs:
                sampling_params[key] = inputs[key]
                
        metadata[SAMPLING][node_id] = {
            "parameters": sampling_params,
            "node_id": node_id,
            IS_SAMPLER: False  # Mark as non-primary sampler
        }

class SamplerCustomAdvancedExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs:
            return
            
        sampling_params = {}

        # Handle noise.seed as seed
        if "noise" in inputs and inputs["noise"] is not None and hasattr(inputs["noise"], "seed"):
            noise = inputs["noise"]
            sampling_params["seed"] = noise.seed
                
        metadata[SAMPLING][node_id] = {
            "parameters": sampling_params,
            "node_id": node_id,
            IS_SAMPLER: True  # Add sampler flag
        }
        
        # Extract latent image dimensions if available
        if "latent_image" in inputs and inputs["latent_image"] is not None:
            latent = inputs["latent_image"]
            if isinstance(latent, dict) and "samples" in latent:
                # Extract dimensions from latent tensor
                samples = latent["samples"]
                if hasattr(samples, "shape") and len(samples.shape) >= 3:
                    # Correct shape interpretation: [batch_size, channels, height/8, width/8]
                    # Multiply by 8 to get actual pixel dimensions
                    height = int(samples.shape[2] * 8)
                    width = int(samples.shape[3] * 8)
                    
                    if SIZE not in metadata:
                        metadata[SIZE] = {}
                        
                    metadata[SIZE][node_id] = {
                        "width": width,
                        "height": height,
                        "node_id": node_id
                    }

import json

class CLIPTextEncodeFluxExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs or "clip_l" not in inputs or "t5xxl" not in inputs:
            return
            
        clip_l_text = inputs.get("clip_l", "")
        t5xxl_text = inputs.get("t5xxl", "")
        
        # If both are empty, use empty string
        if not clip_l_text and not t5xxl_text:
            combined_text = ""
        # If one is empty, use the non-empty one
        elif not clip_l_text:
            combined_text = t5xxl_text
        elif not t5xxl_text:
            combined_text = clip_l_text
        # If both have content, use JSON format
        else:
            combined_text = json.dumps({
                "T5": t5xxl_text,
                "CLIP-L": clip_l_text
            })
        
        metadata[PROMPTS][node_id] = {
            "text": combined_text,
            "node_id": node_id
        }
        
        # Extract guidance value if available
        if "guidance" in inputs:
            guidance_value = inputs.get("guidance")
            
            # Store the guidance value in SAMPLING category
            if SAMPLING not in metadata:
                metadata[SAMPLING] = {}
                
            if node_id not in metadata[SAMPLING]:
                metadata[SAMPLING][node_id] = {"parameters": {}, "node_id": node_id}
                
            metadata[SAMPLING][node_id]["parameters"]["guidance"] = guidance_value

    @staticmethod
    def update(node_id, outputs, metadata):
        if outputs and isinstance(outputs, list) and len(outputs) > 0:
            if isinstance(outputs[0], tuple) and len(outputs[0]) > 0:
                conditioning = outputs[0][0]
                metadata[PROMPTS][node_id]["conditioning"] = conditioning

class CFGGuiderExtractor(NodeMetadataExtractor):
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        if not inputs or "cfg" not in inputs:
            return
            
        cfg_value = inputs.get("cfg")
        
        # Store the cfg value in SAMPLING category
        if SAMPLING not in metadata:
            metadata[SAMPLING] = {}
            
        if node_id not in metadata[SAMPLING]:
            metadata[SAMPLING][node_id] = {"parameters": {}, "node_id": node_id}
            
        metadata[SAMPLING][node_id]["parameters"]["cfg"] = cfg_value

# Registry of node-specific extractors
# Keys are node class names
NODE_EXTRACTORS = {
    # Sampling
    "KSampler": SamplerExtractor,
    "KSamplerAdvanced": KSamplerAdvancedExtractor,
    "SamplerCustomAdvanced": SamplerCustomAdvancedExtractor,  # Updated to use dedicated extractor
    # Sampling Selectors
    "KSamplerSelect": KSamplerSelectExtractor,  # Add KSamplerSelect
    "BasicScheduler": BasicSchedulerExtractor,  # Add BasicScheduler
    # Loaders
    "CheckpointLoaderSimple": CheckpointLoaderExtractor,
    "comfyLoader": CheckpointLoaderExtractor,  # eeasy comfyLoader
    "UNETLoader": UNETLoaderExtractor,          # Updated to use dedicated extractor
    "UnetLoaderGGUF": UNETLoaderExtractor,  # Updated to use dedicated extractor
    "LoraLoader": LoraLoaderExtractor,
    "LoraManagerLoader": LoraLoaderManagerExtractor,
    # Conditioning
    "CLIPTextEncode": CLIPTextEncodeExtractor,
    "CLIPTextEncodeFlux": CLIPTextEncodeFluxExtractor,  # Add CLIPTextEncodeFlux
    "WAS_Text_to_Conditioning": CLIPTextEncodeExtractor,
    "AdvancedCLIPTextEncode": CLIPTextEncodeExtractor,  # From https://github.com/BlenderNeko/ComfyUI_ADV_CLIP_emb
    # Latent
    "EmptyLatentImage": ImageSizeExtractor,
    # Flux
    "FluxGuidance": FluxGuidanceExtractor,      # Add FluxGuidance
    "CFGGuider": CFGGuiderExtractor,            # Add CFGGuider
    # Image
    "VAEDecode": VAEDecodeExtractor,  # Added VAEDecode extractor
    # Add other nodes as needed
}
