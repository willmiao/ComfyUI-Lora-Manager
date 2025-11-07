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
