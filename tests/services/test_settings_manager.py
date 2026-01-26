import asyncio
import copy
import json
import os
from concurrent.futures import Future

import pytest

from py.services import service_registry
from py.services import settings_manager as settings_manager_module
from py.services.settings_manager import SettingsManager
from py.utils import settings_paths


@pytest.mark.no_settings_dir_isolation
def test_portable_settings_use_project_root(tmp_path, monkeypatch):
    from importlib import reload

    settings_paths_module = reload(settings_paths)
    monkeypatch.setattr(settings_paths_module, "get_project_root", lambda: str(tmp_path))
    monkeypatch.setattr(
        settings_paths_module,
        "user_config_dir",
        lambda *_args, **_kwargs: str(tmp_path / "user_config"),
    )

    portable_settings = {"use_portable_settings": True}
    (tmp_path / "settings.json").write_text(json.dumps(portable_settings), encoding="utf-8")

    config_dir = settings_paths_module.get_settings_dir(create=True)
    assert config_dir == str(tmp_path)

    from py.services import persistent_model_cache as persistent_model_cache_module

    cache_module = reload(persistent_model_cache_module)
    monkeypatch.setattr(cache_module.PersistentModelCache, "_instances", {})
    monkeypatch.delenv("LORA_MANAGER_CACHE_DB", raising=False)

    cache = cache_module.PersistentModelCache(library_name="portable_lib")
    expected_cache_path = tmp_path / "cache" / "model" / "portable_lib.sqlite"

    assert cache.get_database_path() == str(expected_cache_path)
    assert expected_cache_path.parent.is_dir()


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


def test_initial_save_persists_minimal_template(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"

    monkeypatch.setattr(
        "py.services.settings_manager.ensure_settings_file",
        lambda logger=None: str(settings_path),
    )

    template = {
        "_note": "template note",
        "language": "fr",
        "folder_paths": {"loras": ["/loras"]},
    }

    def fake_template_loader(self):
        self._seed_template = copy.deepcopy(template)
        return copy.deepcopy(template)

    monkeypatch.setattr(SettingsManager, "_load_settings_template", fake_template_loader)

    manager = SettingsManager()

    persisted = json.loads(settings_path.read_text(encoding="utf-8"))
    assert persisted["_note"] == "template note"
    assert "libraries" not in persisted
    assert persisted["folder_paths"]["loras"] == ["/loras"]
    assert manager.get_libraries()["default"]["folder_paths"]["loras"] == ["/loras"]


def test_existing_folder_paths_seed_default_library(tmp_path, monkeypatch):
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")

    lora_dir = tmp_path / "loras"
    checkpoint_dir = tmp_path / "checkpoints"
    unet_dir = tmp_path / "unet"
    diffusion_dir = tmp_path / "diffusion_models"
    embedding_dir = tmp_path / "embeddings"

    for directory in (lora_dir, checkpoint_dir, unet_dir, diffusion_dir, embedding_dir):
        directory.mkdir()

    initial = {
        "folder_paths": {
            "loras": [str(lora_dir)],
            "checkpoints": [str(checkpoint_dir)],
            "unet": [str(diffusion_dir), str(unet_dir)],
            "embeddings": [str(embedding_dir)],
        }
    }

    manager = _create_manager_with_settings(tmp_path, monkeypatch, initial)

    stored_paths = manager.get("folder_paths")
    assert stored_paths["loras"] == [str(lora_dir)]
    assert stored_paths["checkpoints"] == [str(checkpoint_dir)]
    assert stored_paths["unet"] == [str(diffusion_dir), str(unet_dir)]
    assert stored_paths["embeddings"] == [str(embedding_dir)]

    libraries = manager.get_libraries()
    assert "default" in libraries
    assert libraries["default"]["folder_paths"]["loras"] == [str(lora_dir)]
    assert libraries["default"]["folder_paths"]["checkpoints"] == [str(checkpoint_dir)]
    assert libraries["default"]["folder_paths"]["unet"] == [str(diffusion_dir), str(unet_dir)]
    assert libraries["default"]["folder_paths"]["embeddings"] == [str(embedding_dir)]

    assert manager.get_startup_messages() == []


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


def _create_manager_with_settings(tmp_path, monkeypatch, initial_settings, *, save_spy=None):
    """Helper to instantiate SettingsManager with predefined settings."""

    fake_settings_path = tmp_path / "settings.json"

    monkeypatch.setattr(
        "py.services.settings_manager.ensure_settings_file",
        lambda logger=None: str(fake_settings_path),
    )

    if save_spy is None:
        monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)
    else:
        monkeypatch.setattr(SettingsManager, "_save_settings", save_spy)

    monkeypatch.setattr(
        SettingsManager,
        "_load_settings",
        lambda self: copy.deepcopy(initial_settings),
    )

    mgr = SettingsManager()
    mgr.settings_file = str(fake_settings_path)
    return mgr


