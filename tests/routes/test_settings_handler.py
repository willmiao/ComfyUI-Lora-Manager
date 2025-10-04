import json

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
        self.should_raise = None

    def activate_library(self, name):
        if self.should_raise:
            raise self.should_raise
        self.activated = name


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
    payload = json.loads(response.text)

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
    payload = json.loads(response.text)

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

    response = await handler.activate_library(FakeRequest(json_data={"library": "alpha"}))
    payload = json.loads(response.text)

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
    payload = json.loads(response.text)

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

    response = await handler.activate_library(FakeRequest(json_data={"library": "ghost"}))
    payload = json.loads(response.text)

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

    response = await handler.activate_library(FakeRequest(json_data={"library": "broken"}))
    payload = json.loads(response.text)

    assert response.status == 500
    assert payload["success"] is False
    assert payload["error"] == "bad things"
