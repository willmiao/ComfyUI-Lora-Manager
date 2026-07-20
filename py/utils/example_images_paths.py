"""Utility helpers for resolving example image storage paths."""

from __future__ import annotations

import logging
import os
import re
import shutil
from typing import Iterable, List, Optional, Tuple

from ..services.settings_manager import get_settings_manager

_HEX_PATTERN = re.compile(r"[a-fA-F0-9]{64}")

# Filesystem/metadata files that are never created by the example images system
# and are safe to ignore during validation. The cleanup service only operates on
# directories, so these files pose no data-loss risk.
_SAFE_FILENAMES: frozenset[str] = frozenset({
    ".DS_Store",       # macOS folder metadata
    "Thumbs.db",       # Windows thumbnail cache
    "desktop.ini",     # Windows folder customization
    ".localized",      # macOS folder name localization
    ".gitkeep",        # Placeholder to keep empty dirs in git
    ".gitignore",      # Git ignore rules
})

logger = logging.getLogger(__name__)


def _get_configured_libraries() -> List[str]:
    """Return configured library names if multi-library support is enabled."""

    settings_manager = get_settings_manager()
    libraries = settings_manager.get("libraries")
    if isinstance(libraries, dict) and libraries:
        return list(libraries.keys())
    return []


def get_example_images_root() -> str:
    """Return the root directory configured for example images."""

    settings_manager = get_settings_manager()
    root = settings_manager.get("example_images_path") or ""
    return os.path.abspath(root) if root else ""


def uses_library_scoped_folders() -> bool:
    """Return True when example images should be separated per library."""

    libraries = _get_configured_libraries()
    return len(libraries) > 1


def sanitize_library_name(library_name: Optional[str]) -> str:
    """Return a filesystem safe library name."""

    settings_manager = get_settings_manager()
    name = library_name or settings_manager.get_active_library_name() or "default"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return safe_name or "default"


def get_library_root(library_name: Optional[str] = None) -> str:
    """Return the directory where a library's example images should live."""

    root = get_example_images_root()
    if not root:
        return ""

    if uses_library_scoped_folders():
        return os.path.join(root, sanitize_library_name(library_name))
    return root


def ensure_library_root_exists(library_name: Optional[str] = None) -> str:
    """Ensure the example image directory for a library exists and return it."""

    library_root = get_library_root(library_name)
    if library_root:
        os.makedirs(library_root, exist_ok=True)
    return library_root


def get_model_folder(model_hash: str, library_name: Optional[str] = None) -> str:
    """Return the folder path for a model's example images."""

    if not model_hash:
        return ""

    library_root = ensure_library_root_exists(library_name)
    if not library_root:
        return ""

    normalized_hash = (model_hash or "").lower()
    resolved_folder = os.path.join(library_root, normalized_hash)

    if uses_library_scoped_folders():
        legacy_root = get_example_images_root()
        legacy_folder = os.path.join(legacy_root, normalized_hash)
        if os.path.exists(legacy_folder) and not os.path.exists(resolved_folder):
            try:
                os.makedirs(library_root, exist_ok=True)
                shutil.move(legacy_folder, resolved_folder)
                logger.info(
                    "Migrated legacy example images folder '%s' to '%s'", legacy_folder, resolved_folder
                )
            except OSError as exc:
                logger.error(
                    "Failed to migrate example images from '%s' to '%s': %s",
                    legacy_folder,
                    resolved_folder,
                    exc,
                )
                return legacy_folder
    elif not os.path.exists(resolved_folder):
        # Reverse migration: when consolidating from multi-library to
        # single-library mode (e.g. after "default" was cleaned up), look
        # for existing example images inside library-named subdirectories
        # and bring them back to the root level.
        root = get_example_images_root()
        if root:
            try:
                for entry in os.listdir(root):
                    entry_path = os.path.join(root, entry)
                    if not os.path.isdir(entry_path):
                        continue
                    if is_hash_folder(entry) or entry == "_deleted":
                        continue
                    if not _library_folder_has_only_hash_dirs(entry_path):
                        continue
                    legacy = os.path.join(entry_path, normalized_hash)
                    if os.path.exists(legacy):
                        shutil.move(legacy, resolved_folder)
                        logger.info(
                            "Consolidated example images from '%s' to '%s'",
                            legacy, resolved_folder,
                        )
                        break
            except OSError as exc:
                logger.error(
                    "Failed to consolidate example images during "
                    "library merge: %s", exc,
                )

    return resolved_folder


