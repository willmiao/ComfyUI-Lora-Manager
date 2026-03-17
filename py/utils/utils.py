from difflib import SequenceMatcher
import os
import re
from typing import Dict
from ..services.service_registry import ServiceRegistry
from ..config import config
from ..services.settings_manager import get_settings_manager
import asyncio


def get_lora_info(lora_name):
    """Get the lora path and trigger words from cache"""

    async def _get_lora_info_async():
        scanner = await ServiceRegistry.get_lora_scanner()
        cache = await scanner.get_cached_data()

        for item in cache.raw_data:
            if item.get("file_name") == lora_name:
                file_path = item.get("file_path")
                if file_path:
                    # Check all lora roots including extra paths
                    all_roots = list(config.loras_roots or []) + list(
                        config.extra_loras_roots or []
                    )
                    for root in all_roots:
                        root = root.replace(os.sep, "/")
                        if file_path.startswith(root):
                            relative_path = os.path.relpath(file_path, root).replace(
                                os.sep, "/"
                            )
                            # Get trigger words from civitai metadata
                            civitai = item.get("civitai", {})
                            trigger_words = (
                                civitai.get("trainedWords", []) if civitai else []
                            )
                            return relative_path, trigger_words
                    # If not found in any root, return path with trigger words from cache
                    civitai = item.get("civitai", {})
                    trigger_words = civitai.get("trainedWords", []) if civitai else []
                    return file_path, trigger_words
        return lora_name, []

    try:
        # Check if we're already in an event loop
        loop = asyncio.get_running_loop()
        # If we're in a running loop, we need to use a different approach
        # Create a new thread to run the async code
        import concurrent.futures

        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(_get_lora_info_async())
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            return future.result()

    except RuntimeError:
        # No event loop is running, we can use asyncio.run()
        return asyncio.run(_get_lora_info_async())


def get_lora_info_absolute(lora_name):
    """Get the absolute lora path and trigger words from cache

    Returns:
        tuple: (absolute_path, trigger_words) where absolute_path is the full
               file system path to the LoRA file, or original lora_name if not found
    """

    async def _get_lora_info_absolute_async():
        scanner = await ServiceRegistry.get_lora_scanner()
        cache = await scanner.get_cached_data()

        for item in cache.raw_data:
            if item.get("file_name") == lora_name:
                file_path = item.get("file_path")
                if file_path:
                    # Return absolute path directly
                    # Get trigger words from civitai metadata
                    civitai = item.get("civitai", {})
                    trigger_words = civitai.get("trainedWords", []) if civitai else []
                    return file_path, trigger_words
        return lora_name, []

    try:
        # Check if we're already in an event loop
        loop = asyncio.get_running_loop()
        # If we're in a running loop, we need to use a different approach
        # Create a new thread to run the async code
        import concurrent.futures

        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(_get_lora_info_absolute_async())
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            return future.result()

    except RuntimeError:
        # No event loop is running, we can use asyncio.run()
        return asyncio.run(_get_lora_info_absolute_async())


def get_checkpoint_info_absolute(checkpoint_name):
    """Get the absolute checkpoint path and metadata from cache

    Supports ComfyUI-style model names (e.g., "folder/model_name.ext")

    Args:
        checkpoint_name: The model name, can be:
            - ComfyUI format: "folder/model_name.safetensors"
            - Simple name: "model_name"

    Returns:
        tuple: (absolute_path, metadata) where absolute_path is the full
               file system path to the checkpoint file, or original checkpoint_name if not found,
               metadata is the full model metadata dict or None
    """

    async def _get_checkpoint_info_absolute_async():
        from ..services.service_registry import ServiceRegistry

        scanner = await ServiceRegistry.get_checkpoint_scanner()
        cache = await scanner.get_cached_data()

        # Get model roots for matching
        model_roots = scanner.get_model_roots()

        # Normalize the checkpoint name
        normalized_name = checkpoint_name.replace(os.sep, "/")

        for item in cache.raw_data:
            file_path = item.get("file_path", "")
            if not file_path:
                continue

            # Format the stored path as ComfyUI-style name
            formatted_name = _format_model_name_for_comfyui(file_path, model_roots)

            # Match by formatted name
            if formatted_name == normalized_name or formatted_name == checkpoint_name:
                return file_path, item

            # Also try matching by basename only (for backward compatibility)
            file_name = item.get("file_name", "")
            if (
                file_name == checkpoint_name
                or file_name == os.path.splitext(normalized_name)[0]
            ):
                return file_path, item

        return checkpoint_name, None

    try:
        # Check if we're already in an event loop
        loop = asyncio.get_running_loop()
        # If we're in a running loop, we need to use a different approach
        # Create a new thread to run the async code
        import concurrent.futures

        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(
                    _get_checkpoint_info_absolute_async()
                )
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            return future.result()

    except RuntimeError:
        # No event loop is running, we can use asyncio.run()
        return asyncio.run(_get_checkpoint_info_absolute_async())


