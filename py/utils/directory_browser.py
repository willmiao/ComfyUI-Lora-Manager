"""Shared directory browsing/creation logic for HTTP directory pickers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Tuple

# Virtual path token for the Windows drive list. Browsing up from a drive
# root (e.g. C:\) lands here so users can switch drives without typing a
# path. Only meaningful on Windows; elsewhere it falls through to normal
# path handling and fails the existence check.
WINDOWS_DRIVES_TOKEN = "__drives__"

_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".tif",
}

# A new folder name must be a single path segment on every supported platform:
# reject both separators regardless of the host OS so the request can never
# escape the browsed directory ("../foo" and "a/b" are both rejected).
_NAME_SEPARATORS = ("/", "\\")

# Windows refuses these characters in a file name. POSIX allows them, but a
# folder created here is meant to become a configured library path, so stay
# portable and reject them everywhere.
_INVALID_NAME_CHARS = frozenset('<>:"|?*') | frozenset(
    chr(code) for code in range(32)
)

# Windows device names are unusable as directory names ("CON", "COM1", ...).
_WINDOWS_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{index}" for index in range(1, 10)]
    + [f"LPT{index}" for index in range(1, 10)]
)

_MAX_NAME_LENGTH = 255


def browse_directory(directory_path: str) -> Tuple[Dict[str, Any], int]:
    """Browse a directory and return (payload, http_status).

    The payload shape matches the JSON responses historically produced by
    ``BatchImportHandler.browse_directory``: on success a dict with
    ``success``, ``current_path``, ``parent_path``, ``directories``,
    ``image_files``, ``image_count`` and ``directory_count``; on failure a
    ``{"success": False, "error": ...}`` dict with a 400/403/404/500 status.
    """
    if os.name == "nt" and directory_path == WINDOWS_DRIVES_TOKEN:
        return _windows_drives_payload(), 200

    # Default to the user's home directory. The frontend previously
    # sent "/" as the initial path, which is POSIX-only: on Windows it
    # resolves to the current drive root and then fails the access
    # check below.
    if not directory_path:
        path = Path.home()
    else:
        # Business-path convention: normalize lexically with abspath but
        # never resolve symlinks (no resolve()/realpath). The picker result
        # is stored as a configured library path, and stored paths must
        # match what the user sees on disk.
        path = Path(os.path.abspath(os.path.expanduser(directory_path)))

    # Access check: browsing intentionally covers the whole server
    # filesystem (the server operator browses their own machine). On
    # POSIX every absolute path is under "/", but Path("/") has no
    # drive letter on Windows and can never anchor a drive-qualified
    # path in relative_to(), so test for a drive there instead.
    if os.name == "nt":
        is_allowed = bool(path.drive)
    else:
        is_allowed = path.is_absolute()

    if not is_allowed:
        return {"success": False, "error": "Access denied to this directory"}, 403

    if not path.exists():
        return {"success": False, "error": "Directory does not exist"}, 404

    if not path.is_dir():
        return {"success": False, "error": "Path is not a directory"}, 400

    directories = []
    image_files = []

    try:
        for item in path.iterdir():
            try:
                if item.is_dir():
                    # Skip hidden directories and common system folders
                    if not item.name.startswith(".") and item.name not in [
                        "__pycache__",
                        "node_modules",
                    ]:
                        directories.append(
                            {
                                "name": item.name,
                                "path": str(item),
                                "is_parent": False,
                            }
                        )
                elif item.is_file() and item.suffix.lower() in _IMAGE_EXTENSIONS:
                    image_files.append(
                        {
                            "name": item.name,
                            "path": str(item),
                            "size": item.stat().st_size,
                        }
                    )
            except (PermissionError, OSError):
                # Skip files/directories we can't access
                continue

        directories.sort(key=lambda x: x["name"].lower())
        image_files.sort(key=lambda x: x["name"].lower())

        # Parent directory. A filesystem root is its own parent
        # (parent == path): POSIX "/" gets no parent, while a Windows
        # drive root (C:\) links up to the virtual drive list so users
        # can switch drives. The previous str(path) != str(path.root)
        # check misfired on Windows, where a drive root's parent is
        # itself, producing an infinite self-loop.
        if path.parent == path:
            parent_path = WINDOWS_DRIVES_TOKEN if os.name == "nt" else None
        else:
            parent_path = str(path.parent)

        return (
            {
                "success": True,
                "current_path": str(path),
                "parent_path": parent_path,
                "directories": directories,
                "image_files": image_files,
                "image_count": len(image_files),
                "directory_count": len(directories),
            },
            200,
        )

    except PermissionError:
        return {"success": False, "error": "Permission denied"}, 403
    except OSError as exc:
        return {"success": False, "error": f"Error reading directory: {str(exc)}"}, 500


def _windows_drives_payload() -> Dict[str, Any]:
    """List available drive letters as a virtual directory (Windows only)."""
    try:
        drives = os.listdrives()
    except AttributeError:  # Python < 3.12
        drives = [
            f"{letter}:\\"
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            if os.path.exists(f"{letter}:\\")
        ]
    directories = [{"name": drive, "path": drive, "is_parent": False} for drive in drives]
    return {
        "success": True,
        # Empty current_path marks the virtual level; the frontend
        # disables folder selection there.
        "current_path": "",
        "parent_path": None,
        "directories": directories,
        "image_files": [],
        "image_count": 0,
        "directory_count": len(directories),
    }


def _validate_new_directory_name(name: str) -> str | None:
    """Return an error code when ``name`` is not a safe single path segment."""
    if not name:
        return "name_required"
    if len(name) > _MAX_NAME_LENGTH:
        return "name_invalid"
    if name in (".", "..") or any(sep in name for sep in _NAME_SEPARATORS):
        return "name_invalid"
    if any(char in _INVALID_NAME_CHARS for char in name):
        return "name_invalid"
    # Windows silently strips trailing dots/spaces from paths, so a folder
    # named "foo." would be stored under a different name than the user sees.
    if name.endswith("."):
        return "name_invalid"
    if name.upper().split(".")[0] in _WINDOWS_RESERVED_NAMES:
        return "name_invalid"
    return None


def create_directory(directory_path: str, name: str) -> Tuple[Dict[str, Any], int]:
    """Create a single new subdirectory inside ``directory_path``.

    Returns ``(payload, http_status)``. Failures carry a stable ``error_code``
    so the picker UI can localize them, with ``error`` as the English
    fallback; success returns the created folder's absolute path.
    """
    parent = directory_path.strip() if isinstance(directory_path, str) else ""
    new_name = name.strip() if isinstance(name, str) else ""

    if not parent:
        return {
            "success": False,
            "error": "Missing parent directory",
            "error_code": "parent_required",
        }, 400

    # Business-path convention: abspath only, never realpath (see
    # browse_directory) so the created path matches what the user sees.
    parent_path = Path(os.path.abspath(os.path.expanduser(parent)))

    if os.name == "nt":
        is_allowed = bool(parent_path.drive)
    else:
        is_allowed = parent_path.is_absolute()

    if not is_allowed:
        return {
            "success": False,
            "error": "Access denied to this directory",
            "error_code": "access_denied",
        }, 403

    if not parent_path.exists():
        return {
            "success": False,
            "error": "Directory does not exist",
            "error_code": "parent_not_found",
        }, 404

    if not parent_path.is_dir():
        return {
            "success": False,
            "error": "Path is not a directory",
            "error_code": "parent_not_a_directory",
        }, 400

    name_error = _validate_new_directory_name(new_name)
    if name_error == "name_required":
        return {
            "success": False,
            "error": "Folder name is required",
            "error_code": name_error,
        }, 400
    if name_error:
        return {
            "success": False,
            "error": "Folder name contains invalid characters",
            "error_code": name_error,
        }, 400

    target = parent_path / new_name
    # lexists() also catches a dangling symlink squatting on the name.
    if os.path.lexists(target):
        return {
            "success": False,
            "error": "A folder with this name already exists",
            "error_code": "already_exists",
        }, 409

    try:
        os.mkdir(target)
    except FileExistsError:
        # Lost a race with another creator between lexists() and mkdir().
        return {
            "success": False,
            "error": "A folder with this name already exists",
            "error_code": "already_exists",
        }, 409
    except PermissionError:
        return {
            "success": False,
            "error": "Permission denied",
            "error_code": "permission_denied",
        }, 403
    except OSError as exc:
        return {
            "success": False,
            "error": f"Failed to create folder: {exc}",
            "error_code": "create_failed",
        }, 500

    return {"success": True, "path": str(target), "name": new_name}, 200
