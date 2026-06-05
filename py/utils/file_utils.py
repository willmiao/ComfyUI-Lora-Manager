
import hashlib
import json
import logging
import os
import struct
from typing import Any

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
    """Calculate SHA256 hash of a file (full file content)."""
    sha256_hash = hashlib.sha256()
    chunk_size = _get_hash_chunk_size_bytes()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(chunk_size), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def calculate_autov2(file_path: str) -> str:
    """Calculate CivitAI AutoV2 hash.

    AutoV2 is the first 10 characters of the full file SHA256.
    Used by CivitAI as a shortened file identifier.

    Reference: https://developer.civitai.com/site/reference/model-versions
    """
    full_hash = hashlib.sha256()
    chunk_size = _get_hash_chunk_size_bytes()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(chunk_size), b""):
            full_hash.update(byte_block)
    return full_hash.hexdigest()[:10]


def read_safetensors_metadata(file_path: str) -> dict[str, Any]:
    """Read the ``__metadata__`` dict from a safetensors file header.

    Safetensors file format:
      - 8 bytes: header length (little-endian 64-bit)
      - N bytes: UTF-8 JSON header
      - The header JSON contains a ``__metadata__`` key holding arbitrary metadata.

    Returns an empty dict if the file is not a valid safetensors file or has no
    metadata.
    """
    try:
        with open(file_path, "rb") as f:
            header_len_bytes = f.read(8)
            if len(header_len_bytes) < 8:
                return {}
            header_len = struct.unpack("<Q", header_len_bytes)[0]
            header_bytes = f.read(header_len)
            if len(header_bytes) < header_len:
                return {}
            header = json.loads(header_bytes.decode("utf-8"))
            return header.get("__metadata__", {})
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, struct.error, MemoryError, Exception):
        return {}


def calculate_autov3(file_path: str) -> str | None:
    """Calculate CivitAI AutoV3 hash from a safetensors file.

    AutoV3 is extracted from the safetensors file's embedded metadata, not
    computed from the file bytes directly. The orchestrator reads the
    ``sshs_model_hash`` (kohya-ss format) or ``modelspec.hash_sha256`` field
    from the safetensors header and stores the first 12 characters.

    The embedded hash itself is the SHA256 of the file after skipping the
    8-byte header length + JSON header (a.k.a. the addnet hash / tensor-only
    hash).

    Reference:
      - CivitAI DB trigger: ``SUBSTRING(NEW.hash FROM 1 FOR 12)``
      - https://developer.civitai.com/site/reference/model-versions

    Returns ``None`` when no AutoV3 hash can be determined (e.g. the file is
    not safetensors, or the metadata doesn't contain a recognised hash field).
    """
    metadata = read_safetensors_metadata(file_path)
    if not metadata:
        return None

    embedded_hash = metadata.get("sshs_model_hash") or metadata.get("modelspec.hash_sha256")
    if embedded_hash and isinstance(embedded_hash, str) and len(embedded_hash) >= 12:
        return embedded_hash[:12]

    return None


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
