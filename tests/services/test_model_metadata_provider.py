from unittest.mock import AsyncMock

import pytest

from py.services import model_metadata_provider as provider_module
from py.services.errors import RateLimitError
from py.services.model_metadata_provider import FallbackMetadataProvider


class RateLimitThenSuccessProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def get_model_by_hash(self, model_hash: str):
        self.calls += 1
        if self.calls == 1:
            raise RateLimitError("limited", retry_after=1.0)
        return {"id": "ok"}, None


class AlwaysRateLimitedProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def get_model_by_hash(self, model_hash: str):
        self.calls += 1
        raise RateLimitError("limited")


class TrackingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def get_model_by_hash(self, model_hash: str):
        self.calls += 1
        return {"id": "secondary"}, None


@pytest.mark.asyncio
async def test_fallback_retries_same_provider_on_rate_limit(monkeypatch):
    sleep_mock = AsyncMock()
    monkeypatch.setattr(provider_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(provider_module.random, "uniform", lambda *_: 0.0)

    primary = RateLimitThenSuccessProvider()
    secondary = TrackingProvider()

    fallback = FallbackMetadataProvider(
        [("primary", primary), ("secondary", secondary)],
    )

    result, error = await fallback.get_model_by_hash("abc")

    assert error is None
    assert result == {"id": "ok"}
    assert primary.calls == 2
    assert secondary.calls == 0
    sleep_mock.assert_awaited_once()
    assert sleep_mock.await_args_list[0].args[0] == pytest.approx(1.0, rel=0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_fallback_respects_retry_limit(monkeypatch):
    sleep_mock = AsyncMock()
    monkeypatch.setattr(provider_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(provider_module.random, "uniform", lambda *_: 0.0)

    primary = AlwaysRateLimitedProvider()
    secondary = TrackingProvider()

    fallback = FallbackMetadataProvider(
        [("primary", primary), ("secondary", secondary)],
        rate_limit_retry_limit=2,
    )

    with pytest.raises(RateLimitError) as exc_info:
        await fallback.get_model_by_hash("abc")

    assert exc_info.value.provider == "primary"
    assert primary.calls == 2
    assert secondary.calls == 0
    sleep_mock.assert_awaited_once()
