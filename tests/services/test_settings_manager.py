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
    monkeypatch.setattr(
        settings_paths_module, "get_project_root", lambda: str(tmp_path)
    )
    monkeypatch.setattr(
        settings_paths_module,
        "user_config_dir",
        lambda *_args, **_kwargs: str(tmp_path / "user_config"),
    )

    portable_settings = {"use_portable_settings": True}
    (tmp_path / "settings.json").write_text(
        json.dumps(portable_settings), encoding="utf-8"
    )

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

    monkeypatch.setattr(
        SettingsManager, "_load_settings_template", fake_template_loader
    )

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
    assert libraries["default"]["folder_paths"]["unet"] == [
        str(diffusion_dir),
        str(unet_dir),
    ]
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


def test_default_download_backend_is_python(manager):
    assert manager.get("download_backend") == "python"
    assert manager.get("aria2c_path") == ""


def _create_manager_with_settings(
    tmp_path, monkeypatch, initial_settings, *, save_spy=None
):
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
    assert (project_root / "model_cache.sqlite").read_text(
        encoding="utf-8"
    ) == "user_db"
    assert user_settings.exists()


def test_switching_back_to_user_config_moves_cache(tmp_path, monkeypatch):
    project_root, user_dir, user_settings = _setup_storage_paths(tmp_path, monkeypatch)
    _populate_cache(user_dir, "user_marker.txt", "user_db")

    manager = SettingsManager()
    manager.set("use_portable_settings", True)

    project_cache_dir = project_root / "model_cache"
    project_cache_dir.mkdir(exist_ok=True)
    (project_cache_dir / "project_marker.txt").write_text(
        "project_marker", encoding="utf-8"
    )
    (project_root / "model_cache.sqlite").write_text("project_db", encoding="utf-8")

    manager.set("use_portable_settings", False)

    assert manager.settings_file == str(user_settings)
    assert (user_dir / "model_cache" / "project_marker.txt").read_text(
        encoding="utf-8"
    ) == "project_marker"
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
    assert (
        manager.settings["download_path_templates"]["lora"]
        == "{base_model}/{first_tag}"
    )


def test_auto_set_default_roots(manager):
    # Clear any previously auto-set values to test fresh behavior
    manager.settings["default_lora_root"] = ""
    manager.settings["default_checkpoint_root"] = ""
    manager.settings["default_embedding_root"] = ""
    manager.settings["default_unet_root"] = ""

    manager.settings["folder_paths"] = {
        "loras": ["/loras"],
        "checkpoints": ["/checkpoints"],
        "embeddings": ["/embeddings"],
    }

    manager._auto_set_default_roots()

    assert manager.get("default_lora_root") == "/loras"
    assert manager.get("default_checkpoint_root") == "/checkpoints"
    assert manager.get("default_embedding_root") == "/embeddings"


def test_auto_set_default_roots_repairs_stale_values(manager):
    manager.settings["default_lora_root"] = "/stale-lora"
    manager.settings["default_checkpoint_root"] = "/stale-checkpoint"
    manager.settings["default_embedding_root"] = "/stale-embedding"
    manager.settings["default_unet_root"] = "/stale-unet"

    manager.settings["folder_paths"] = {
        "loras": ["/loras"],
        "checkpoints": ["/checkpoints"],
        "unet": ["/unet"],
        "embeddings": ["/embeddings"],
    }

    manager._auto_set_default_roots()

    assert manager.get("default_lora_root") == "/loras"
    assert manager.get("default_checkpoint_root") == "/checkpoints"
    assert manager.get("default_unet_root") == "/unet"
    assert manager.get("default_embedding_root") == "/embeddings"


def test_auto_set_default_roots_keeps_valid_values(manager):
    manager.settings["default_lora_root"] = "/loras"
    manager.settings["default_checkpoint_root"] = "/checkpoints"
    manager.settings["default_embedding_root"] = "/embeddings"
    manager.settings["default_unet_root"] = "/unet"

    manager.settings["folder_paths"] = {
        "loras": ["/loras", "/other-loras"],
        "checkpoints": ["/checkpoints"],
        "unet": ["/unet", "/other-unet"],
        "embeddings": ["/embeddings"],
    }

    manager._auto_set_default_roots()

    assert manager.get("default_lora_root") == "/loras"
    assert manager.get("default_checkpoint_root") == "/checkpoints"
    assert manager.get("default_unet_root") == "/unet"
    assert manager.get("default_embedding_root") == "/embeddings"


