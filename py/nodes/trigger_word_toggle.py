import json
import logging
import re
from collections import defaultdict, deque
from collections.abc import Iterator
from typing import Any

from .utils import FlexibleOptionalInputType, any_type

logger = logging.getLogger(__name__)


class TriggerWordToggleLM:
    NAME = "TriggerWord Toggle (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = "Toggle trigger words on/off"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "group_mode": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "When enabled, treats each group of trigger words as a single toggleable unit.",
                    },
                ),
                "default_active": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "Sets the default initial state (active or inactive) when trigger words are added.",
                    },
                ),
                "allow_strength_adjustment": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Enable mouse wheel adjustment of each trigger word's strength.",
                    },
                ),
            },
            "optional": FlexibleOptionalInputType(any_type),
            "hidden": {
                "id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("filtered_trigger_words",)
    FUNCTION = "process_trigger_words"

    def _get_toggle_data(self, kwargs, key="toggle_trigger_words"):
        """Helper to extract data from either old or new kwargs format"""
        if key not in kwargs:
            return None

        data = kwargs[key]
        # Handle new format: {'key': {'__value__': ...}}
        if isinstance(data, dict) and "__value__" in data:
            return data["__value__"]
        # Handle old format: {'key': ...}
        else:
            return data

    def _normalize_trigger_words(self, trigger_words):
        """Normalize trigger words by splitting by both single and double commas, stripping whitespace, and filtering empty strings"""
        if not trigger_words or not isinstance(trigger_words, str):
            return set()
        
        # Split by double commas first to preserve groups, then by single commas
        groups = re.split(r",{2,}", trigger_words)
        words = []
        for group in groups:
            # Split each group by single comma
            group_words = [word.strip() for word in group.split(",")]
            words.extend(group_words)
        
        # Filter out empty strings and return as set
        return set(word for word in words if word)

    def _split_individual_triggers(self, text: str) -> Iterator[str]:
        # Match the widget's comma handling, including weighted phrases.
        depth = 0
        start = 0
        for index, char in enumerate(text):
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                word = text[start:index].strip()
                if word:
                    yield word
                start = index + 1
        word = text[start:].strip()
        if word:
            yield word

    def _resolve_individual_triggers(
        self,
        runtime_words: str,
        saved_items: list[dict[str, Any]],
        default_active: bool,
        allow_strength_adjustment: bool,
    ) -> str:
        states: defaultdict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for item in saved_items:
            parsed = self._parse_trigger_item(item, allow_strength_adjustment)
            states[parsed["text"]].append(parsed)

        filtered = []
        for word in self._split_individual_triggers(runtime_words):
            parsed = self._parse_trigger_item(
                {"text": word, "active": default_active}, allow_strength_adjustment
            )
            saved = states[parsed["text"]]
            if saved:
                parsed = saved.popleft()
            if parsed["active"]:
                filtered.append(
                    self._format_word_output(
                        parsed["text"], parsed["strength"], allow_strength_adjustment
                    )
                )
        return ", ".join(filtered)

    def _group_has_child_items(self, item):
        return isinstance(item, dict) and isinstance(item.get("items"), list)

    def process_trigger_words(
        self,
        id,
        group_mode,
        default_active,
        allow_strength_adjustment=False,
        **kwargs,
    ):
        # Handle both old and new formats for trigger_words
        trigger_words_data = self._get_toggle_data(kwargs, "orinalMessage")
        trigger_words = (
            trigger_words_data if isinstance(trigger_words_data, str) else ""
        )

        filtered_triggers = trigger_words

        # Check if trigger_words is provided and different from orinalMessage
        trigger_words_override = self._get_toggle_data(kwargs, "trigger_words")
        if (
            group_mode
            and trigger_words_override
            and isinstance(trigger_words_override, str)
            and self._normalize_trigger_words(trigger_words_override) != self._normalize_trigger_words(trigger_words)
        ):
            filtered_triggers = trigger_words_override
            return (filtered_triggers,)

        # Get toggle data with support for both formats
        trigger_data = self._get_toggle_data(kwargs, "toggle_trigger_words")
        if not group_mode and isinstance(trigger_words_override, str):
            try:
                if isinstance(trigger_data, str):
                    trigger_data = json.loads(trigger_data)
                saved_items = trigger_data if isinstance(trigger_data, list) else []
                return (
                    self._resolve_individual_triggers(
                        trigger_words_override,
                        saved_items,
                        default_active,
                        allow_strength_adjustment,
                    ),
                )
            except (AttributeError, TypeError, ValueError):
                logger.exception("Error processing individual trigger words")

        if trigger_data:
            try:
                # Convert to list if it's a JSON string
                if isinstance(trigger_data, str):
                    trigger_data = json.loads(trigger_data)

                if isinstance(trigger_data, list):
                    if group_mode:
                        if any(self._group_has_child_items(item) for item in trigger_data):
                            filtered_groups = self._process_group_items(
                                trigger_data, allow_strength_adjustment
                            )
                        elif allow_strength_adjustment:
                            parsed_items = [
                                self._parse_trigger_item(
                                    item, allow_strength_adjustment
                                )
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
                                (item.get("text") or "").strip()
                                for item in trigger_data
                                if (item.get("text") or "").strip()
                                and item.get("active", False)
                            ]
                        filtered_triggers = (
                            ", ".join(filtered_groups) if filtered_groups else ""
                        )
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
                        filtered_triggers = (
                            ", ".join(filtered_words) if filtered_words else ""
                        )
                else:
                    # Fallback to original message parsing if data is not in the expected list format
                    if group_mode:
                        groups = re.split(r",{2,}", trigger_words)
                        groups = [group.strip() for group in groups if group.strip()]
                        filtered_triggers = ", ".join(groups)
                    else:
                        words = [
                            word.strip()
                            for word in trigger_words.split(",")
                            if word.strip()
                        ]
                        filtered_triggers = ", ".join(words)

            except Exception as e:
                logger.error(f"Error processing trigger words: {e}")

        return (filtered_triggers,)

    def _process_group_items(self, trigger_data, allow_strength_adjustment):
        filtered_groups = []

        for item in trigger_data:
            group = self._parse_trigger_item(item, allow_strength_adjustment)
            if not group["text"] or not group["active"]:
                continue

            raw_items = item.get("items") if isinstance(item, dict) else None
            if isinstance(raw_items, list):
                active_items = []
                for raw_item in raw_items:
                    child = self._parse_trigger_item(
                        raw_item, allow_strength_adjustment=False
                    )
                    if child["text"] and child["active"]:
                        active_items.append(child["text"])

                if not active_items:
                    continue

                group_text = ", ".join(active_items)
            else:
                group_text = group["text"]

            filtered_groups.append(
                self._format_word_output(
                    group_text,
                    group["strength"],
                    allow_strength_adjustment,
                )
            )

        return filtered_groups

    def _parse_trigger_item(self, item, allow_strength_adjustment):
        text = (item.get("text") or "").strip()
        active = bool(item.get("active", False))
        strength = item.get("strength")

        strength_match = re.match(r"^\((.+):([\d.]+)\)$", text)
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
