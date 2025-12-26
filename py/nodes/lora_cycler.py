"""
LoRA Cycler Node for ComfyUI-Lora-Manager

This node provides LoRA cycling/randomization functionality, allowing users to
automatically select different LoRAs on each workflow execution.

Addresses GitHub Issue #316: https://github.com/willmiao/ComfyUI-Lora-Manager/issues/316
"""

import os
import random
import logging
from typing import List, Dict, Optional, Any

from ..utils.utils import get_lora_info
from ..services.service_registry import ServiceRegistry
from ..config import config
from .utils import extract_lora_name

logger = logging.getLogger(__name__)


# Global counter for increment/decrement modes
# This persists across node executions within the same ComfyUI session
_execution_counters: Dict[str, int] = {}


class LoraCycler:
    """
    A node that cycles or randomizes through available LoRAs.

    This node allows users to automatically select different LoRAs on each
    workflow execution, with options for:
    - fixed: Stay on selected index
    - increment: Move to next LoRA each execution
    - decrement: Move to previous LoRA each execution
    - random: Randomly select a LoRA each execution

    The node outputs the selected LoRA as a LORA_STACK compatible with
    existing LoRA loader nodes, along with the trigger words for the
    selected LoRA only.
    """

    NAME = "Lora Cycler (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = "Cycle or randomize through LoRAs. Connect LORA_STACK to a Lora Loader and trigger_words to a TriggerWord Toggle."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selection_mode": (["fixed", "increment", "decrement", "random"], {
                    "default": "increment",
                    "tooltip": "How to select LoRAs:\n"
                               "• fixed: Always use the LoRA at 'index'\n"
                               "• increment: Move to next LoRA each run (wraps around)\n"
                               "• decrement: Move to previous LoRA each run (wraps around)\n"
                               "• random: Pick a random LoRA each run"
                }),
                "index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 9999,
                    "step": 1,
                    "tooltip": "Starting position in the LoRA list (0 = first LoRA).\n"
                               "Used as the fixed position in 'fixed' mode, or starting point for increment/decrement."
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "tooltip": "Seed for random mode:\n"
                               "• 0 = Different random LoRA each run\n"
                               "• Any other value = Reproducible random selection"
                }),
                "model_strength": ("FLOAT", {
                    "default": 1.0,
                    "min": -10.0,
                    "max": 10.0,
                    "step": 0.01,
                    "tooltip": "Strength of the LoRA effect on the model (UNet). Range: -10 to 10, typical: 0.5 to 1.0"
                }),
                "clip_strength": ("FLOAT", {
                    "default": 1.0,
                    "min": -10.0,
                    "max": 10.0,
                    "step": 0.01,
                    "tooltip": "Strength of the LoRA effect on CLIP (text encoder). Range: -10 to 10, typical: 0.5 to 1.0"
                }),
            },
            "optional": {
                "folder_filter": ("STRING", {
                    "default": "",
                    "tooltip": "Filter LoRAs by folder path. Matches any part of the folder name (case-insensitive).\n\n"
                               "Examples:\n"
                               "• 'character' matches 'characters/', 'my_characters/', 'character_v2/'\n"
                               "• 'styles/anime' matches 'styles/anime/', 'my_styles/anime_v2/'\n"
                               "• Leave empty to include all folders"
                }),
                "base_model_filter": ("STRING", {
                    "default": "",
                    "tooltip": "Filter by base model type. Matches any part of the name (case-insensitive).\n\n"
                               "Examples:\n"
                               "• 'sdxl' matches 'SDXL 1.0', 'SDXL Turbo'\n"
                               "• 'pony' matches 'Pony', 'Pony Diffusion'\n"
                               "• 'illustrious' matches 'Illustrious XL'\n"
                               "• Leave empty to include all base models"
                }),
                "tag_filter": ("STRING", {
                    "default": "",
                    "tooltip": "Filter by LoRA tags (from Civitai metadata). Matches any part of tag names (case-insensitive).\n\n"
                               "Examples:\n"
                               "• 'character' matches tags containing 'character'\n"
                               "• 'style' matches 'style', 'art style', 'clothing style'\n"
                               "• Leave empty to include all tags"
                }),
                "name_filter": ("STRING", {
                    "default": "",
                    "tooltip": "Filter by LoRA filename or model name. Matches any part (case-insensitive).\n\n"
                               "Examples:\n"
                               "• 'anime' matches 'anime_style_v2', 'my_anime_lora'\n"
                               "• 'realistic' matches 'hyper_realistic', 'realistic_skin'\n"
                               "• Leave empty to include all names"
                }),
                "lora_stack": ("LORA_STACK", {
                    "tooltip": "Optional: Connect a LORA_STACK from another node (like Lora Stacker) to select from that specific list instead of scanning your LoRA folders."
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("LORA_STACK", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("LORA_STACK", "trigger_words", "selected_lora", "total_count", "current_index")
    OUTPUT_TOOLTIPS = (
        "Connect to 'lora_stack' input of a Lora Loader node",
        "Connect to a TriggerWord Toggle node to see the selected LoRA's trigger words",
        "The selected LoRA in <lora:name:strength> format (for display/debugging)",
        "Total number of LoRAs matching your filters",
        "Index of the currently selected LoRA (0-based)",
    )
    FUNCTION = "cycle_loras"

    @classmethod
    def IS_CHANGED(cls, selection_mode, index, seed, model_strength, clip_strength,
                   folder_filter="", base_model_filter="", tag_filter="", name_filter="",
                   lora_stack=None, unique_id=None):
        """
        This method controls when ComfyUI re-executes the node.

        For cycling to work properly, we need to return different values
        on each execution for increment/decrement/random modes.
        """
        if selection_mode == "fixed":
            # Fixed mode: only re-execute if inputs change
            return (index, model_strength, clip_strength, folder_filter,
                    base_model_filter, tag_filter, name_filter)

        elif selection_mode == "random":
            if seed == 0:
                # Seed 0 means "different each time"
                return float("nan")  # NaN is never equal to itself
            else:
                # Specific seed: consistent behavior
                return seed

        else:  # increment or decrement
            # Get the current counter for this node instance
            node_key = str(unique_id) if unique_id else "default"
            counter = _execution_counters.get(node_key, 0)
            return counter

    def _get_available_loras(self, folder_filter: str, base_model_filter: str,
                              tag_filter: str, name_filter: str,
                              lora_stack: Optional[List] = None) -> List[Dict[str, Any]]:
        """Get list of available LoRAs based on filters or input stack."""

        # If lora_stack is provided, convert it to our format
        if lora_stack:
            loras = []
            for lora_path, model_str, clip_str in lora_stack:
                lora_name = extract_lora_name(lora_path)
                _, trigger_words = get_lora_info(lora_name)
                loras.append({
                    'file_name': lora_name,
                    'file_path': lora_path,
                    'trigger_words': trigger_words,
                    'model_strength': model_str,
                    'clip_strength': clip_str,
                })
            return loras

        # Otherwise, get LoRAs from scanner cache
        try:
            import asyncio

            async def _get_loras_async():
                scanner = await ServiceRegistry.get_lora_scanner()
                cache = await scanner.get_cached_data()
                return cache.raw_data

            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures

                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_get_loras_async())
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    raw_data = future.result()
            except RuntimeError:
                raw_data = asyncio.run(_get_loras_async())

        except Exception as e:
            logger.error(f"Error getting LoRA cache: {e}")
            return []

        # Apply filters
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

            # Get trigger words
            civitai = item.get('civitai', {})
            trigger_words = civitai.get('trainedWords', []) if civitai else []

            # Get relative path for loading
            file_path = item.get('file_path', '')
            relative_path = ''
            for root in config.loras_roots:
                root_normalized = root.replace(os.sep, '/')
                if file_path.startswith(root_normalized):
                    relative_path = os.path.relpath(file_path, root_normalized).replace(os.sep, '/')
                    break

            if not relative_path:
                # Fallback: use file_name + .safetensors
                relative_path = item.get('file_name', '') + '.safetensors'

            filtered_loras.append({
                'file_name': item.get('file_name', ''),
                'model_name': item.get('model_name', ''),
                'file_path': relative_path,
                'trigger_words': trigger_words,
                'folder': item.get('folder', ''),
                'base_model': item.get('base_model', ''),
            })

        # Sort by file_name for consistent ordering
        filtered_loras.sort(key=lambda x: x.get('file_name', '').lower())

        return filtered_loras

    def cycle_loras(self, selection_mode: str, index: int, seed: int,
                    model_strength: float, clip_strength: float,
                    folder_filter: str = "", base_model_filter: str = "",
                    tag_filter: str = "", name_filter: str = "",
                    lora_stack: Optional[List] = None, unique_id: str = None):
        """
        Main execution method for the LoRA cycler.

        Selects a single LoRA from the available list based on the selection mode
        and returns it as a LORA_STACK with the appropriate trigger words.
        """

        # Get available LoRAs
        available_loras = self._get_available_loras(
            folder_filter, base_model_filter, tag_filter, name_filter, lora_stack
        )

        total_count = len(available_loras)

        # Handle empty list
        if total_count == 0:
            logger.warning("No LoRAs found matching the specified filters")
            return ([], "", "", 0, 0)

        # Determine the selection index based on mode
        node_key = str(unique_id) if unique_id else "default"

        if selection_mode == "fixed":
            # Use the provided index directly
            selected_index = index % total_count

        elif selection_mode == "random":
            if seed == 0:
                # Use random selection
                selected_index = random.randint(0, total_count - 1)
            else:
                # Use seeded random for reproducibility
                rng = random.Random(seed)
                selected_index = rng.randint(0, total_count - 1)

        elif selection_mode == "increment":
            # Get current counter and increment
            current_counter = _execution_counters.get(node_key, index)
            selected_index = current_counter % total_count
            _execution_counters[node_key] = (current_counter + 1) % total_count

        elif selection_mode == "decrement":
            # Get current counter and decrement
            current_counter = _execution_counters.get(node_key, index)
            if current_counter <= 0:
                current_counter = total_count - 1
            else:
                current_counter -= 1
            selected_index = current_counter % total_count
            _execution_counters[node_key] = current_counter

        else:
            selected_index = 0

        # Get the selected LoRA
        selected_lora = available_loras[selected_index]
        lora_path = selected_lora.get('file_path', '')
        lora_name = selected_lora.get('file_name', '') or selected_lora.get('model_name', '')
        trigger_words = selected_lora.get('trigger_words', [])

        # Format trigger words with ',, ' separator for group mode compatibility
        trigger_words_text = ",, ".join(trigger_words) if trigger_words else ""

        # Create LORA_STACK output (list of tuples)
        output_stack = [(lora_path.replace('/', os.sep), model_strength, clip_strength)]

        # Format selected lora info
        if abs(model_strength - clip_strength) > 0.001:
            selected_lora_text = f"<lora:{lora_name}:{model_strength}:{clip_strength}>"
        else:
            selected_lora_text = f"<lora:{lora_name}:{model_strength}>"

        logger.info(f"LoraCycler selected: {lora_name} (index {selected_index}/{total_count-1})")

        return (output_stack, trigger_words_text, selected_lora_text, total_count, selected_index)
