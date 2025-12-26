"""
Shared utilities for LoRA Cycler functionality.

This module extracts common logic used by both the LoraCycler node
and the cycler_preview API endpoint to ensure consistent behavior
and reduce code duplication.
"""

import logging
import random
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Shared execution counters for increment/decrement modes
# Key: node unique_id, Value: current counter
_execution_counters: Dict[str, int] = {}


def filter_loras(
    raw_data: List[Dict[str, Any]],
    folder_filter: str = "",
    base_model_filter: str = "",
    tag_filter: str = "",
    name_filter: str = "",
) -> List[Dict[str, Any]]:
    """
    Filter LoRA data based on provided filter criteria.

    Args:
        raw_data: List of LoRA metadata dictionaries from cache
        folder_filter: Filter by folder path (case-insensitive substring match)
        base_model_filter: Filter by base model (case-insensitive substring match)
        tag_filter: Filter by tags (case-insensitive substring match)
        name_filter: Filter by file name or model name (case-insensitive substring match)

    Returns:
        Filtered list of LoRA dictionaries with extracted trigger words
    """
    filtered_loras = []

    folder_filter_lower = folder_filter.lower().strip() if folder_filter else ""
    base_model_filter_lower = base_model_filter.lower().strip() if base_model_filter else ""
    tag_filter_lower = tag_filter.lower().strip() if tag_filter else ""
    name_filter_lower = name_filter.lower().strip() if name_filter else ""

    for item in raw_data:
        # Skip excluded items
        if item.get('exclude', False):
            continue

        # Folder filter
        if folder_filter_lower:
            item_folder = (item.get('folder') or '').lower()
            if folder_filter_lower not in item_folder:
                continue

        # Base model filter
        if base_model_filter_lower:
            item_base = (item.get('base_model') or '').lower()
            if base_model_filter_lower not in item_base:
                continue

        # Tag filter
        if tag_filter_lower:
            item_tags = [t.lower() for t in (item.get('tags') or [])]
            if not any(tag_filter_lower in tag for tag in item_tags):
                continue

        # Name filter
        if name_filter_lower:
            item_name = (item.get('file_name') or '').lower()
            model_name = (item.get('model_name') or '').lower()
            if name_filter_lower not in item_name and name_filter_lower not in model_name:
                continue

        # Get trigger words from civitai data
        civitai = item.get('civitai', {})
        trigger_words = civitai.get('trainedWords', []) if civitai else []

        filtered_loras.append({
            'file_path': item.get('file_path', ''),
            'file_name': item.get('file_name', ''),
            'model_name': item.get('model_name', ''),
            'trigger_words': trigger_words,
            'folder': item.get('folder', ''),
            'base_model': item.get('base_model', ''),
        })

    # Sort for consistent ordering
    filtered_loras.sort(key=lambda x: (x.get('file_name') or '').lower())

    return filtered_loras


def select_lora_index(
    selection_mode: str,
    index: int,
    seed: int,
    total_count: int,
    node_key: str,
    update_counter: bool = True,
) -> int:
    """
    Determine which LoRA index to select based on mode.

    Args:
        selection_mode: One of "fixed", "increment", "decrement", "random"
        index: Starting index (used for fixed mode and as initial counter)
        seed: Random seed (0 = different each time, non-zero = reproducible)
        total_count: Total number of available LoRAs
        node_key: Unique identifier for this node instance
        update_counter: Whether to update the counter (True for execution, False for preview)

    Returns:
        Selected index (0-based)
    """
    if total_count == 0:
        return 0

    if selection_mode == "fixed":
        return index % total_count

    elif selection_mode == "random":
        if seed == 0:
            return random.randint(0, total_count - 1)
        else:
            rng = random.Random(seed)
            return rng.randint(0, total_count - 1)

    elif selection_mode == "increment":
        current_counter = _execution_counters.get(node_key, index)
        selected_index = current_counter % total_count
        if update_counter:
            _execution_counters[node_key] = (current_counter + 1) % total_count
        return selected_index

    elif selection_mode == "decrement":
        current_counter = _execution_counters.get(node_key, index)
        if current_counter <= 0:
            current_counter = total_count - 1
        else:
            current_counter -= 1
        selected_index = current_counter % total_count
        if update_counter:
            _execution_counters[node_key] = current_counter
        return selected_index

    return 0


def format_trigger_words(trigger_words: List[str], first_only: bool = False) -> str:
    """
    Format trigger words for output.

    Args:
        trigger_words: List of trigger word strings
        first_only: If True, only use the first trigger word

    Returns:
        Formatted trigger words string with ',, ' separator
    """
    if not trigger_words:
        return ""

    if first_only:
        return trigger_words[0]

    return ",, ".join(trigger_words)


def get_execution_counters() -> Dict[str, int]:
    """Get reference to execution counters dict (for API access)."""
    return _execution_counters


def reset_counter(node_key: str) -> None:
    """Reset the counter for a specific node."""
    if node_key in _execution_counters:
        del _execution_counters[node_key]
