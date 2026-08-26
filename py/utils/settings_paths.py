"""Utilities for locating and migrating the LoRA Manager settings file."""

from __future__ import annotations

import json
import logging
import os
import shutil
from typing import Any, Dict, Optional

from platformdirs import user_config_dir


APP_NAME = "ComfyUI-LoRA-Manager"
_LM_PORTABLE_ENV = "LORA_MANAGER_PORTABLE"

# Explicit settings-directory override. Setting this (env var, or standalone's
# ``--settings-path`` which publishes it) pins the settings location: settings.json,
# cache/, wildcards/, backups/, logs/, stats/ all resolve under this directory,
# bypassing portable mode and the platform user config dir. Useful for sandboxed
# development/E2E runs that must not touch the real user data or the project root.
SETTINGS_DIR_ENV = "LORA_MANAGER_SETTINGS_DIR"
_settings_dir_override: Optional[str] = None

_LOGGER = logging.getLogger(__name__)


def get_project_root() -> str:
    """Return the root directory of the project repository."""

    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _normalize_settings_dir(path: str) -> str:
    """Expand ``~`` and absolutize a user-supplied settings directory."""

    return os.path.abspath(os.path.expanduser(path))


def set_settings_dir_override(path: Optional[str]) -> Optional[str]:
    """Set or clear the programmatic settings-directory override.

    Args:
        path: Absolute/relative directory to pin, or ``None`` to clear the
            override. ``~`` is expanded and the path absolutized.

    Returns:
        The previous override value (``None`` when none was active).
    """

    global _settings_dir_override
    previous = _settings_dir_override
    _settings_dir_override = (
        _normalize_settings_dir(path) if path else None
    )
    return previous


def get_settings_dir_override() -> Optional[str]:
    """Return the active explicit settings-directory override, if any.

    The ``LORA_MANAGER_SETTINGS_DIR`` environment variable takes precedence over
    the programmatic override so that standalone's ``--settings-path`` (which
    publishes itself through the environment) wins over embedded callers.
    """

    env_path = os.environ.get(SETTINGS_DIR_ENV)
    if env_path:
        return _normalize_settings_dir(env_path)
    return _settings_dir_override


def is_settings_dir_pinned() -> bool:
    """Return ``True`` when an explicit settings-directory override is active."""

    return get_settings_dir_override() is not None


def get_legacy_settings_path() -> str:
    """Return the legacy location of ``settings.json`` within the project tree."""

    return os.path.join(get_project_root(), "settings.json")


def get_settings_dir(create: bool = True) -> str:
    """Return the user configuration directory for the application.

    An explicit override (``LORA_MANAGER_SETTINGS_DIR`` or
    :func:`set_settings_dir_override`) takes precedence. Otherwise the portable
    project-root ``settings.json`` is used when enabled, falling back to the
    platform-specific user configuration directory.

    Args:
        create: Whether to create the directory if it does not already exist.

    Returns:
        The absolute path to the user configuration directory.
    """

    override = get_settings_dir_override()
    if override:
        config_dir = override
    else:
        legacy_path = get_legacy_settings_path()
        if _should_use_portable_settings(legacy_path, _LOGGER):
            config_dir = os.path.dirname(legacy_path)
        else:
            config_dir = user_config_dir(APP_NAME, appauthor=False)

    if create and config_dir:
        os.makedirs(config_dir, exist_ok=True)
    return config_dir


def get_settings_file_path(create_dir: bool = True) -> str:
    """Return the path to ``settings.json`` in the user configuration directory."""

    return os.path.join(get_settings_dir(create=create_dir), "settings.json")


def ensure_settings_file(logger: Optional[logging.Logger] = None) -> str:
    """Ensure the settings file resides in the user configuration directory.

    An explicit override (``LORA_MANAGER_SETTINGS_DIR`` or
    :func:`set_settings_dir_override`) pins the settings file to
    ``<override>/settings.json`` and skips legacy migration entirely.

    Otherwise, if a legacy ``settings.json`` is detected in the project root it is
    migrated to the platform-specific user configuration folder. The caller
    receives the path to the settings file irrespective of whether a migration was
    needed.

    Args:
        logger: Optional logger used for migration messages. Falls back to a
            module level logger when omitted.

    Returns:
        The absolute path to ``settings.json`` in the user configuration folder.
    """

    logger = logger or _LOGGER

    override = get_settings_dir_override()
    if override:
        os.makedirs(override, exist_ok=True)
        return os.path.join(override, "settings.json")

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
    """Return ``True`` when the env var forces it or the settings file enables it."""

    if os.environ.get(_LM_PORTABLE_ENV, "0") == "1":
        logger.debug("Portable mode enabled via %s", _LM_PORTABLE_ENV)
        return True

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


def load_settings_template() -> Optional[Dict[str, Any]]:
    """Return the parsed contents of ``settings.json.example`` when available."""

    template_path = os.path.join(get_project_root(), "settings.json.example")

    try:
        with open(template_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        _LOGGER.debug("settings.json.example not found at %s", template_path)
        return None
    except json.JSONDecodeError as exc:
        _LOGGER.warning("Failed to parse settings.json.example: %s", exc)
        return None
    except OSError as exc:
        _LOGGER.warning(
            "Could not read settings.json.example at %s: %s", template_path, exc
        )
        return None

    if not isinstance(payload, dict):
        _LOGGER.debug(
            "settings.json.example at %s does not contain a JSON object", template_path
        )
        return None

    return payload

