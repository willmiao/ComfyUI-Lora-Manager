import importlib
import json
from pathlib import Path

import pytest

from py.services.settings_manager import get_settings_manager, reset_settings_manager
from py.utils import settings_paths


@pytest.fixture(autouse=True)
def reset_settings(tmp_path, monkeypatch):
    """Reset the settings manager and redirect config to a temp directory."""
    def fake_user_config_dir(*args, **kwargs):
        return str(tmp_path / "config")

    monkeypatch.setattr(settings_paths, "user_config_dir", fake_user_config_dir)
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")
    reset_settings_manager()
    yield
    reset_settings_manager()


def read_settings_file(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def read_example_settings() -> dict:
    example_path = Path(__file__).resolve().parents[1] / "settings.json.example"
    with example_path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def test_missing_settings_creates_defaults_and_emits_warnings(tmp_path):
    manager = get_settings_manager()
    settings_path = Path(manager.settings_file)

    assert settings_path.exists()
    assert read_settings_file(settings_path)

    messages = manager.get_startup_messages()
    codes = {message["code"] for message in messages}
    assert codes == {"missing-model-paths"}

    warning = messages[0]
    assert "default settings.json" in warning["message"].lower()
    assert warning["dismissible"] is False

    actions = warning.get("actions") or []
    assert actions == [
        {
            "action": "open-settings-location",
            "label": "Open settings folder",
            "type": "primary",
            "icon": "fas fa-folder-open",
        }
    ]


def test_template_settings_are_preserved_on_restart(tmp_path):
    manager = get_settings_manager()
    settings_path = Path(manager.settings_file)

    example_payload = read_example_settings()
    assert read_settings_file(settings_path) == example_payload

    reset_settings_manager()

    manager = get_settings_manager()
    assert Path(manager.settings_file) == settings_path
    assert read_settings_file(settings_path) == example_payload


def test_invalid_settings_recovers_with_defaults(tmp_path):
    config_dir = Path(settings_paths.user_config_dir())
    config_dir.mkdir(parents=True, exist_ok=True)
    settings_path = config_dir / "settings.json"
    settings_path.write_text("{ invalid json", encoding='utf-8')

    manager = get_settings_manager()

    assert settings_path.exists()
    data = read_settings_file(settings_path)
    assert isinstance(data, dict)

    codes = {message["code"] for message in manager.get_startup_messages()}
    assert "settings-json-invalid" in codes


def test_missing_settings_skips_warning_when_embedded(tmp_path, monkeypatch):
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "0")
    reset_settings_manager()

    manager = get_settings_manager()

    assert manager.get_startup_messages() == []


def test_validate_settings_logs_warnings(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(settings_paths, "user_config_dir", lambda *args, **kwargs: str(tmp_path / "config"))

    reset_settings_manager()
    import standalone
    importlib.reload(standalone)

    reset_settings_manager()

    with caplog.at_level("INFO", logger="lora-manager-standalone"):
        assert standalone.validate_settings() is True

    messages = [record.message for record in caplog.records]
    assert any("Standalone mode is using fallback configuration values." in message for message in messages)
