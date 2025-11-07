import json
import re
from .utils import FlexibleOptionalInputType, any_type
import logging

logger = logging.getLogger(__name__)


class TriggerWordToggle:
    NAME = "TriggerWord Toggle (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = "Toggle trigger words on/off"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "group_mode": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "When enabled, treats each group of trigger words as a single toggleable unit."
                }),
                "default_active": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Sets the default initial state (active or inactive) when trigger words are added."
                }),
            },
            "optional": FlexibleOptionalInputType(any_type),
            "hidden": {
                "id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("filtered_trigger_words",)
    FUNCTION = "process_trigger_words"

    def _get_toggle_data(self, kwargs, key='toggle_trigger_words'):
        """Helper to extract data from either old or new kwargs format"""
        if key not in kwargs:
            return None
            
        data = kwargs[key]
        # Handle new format: {'key': {'__value__': ...}}
        if isinstance(data, dict) and '__value__' in data:
            return data['__value__']
        # Handle old format: {'key': ...}
        else:
            return data

    def process_trigger_words(self, id, group_mode, default_active, **kwargs):
        # Handle both old and new formats for trigger_words
        trigger_words_data = self._get_toggle_data(kwargs, 'orinalMessage')
        trigger_words = trigger_words_data if isinstance(trigger_words_data, str) else ""
        
        filtered_triggers = trigger_words
        
        # Get toggle data with support for both formats
        trigger_data = self._get_toggle_data(kwargs, 'toggle_trigger_words')
        if trigger_data:
            try:
                # Convert to list if it's a JSON string
                if isinstance(trigger_data, str):
                    trigger_data = json.loads(trigger_data)
                
                # Create dictionaries to track active state of words or groups
                # Also track strength values for each trigger word
                active_state = {}
                strength_map = {}
                
                for item in trigger_data:
                    text = item['text']
                    active = item.get('active', False)
                    # Extract strength if it's in the format "(word:strength)"
                    strength_match = re.match(r'\((.+):([\d.]+)\)', text)
                    if strength_match:
                        original_word = strength_match.group(1)
                        strength = float(strength_match.group(2))
                        active_state[original_word] = active
                        strength_map[original_word] = strength
                    else:
                        active_state[text] = active
                
                if group_mode:
                    # Split by two or more consecutive commas to get groups
                    groups = re.split(r',{2,}', trigger_words)
                    # Remove leading/trailing whitespace from each group
                    groups = [group.strip() for group in groups]
                    
                    # Process groups: keep those not in toggle_trigger_words or those that are active
                    filtered_groups = []
                    for group in groups:
                        # Check if this group contains any words that are in the active_state
                        group_words = [word.strip() for word in group.split(',')]
                        active_group_words = []
                        
                        for word in group_words:
                            # Remove any existing strength formatting for comparison
                            word_comparison = re.sub(r'\((.+):([\d.]+)\)', r'\1', word).strip()
                            
                            if word_comparison not in active_state or active_state[word_comparison]:
                                # If this word has a strength value, use that instead of the original
                                if word_comparison in strength_map:
                                    active_group_words.append(f"({word_comparison}:{strength_map[word_comparison]:.2f})")
                                else:
                                    # Preserve existing strength formatting if the word was previously modified
                                    # Check if the original word had strength formatting
                                    strength_match = re.match(r'\((.+):([\d.]+)\)', word)
                                    if strength_match:
                                        active_group_words.append(word)
                                    else:
                                        active_group_words.append(word)
                        
                        if active_group_words:
                            filtered_groups.append(', '.join(active_group_words))
                    
                    if filtered_groups:
                        filtered_triggers = ', '.join(filtered_groups)
                    else:
                        filtered_triggers = ""
                else:
                    # Normal mode: split by commas and treat each word as a separate tag
                    original_words = [word.strip() for word in trigger_words.split(',')]
                    # Filter out empty strings
                    original_words = [word for word in original_words if word]
                    
                    filtered_words = []
                    for word in original_words:
                        # Remove any existing strength formatting for comparison
                        word_comparison = re.sub(r'\((.+):([\d.]+)\)', r'\1', word).strip()
                        
                        if word_comparison not in active_state or active_state[word_comparison]:
                            # If this word has a strength value, use that instead of the original
                            if word_comparison in strength_map:
                                filtered_words.append(f"({word_comparison}:{strength_map[word_comparison]:.2f})")
                            else:
                                # Preserve existing strength formatting if the word was previously modified
                                # Check if the original word had strength formatting
                                strength_match = re.match(r'\((.+):([\d.]+)\)', word)
                                if strength_match:
                                    filtered_words.append(word)
                                else:
                                    filtered_words.append(word)
                    
                    if filtered_words:
                        filtered_triggers = ', '.join(filtered_words)
                    else:
                        filtered_triggers = ""
                    
            except Exception as e:
                logger.error(f"Error processing trigger words: {e}")
            
        return (filtered_triggers,)