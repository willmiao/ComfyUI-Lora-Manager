"""Tests for settings path resolution."""

import json
import logging
import os

import pytest

from py.utils.settings_paths import _should_use_portable_settings


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