def _format_model_name_for_comfyui(file_path: str, model_roots: list) -> str:
    """Format file path to ComfyUI-style model name (relative path with extension)

    Example: /path/to/checkpoints/Illustrious/model.safetensors -> Illustrious/model.safetensors

    Args:
        file_path: Absolute path to the model file
        model_roots: List of model root directories

    Returns:
        ComfyUI-style model name with relative path and extension
    """
    # Normalize path separators
    normalized_path = file_path.replace(os.sep, "/")

    # Find the matching root and get relative path
    for root in model_roots:
        normalized_root = root.replace(os.sep, "/")
        # Ensure root ends with / for proper matching
        if not normalized_root.endswith("/"):
            normalized_root += "/"

        if normalized_path.startswith(normalized_root):
            rel_path = normalized_path[len(normalized_root) :]
            return rel_path

    # If no root matches, just return the basename with extension
    return os.path.basename(file_path)


def fuzzy_match(text: str, pattern: str, threshold: float = 0.85) -> bool:
    """
    Check if text matches pattern using fuzzy matching.
    Returns True if similarity ratio is above threshold.
    """
    if not pattern or not text:
        return False

    # Convert both to lowercase for case-insensitive matching
    text = text.lower()
    pattern = pattern.lower()

    # Split pattern into words
    search_words = pattern.split()

    # Check each word
    for word in search_words:
        # First check if word is a substring (faster)
        if word in text:
            continue

        # If not found as substring, try fuzzy matching
        # Check if any part of the text matches this word
        found_match = False
        for text_part in text.split():
            ratio = SequenceMatcher(None, text_part, word).ratio()
            if ratio >= threshold:
                found_match = True
                break

        if not found_match:
            return False

    # All words found either as substrings or fuzzy matches
    return True


def sanitize_folder_name(name: str, replacement: str = "_") -> str:
    """Sanitize a folder name by removing or replacing invalid characters.

    Args:
        name: The original folder name.
        replacement: The character to use when replacing invalid characters.

    Returns:
        A sanitized folder name safe to use across common filesystems.
    """

    if not name:
        return ""

    # Replace invalid characters commonly restricted on Windows and POSIX
    invalid_chars_pattern = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars_pattern, replacement, name)

    # Trim whitespace introduced during sanitization
    sanitized = sanitized.strip()

    # Collapse repeated replacement characters to a single instance
    if replacement:
        sanitized = re.sub(f"{re.escape(replacement)}+", replacement, sanitized)
        # Combine stripping to be idempotent:
        # Right side: strip replacement, space, and dot (Windows restriction)
        # Left side: strip replacement and space (leading dots are allowed)
        sanitized = sanitized.rstrip(" ." + replacement).lstrip(" " + replacement)
    else:
        # If no replacement, just strip spaces and dots from right, spaces from left
        sanitized = sanitized.rstrip(" .").lstrip(" ")

    if not sanitized:
        return "unnamed"

    return sanitized


