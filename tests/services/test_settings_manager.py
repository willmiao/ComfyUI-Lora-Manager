import json

import pytest

from py.services.settings_manager import SettingsManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)
    mgr = SettingsManager()
    mgr.settings_file = str(tmp_path / "settings.json")
    return mgr


def test_environment_variable_overrides_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)
    monkeypatch.setenv("CIVITAI_API_KEY", "secret")
    mgr = SettingsManager()
    mgr.settings_file = str(tmp_path / "settings.json")

    assert mgr.get("civitai_api_key") == "secret"


def test_download_path_template_parses_json_string(manager):
    templates = {"lora": "{author}", "checkpoint": "{author}", "embedding": "{author}"}
    manager.settings["download_path_templates"] = json.dumps(templates)

    template = manager.get_download_path_template("lora")

    assert template == "{author}"
    assert isinstance(manager.settings["download_path_templates"], dict)


def test_download_path_template_invalid_json(manager):
    manager.settings["download_path_templates"] = "not json"

    template = manager.get_download_path_template("checkpoint")

    assert template == "{base_model}/{first_tag}"
    assert manager.settings["download_path_templates"]["lora"] == "{base_model}/{first_tag}"


def test_auto_set_default_roots(manager):
    manager.settings["folder_paths"] = {
        "loras": ["/loras"],
        "checkpoints": ["/checkpoints"],
        "embeddings": ["/embeddings"],
    }

    manager._auto_set_default_roots()

    assert manager.get("default_lora_root") == "/loras"
    assert manager.get("default_checkpoint_root") == "/checkpoints"
    assert manager.get("default_embedding_root") == "/embeddings"


def test_delete_setting(manager):
    manager.set("example", 1)
    manager.delete("example")
    assert manager.get("example") is None
