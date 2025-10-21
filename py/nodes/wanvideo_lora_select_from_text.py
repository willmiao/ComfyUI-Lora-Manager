import folder_paths # type: ignore
from ..utils.utils import get_lora_info
from .utils import any_type 
import logging

# 初始化日志记录器
logger = logging.getLogger(__name__)

# 定义新节点的类
class WanVideoLoraSelectFromText:
    # 节点在UI中显示的名称
    NAME = "WanVideo Lora Select From Text (LoraManager)"
    # 节点所属的分类
    CATEGORY = "Lora Manager/stackers"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "low_mem_load": ("BOOLEAN", {"default": False, "tooltip": "Load LORA models with less VRAM usage, slower loading. This affects ALL LoRAs, not just the current ones. No effect if merge_loras is False"}),
                "merge_lora": ("BOOLEAN", {"default": True, "tooltip": "Merge LoRAs into the model, otherwise they are loaded on the fly. Always disabled for GGUF and scaled fp8 models. This affects ALL LoRAs, not just the current one"}),
                "lora_syntax": ("STRING", {
                    "multiline": True,
                    "forceInput": True,
                    "tooltip": "Connect a TEXT output for LoRA syntax: <lora:name:strength>"
                }),
            },

            "optional": {
                "prev_lora": ("WANVIDLORA",), 
                "blocks": ("BLOCKS",)        
            }
        }

    RETURN_TYPES = ("WANVIDLORA", "STRING", "STRING")
    RETURN_NAMES = ("lora", "trigger_words", "active_loras")

    FUNCTION = "process_loras_from_syntax"
    
    def process_loras_from_syntax(self, lora_syntax, low_mem_load=False, merge_lora=True, **kwargs):
        text_to_process = lora_syntax

        blocks = kwargs.get('blocks', {})
        selected_blocks = blocks.get("selected_blocks", {})
        layer_filter = blocks.get("layer_filter", "")

        loras_list = []
        all_trigger_words = []
        active_loras = []
        
        prev_lora = kwargs.get('prev_lora', None)
        if prev_lora is not None:
            loras_list.extend(prev_lora)

        if not merge_lora:
            low_mem_load = False

        parts = text_to_process.split('<lora:')
        for part in parts[1:]:
            end_index = part.find('>')
            if end_index == -1:
                continue

            content = part[:end_index]
            lora_parts = content.split(':')
            
            lora_name_raw = ""
            model_strength = 1.0
            clip_strength = 1.0

            if len(lora_parts) == 2:
                lora_name_raw = lora_parts[0].strip()
                try:
                    model_strength = float(lora_parts[1])
                    clip_strength = model_strength
                except (ValueError, IndexError):
                    logger.warning(f"Invalid strength for LoRA '{lora_name_raw}'. Skipping.")
                    continue
            elif len(lora_parts) >= 3:
                lora_name_raw = lora_parts[0].strip()
                try:
                    model_strength = float(lora_parts[1])
                    clip_strength = float(lora_parts[2])
                except (ValueError, IndexError):
                    logger.warning(f"Invalid strengths for LoRA '{lora_name_raw}'. Skipping.")
                    continue
            else:
                continue

            lora_path, trigger_words = get_lora_info(lora_name_raw)

            lora_item = {
                "path": folder_paths.get_full_path("loras", lora_path),
                "strength": model_strength,
                "name": lora_path.split(".")[0],
                "blocks": selected_blocks,
                "layer_filter": layer_filter,
                "low_mem_load": low_mem_load,
                "merge_loras": merge_lora,
            }

            loras_list.append(lora_item)
            active_loras.append((lora_name_raw, model_strength, clip_strength))
            all_trigger_words.extend(trigger_words)

        trigger_words_text = ",, ".join(all_trigger_words) if all_trigger_words else ""
        
        formatted_loras = []
        for name, model_strength, clip_strength in active_loras:
            if abs(model_strength - clip_strength) > 0.001:
                formatted_loras.append(f"<lora:{name}:{str(model_strength).strip()}:{str(clip_strength).strip()}>")
            else:
                formatted_loras.append(f"<lora:{name}:{str(model_strength).strip()}>")
                
        active_loras_text = " ".join(formatted_loras)

        return (loras_list, trigger_words_text, active_loras_text)

NODE_CLASS_MAPPINGS = {
    "WanVideoLoraSelectFromText": WanVideoLoraSelectFromText
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WanVideoLoraSelectFromText": "WanVideo Lora Select From Text (LoraManager)"
}
