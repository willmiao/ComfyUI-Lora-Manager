import json
from typing import Any, Optional

import pytest

from py.config import config
from py.routes.handlers.misc_handlers import SettingsHandler


class FakeRequest:
    def __init__(self, *, json_data=None):
        self._json_data = json_data or {}

    async def json(self):
        return self._json_data


class DummySettings:
    def __init__(self):
        self.activated = None
        self.should_raise: Optional[Exception] = None

    def activate_library(self, name):
        if self.should_raise:
            raise self.should_raise
        self.activated = name


def json_payload(response) -> Any:
    """Decode the JSON body of a web.Response, asserting it is not null."""
    text = response.text
    assert text is not None
    return json.loads(text)


class DummyDownloader:
    async def refresh_session(self):  # pragma: no cover - helper
        return None


async def dummy_downloader_factory():  # pragma: no cover - helper
    return DummyDownloader()


async def noop_async(*_args, **_kwargs):  # pragma: no cover - helper
    return None


@pytest.fixture
def handler():
    return SettingsHandler(
        settings_service=DummySettings(),
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
    )


@pytest.mark.asyncio
async def test_get_libraries_returns_registry(monkeypatch, handler):
    registry = {"libraries": {"default": {"name": "Default"}}, "active_library": "default"}
    monkeypatch.setattr(config, "get_library_registry_snapshot", lambda: registry)

    response = await handler.get_libraries(FakeRequest())
    payload = json_payload(response)

    assert response.status == 200
    assert payload == {
        "success": True,
        "libraries": registry["libraries"],
        "active_library": "default",
    }


@pytest.mark.asyncio
async def test_get_libraries_handles_errors(monkeypatch, handler):
    def boom():
        raise RuntimeError("exploded")

    monkeypatch.setattr(config, "get_library_registry_snapshot", boom)

    response = await handler.get_libraries(FakeRequest())
    payload = json_payload(response)

    assert response.status == 500
    assert payload["success"] is False
    assert payload["error"] == "exploded"


@pytest.mark.asyncio
async def test_activate_library_success(monkeypatch):
    dummy_settings = DummySettings()
    handler = SettingsHandler(
        settings_service=dummy_settings,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
    )

    registry = {"libraries": {"alpha": {"name": "Alpha"}}, "active_library": "alpha"}
    monkeypatch.setattr(config, "get_library_registry_snapshot", lambda: registry)

    response = await handler.activate_library(
    FakeRequest(json_data={"library": "alpha"})  # pyright: ignore[reportArgumentType]
)
    payload = json_payload(response)

    assert response.status == 200
    assert payload == {
        "success": True,
        "active_library": "alpha",
        "libraries": registry["libraries"],
    }
    assert dummy_settings.activated == "alpha"


@pytest.mark.asyncio
async def test_activate_library_requires_name(handler):
    response = await handler.activate_library(FakeRequest(json_data={}))
    payload = json_payload(response)

    assert response.status == 400
    assert payload["success"] is False
    assert payload["error"] == "Library name is required"


@pytest.mark.asyncio
async def test_activate_library_unknown_returns_404(monkeypatch):
    dummy_settings = DummySettings()
    dummy_settings.should_raise = KeyError("Unknown library")
    handler = SettingsHandler(
        settings_service=dummy_settings,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
    )

    response = await handler.activate_library(
    FakeRequest(json_data={"library": "ghost"})  # pyright: ignore[reportArgumentType]
)
    payload = json_payload(response)

    assert response.status == 404
    assert payload["success"] is False
    assert payload["error"] == "'Unknown library'"


@pytest.mark.asyncio
async def test_activate_library_unexpected_error_returns_500(monkeypatch):
    dummy_settings = DummySettings()
    dummy_settings.should_raise = ValueError("bad things")
    handler = SettingsHandler(
        settings_service=dummy_settings,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
    )

    response = await handler.activate_library(
    FakeRequest(json_data={"library": "broken"})  # pyright: ignore[reportArgumentType]
)
    payload = json_payload(response)

    assert response.status == 500
    assert payload["success"] is False
    assert payload["error"] == "bad things"