def _setup_storage_paths(tmp_path, monkeypatch):
    project_root = tmp_path / "repo"
    project_root.mkdir(parents=True, exist_ok=True)
    user_dir = tmp_path / "user_config"
    user_dir.mkdir(parents=True, exist_ok=True)
    user_settings_path = user_dir / "settings.json"

    monkeypatch.setattr(
        "py.services.settings_manager.ensure_settings_file",
        lambda logger=None: str(user_settings_path),
    )
    monkeypatch.setattr(
        settings_manager_module,
        "user_config_dir",
        lambda *args, **kwargs: str(user_dir),
    )
    monkeypatch.setattr(settings_paths, "get_project_root", lambda: str(project_root))
    return project_root, user_dir, user_settings_path


def _populate_cache(root_dir, marker_name, db_text):
    cache_dir = root_dir / "model_cache"
    cache_dir.mkdir(exist_ok=True)
    marker_file = cache_dir / marker_name
    marker_file.write_text(marker_name, encoding="utf-8")
    (root_dir / "model_cache.sqlite").write_text(db_text, encoding="utf-8")


def test_switch_to_portable_mode_copies_cache(tmp_path, monkeypatch):
    project_root, user_dir, user_settings = _setup_storage_paths(tmp_path, monkeypatch)
    _populate_cache(user_dir, "user_marker.txt", "user_db")

    manager = SettingsManager()

    manager.set("use_portable_settings", True)

    assert manager.settings_file == str(project_root / "settings.json")
    marker_copy = project_root / "model_cache" / "user_marker.txt"
    assert marker_copy.read_text(encoding="utf-8") == "user_marker.txt"
    assert (project_root / "model_cache.sqlite").read_text(encoding="utf-8") == "user_db"
    assert user_settings.exists()


def test_switching_back_to_user_config_moves_cache(tmp_path, monkeypatch):
    project_root, user_dir, user_settings = _setup_storage_paths(tmp_path, monkeypatch)
    _populate_cache(user_dir, "user_marker.txt", "user_db")

    manager = SettingsManager()
    manager.set("use_portable_settings", True)

    project_cache_dir = project_root / "model_cache"
    project_cache_dir.mkdir(exist_ok=True)
    (project_cache_dir / "project_marker.txt").write_text("project_marker", encoding="utf-8")
    (project_root / "model_cache.sqlite").write_text("project_db", encoding="utf-8")

    manager.set("use_portable_settings", False)

    assert manager.settings_file == str(user_settings)
    assert (user_dir / "model_cache" / "project_marker.txt").read_text(encoding="utf-8") == "project_marker"
    assert (user_dir / "model_cache.sqlite").read_text(encoding="utf-8") == "project_db"


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


def test_model_name_display_setting_notifies_scanners(tmp_path, monkeypatch):
    initial = {
        "libraries": {"default": {"folder_paths": {}, "default_lora_root": "", "default_checkpoint_root": "", "default_embedding_root": ""}},
        "active_library": "default",
        "model_name_display": "model_name",
    }

    manager = _create_manager_with_settings(tmp_path, monkeypatch, initial)

    loop = asyncio.new_event_loop()
    loop._thread_id = 1

    class DummyScanner:
        def __init__(self):
            self.calls = []
            self.loop = loop

        async def on_model_name_display_changed(self, mode: str) -> None:
            self.calls.append(mode)

    dummy_scanner = DummyScanner()

    dispatched_loops = []
    futures = []
    def tracking_run_coroutine_threadsafe(coro, target_loop):
        dispatched_loops.append(target_loop)
        future = Future()
        futures.append(future)
        try:
            result = asyncio.run(coro)
        except Exception as exc:
            future.set_exception(exc)
        else:
            future.set_result(result)
        return future

    def fake_get_service_sync(cls, name):
        return dummy_scanner if name == "lora_scanner" else None

    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_service_sync",
        classmethod(fake_get_service_sync),
    )
    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", tracking_run_coroutine_threadsafe)

    try:
        manager.set("model_name_display", "file_name")

        for future in futures:
            future.result(timeout=1)

        assert dummy_scanner.calls == ["file_name"]
        assert dispatched_loops == [dummy_scanner.loop]
    finally:
        loop._thread_id = None
        loop.close()


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


