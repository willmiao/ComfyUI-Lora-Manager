"""Utilities for locating and migrating the LoRA Manager settings file."""

from __future__ import annotations

import json
import logging
import os
import shutil
from typing import Optional

from platformdirs import user_config_dir


APP_NAME = "ComfyUI-LoRA-Manager"
_LOGGER = logging.getLogger(__name__)


def get_project_root() -> str:
    """Return the root directory of the project repository."""

    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def get_legacy_settings_path() -> str:
    """Return the legacy location of ``settings.json`` within the project tree."""

    return os.path.join(get_project_root(), "settings.json")


def get_settings_dir(create: bool = True) -> str:
    """Return the user configuration directory for the application.

    Args:
        create: Whether to create the directory if it does not already exist.

    Returns:
        The absolute path to the user configuration directory.
    """

    config_dir = user_config_dir(APP_NAME, appauthor=False)
    if create:
        os.makedirs(config_dir, exist_ok=True)
    return config_dir


def get_settings_file_path(create_dir: bool = True) -> str:
    """Return the path to ``settings.json`` in the user configuration directory."""

    return os.path.join(get_settings_dir(create=create_dir), "settings.json")


def ensure_settings_file(logger: Optional[logging.Logger] = None) -> str:
    """Ensure the settings file resides in the user configuration directory.

    If a legacy ``settings.json`` is detected in the project root it is migrated to
    the platform-specific user configuration folder. The caller receives the path
    to the settings file irrespective of whether a migration was needed.

    Args:
        logger: Optional logger used for migration messages. Falls back to a
            module level logger when omitted.

    Returns:
        The absolute path to ``settings.json`` in the user configuration folder.
    """

    logger = logger or _LOGGER
    legacy_path = get_legacy_settings_path()

    if _should_use_portable_settings(legacy_path, logger):
        return legacy_path

    target_path = get_settings_file_path(create_dir=True)
    preferred_dir = user_config_dir(APP_NAME, appauthor=False)
    preferred_path = os.path.join(preferred_dir, "settings.json")

    if os.path.abspath(target_path) != os.path.abspath(preferred_path):
        os.makedirs(preferred_dir, exist_ok=True)
        target_path = preferred_path

    if os.path.exists(legacy_path) and not os.path.exists(target_path):
        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.move(legacy_path, target_path)
            logger.info("Migrated settings.json to %s", target_path)
        except Exception as exc:  # pragma: no cover - defensive fallback path
            logger.warning("Failed to move legacy settings.json: %s", exc)
            try:
                shutil.copy2(legacy_path, target_path)
                logger.info("Copied legacy settings.json to %s", target_path)
            except Exception as copy_exc:  # pragma: no cover - defensive fallback path
                logger.error("Could not migrate settings.json: %s", copy_exc)

    return target_path


def _should_use_portable_settings(path: str, logger: logging.Logger) -> bool:
    """Return ``True`` when the repository settings file enables portable mode."""

    if not os.path.exists(path):
        return False

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse %s for portable mode flag: %s", path, exc)
        return False
    except OSError as exc:
        logger.warning("Could not read %s to determine portable mode: %s", path, exc)
        return False

    if not isinstance(payload, dict):
        logger.debug("Portable settings file %s does not contain a JSON object", path)
        return False

    flag = payload.get("use_portable_settings")
    if isinstance(flag, bool):
        return flag

    if flag is not None:
        logger.warning(
            "Ignoring non-boolean use_portable_settings value in %s", path
        )
    return False

