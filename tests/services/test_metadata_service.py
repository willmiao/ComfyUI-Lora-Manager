from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from py.services import metadata_service
from py.services.model_metadata_provider import (
    FallbackMetadataProvider,
    ModelMetadataProvider,
    RateLimitRetryingProvider,
)


class DummyProvider(ModelMetadataProvider):
    async def get_model_by_hash(self, model_hash: str):
        return None, None

    async def get_model_versions(self, model_id: str):
        return None

    async def get_model_versions_bulk(self, model_ids):
        return None

    async def get_model_version(self, model_id: int = None, version_id: int = None):
        return None

    async def get_model_version_info(self, version_id: str):
        return None, None

    async def get_user_models(self, username: str):
        return None


@pytest.mark.asyncio
async def test_get_metadata_provider_wraps_non_fallback(monkeypatch):
    provider = DummyProvider()
    dummy_manager = SimpleNamespace(_get_provider=lambda _name=None: provider)
    monkeypatch.setattr(
        metadata_service.ModelMetadataProviderManager,
        "get_instance",
        AsyncMock(return_value=dummy_manager),
    )

    wrapped = await metadata_service.get_metadata_provider("dummy")

    assert isinstance(wrapped, RateLimitRetryingProvider)
    assert wrapped is not provider


@pytest.mark.asyncio
async def test_get_metadata_provider_returns_fallback_as_is(monkeypatch):
    fallback = FallbackMetadataProvider([("dummy", DummyProvider())])
    dummy_manager = SimpleNamespace(_get_provider=lambda _name=None: fallback)
    monkeypatch.setattr(
        metadata_service.ModelMetadataProviderManager,
        "get_instance",
        AsyncMock(return_value=dummy_manager),
    )

    provider = await metadata_service.get_metadata_provider()

    assert provider is fallback


# ---------------------------------------------------------------------------
# initialize_metadata_providers — provider gating + fallback ordering
# ---------------------------------------------------------------------------


def _stub_settings(**overrides):
    """Minimal settings stub returning configured values."""
    base = {
        "enable_metadata_archive_db": False,
        "enable_civarchive_api": True,
        "metadata_provider_order": "civitai_archive_sqlite",
    }
    base.update(overrides)
    return SimpleNamespace(get=lambda key, default=None: base.get(key, default))


async def _run_initialize(monkeypatch, settings):
    # Fresh provider manager for each test
    monkeypatch.setattr(
        metadata_service.ModelMetadataProviderManager,
        "get_instance",
        AsyncMock(return_value=metadata_service.ModelMetadataProviderManager()),
    )
    monkeypatch.setattr(
        metadata_service, "get_settings_manager", lambda: settings
    )
    monkeypatch.setattr(
        metadata_service.ServiceRegistry,
        "get_civitai_client",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        metadata_service.ServiceRegistry,
        "get_civarchive_client",
        AsyncMock(return_value=object()),
    )

    # Make MetadataArchiveManager report a usable db path when enabled
    fake_archive = SimpleNamespace(get_database_path=lambda: "/tmp/fake.db")
    monkeypatch.setattr(
        metadata_service, "MetadataArchiveManager", lambda _base: fake_archive
    )
    # Pretend the db file exists
    monkeypatch.setattr(metadata_service.os.path, "exists", lambda _p: True)

    manager = await metadata_service.initialize_metadata_providers()
    return manager


def _fallback_provider_order(manager):
    """Return the ordered list of provider labels inside the fallback provider."""
    fallback = manager.providers.get("fallback")
    assert isinstance(fallback, FallbackMetadataProvider), "expected a fallback provider"
    return list(fallback._provider_labels)


@pytest.mark.asyncio
async def test_initialize_providers_default_order(monkeypatch):
    settings = _stub_settings(enable_metadata_archive_db=True)
    manager = await _run_initialize(monkeypatch, settings)
    assert _fallback_provider_order(manager) == ["civitai_api", "civarchive_api", "sqlite"]


@pytest.mark.asyncio
async def test_initialize_providers_prefer_sqlite_order(monkeypatch):
    settings = _stub_settings(
        enable_metadata_archive_db=True,
        metadata_provider_order="civitai_sqlite_archive",
    )
    manager = await _run_initialize(monkeypatch, settings)
    assert _fallback_provider_order(manager) == ["civitai_api", "sqlite", "civarchive_api"]


@pytest.mark.asyncio
async def test_initialize_providers_disables_civarchive(monkeypatch):
    settings = _stub_settings(
        enable_metadata_archive_db=True,
        enable_civarchive_api=False,
    )
    manager = await _run_initialize(monkeypatch, settings)
    # civarchive_api must not be registered at all
    assert "civarchive_api" not in manager.providers
    assert _fallback_provider_order(manager) == ["civitai_api", "sqlite"]


@pytest.mark.asyncio
async def test_initialize_providers_skips_unavailable_sqlite_in_preset(monkeypatch):
    # Preset wants sqlite before civarchive, but archive db is disabled ->
    # sqlite is unavailable and must be skipped, civarchive stays.
    settings = _stub_settings(
        enable_metadata_archive_db=False,
        metadata_provider_order="civitai_sqlite_archive",
    )
    manager = await _run_initialize(monkeypatch, settings)
    assert _fallback_provider_order(manager) == ["civitai_api", "civarchive_api"]


@pytest.mark.asyncio
async def test_initialize_providers_single_provider_when_only_civitai(monkeypatch):
    # Both archive db and civarchive disabled -> only civitai_api remains,
    # which takes the single-provider path (registered as default, no fallback).
    settings = _stub_settings(
        enable_metadata_archive_db=False,
        enable_civarchive_api=False,
    )
    manager = await _run_initialize(monkeypatch, settings)
    assert "fallback" not in manager.providers
    assert manager.default_provider == "civitai_api"