def test_uses_portable_settings_file_when_enabled(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo_settings = repo_root / "settings.json"
    repo_settings.write_text(
        json.dumps({"use_portable_settings": True, "value": 1}),
        encoding="utf-8",
    )

    user_dir = tmp_path / "user"

    monkeypatch.setattr(settings_paths, "get_project_root", lambda: str(repo_root))
    monkeypatch.setattr(settings_paths, "user_config_dir", lambda *_, **__: str(user_dir))

    resolved = settings_paths.ensure_settings_file()

    assert resolved == str(repo_settings)
    assert repo_settings.exists()
    assert not user_dir.exists()


def test_migrate_creates_default_library(manager):
    libraries = manager.get_libraries()
    assert "default" in libraries
    assert manager.get_active_library_name() == "default"
    assert libraries["default"].get("folder_paths", {}) == manager.settings.get("folder_paths", {})


def test_migrate_sanitizes_legacy_libraries(tmp_path, monkeypatch):
    initial = {
        "libraries": {"legacy": "not-a-dict"},
        "active_library": "legacy",
        "folder_paths": {"loras": ["/old"]},
    }

    manager = _create_manager_with_settings(tmp_path, monkeypatch, initial)

    libraries = manager.get_libraries()
    assert set(libraries.keys()) == {"legacy"}
    payload = libraries["legacy"]
    assert payload["folder_paths"] == {}
    assert payload["default_lora_root"] == ""
    assert payload["default_checkpoint_root"] == ""
    assert payload["default_embedding_root"] == ""
    assert manager.get_active_library_name() == "legacy"


def test_active_library_syncs_top_level_settings(tmp_path, monkeypatch):
    initial = {
        "libraries": {
            "default": {
                "folder_paths": {"loras": ["/loras"]},
                "default_lora_root": "/loras",
                "default_checkpoint_root": "/ckpt",
                "default_embedding_root": "/embed",
            },
            "studio": {
                "folder_paths": {"loras": ["/studio"]},
                "default_lora_root": "/studio",
                "default_checkpoint_root": "/studio_ckpt",
                "default_embedding_root": "/studio_embed",
            },
        },
        "active_library": "studio",
        # Drifted top-level values that should be corrected during init
        "folder_paths": {"loras": ["/loras"]},
        "default_lora_root": "/loras",
        "default_checkpoint_root": "/ckpt",
        "default_embedding_root": "/embed",
    }

    manager = _create_manager_with_settings(tmp_path, monkeypatch, initial)

    assert manager.get_active_library_name() == "studio"
    assert manager.get("folder_paths")["loras"] == ["/studio"]
    assert manager.get("default_lora_root") == "/studio"
    assert manager.get("default_checkpoint_root") == "/studio_ckpt"
    assert manager.get("default_embedding_root") == "/studio_embed"

    # Drift the top-level values again and ensure activate_library repairs them
    manager.settings["folder_paths"] = {"loras": ["/loras"]}
    manager.settings["default_lora_root"] = "/loras"
    manager.activate_library("studio")

    assert manager.get("folder_paths")["loras"] == ["/studio"]
    assert manager.get("default_lora_root") == "/studio"


def test_refresh_environment_variables_updates_stored_value(tmp_path, monkeypatch):
    calls = []

    def save_spy(self):
        calls.append(self.settings.get("civitai_api_key"))

    initial = {
        "civitai_api_key": "stale",
        "libraries": {"default": {"folder_paths": {}, "default_lora_root": "", "default_checkpoint_root": "", "default_embedding_root": ""}},
        "active_library": "default",
    }

    monkeypatch.setenv("CIVITAI_API_KEY", "from-init")
    manager = _create_manager_with_settings(tmp_path, monkeypatch, initial, save_spy=save_spy)

    assert calls[-1] == "from-init"

    monkeypatch.setenv("CIVITAI_API_KEY", "refreshed")
    manager.refresh_environment_variables()

    assert calls[-1] == "refreshed"


def test_upsert_library_creates_entry_and_activates(manager, tmp_path):
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()

    manager.upsert_library(
        "studio",
        folder_paths={"loras": [str(lora_dir)]},
        activate=True,
    )

    assert manager.get_active_library_name() == "studio"
    libraries = manager.get_libraries()
    stored_paths = libraries["studio"]["folder_paths"]["loras"]
    normalized_stored_paths = [p.replace(os.sep, "/") for p in stored_paths]
    assert str(lora_dir).replace(os.sep, "/") in normalized_stored_paths


def test_delete_library_switches_active(manager, tmp_path):
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    manager.create_library(
        "other",
        folder_paths={"loras": [str(other_dir)]},
        activate=True,
    )

    assert manager.get_active_library_name() == "other"

    manager.delete_library("other")

    assert manager.get_active_library_name() == "default"