def calculate_recipe_fingerprint(loras):
    """
    Calculate a unique fingerprint for a recipe based on its LoRAs.

    The fingerprint is created by sorting LoRA hashes, filtering invalid entries,
    normalizing strength values to 2 decimal places, and joining in format:
    hash1:strength1|hash2:strength2|...

    Args:
        loras (list): List of LoRA dictionaries with hash and strength values

    Returns:
        str: The calculated fingerprint
    """
    if not loras:
        return ""

    valid_loras = []
    for lora in loras:
        if lora.get("exclude", False):
            continue

        hash_value = lora.get("hash", "")
        if isinstance(hash_value, str):
            hash_value = hash_value.lower()
        else:
            hash_value = str(hash_value).lower() if hash_value else ""
        if not hash_value and lora.get("modelVersionId"):
            hash_value = str(lora.get("modelVersionId"))

        if not hash_value:
            continue

        # Normalize strength to 2 decimal places (check both strength and weight fields)
        strength_val = lora.get("strength", lora.get("weight", 1.0))
        try:
            strength = round(float(strength_val), 2)
        except (ValueError, TypeError):
            strength = 1.0

        valid_loras.append((hash_value, strength))

    # Sort by hash
    valid_loras.sort()

    # Join in format hash1:strength1|hash2:strength2|...
    fingerprint = "|".join(
        [f"{hash_value}:{strength}" for hash_value, strength in valid_loras]
    )

    return fingerprint


def calculate_relative_path_for_model(
    model_data: Dict, model_type: str = "lora"
) -> str:
    """Calculate relative path for existing model using template from settings

    Args:
        model_data: Model data from scanner cache
        model_type: Type of model ('lora', 'checkpoint', 'embedding')

    Returns:
        Relative path string (empty string for flat structure)
    """
    # Get path template from settings for specific model type
    settings_manager = get_settings_manager()
    path_template = settings_manager.get_download_path_template(model_type)

    # If template is empty, return empty path (flat structure)
    if not path_template:
        return ""

    # Get base model name from model metadata
    civitai_data = model_data.get("civitai", {})

    # For CivitAI models, prefer civitai data only if 'id' exists; for non-CivitAI models, use model_data directly
    if civitai_data and civitai_data.get("id") is not None:
        base_model = model_data.get("base_model", "")
        # Get author from civitai creator data
        creator_info = civitai_data.get("creator") or {}
        author = creator_info.get("username") or "Anonymous"
    else:
        # Fallback to model_data fields for non-CivitAI models
        base_model = model_data.get("base_model", "")
        author = "Anonymous"  # Default for non-CivitAI models

    model_tags = model_data.get("tags", [])

    # Apply mapping if available
    base_model_mappings = settings_manager.get("base_model_path_mappings", {})
    mapped_base_model = base_model_mappings.get(base_model, base_model)

    # Convert all tags to lowercase to avoid case sensitivity issues on Windows
    lowercase_tags = [tag.lower() for tag in model_tags if isinstance(tag, str)]
    first_tag = settings_manager.resolve_priority_tag_for_model(
        lowercase_tags, model_type
    )

    if not first_tag:
        first_tag = "no tags"  # Default if no tags available

    # Format the template with available data
    model_name = sanitize_folder_name(model_data.get("model_name", ""))
    version_name = ""

    if isinstance(civitai_data, dict):
        version_name = sanitize_folder_name(civitai_data.get("name") or "")

    formatted_path = path_template
    formatted_path = formatted_path.replace("{base_model}", mapped_base_model)
    formatted_path = formatted_path.replace("{first_tag}", first_tag)
    formatted_path = formatted_path.replace("{author}", author)
    formatted_path = formatted_path.replace("{model_name}", model_name)
    formatted_path = formatted_path.replace("{version_name}", version_name)

    if model_type == "embedding":
        formatted_path = formatted_path.replace(" ", "_")

    return formatted_path


def remove_empty_dirs(path):
    """Recursively remove empty directories starting from the given path.

    Args:
        path (str): Root directory to start cleaning from

    Returns:
        int: Number of empty directories removed
    """
    removed_count = 0

    if not os.path.isdir(path):
        return removed_count

    # List all files in directory
    files = os.listdir(path)

    # Process all subdirectories first
    for file in files:
        full_path = os.path.join(path, file)
        if os.path.isdir(full_path):
            removed_count += remove_empty_dirs(full_path)

    # Check if directory is now empty (after processing subdirectories)
    if not os.listdir(path):
        try:
            os.rmdir(path)
            removed_count += 1
        except OSError:
            pass

    return removed_count
