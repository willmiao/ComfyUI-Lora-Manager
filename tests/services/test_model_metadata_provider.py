from unittest.mock import AsyncMock

import pytest

from py.services import model_metadata_provider as provider_module
from py.services.errors import RateLimitError
from py.services.model_metadata_provider import (
    FallbackMetadataProvider,
    RateLimitRetryingProvider,
)


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
async def test_fallback_continues_to_next_provider_on_rate_limit(monkeypatch):
    """After exhausting retries on primary, fallback should continue to secondary."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr(provider_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(provider_module.random, "uniform", lambda *_: 0.0)

    primary = AlwaysRateLimitedProvider()
    secondary = TrackingProvider()

    fallback = FallbackMetadataProvider(
        [("primary", primary), ("secondary", secondary)],
        rate_limit_retry_limit=2,
    )

    # After Change A: no longer raises; falls through to secondary
    result, error = await fallback.get_model_by_hash("abc")

    assert error is None
    assert result == {"id": "secondary"}
    assert primary.calls == 2          # retry_limit exhausted on primary
    assert secondary.calls == 1        # secondary IS called now


@pytest.mark.asyncio
async def test_rate_limit_retrying_provider_retries(monkeypatch):
    sleep_mock = AsyncMock()
    monkeypatch.setattr(provider_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(provider_module.random, "uniform", lambda *_: 0.0)

    inner = RateLimitThenSuccessProvider()
    wrapper = RateLimitRetryingProvider(inner, label="inner", rate_limit_base_delay=0.1)

    result, error = await wrapper.get_model_by_hash("abc")

    assert error is None
    assert result == {"id": "ok"}
    assert inner.calls == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limit_retrying_provider_respects_limit(monkeypatch):
    sleep_mock = AsyncMock()
    monkeypatch.setattr(provider_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(provider_module.random, "uniform", lambda *_: 0.0)

    inner = AlwaysRateLimitedProvider()
    wrapper = RateLimitRetryingProvider(inner, label="inner", rate_limit_retry_limit=2)

    with pytest.raises(RateLimitError) as exc_info:
        await wrapper.get_model_by_hash("abc")

    assert exc_info.value.provider == "inner"
    assert inner.calls == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_helper_limits_retries_for_large_retry_after():
    """With retry_after >= 120s, _RateLimitRetryHelper should only attempt once (no retries)."""
    calls = 0

    async def failing():
        nonlocal calls
        calls += 1
        raise RateLimitError("limited", retry_after=1500.0)

    helper = provider_module._RateLimitRetryHelper(retry_limit=3)
    with pytest.raises(RateLimitError):
        await helper.run("test", failing)
    assert calls == 1  # No retries for large retry_after


@pytest.mark.asyncio
async def test_retry_helper_retries_normally_for_small_retry_after(monkeypatch):
    """With retry_after < 120s, _RateLimitRetryHelper should retry normally (up to limit)."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr(provider_module.asyncio, "sleep", sleep_mock)

    calls = 0

    async def succeeding():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RateLimitError("limited", retry_after=30.0)
        return {"ok": True}, None

    helper = provider_module._RateLimitRetryHelper(retry_limit=3)
    result, _ = await helper.run("test", succeeding)
    assert result == {"ok": True}
    assert calls == 2  # Retried once (small retry_after)
