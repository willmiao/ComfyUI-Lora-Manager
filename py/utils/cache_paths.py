"""Centralized cache path resolution with automatic migration support.

This module provides a unified interface for resolving cache file paths,
with automatic migration from legacy locations to the new organized
cache directory structure.

Target structure:
    {settings_dir}/
    └── cache/
        ├── symlink/
        │   └── symlink_map.json
        ├── model/
        │   └── {library_name}.sqlite
        ├── recipe/
        │   └── {library_name}.sqlite
        └── fts/
            ├── recipe_fts.sqlite
            └── tag_fts.sqlite
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from enum import Enum
from typing import List, Optional

from .settings_paths import get_project_root, get_settings_dir

logger = logging.getLogger(__name__)


class CacheType(Enum):
    """Types of cache files managed by the cache path resolver."""

    MODEL = "model"
    RECIPE = "recipe"
    RECIPE_FTS = "recipe_fts"
    TAG_FTS = "tag_fts"
    SYMLINK = "symlink"


# Subdirectory structure for each cache type
_CACHE_SUBDIRS = {
    CacheType.MODEL: "model",
    CacheType.RECIPE: "recipe",
    CacheType.RECIPE_FTS: "fts",
    CacheType.TAG_FTS: "fts",
    CacheType.SYMLINK: "symlink",
}

# Filename patterns for each cache type
_CACHE_FILENAMES = {
    CacheType.MODEL: "{library_name}.sqlite",
    CacheType.RECIPE: "{library_name}.sqlite",
    CacheType.RECIPE_FTS: "recipe_fts.sqlite",
    CacheType.TAG_FTS: "tag_fts.sqlite",
    CacheType.SYMLINK: "symlink_map.json",
}


def get_cache_base_dir(create: bool = True) -> str:
    """Return the base cache directory path.

    Args:
        create: Whether to create the directory if it does not exist.

    Returns:
        The absolute path to the cache base directory ({settings_dir}/cache/).
    """
    settings_dir = get_settings_dir(create=create)
    cache_dir = os.path.join(settings_dir, "cache")
    if create:
        os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _sanitize_library_name(library_name: Optional[str]) -> str:
    """Sanitize a library name for use in filenames.

    Args:
        library_name: The library name to sanitize.

    Returns:
        A sanitized version safe for use in filenames.
    """
    name = library_name or "default"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def get_cache_file_path(
    cache_type: CacheType,
    library_name: Optional[str] = None,
    create_dir: bool = True,
) -> str:
    """Get the canonical path for a cache file.

    Args:
        cache_type: The type of cache file.
        library_name: The library name (only used for MODEL and RECIPE types).
        create_dir: Whether to create the parent directory if it does not exist.

    Returns:
        The absolute path to the cache file in its canonical location.
    """
    cache_base = get_cache_base_dir(create=create_dir)
    subdir = _CACHE_SUBDIRS[cache_type]
    cache_dir = os.path.join(cache_base, subdir)

    if create_dir:
        os.makedirs(cache_dir, exist_ok=True)

    filename_template = _CACHE_FILENAMES[cache_type]
    safe_name = _sanitize_library_name(library_name)
    filename = filename_template.format(library_name=safe_name)

    return os.path.join(cache_dir, filename)


def get_legacy_cache_paths(
    cache_type: CacheType,
    library_name: Optional[str] = None,
) -> List[str]:
    """Get a list of legacy cache file paths to check for migration.

    The paths are returned in order of priority (most recent first).

    Args:
        cache_type: The type of cache file.
        library_name: The library name (only used for MODEL and RECIPE types).

    Returns:
        A list of potential legacy paths to check, in order of preference.
    """
    try:
        settings_dir = get_settings_dir(create=False)
    except Exception:
        settings_dir = get_project_root()

    safe_name = _sanitize_library_name(library_name)
    legacy_paths: List[str] = []

    if cache_type == CacheType.MODEL:
        # Legacy per-library path: {settings_dir}/model_cache/{library}.sqlite
        legacy_paths.append(
            os.path.join(settings_dir, "model_cache", f"{safe_name}.sqlite")
        )
        # Legacy root-level single cache (for "default" library only)
        if safe_name.lower() in ("default", ""):
            legacy_paths.append(os.path.join(settings_dir, "model_cache.sqlite"))

    elif cache_type == CacheType.RECIPE:
        # Legacy per-library path: {settings_dir}/recipe_cache/{library}.sqlite
        legacy_paths.append(
            os.path.join(settings_dir, "recipe_cache", f"{safe_name}.sqlite")
        )
        # Legacy root-level single cache (for "default" library only)
        if safe_name.lower() in ("default", ""):
            legacy_paths.append(os.path.join(settings_dir, "recipe_cache.sqlite"))

    elif cache_type == CacheType.RECIPE_FTS:
        # Legacy root-level path
        legacy_paths.append(os.path.join(settings_dir, "recipe_fts.sqlite"))

    elif cache_type == CacheType.TAG_FTS:
        # Legacy root-level path
        legacy_paths.append(os.path.join(settings_dir, "tag_fts.sqlite"))

    elif cache_type == CacheType.SYMLINK:
        # Current location in cache/ but without subdirectory
        legacy_paths.append(
            os.path.join(settings_dir, "cache", "symlink_map.json")
        )

    return legacy_paths


def _cleanup_legacy_file_after_migration(
    legacy_path: str,
    canonical_path: str,
) -> bool:
    """Safely remove a legacy file after successful migration.

    Args:
        legacy_path: The legacy file path to remove.
        canonical_path: The canonical path where the file was copied to.

    Returns:
        True if cleanup succeeded, False otherwise.
    """
    try:
        if not os.path.exists(canonical_path):
            logger.warning(
                "Skipping cleanup of %s: canonical file not found at %s",
                legacy_path,
                canonical_path,
            )
            return False

        legacy_size = os.path.getsize(legacy_path)
        canonical_size = os.path.getsize(canonical_path)
        if legacy_size != canonical_size:
            logger.warning(
                "Skipping cleanup of %s: file size mismatch (legacy=%d, canonical=%d)",
                legacy_path,
                legacy_size,
                canonical_size,
            )
            return False

        os.remove(legacy_path)
        logger.info("Cleaned up legacy cache file: %s", legacy_path)

        _cleanup_empty_legacy_directories(legacy_path)

        return True

    except Exception as exc:
        logger.warning(
            "Failed to cleanup legacy cache file %s: %s",
            legacy_path,
            exc,
        )
        return False


def _cleanup_empty_legacy_directories(legacy_path: str) -> None:
    """Remove empty parent directories of a legacy file.

    This function only removes directories if they are empty,
    using os.rmdir() which fails on non-empty directories.

    Args:
        legacy_path: The legacy file path whose parent directories should be cleaned.
    """
    try:
        parent_dir = os.path.dirname(legacy_path)

        legacy_dir_names = ("model_cache", "recipe_cache")

        current = parent_dir
        while current:
            base_name = os.path.basename(current)

            if base_name in legacy_dir_names:
                if os.path.isdir(current) and not os.listdir(current):
                    try:
                        os.rmdir(current)
                        logger.info("Removed empty legacy directory: %s", current)
                    except Exception:
                        pass

            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent

    except Exception as exc:
        logger.debug("Failed to cleanup empty legacy directories: %s", exc)


def resolve_cache_path_with_migration(
    cache_type: CacheType,
    library_name: Optional[str] = None,
    env_override: Optional[str] = None,
) -> str:
    """Resolve the cache file path, migrating from legacy locations if needed.

    This function performs lazy migration: on first access, it checks if the
    file exists at the canonical location. If not, it looks for legacy files
    and copies them to the new location. After successful migration, the
    legacy file is automatically removed.

    Args:
        cache_type: The type of cache file.
        library_name: The library name (only used for MODEL and RECIPE types).
        env_override: Optional environment variable value that overrides all
            path resolution. When set, returns this path directly without
            any migration.

    Returns:
        The resolved path to use for the cache file.
    """
    # Environment override bypasses all migration logic
    if env_override:
        return env_override

    canonical_path = get_cache_file_path(cache_type, library_name, create_dir=True)

    # If file already exists at canonical location, use it
    if os.path.exists(canonical_path):
        return canonical_path

    # Check legacy paths for migration
    legacy_paths = get_legacy_cache_paths(cache_type, library_name)

    for legacy_path in legacy_paths:
        if os.path.exists(legacy_path):
            try:
                shutil.copy2(legacy_path, canonical_path)
                logger.info(
                    "Migrated %s cache from %s to %s",
                    cache_type.value,
                    legacy_path,
                    canonical_path,
                )

                _cleanup_legacy_file_after_migration(legacy_path, canonical_path)

                return canonical_path
            except Exception as exc:
                logger.warning(
                    "Failed to migrate %s cache from %s: %s",
                    cache_type.value,
                    legacy_path,
                    exc,
                )

    # No legacy file found; return canonical path (will be created fresh)
    return canonical_path


def get_legacy_cache_files_for_cleanup() -> List[str]:
    """Get a list of legacy cache files that can be removed after migration.

    This function returns files that exist in legacy locations and have
    corresponding files in the new canonical locations.

    Returns:
        A list of legacy file paths that are safe to remove.
    """
    files_to_remove: List[str] = []

    try:
        settings_dir = get_settings_dir(create=False)
    except Exception:
        return files_to_remove

    # Check each cache type for migrated legacy files
    for cache_type in CacheType:
        # For MODEL and RECIPE, we need to check each library
        if cache_type in (CacheType.MODEL, CacheType.RECIPE):
            # Check default library
            _check_legacy_for_cleanup(cache_type, "default", files_to_remove)
            # Check for any per-library caches in legacy directories
            legacy_dir_name = "model_cache" if cache_type == CacheType.MODEL else "recipe_cache"
            legacy_dir = os.path.join(settings_dir, legacy_dir_name)
            if os.path.isdir(legacy_dir):
                try:
                    for filename in os.listdir(legacy_dir):
                        if filename.endswith(".sqlite"):
                            library_name = filename[:-7]  # Remove .sqlite
                            _check_legacy_for_cleanup(cache_type, library_name, files_to_remove)
                except Exception:
                    pass
        else:
            _check_legacy_for_cleanup(cache_type, None, files_to_remove)

    return files_to_remove


def _check_legacy_for_cleanup(
    cache_type: CacheType,
    library_name: Optional[str],
    files_to_remove: List[str],
) -> None:
    """Check if a legacy cache file can be removed after migration.

    Args:
        cache_type: The type of cache file.
        library_name: The library name (only used for MODEL and RECIPE types).
        files_to_remove: List to append removable files to.
    """
    canonical_path = get_cache_file_path(cache_type, library_name, create_dir=False)
    if not os.path.exists(canonical_path):
        return

    legacy_paths = get_legacy_cache_paths(cache_type, library_name)
    for legacy_path in legacy_paths:
        if os.path.exists(legacy_path) and legacy_path not in files_to_remove:
            files_to_remove.append(legacy_path)


def cleanup_legacy_cache_files(dry_run: bool = True) -> List[str]:
    """Remove legacy cache files that have been migrated.

    Args:
        dry_run: If True, only return the list of files that would be removed
            without actually removing them.

    Returns:
        A list of files that were (or would be) removed.
    """
    files = get_legacy_cache_files_for_cleanup()

    if dry_run or not files:
        return files

    removed: List[str] = []
    for file_path in files:
        try:
            os.remove(file_path)
            removed.append(file_path)
            logger.info("Removed legacy cache file: %s", file_path)
        except Exception as exc:
            logger.warning("Failed to remove legacy cache file %s: %s", file_path, exc)

    # Try to remove empty legacy directories
    try:
        settings_dir = get_settings_dir(create=False)
        for legacy_dir_name in ("model_cache", "recipe_cache"):
            legacy_dir = os.path.join(settings_dir, legacy_dir_name)
            if os.path.isdir(legacy_dir) and not os.listdir(legacy_dir):
                os.rmdir(legacy_dir)
                logger.info("Removed empty legacy directory: %s", legacy_dir)
    except Exception:
        pass

    return removed