class DummySettingsForGet:
    def __init__(self, values=None):
        self._values = dict(values or {})
        self.settings_file = "/tmp/settings.json"
        self.set_calls = []

    def keys(self):
        return self._values.keys()

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self.set_calls.append((key, value))
        self._values[key] = value

    def get_startup_messages(self):
        return []


def make_get_handler(values=None) -> SettingsHandler:
    return SettingsHandler(
        settings_service=DummySettingsForGet(values),
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
    )


@pytest.fixture
def patch_other_models_availability(monkeypatch):
    monkeypatch.setattr(
        config,
        "get_other_models_availability",
        lambda: {"available": False},
    )


@pytest.mark.asyncio
async def test_get_settings_plugin_mode_hides_folder_paths(
    monkeypatch, patch_other_models_availability
):
    monkeypatch.delenv("LORA_MANAGER_STANDALONE", raising=False)
    handler = make_get_handler(
        {
            "language": "en",
            "folder_paths": {"loras": ["/models/loras"]},
        }
    )

    response = await handler.get_settings(FakeRequest())
    payload = json_payload(response)

    assert response.status == 200
    settings = payload["settings"]
    assert settings["standalone_mode"] is False
    assert "folder_paths" not in settings
    assert "folder_path_schema" not in settings


@pytest.mark.asyncio
async def test_get_settings_standalone_exposes_folder_paths_and_schema(
    monkeypatch, patch_other_models_availability
):
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")
    folder_paths = {"loras": ["/models/loras"], "vae": ["/models/vae"]}
    handler = make_get_handler({"language": "en", "folder_paths": folder_paths})

    response = await handler.get_settings(FakeRequest())
    payload = json_payload(response)

    assert response.status == 200
    settings = payload["settings"]
    assert settings["standalone_mode"] is True
    assert settings["folder_paths"] == folder_paths

    schema = settings["folder_path_schema"]
    core_keys = [entry["key"] for entry in schema if entry["category"] == "core"]
    assert core_keys == ["loras", "checkpoints", "unet", "embeddings"]
    other_entries = {entry["key"]: entry for entry in schema if entry["category"] == "other"}
    assert other_entries["vae"]["sub_type"] == "vae"
    assert other_entries["text_encoders"]["sub_type"] == "text_encoder"


@pytest.mark.asyncio
async def test_update_settings_passes_folder_paths_through(
    monkeypatch, patch_other_models_availability
):
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")
    handler = make_get_handler({"folder_paths": {}})
    new_paths = {"loras": ["/models/loras"]}

    response = await handler.update_settings(
        FakeRequest(json_data={"folder_paths": new_paths})
    )
    payload = json_payload(response)

    assert response.status == 200
    assert payload["success"] is True
    assert handler._settings.set_calls == [("folder_paths", new_paths)]


@pytest.mark.asyncio
async def test_get_settings_standalone_filters_template_placeholders(
    monkeypatch, patch_other_models_availability
):
    """Fresh installs are seeded from settings.json.example; its placeholder
    paths must not show up as real values in the Model Paths UI."""
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")
    handler = make_get_handler(
        {
            "folder_paths": {
                "loras": ["C:/path/to/your/loras_folder", "/real/loras"],
                "vae": ["C:/path/to/another/vae_folder"],
            }
        }
    )
    handler._settings.get_template_folder_path_placeholders = lambda: {
        "C:/path/to/your/loras_folder",
        "C:/path/to/another/vae_folder",
    }

    response = await handler.get_settings(FakeRequest())
    payload = json_payload(response)

    assert response.status == 200
    assert payload["settings"]["folder_paths"] == {
        "loras": ["/real/loras"],
        "vae": [],
    }