def test_auto_set_default_roots_keeps_valid_extra_values(manager):
    manager.settings["default_lora_root"] = "/extra-loras"
    manager.settings["default_checkpoint_root"] = "/extra-checkpoints"
    manager.settings["default_embedding_root"] = "/extra-embeddings"
    manager.settings["default_unet_root"] = "/extra-unet"

    manager.settings["folder_paths"] = {
        "loras": ["/loras"],
        "checkpoints": ["/checkpoints"],
        "unet": ["/unet"],
        "embeddings": ["/embeddings"],
    }
    manager.settings["extra_folder_paths"] = {
        "loras": ["/extra-loras"],
        "checkpoints": ["/extra-checkpoints"],
        "unet": ["/extra-unet"],
        "embeddings": ["/extra-embeddings"],
    }

    manager._auto_set_default_roots()

    assert manager.get("default_lora_root") == "/extra-loras"
    assert manager.get("default_checkpoint_root") == "/extra-checkpoints"
    assert manager.get("default_unet_root") == "/extra-unet"
    assert manager.get("default_embedding_root") == "/extra-embeddings"


def test_auto_set_default_roots_keeps_valid_extra_values_with_windows_slash_mismatch(manager):
    manager.settings["default_lora_root"] = "U:/Lora7/Loras"
    manager.settings["default_checkpoint_root"] = "U:/Lora7/Models"

    manager.settings["folder_paths"] = {
        "loras": ["R:/ComfyUI/models/loras"],
        "checkpoints": ["R:/ComfyUI/models/checkpoints"],
    }
    manager.settings["extra_folder_paths"] = {
        "loras": ["U:\\Lora7\\Loras"],
        "checkpoints": ["U:\\Lora7\\Models"],
    }

    manager._auto_set_default_roots()

    assert manager.get("default_lora_root") == "U:/Lora7/Loras"
    assert manager.get("default_checkpoint_root") == "U:/Lora7/Models"


def test_auto_set_default_roots_falls_back_to_extra_when_primary_missing(manager):
    manager.settings["default_lora_root"] = ""
    manager.settings["folder_paths"] = {"loras": []}
    manager.settings["extra_folder_paths"] = {"loras": ["/extra-loras"]}

    manager._auto_set_default_roots()

    assert manager.get("default_lora_root") == "/extra-loras"


def test_delete_setting(manager):
    manager.set("example", 1)
    manager.delete("example")
    assert manager.get("example") is None


def test_missing_mature_blur_level_defaults_to_r(tmp_path, monkeypatch):
    manager = _create_manager_with_settings(
        tmp_path,
        monkeypatch,
        {
            "blur_mature_content": True,
            "folder_paths": {},
        },
    )

    assert manager.get("mature_blur_level") == "R"


def test_invalid_mature_blur_level_is_normalized_to_r(tmp_path, monkeypatch):
    manager = _create_manager_with_settings(
        tmp_path,
        monkeypatch,
        {
            "mature_blur_level": "unsafe",
            "folder_paths": {},
        },
    )

    assert manager.get("mature_blur_level") == "R"


