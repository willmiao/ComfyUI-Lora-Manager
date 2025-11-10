
import hashlib
import logging
import os

from .constants import (
    CARD_PREVIEW_WIDTH,
    DEFAULT_HASH_CHUNK_SIZE_MB,
    PREVIEW_EXTENSIONS,
)
from .exif_utils import ExifUtils
from ..services.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


def _get_hash_chunk_size_bytes() -> int:
    """Return the chunk size used for hashing, in bytes."""

    settings_manager = get_settings_manager()
    chunk_size_mb = settings_manager.get("hash_chunk_size_mb", DEFAULT_HASH_CHUNK_SIZE_MB)
    try:
        chunk_size_value = float(chunk_size_mb)
    except (TypeError, ValueError):
        chunk_size_value = float(DEFAULT_HASH_CHUNK_SIZE_MB)

    if chunk_size_value <= 0:
        chunk_size_value = float(DEFAULT_HASH_CHUNK_SIZE_MB)

    return max(1, int(chunk_size_value * 1024 * 1024))


async def calculate_sha256(file_path: str) -> str:
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    chunk_size = _get_hash_chunk_size_bytes()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(chunk_size), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def find_preview_file(base_name: str, dir_path: str) -> str:
    """Find preview file for given base name in directory"""
    
    temp_extensions = PREVIEW_EXTENSIONS.copy()
    # Add example extension for compatibility
    # https://github.com/willmiao/ComfyUI-Lora-Manager/issues/225
    # The preview image will be optimized to lora-name.webp, so it won't affect other logic
    temp_extensions.append(".example.0.jpeg")
    for ext in temp_extensions:
        full_pattern = os.path.join(dir_path, f"{base_name}{ext}")
        if os.path.exists(full_pattern):
            # Check if this is an image and not already webp
            # TODO: disable the optimization for now, maybe add a config option later
            # if ext.lower().endswith(('.jpg', '.jpeg', '.png')) and not ext.lower().endswith('.webp'):
            #     try:
            #         # Optimize the image to webp format
            #         webp_path = os.path.join(dir_path, f"{base_name}.webp")
                    
            #         # Use ExifUtils to optimize the image
            #         with open(full_pattern, 'rb') as f:
            #             image_data = f.read()
                    
            #         optimized_data, _ = ExifUtils.optimize_image(
            #             image_data=image_data,
            #             target_width=CARD_PREVIEW_WIDTH,
            #             format='webp',
            #             quality=85,
            #             preserve_metadata=False
            #         )
                    
            #         # Save the optimized webp file
            #         with open(webp_path, 'wb') as f:
            #             f.write(optimized_data)
                    
            #         logger.debug(f"Optimized preview image from {full_pattern} to {webp_path}")
            #         return webp_path.replace(os.sep, "/")
            #     except Exception as e:
            #         logger.error(f"Error optimizing preview image {full_pattern}: {e}")
            #         # Fall back to original file if optimization fails
            #         return full_pattern.replace(os.sep, "/")
            
            # Return the original path for webp images or non-image files
            return full_pattern.replace(os.sep, "/")
    
    return ""

def get_preview_extension(preview_path: str) -> str:
    """Get the complete preview extension from a preview file path
    
    Args:
        preview_path: Path to the preview file
        
    Returns:
        str: The complete extension (e.g., '.preview.png', '.png', '.webp')
    """
    preview_path_lower = preview_path.lower()
    
    # Check for compound extensions first (longer matches first)
    for ext in sorted(PREVIEW_EXTENSIONS, key=len, reverse=True):
        if preview_path_lower.endswith(ext.lower()):
            return ext
    
    return os.path.splitext(preview_path)[1]

def normalize_path(path: str) -> str:
    """Normalize file path to use forward slashes"""
    return path.replace(os.sep, "/") if path else path
