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
                "allow_strength_adjustment": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Enable mouse wheel adjustment of each trigger word's strength."
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

    def process_trigger_words(
        self,
        id,
        group_mode,
        default_active,
        allow_strength_adjustment=False,
        **kwargs,
    ):
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

                if isinstance(trigger_data, list):
                    if group_mode:
                        if allow_strength_adjustment:
                            parsed_items = [
                                self._parse_trigger_item(item, allow_strength_adjustment)
                                for item in trigger_data
                            ]
                            filtered_groups = [
                                self._format_word_output(
                                    item["text"],
                                    item["strength"],
                                    allow_strength_adjustment,
                                )
                                for item in parsed_items
                                if item["text"] and item["active"]
                            ]
                        else:
                            filtered_groups = [
                                (item.get('text') or "").strip()
                                for item in trigger_data
                                if (item.get('text') or "").strip() and item.get('active', False)
                            ]
                        filtered_triggers = ', '.join(filtered_groups) if filtered_groups else ""
                    else:
                        parsed_items = [
                            self._parse_trigger_item(item, allow_strength_adjustment)
                            for item in trigger_data
                        ]
                        filtered_words = [
                            self._format_word_output(
                                item["text"],
                                item["strength"],
                                allow_strength_adjustment,
                            )
                            for item in parsed_items
                            if item["text"] and item["active"]
                        ]
                        filtered_triggers = ', '.join(filtered_words) if filtered_words else ""
                else:
                    # Fallback to original message parsing if data is not in the expected list format
                    if group_mode:
                        groups = re.split(r',{2,}', trigger_words)
                        groups = [group.strip() for group in groups if group.strip()]
                        filtered_triggers = ', '.join(groups)
                    else:
                        words = [word.strip() for word in trigger_words.split(',') if word.strip()]
                        filtered_triggers = ', '.join(words)

            except Exception as e:
                logger.error(f"Error processing trigger words: {e}")
            
        return (filtered_triggers,)

    def _parse_trigger_item(self, item, allow_strength_adjustment):
        text = (item.get('text') or "").strip()
        active = bool(item.get('active', False))
        strength = item.get('strength')

        strength_match = re.match(r'^\((.+):([\d.]+)\)$', text)
        if strength_match:
            text = strength_match.group(1).strip()
            if strength is None:
                try:
                    strength = float(strength_match.group(2))
                except ValueError:
                    strength = None

        return {
            "text": text,
            "active": active,
            "strength": strength if allow_strength_adjustment else None,
        }

    def _format_word_output(self, base_word, strength, allow_strength_adjustment):
        if allow_strength_adjustment and strength is not None:
            return f"({base_word}:{strength:.2f})"
        return base_word