def test_model_name_display_setting_notifies_scanners(tmp_path, monkeypatch):
    initial = {
        "libraries": {
            "default": {
                "folder_paths": {},
                "default_lora_root": "",
                "default_checkpoint_root": "",
                "default_embedding_root": "",
            }
        },
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
    monkeypatch.setattr(
        asyncio, "run_coroutine_threadsafe", tracking_run_coroutine_threadsafe
    )

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
    legacy_file.write_text('{"value": 1}', encoding="utf-8")

    target_dir = tmp_path / "config"

    monkeypatch.setattr(settings_paths, "get_project_root", lambda: str(legacy_root))
    monkeypatch.setattr(
        settings_paths, "user_config_dir", lambda *_, **__: str(target_dir)
    )

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
    monkeypatch.setattr(
        settings_paths, "user_config_dir", lambda *_, **__: str(user_dir)
    )

    resolved = settings_paths.ensure_settings_file()

    assert resolved == str(repo_settings)
    assert repo_settings.exists()
    assert not user_dir.exists()


def test_migrate_creates_default_library(manager):
    libraries = manager.get_libraries()
    assert "default" in libraries
    assert manager.get_active_library_name() == "default"
    assert libraries["default"].get("folder_paths", {}) == manager.settings.get(
        "folder_paths", {}
    )


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
    assert payload["recipes_path"] == ""
    assert manager.get_active_library_name() == "legacy"


def test_active_library_syncs_top_level_settings(tmp_path, monkeypatch):
    initial = {
        "libraries": {
            "default": {
                "folder_paths": {"loras": ["/loras"]},
                "default_lora_root": "/loras",
                "default_checkpoint_root": "/ckpt",
                "default_embedding_root": "/embed",
                "recipes_path": "/loras/recipes",
            },
            "studio": {
                "folder_paths": {"loras": ["/studio"]},
                "default_lora_root": "/studio",
                "default_checkpoint_root": "/studio_ckpt",
                "default_embedding_root": "/studio_embed",
                "recipes_path": "/studio/custom-recipes",
            },
        },
        "active_library": "studio",
        # Drifted top-level values that should be corrected during init
        "folder_paths": {"loras": ["/loras"]},
        "default_lora_root": "/loras",
        "default_checkpoint_root": "/ckpt",
        "default_embedding_root": "/embed",
        "recipes_path": "/loras/recipes",
    }

    manager = _create_manager_with_settings(tmp_path, monkeypatch, initial)

    assert manager.get_active_library_name() == "studio"
    assert manager.get("folder_paths")["loras"] == ["/studio"]
    assert manager.get("default_lora_root") == "/studio"
    assert manager.get("default_checkpoint_root") == "/studio_ckpt"
    assert manager.get("default_embedding_root") == "/studio_embed"
    assert manager.get("recipes_path") == "/studio/custom-recipes"

    # Drift the top-level values again and ensure activate_library repairs them
    manager.settings["folder_paths"] = {"loras": ["/loras"]}
    manager.settings["default_lora_root"] = "/loras"
    manager.settings["recipes_path"] = "/loras/recipes"
    manager.activate_library("studio")

    assert manager.get("folder_paths")["loras"] == ["/studio"]
    assert manager.get("default_lora_root") == "/studio"
    assert manager.get("recipes_path") == "/studio/custom-recipes"


def test_refresh_environment_variables_updates_stored_value(tmp_path, monkeypatch):
    calls = []

    def save_spy(self):
        calls.append(self.settings.get("civitai_api_key"))

    initial = {
        "civitai_api_key": "stale",
        "libraries": {
            "default": {
                "folder_paths": {},
                "default_lora_root": "",
                "default_checkpoint_root": "",
                "default_embedding_root": "",
                "recipes_path": "",
            }
        },
        "active_library": "default",
    }

    monkeypatch.setenv("CIVITAI_API_KEY", "from-init")
    manager = _create_manager_with_settings(
        tmp_path, monkeypatch, initial, save_spy=save_spy
    )

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


def test_set_recipes_path_updates_active_library_entry(manager, tmp_path):
    recipes_dir = tmp_path / "custom" / "recipes"

    manager.set("recipes_path", str(recipes_dir))

    assert manager.get("recipes_path") == str(recipes_dir.resolve())
    assert (
        manager.get_libraries()["default"]["recipes_path"]
        == str(recipes_dir.resolve())
    )


def test_set_recipes_path_migrates_existing_recipe_files(manager, tmp_path):
    lora_root = tmp_path / "loras"
    old_recipes_dir = lora_root / "recipes" / "nested"
    old_recipes_dir.mkdir(parents=True)
    manager.set("folder_paths", {"loras": [str(lora_root)]})

    recipe_id = "recipe-1"
    old_image_path = old_recipes_dir / f"{recipe_id}.webp"
    old_json_path = old_recipes_dir / f"{recipe_id}.recipe.json"
    old_image_path.write_bytes(b"image-bytes")
    old_json_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": str(old_image_path),
                "title": "Recipe 1",
            }
        ),
        encoding="utf-8",
    )

    new_recipes_dir = tmp_path / "custom_recipes"
    manager.set("recipes_path", str(new_recipes_dir))

    migrated_image_path = new_recipes_dir / "nested" / f"{recipe_id}.webp"
    migrated_json_path = new_recipes_dir / "nested" / f"{recipe_id}.recipe.json"

    assert manager.get("recipes_path") == str(new_recipes_dir.resolve())
    assert migrated_image_path.read_bytes() == b"image-bytes"
    migrated_payload = json.loads(migrated_json_path.read_text(encoding="utf-8"))
    assert migrated_payload["file_path"] == str(migrated_image_path)
    assert not old_image_path.exists()
    assert not old_json_path.exists()


