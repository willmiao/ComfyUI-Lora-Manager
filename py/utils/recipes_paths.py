"""Resolution of the recipe library's storage directory.

Kept side-effect free (no directory creation): model scanners and file
services consult these helpers on hot paths, where silently materializing
the folder would be a surprise. ``RecipeScanner.recipes_dir`` remains the
write endpoint and adds the ``makedirs`` itself.
"""

from __future__ import annotations

import os


def get_effective_recipes_dir() -> str:
    """Resolve the directory recipe data lives in. May not exist on disk.

    Mirrors ``RecipeScanner.recipes_dir`` minus the auto-create: the
    ``recipes_path`` setting wins; otherwise the default is ``recipes``
    under the first configured lora root (``config.loras_roots`` is already
    sorted case-insensitively). Returns ``""`` when no lora root exists.
    """
    # Local imports: services -> config -> utils dependency direction must
    # not pick up a utils -> services edge at module import time.
    from ..services.settings_manager import get_settings_manager
    from ..config import config

    custom_recipes_dir = get_settings_manager().get("recipes_path", "")
    if isinstance(custom_recipes_dir, str) and custom_recipes_dir.strip():
        return os.path.abspath(
            os.path.normpath(os.path.expanduser(custom_recipes_dir.strip()))
        )

    lora_roots = [
        path
        for path in (getattr(config, "loras_roots", None) or [])
        if isinstance(path, str) and path.strip()
    ]
    if not lora_roots:
        return ""

    return os.path.abspath(os.path.join(lora_roots[0], "recipes"))


def normalized_recipes_dir_key() -> str:
    """Comparison key (normcase + abspath) for the recipes dir; "" if unknown."""
    try:
        recipes_dir = get_effective_recipes_dir()
    except Exception:  # pragma: no cover - never break a scan over settings access
        return ""
    if not recipes_dir:
        return ""
    return os.path.normcase(os.path.abspath(recipes_dir))


def path_is_or_contains_recipes_dir(path: str) -> bool:
    """True when *path* is the recipes dir or one of its ancestors.

    Deleting or renaming an ancestor wipes the recipe library just the same,
    so folder operations must refuse both shapes.
    """
    key = normalized_recipes_dir_key()
    if not key:
        return False
    candidate = os.path.normcase(os.path.abspath(path))
    return candidate == key or key.startswith(candidate + os.sep)