class ExampleImagePathResolver:
    """Convenience wrapper exposing example image path helpers."""

    @staticmethod
    def get_model_folder(model_hash: str, library_name: Optional[str] = None) -> str:
        """Return the example image folder for a model, migrating legacy paths."""

        return get_model_folder(model_hash, library_name)

    @staticmethod
    def get_library_root(library_name: Optional[str] = None) -> str:
        """Return the configured library root for example images."""

        return get_library_root(library_name)

    @staticmethod
    def ensure_library_root_exists(library_name: Optional[str] = None) -> str:
        """Ensure the library root exists before writing files."""

        return ensure_library_root_exists(library_name)

    @staticmethod
    def get_model_relative_path(model_hash: str, library_name: Optional[str] = None) -> str:
        """Return the relative path to a model folder from the static mount point."""

        return get_model_relative_path(model_hash, library_name)


def get_model_relative_path(model_hash: str, library_name: Optional[str] = None) -> str:
    """Return the relative URL path from the static mount to a model folder."""

    root = get_example_images_root()
    folder = get_model_folder(model_hash, library_name)
    if not root or not folder:
        return ""

    try:
        relative = os.path.relpath(folder, root)
    except ValueError:
        return ""

    return relative.replace("\\", "/")


def iter_library_roots() -> Iterable[Tuple[str, str]]:
    """Yield configured library names and their resolved filesystem roots."""

    root = get_example_images_root()
    if not root:
        return []

    libraries = _get_configured_libraries()
    if uses_library_scoped_folders():
        results: List[Tuple[str, str]] = []
        if libraries:
            for library in libraries:
                results.append((library, get_library_root(library)))
        else:
            # Fall back to the active library to avoid skipping migrations/cleanup
            settings_manager = get_settings_manager()
            active = settings_manager.get_active_library_name() or "default"
            results.append((active, get_library_root(active)))
        return results

    settings_manager = get_settings_manager()
    active = settings_manager.get_active_library_name() or "default"
    return [(active, root)]


def is_hash_folder(name: str) -> bool:
    """Return True if the provided name looks like a model hash folder."""

    return bool(_HEX_PATTERN.fullmatch(name or ""))


def _is_safe_ignorable_entry(item: str, item_path: str) -> bool:
    """Return True if *item* is a harmless system/hidden file we can skip.

    These files are never created by the example images system and are safe to
    ignore because the cleanup/delete operations only act on **directories**,
    never on individual files (other than ``.download_progress.json``).
    """
    if item in _SAFE_FILENAMES:
        return True
    # Hide Unix hidden files (dotfiles) that are regular files,
    # since the cleanup system never deletes or moves files.
    if item.startswith(".") and os.path.isfile(item_path):
        return True
    return False


def is_valid_example_images_root(folder_path: str) -> bool:
    """Check whether a folder looks like a dedicated example images root."""

    try:
        items = os.listdir(folder_path)
    except OSError:
        return False

    for item in items:
        item_path = os.path.join(folder_path, item)

        # .download_progress.json is an expected metadata file — check before
        # the generic dotfile rule so it stays explicitly documented.
        if item == ".download_progress.json" and os.path.isfile(item_path):
            continue

        # Skip harmless system/hidden files — cleanup only touches directories
        if _is_safe_ignorable_entry(item, item_path):
            continue

        if os.path.isdir(item_path):
            if is_hash_folder(item):
                continue
            if item == "_deleted":
                # Allow cleanup staging folders
                continue
            # Accept legacy library folders even when current settings do not
            # explicitly enable multi-library mode. This allows users to reuse a
            # previously configured example images directory after settings are
            # reset, as long as the nested structure still looks like dedicated
            # hash folders.
            if _library_folder_has_only_hash_dirs(item_path):
                continue
        return False

    return True


def find_non_compliant_items_in_example_images_root(folder_path: str) -> list[str]:
    """Return the names of items that prevent *folder_path* from being a valid
    example images root, or an empty list if the folder is valid.

    This mirrors ``is_valid_example_images_root`` but **returns** the offending
    names instead of a boolean, so callers can produce actionable error messages.
    """
    try:
        items = os.listdir(folder_path)
    except OSError as exc:
        return [f"<cannot list directory: {exc}>"]

    offending: list[str] = []

    for item in items:
        item_path = os.path.join(folder_path, item)

        # Same skip rules as is_valid_example_images_root
        if item == ".download_progress.json" and os.path.isfile(item_path):
            continue
        if _is_safe_ignorable_entry(item, item_path):
            continue
        if os.path.isdir(item_path):
            if is_hash_folder(item):
                continue
            if item == "_deleted":
                continue
            if _library_folder_has_only_hash_dirs(item_path):
                continue

        offending.append(item)

    return offending


def _library_folder_has_only_hash_dirs(path: str) -> bool:
    """Return True when a library subfolder only contains hash folders or metadata files."""

    try:
        for entry in os.listdir(path):
            entry_path = os.path.join(path, entry)
            if entry == ".download_progress.json" and os.path.isfile(entry_path):
                continue
            if entry == "_deleted" and os.path.isdir(entry_path):
                continue
            if not os.path.isdir(entry_path) or not is_hash_folder(entry):
                return False
    except OSError:
        return False

    return True