def test_clearing_recipes_path_migrates_files_to_default_location(manager, tmp_path):
    lora_root = tmp_path / "loras"
    custom_recipes_dir = tmp_path / "custom_recipes"
    old_recipes_dir = custom_recipes_dir / "nested"
    old_recipes_dir.mkdir(parents=True)
    manager.set("folder_paths", {"loras": [str(lora_root)]})
    manager.settings["recipes_path"] = str(custom_recipes_dir)

    recipe_id = "recipe-2"
    old_image_path = old_recipes_dir / f"{recipe_id}.webp"
    old_json_path = old_recipes_dir / f"{recipe_id}.recipe.json"
    old_image_path.write_bytes(b"image-bytes")
    old_json_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": str(old_image_path),
                "title": "Recipe 2",
            }
        ),
        encoding="utf-8",
    )

    manager.set("recipes_path", "")

    fallback_recipes_dir = lora_root / "recipes"
    migrated_image_path = fallback_recipes_dir / "nested" / f"{recipe_id}.webp"
    migrated_json_path = fallback_recipes_dir / "nested" / f"{recipe_id}.recipe.json"

    assert manager.get("recipes_path") == ""
    assert migrated_image_path.read_bytes() == b"image-bytes"
    migrated_payload = json.loads(migrated_json_path.read_text(encoding="utf-8"))
    assert migrated_payload["file_path"] == str(migrated_image_path)
    assert not old_image_path.exists()
    assert not old_json_path.exists()


def test_moving_recipes_path_back_to_parent_directory_is_allowed(manager, tmp_path):
    lora_root = tmp_path / "loras"
    manager.set("folder_paths", {"loras": [str(lora_root)]})

    source_recipes_dir = lora_root / "recipes" / "custom"
    source_recipes_dir.mkdir(parents=True)

    recipe_id = "recipe-parent"
    old_image_path = source_recipes_dir / f"{recipe_id}.webp"
    old_json_path = source_recipes_dir / f"{recipe_id}.recipe.json"
    old_image_path.write_bytes(b"parent-bytes")
    old_json_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": str(old_image_path),
                "title": "Recipe Parent",
            }
        ),
        encoding="utf-8",
    )

    manager.settings["recipes_path"] = str(source_recipes_dir)
    manager.set("recipes_path", str(lora_root / "recipes"))

    migrated_image_path = lora_root / "recipes" / f"{recipe_id}.webp"
    migrated_json_path = lora_root / "recipes" / f"{recipe_id}.recipe.json"

    assert manager.get("recipes_path") == str((lora_root / "recipes").resolve())
    assert migrated_image_path.read_bytes() == b"parent-bytes"
    migrated_payload = json.loads(migrated_json_path.read_text(encoding="utf-8"))
    assert migrated_payload["file_path"] == str(migrated_image_path)
    assert not old_image_path.exists()
    assert not old_json_path.exists()


def test_set_recipes_path_rewrites_symlinked_recipe_metadata(manager, tmp_path):
    real_recipes_dir = tmp_path / "real_recipes"
    real_recipes_dir.mkdir()
    symlink_recipes_dir = tmp_path / "linked_recipes"
    symlink_recipes_dir.symlink_to(real_recipes_dir, target_is_directory=True)

    manager.settings["recipes_path"] = str(symlink_recipes_dir)
    manager.set("folder_paths", {"loras": [str(tmp_path / "loras")]})

    recipe_id = "recipe-symlink"
    old_image_path = real_recipes_dir / f"{recipe_id}.webp"
    old_json_path = real_recipes_dir / f"{recipe_id}.recipe.json"
    old_image_path.write_bytes(b"symlink-bytes")
    old_json_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": str(old_image_path),
                "title": "Recipe Symlink",
            }
        ),
        encoding="utf-8",
    )

    new_recipes_dir = tmp_path / "migrated_recipes"
    manager.set("recipes_path", str(new_recipes_dir))

    migrated_image_path = new_recipes_dir / f"{recipe_id}.webp"
    migrated_json_path = new_recipes_dir / f"{recipe_id}.recipe.json"

    assert migrated_image_path.read_bytes() == b"symlink-bytes"
    migrated_payload = json.loads(migrated_json_path.read_text(encoding="utf-8"))
    assert migrated_payload["file_path"] == str(migrated_image_path)
    assert not old_image_path.exists()
    assert not old_json_path.exists()


