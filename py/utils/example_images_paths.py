"""Utility helpers for resolving example image storage paths."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Iterable, Optional, Tuple

from ..services.settings_manager import get_settings_manager

_HEX_PATTERN = re.compile(r"[a-fA-F0-9]{64}")

# Marker written inside a model's example folder after a download pass has
# accounted for every media entry (downloaded now, or permanently flagged).
# A populated folder without it is treated as unverified and re-checked, which
# repairs folders left behind by an interrupted run.
COMPLETION_MARKER_FILENAME = ".lm-examples-complete"

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


def get_example_images_root() -> str:
    """Return the root directory configured for example images."""

    settings_manager = get_settings_manager()
    root = settings_manager.get("example_images_path") or ""
    return os.path.abspath(root) if root else ""


def get_library_root(library_name: Optional[str] = None) -> str:
    """Return the example images root; the legacy name argument is ignored."""

    return get_example_images_root()


def ensure_library_root_exists(library_name: Optional[str] = None) -> str:
    """Ensure the example images root exists and return it."""

    root = get_library_root()
    if root:
        os.makedirs(root, exist_ok=True)
    return root


def get_model_folder(model_hash: str, library_name: Optional[str] = None) -> str:
    """Return the folder path for a model's example images."""

    if not model_hash:
        return ""

    root = ensure_library_root_exists()
    if not root:
        return ""

    return os.path.join(root, model_hash.lower())


def get_completion_marker_path(model_dir: str) -> str:
    """Return the completion marker path for a model's example folder."""

    return os.path.join(model_dir, COMPLETION_MARKER_FILENAME) if model_dir else ""


def has_completion_marker(model_dir: str) -> bool:
    """Return True when a completed download marker exists."""

    marker = get_completion_marker_path(model_dir)
    return bool(marker) and os.path.isfile(marker)


def mark_example_folder_complete(model_dir: str, media_count: int = 0) -> bool:
    """Record that *model_dir* has no outstanding downloadable media.

    The marker is only written once the folder actually contains a media file:
    a model whose every asset returned 404 has nothing to skip and stays on the
    failed list instead. The write is atomic so an interrupted run cannot leave
    a half-written marker behind.
    """

    if not model_dir or not os.path.isdir(model_dir):
        return False

    try:
        with os.scandir(model_dir) as entries:
            has_media = any(
                entry.is_file()
                and not entry.name.startswith(COMPLETION_MARKER_FILENAME)
                for entry in entries
            )
    except OSError:
        return False
    if not has_media:
        return False

    marker = get_completion_marker_path(model_dir)
    temp_path = f"{marker}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": 1,
                    "media": int(media_count or 0),
                    "completed_at": time.time(),
                },
                handle,
            )
        os.replace(temp_path, marker)
        return True
    except OSError as exc:
        logger.warning(
            "Failed to write example completion marker for %s: %s", model_dir, exc
        )
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return False


def clear_example_completion_marker(model_dir: str) -> None:
    """Remove the completion marker so the next run re-checks the folder."""

    marker = get_completion_marker_path(model_dir)
    if not marker:
        return
    for path in (marker, f"{marker}.tmp"):
        try:
            os.remove(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.debug(
                "Failed to remove example completion marker %s: %s", path, exc
            )


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
    """Return the single example images root using the legacy tuple shape."""

    root = get_example_images_root()
    if not root:
        return []

    return [("default", root)]


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
            # Accept legacy library folders so the startup consolidation can
            # recover their hash directories.
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
