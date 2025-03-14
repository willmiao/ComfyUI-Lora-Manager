import json
import re
from server import PromptServer # type: ignore
from .utils import FlexibleOptionalInputType, any_type

class TriggerWordToggle:
    NAME = "TriggerWord Toggle (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = "Toggle trigger words on/off"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "group_mode": ("BOOLEAN", {"default": True}),
            },
            "optional": FlexibleOptionalInputType(any_type),
            "hidden": {
                "id": "UNIQUE_ID",  # 会被 ComfyUI 自动替换为唯一ID
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("filtered_trigger_words",)
    FUNCTION = "process_trigger_words"

    def process_trigger_words(self, id, group_mode, **kwargs):
        trigger_words = kwargs.get("trigger_words", "")
        # Send trigger words to frontend
        PromptServer.instance.send_sync("trigger_word_update", {
            "id": id,
            "message": trigger_words
        })
        
        filtered_triggers = trigger_words
        
        if 'toggle_trigger_words' in kwargs:
            try:
                # Get trigger word toggle data
                trigger_data = kwargs['toggle_trigger_words']
                
                # Convert to list if it's a JSON string
                if isinstance(trigger_data, str):
                    trigger_data = json.loads(trigger_data)
                
                # Create dictionaries to track active state of words or groups
                active_state = {item['text']: item.get('active', False) for item in trigger_data}
                
                if group_mode:
                    # Split by two or more consecutive commas to get groups
                    groups = re.split(r',{2,}', trigger_words)
                    # Remove leading/trailing whitespace from each group
                    groups = [group.strip() for group in groups]
                    
                    # Filter groups: keep those not in toggle_trigger_words or those that are active
                    filtered_groups = [group for group in groups if group not in active_state or active_state[group]]
                    
                    if filtered_groups:
                        filtered_triggers = ', '.join(filtered_groups)
                    else:
                        filtered_triggers = ""
                else:
                    # Original behavior for individual words mode
                    original_words = [word.strip() for word in trigger_words.split(',')]
                    # Filter out empty strings
                    original_words = [word for word in original_words if word]
                    filtered_words = [word for word in original_words if word not in active_state or active_state[word]]
                    
                    if filtered_words:
                        filtered_triggers = ', '.join(filtered_words)
                    else:
                        filtered_triggers = ""
                    
            except Exception as e:
                print(f"Error processing trigger words: {e}")
            
        return (filtered_triggers,)