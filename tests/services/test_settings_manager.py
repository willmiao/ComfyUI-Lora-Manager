import json

import pytest

from py.services.settings_manager import SettingsManager
from py.utils import settings_paths


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)
    fake_settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(
        "py.services.settings_manager.ensure_settings_file",
        lambda logger=None: str(fake_settings_path),
    )
    mgr = SettingsManager()
    mgr.settings_file = str(fake_settings_path)
    return mgr


def test_environment_variable_overrides_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)
    monkeypatch.setenv("CIVITAI_API_KEY", "secret")
    fake_settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(
        "py.services.settings_manager.ensure_settings_file",
        lambda logger=None: str(fake_settings_path),
    )
    mgr = SettingsManager()
    mgr.settings_file = str(fake_settings_path)

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


def test_migrates_legacy_settings_file(tmp_path, monkeypatch):
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    legacy_file = legacy_root / "settings.json"
    legacy_file.write_text("{\"value\": 1}", encoding="utf-8")

    target_dir = tmp_path / "config"

    monkeypatch.setattr(settings_paths, "get_project_root", lambda: str(legacy_root))
    monkeypatch.setattr(settings_paths, "user_config_dir", lambda *_, **__: str(target_dir))

    migrated_path = settings_paths.ensure_settings_file()

    assert migrated_path == str(target_dir / "settings.json")
    assert (target_dir / "settings.json").exists()
    assert not legacy_file.exists()
