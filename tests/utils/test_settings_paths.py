"""Tests for settings path resolution."""

import json
import logging
import os

import pytest

from py.utils.settings_paths import (
    SETTINGS_DIR_ENV,
    _should_use_portable_settings,
    ensure_settings_file,
    get_settings_dir,
    get_settings_dir_override,
    is_settings_dir_pinned,
    set_settings_dir_override,
)


def _redirect_paths(tmp_path, monkeypatch):
    """Pin project root and user config dir resolution to temp paths."""
    monkeypatch.setattr(
        "py.utils.settings_paths.get_project_root", lambda: str(tmp_path / "repo")
    )
    monkeypatch.setattr(
        "py.utils.settings_paths.user_config_dir",
        lambda *args, **kwargs: str(tmp_path / "user_config"),
    )


class TestShouldUsePortableSettings:
    """Tests for _should_use_portable_settings()."""

    @pytest.mark.parametrize(
        "env_value, settings_flag, expected",
        [
            ("1", False, True),   # env = 1 overrides settings.json false
            ("1", True, True),    # env = 1 matches settings.json true
            ("0", False, False),  # env = 0 → rely on settings.json
            ("0", True, True),    # env = 0 → rely on settings.json
            ("", False, False),   # unset → rely on settings.json
            ("", True, True),     # unset → rely on settings.json
        ],
    )
    def test_env_var_overrides_settings(self, tmp_path, env_value, settings_flag, expected):
        """The LORA_MANAGER_PORTABLE env var takes precedence over settings.json."""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"use_portable_settings": settings_flag})
        )

        with pytest.MonkeyPatch.context() as mp:
            if env_value:
                mp.setenv("LORA_MANAGER_PORTABLE", env_value)
            else:
                mp.delenv("LORA_MANAGER_PORTABLE", raising=False)

            result = _should_use_portable_settings(str(settings_file), logging.getLogger())
            assert result == expected

    def test_missing_file_without_env(self, tmp_path):
        """Without env var, missing settings file returns False."""
        missing = tmp_path / "nonexistent.json"

        result = _should_use_portable_settings(str(missing), logging.getLogger())
        assert result is False

    def test_missing_file_with_env(self, tmp_path):
        """With env var, even a missing settings file returns True."""
        missing = tmp_path / "nonexistent.json"

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("LORA_MANAGER_PORTABLE", "1")
            result = _should_use_portable_settings(str(missing), logging.getLogger())
            assert result is True


class TestExplicitSettingsDirOverride:
    """Tests for the LORA_MANAGER_SETTINGS_DIR / --settings-path override."""

    def test_env_override_wins_over_portable_and_user_config(self, tmp_path, monkeypatch):
        _redirect_paths(tmp_path, monkeypatch)
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "settings.json").write_text(
            json.dumps({"use_portable_settings": True}), encoding="utf-8"
        )
        custom_dir = tmp_path / "custom" / "e2e"

        monkeypatch.setenv(SETTINGS_DIR_ENV, str(custom_dir))
        monkeypatch.delenv("LORA_MANAGER_PORTABLE", raising=False)

        assert is_settings_dir_pinned()
        target = get_settings_dir(create=True)
        assert target == str(custom_dir.resolve())
        assert target == os.path.abspath(str(custom_dir))
        assert custom_dir.is_dir()

        # The override is independent of the effective use_portable flag.
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("LORA_MANAGER_PORTABLE", "1")
            assert get_settings_dir(create=False) == os.path.abspath(str(custom_dir))

    def test_env_override_normalizes_tilde(self, monkeypatch):
        monkeypatch.setenv(SETTINGS_DIR_ENV, "~/lm-e2e-settings")
        override = get_settings_dir_override()
        assert override == os.path.abspath(os.path.expanduser("~/lm-e2e-settings"))

    def test_ensure_settings_file_pins_path_and_skips_migration(self, tmp_path, monkeypatch):
        _redirect_paths(tmp_path, monkeypatch)
        repo = tmp_path / "repo"
        repo.mkdir()
        legacy = repo / "settings.json"
        legacy.write_text(json.dumps({"language": "ja"}), encoding="utf-8")
        custom_dir = tmp_path / "custom"

        monkeypatch.setenv(SETTINGS_DIR_ENV, str(custom_dir))

        settings_file = ensure_settings_file()
        assert settings_file == os.path.join(os.path.abspath(str(custom_dir)), "settings.json")
        assert os.path.isdir(str(custom_dir))
        # The legacy (project-root) file must NOT be migrated into the custom dir.
        assert legacy.exists()
        assert not (custom_dir / "settings.json").exists()
        assert not (tmp_path / "user_config" / "settings.json").exists()

    def test_programmatic_override_and_clear(self, tmp_path, monkeypatch):
        _redirect_paths(tmp_path, monkeypatch)
        monkeypatch.delenv(SETTINGS_DIR_ENV, raising=False)

        custom_dir = tmp_path / "prog"
        previous = set_settings_dir_override(str(custom_dir))
        assert previous is None
        assert is_settings_dir_pinned()
        assert get_settings_dir(create=False) == os.path.abspath(str(custom_dir))

        previous = set_settings_dir_override(None)
        assert previous == os.path.abspath(str(custom_dir))
        assert not is_settings_dir_pinned()
        # Falls back to the (redirected) platform user config dir.
        assert get_settings_dir(create=False) == str(tmp_path / "user_config")