def test_set_recipes_path_rejects_file_target(manager, tmp_path):
    lora_root = tmp_path / "loras"
    lora_root.mkdir()
    manager.set("folder_paths", {"loras": [str(lora_root)]})

    target_file = tmp_path / "not_a_directory"
    target_file.write_text("blocked", encoding="utf-8")

    with pytest.raises(ValueError, match="directory"):
        manager.set("recipes_path", str(target_file))

    assert manager.get("recipes_path") == ""


def test_extra_folder_paths_stored_separately(manager, tmp_path):
    lora_dir = tmp_path / "loras"
    extra_dir = tmp_path / "extra_loras"
    lora_dir.mkdir()
    extra_dir.mkdir()

    manager.upsert_library(
        "test_library",
        folder_paths={"loras": [str(lora_dir)]},
        extra_folder_paths={"loras": [str(extra_dir)]},
        activate=True,
    )

    libraries = manager.get_libraries()
    lib = libraries["test_library"]

    # Verify folder_paths contains main path
    assert str(lora_dir) in lib["folder_paths"]["loras"]
    # Verify extra_folder_paths contains extra path
    assert str(extra_dir) in lib["extra_folder_paths"]["loras"]
    # Verify they are separate
    assert str(extra_dir) not in lib["folder_paths"]["loras"]


def test_get_extra_folder_paths(manager, tmp_path):
    extra_dir = tmp_path / "extra_loras"
    extra_dir.mkdir()

    manager.update_extra_folder_paths({"loras": [str(extra_dir)]})

    extra_paths = manager.get_extra_folder_paths()
    assert str(extra_dir) in extra_paths.get("loras", [])


def test_library_switch_preserves_extra_paths(manager, tmp_path):
    """Test that switching libraries preserves each library's extra paths."""
    lora_dir1 = tmp_path / "lib1_loras"
    extra_dir1 = tmp_path / "lib1_extra"
    lora_dir2 = tmp_path / "lib2_loras"
    extra_dir2 = tmp_path / "lib2_extra"

    for directory in (lora_dir1, extra_dir1, lora_dir2, extra_dir2):
        directory.mkdir()

    manager.create_library(
        "library1",
        folder_paths={"loras": [str(lora_dir1)]},
        extra_folder_paths={"loras": [str(extra_dir1)]},
        activate=True,
    )

    manager.create_library(
        "library2",
        folder_paths={"loras": [str(lora_dir2)]},
        extra_folder_paths={"loras": [str(extra_dir2)]},
    )

    assert manager.get_active_library_name() == "library1"
    lib1 = manager.get_active_library()
    assert str(lora_dir1) in lib1["folder_paths"]["loras"]
    assert str(extra_dir1) in lib1["extra_folder_paths"]["loras"]

    manager.activate_library("library2")

    assert manager.get_active_library_name() == "library2"
    lib2 = manager.get_active_library()
    assert str(lora_dir2) in lib2["folder_paths"]["loras"]
    assert str(extra_dir2) in lib2["extra_folder_paths"]["loras"]


def test_extra_paths_validation_no_overlap_with_other_libraries(manager, tmp_path):
    """Test that extra paths cannot overlap with other libraries' paths."""
    lora_dir1 = tmp_path / "lib1_loras"
    lora_dir1.mkdir()

    manager.create_library(
        "library1",
        folder_paths={"loras": [str(lora_dir1)]},
        activate=True,
    )

    extra_dir = tmp_path / "extra_loras"
    extra_dir.mkdir()

    manager.create_library(
        "library2",
        folder_paths={"loras": [str(extra_dir)]},
        activate=True,
    )

    with pytest.raises(ValueError, match="already assigned to library"):
        manager.update_extra_folder_paths({"loras": [str(lora_dir1)]})


