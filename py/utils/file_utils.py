
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
    """Find preview file for given base name in directory.

    Performs an exact-case check first (fast path), then falls back to a
    case-insensitive scan so that files like ``model.WEBP`` or ``model.Png``
    are discovered on case-sensitive filesystems.
    """

    temp_extensions = PREVIEW_EXTENSIONS.copy()
    # Add example extension for compatibility
    # https://github.com/willmiao/ComfyUI-Lora-Manager/issues/225
    # The preview image will be optimized to lora-name.webp, so it won't affect other logic
    temp_extensions.append(".example.0.jpeg")

    # Fast path: exact-case match
    for ext in temp_extensions:
        full_pattern = os.path.join(dir_path, f"{base_name}{ext}")
        if os.path.exists(full_pattern):
            return full_pattern.replace(os.sep, "/")

    # Slow path: case-insensitive match for systems with mixed-case extensions
    # (e.g. .WEBP, .Png, .JPG placed manually or by external tools)
    try:
        dir_entries = os.listdir(dir_path)
    except OSError:
        return ""

    base_lower = base_name.lower()
    for ext in temp_extensions:
        target = f"{base_lower}{ext}"  # ext is already lowercase
        for entry in dir_entries:
            if entry.lower() == target:
                return os.path.join(dir_path, entry).replace(os.sep, "/")

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
