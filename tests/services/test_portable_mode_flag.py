"""Tests for the portable-mode flag lifecycle (issue #1114 follow-up).

``LORA_MANAGER_PORTABLE=1`` persists ``use_portable_settings: true`` into the
plugin''s own settings.json. That is convenient for repeat runs, but it used to
be a one-way trip: the flag made every instance sharing that plugin folder read
(and write) the portable settings directory, and the only way back was editing
settings.json by hand. ``LORA_MANAGER_PORTABLE=0`` is now the explicit exit.
"""

from __future__ import annotations

import json

import pytest

from py.services import settings_manager as settings_manager_module
from py.services.settings_manager import SettingsManager


def _write_settings(path, **extra):
    payload = {
        "folder_paths": {"loras": ["/loras"]},
    }
    payload.update(extra)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


@pytest.fixture
def isolated_settings_path(tmp_path, monkeypatch):
    """Point SettingsManager at a settings.json we control."""
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(
        "py.services.settings_manager.ensure_settings_file",
        lambda logger=None: str(settings_path),
    )
    settings_manager_module.reset_settings_manager()
    yield settings_path
    settings_manager_module.reset_settings_manager()


def test_portable_env_enables_and_persists_the_flag(
    isolated_settings_path, monkeypatch
):
    _write_settings(isolated_settings_path)
    monkeypatch.setenv("LORA_MANAGER_PORTABLE", "1")

    manager = SettingsManager()

    assert manager.get("use_portable_settings") is True
    persisted = json.loads(isolated_settings_path.read_text(encoding="utf-8"))
    assert persisted["use_portable_settings"] is True


def test_explicit_zero_clears_the_persisted_flag(
    isolated_settings_path, monkeypatch
):
    """`=0` must undo a previous `=1`, without hand-editing settings.json."""
    _write_settings(isolated_settings_path, use_portable_settings=True)
    monkeypatch.setenv("LORA_MANAGER_PORTABLE", "0")

    manager = SettingsManager()

    assert manager.get("use_portable_settings") is False
    persisted = json.loads(isolated_settings_path.read_text(encoding="utf-8"))
    # A default value is omitted from disk, so the key is gone entirely.
    assert persisted.get("use_portable_settings") is None


def test_unset_env_keeps_the_persisted_flag(
    isolated_settings_path, monkeypatch
):
    """Portable mode must persist across runs when the variable is unset."""
    _write_settings(isolated_settings_path, use_portable_settings=True)
    monkeypatch.delenv("LORA_MANAGER_PORTABLE", raising=False)

    manager = SettingsManager()

    assert manager.get("use_portable_settings") is True


def test_zero_is_a_noop_when_portable_was_never_enabled(
    isolated_settings_path, monkeypatch
):
    _write_settings(isolated_settings_path)
    monkeypatch.setenv("LORA_MANAGER_PORTABLE", "0")

    manager = SettingsManager()

    assert manager.get("use_portable_settings") in (False, None)


def test_pinned_settings_dir_wins_over_portable_env(
    isolated_settings_path, monkeypatch
):
    """LORA_MANAGER_SETTINGS_DIR still takes precedence, as documented."""
    _write_settings(isolated_settings_path)
    monkeypatch.setenv("LORA_MANAGER_PORTABLE", "1")
    monkeypatch.setenv("LORA_MANAGER_SETTINGS_DIR", str(isolated_settings_path.parent))

    manager = SettingsManager()

    # The pinned directory already decides the location, so the portable flag
    # is deliberately left alone.
    assert not manager.get("use_portable_settings")