def test_extra_paths_validation_no_overlap_with_active_primary_lora_root(
    manager, tmp_path
):
    """Test that extra LoRA paths cannot overlap the active library primary LoRA roots."""
    real_lora_dir = tmp_path / "loras_real"
    real_lora_dir.mkdir()
    lora_link = tmp_path / "loras_link"
    lora_link.symlink_to(real_lora_dir, target_is_directory=True)

    manager.create_library(
        "library1",
        folder_paths={"loras": [str(lora_link)]},
        activate=True,
    )

    with pytest.raises(
        ValueError, match="overlap with the active library's primary LoRA roots"
    ):
        manager.update_extra_folder_paths({"loras": [str(real_lora_dir)]})


def test_extra_paths_validation_no_overlap_with_active_primary_lora_root_case_insensitive(
    manager, monkeypatch, tmp_path
):
    """Overlap validation should treat differently-cased Windows-like paths as the same path."""
    real_lora_dir = tmp_path / "loras_real"
    real_lora_dir.mkdir()
    lora_link = tmp_path / "loras_link"
    lora_link.symlink_to(real_lora_dir, target_is_directory=True)

    manager.create_library(
        "library1",
        folder_paths={"loras": [str(lora_link)]},
        activate=True,
    )

    original_exists = settings_manager_module.os.path.exists
    original_realpath = settings_manager_module.os.path.realpath
    original_normcase = settings_manager_module.os.path.normcase

    def fake_exists(path):
        if isinstance(path, str) and path.lower() in {
            str(lora_link).lower(),
            str(real_lora_dir).lower(),
        }:
            return True
        return original_exists(path)

    def fake_realpath(path):
        if isinstance(path, str) and path.lower() == str(lora_link).lower():
            return str(real_lora_dir)
        return original_realpath(path)

    monkeypatch.setattr(settings_manager_module.os.path, "exists", fake_exists)
    monkeypatch.setattr(settings_manager_module.os.path, "realpath", fake_realpath)
    monkeypatch.setattr(
        settings_manager_module.os.path,
        "normcase",
        lambda value: original_normcase(value).lower(),
    )

    with pytest.raises(
        ValueError, match="overlap with the active library's primary LoRA roots"
    ):
        manager.update_extra_folder_paths({"loras": [str(real_lora_dir).upper()]})


def test_extra_paths_validation_allows_missing_non_overlapping_lora_root(
    manager, tmp_path
):
    """Missing non-overlapping extra LoRA paths should not be rejected."""
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()
    missing_extra = tmp_path / "missing_loras"

    manager.create_library(
        "library1",
        folder_paths={"loras": [str(lora_dir)]},
        activate=True,
    )

    manager.update_extra_folder_paths({"loras": [str(missing_extra)]})

    extra_paths = manager.get_extra_folder_paths()
    assert extra_paths["loras"] == [str(missing_extra)]


def test_extra_paths_validation_rejects_primary_root_first_level_symlink_target(
    manager, tmp_path
):
    """Extra LoRA paths should be rejected when already reachable via a first-level symlink under the primary root."""
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()
    external_dir = tmp_path / "external_loras"
    external_dir.mkdir()
    link_dir = lora_dir / "link"
    link_dir.symlink_to(external_dir, target_is_directory=True)

    manager.create_library(
        "library1",
        folder_paths={"loras": [str(lora_dir)]},
        activate=True,
    )

    with pytest.raises(
        ValueError, match="overlap with the active library's primary LoRA roots"
    ):
        manager.update_extra_folder_paths({"loras": [str(external_dir)]})


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


def test_download_skip_base_models_are_normalized(manager):
    manager.settings["download_skip_base_models"] = [
        "SDXL 1.0",
        "Invalid",
        "SDXL 1.0",
        "Pony",
        "Other",
    ]

    result = manager.get_download_skip_base_models()

    assert result == ["SDXL 1.0", "Pony"]
    assert manager.settings["download_skip_base_models"] == ["SDXL 1.0", "Pony"]


def test_setting_download_skip_base_models_normalizes_string_input(manager):
    manager.set("download_skip_base_models", "SDXL 1.0, Pony; Invalid\nSDXL 1.0")

    assert manager.get("download_skip_base_models") == ["SDXL 1.0", "Pony"]


def test_skip_previously_downloaded_model_versions_defaults_false(manager):
    assert manager.get_skip_previously_downloaded_model_versions() is False


def test_skip_previously_downloaded_model_versions_coerces_string_input(manager):
    manager.settings["skip_previously_downloaded_model_versions"] = "true"

    assert manager.get_skip_previously_downloaded_model_versions() is True
    assert manager.settings["skip_previously_downloaded_model_versions"] is True
