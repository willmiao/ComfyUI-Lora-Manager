"""Tests for the per-destination rate-limit gate (#1085).

Covers the RateLimitCoordinator itself, its integration into
``Downloader.make_request``, the failover semantics change in
``FallbackMetadataProvider``, and the ``_RateLimitRetryHelper`` double-wait
fix.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

import pytest

from py.services.connectivity_guard import ConnectivityGuard
from py.services.downloader import Downloader
from py.services.errors import RateLimitError
from py.services.model_metadata_provider import (
    FallbackMetadataProvider,
    _RateLimitRetryHelper,
)
from py.services.rate_limit_coordinator import RateLimitCoordinator


@pytest.fixture(autouse=True)
def _reset_singletons():
    RateLimitCoordinator._instance = None
    ConnectivityGuard._instance = None
    yield
    RateLimitCoordinator._instance = None
    ConnectivityGuard._instance = None


def _patch_gate_settings(monkeypatch, **overrides):
    """Override the coordinator's settings reads for the test."""
    monkeypatch.setattr(
        RateLimitCoordinator,
        "_setting",
        staticmethod(lambda key, default: overrides.get(key, default)),
    )


async def _make_coordinator(monkeypatch, **overrides) -> RateLimitCoordinator:
    _patch_gate_settings(monkeypatch, **overrides)
    return await RateLimitCoordinator.get_instance()


# ----------------------------------------------------------------------
# Coordinator unit tests


async def test_pacing_enforces_min_interval(monkeypatch):
    coordinator = await _make_coordinator(
        monkeypatch, rate_limit_min_interval_seconds=0.1
    )
    start = time.monotonic()
    await coordinator.wait_for_slot("example.com")
    await coordinator.wait_for_slot("example.com")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.1


async def test_pacing_is_per_destination(monkeypatch):
    coordinator = await _make_coordinator(
        monkeypatch, rate_limit_min_interval_seconds=0.2
    )
    await coordinator.wait_for_slot("a.example.com")
    start = time.monotonic()
    await coordinator.wait_for_slot("b.example.com")
    elapsed = time.monotonic() - start
    assert elapsed < 0.1


async def test_register_rate_limit_arms_cooldown_and_waits(monkeypatch):
    coordinator = await _make_coordinator(
        monkeypatch,
        rate_limit_min_interval_seconds=0.0,
        rate_limit_max_wait_seconds=5.0,
    )
    coordinator.register_rate_limit("example.com", retry_after=0.15)
    assert coordinator.in_cooldown("example.com")
    assert 0.1 < coordinator.remaining_seconds("example.com") <= 0.15

    start = time.monotonic()
    await coordinator.wait_for_slot("example.com")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.14
    assert not coordinator.in_cooldown("example.com")


async def test_concurrent_waiters_share_one_cooldown_window(monkeypatch):
    """Herd test: N waiters wake after ~one window, not N windows."""
    coordinator = await _make_coordinator(
        monkeypatch,
        rate_limit_min_interval_seconds=0.0,
        rate_limit_max_wait_seconds=5.0,
    )
    coordinator.register_rate_limit("example.com", retry_after=0.2)

    start = time.monotonic()
    await asyncio.gather(
        *(coordinator.wait_for_slot("example.com") for _ in range(4))
    )
    elapsed = time.monotonic() - start
    # 4 independent windows would take ~0.8s; a shared window is ~0.2s.
    assert 0.19 <= elapsed < 0.5


async def test_backoff_grows_on_consecutive_429_and_resets_on_success(
    monkeypatch,
):
    coordinator = await _make_coordinator(
        monkeypatch, rate_limit_min_interval_seconds=0.0
    )
    coordinator.register_rate_limit("example.com", retry_after=None)
    first = coordinator.remaining_seconds("example.com")
    assert 29.0 < first <= 30.0

    coordinator.register_rate_limit("example.com", retry_after=None)
    second = coordinator.remaining_seconds("example.com")
    assert 59.0 < second <= 60.0

    coordinator.register_success("example.com")
    coordinator.register_rate_limit("example.com", retry_after=None)
    third = coordinator.remaining_seconds("example.com")
    assert 29.0 < third <= 30.0


async def test_wait_beyond_cap_raises_rate_limit_error(monkeypatch):
    coordinator = await _make_coordinator(
        monkeypatch,
        rate_limit_min_interval_seconds=0.0,
        rate_limit_max_wait_seconds=0.05,
    )
    coordinator.register_rate_limit("example.com", retry_after=30.0)

    start = time.monotonic()
    with pytest.raises(RateLimitError) as excinfo:
        await coordinator.wait_for_slot("example.com")
    elapsed = time.monotonic() - start
    assert elapsed < 1.0  # refused immediately instead of parking
    assert excinfo.value.retry_after is not None
    assert excinfo.value.retry_after > 1.0


# ----------------------------------------------------------------------
# Downloader integration tests


class _FakeResponse:
    def __init__(
        self,
        status: int,
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.status = status
        self._payload = payload
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        if self._payload is None:
            raise ValueError("no json payload")
        return self._payload

    async def text(self):
        return ""


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def request(self, method, url, headers=None, **kwargs):
        self.requests.append({"method": method, "url": url})
        assert self._responses, "unexpected extra request"
        return self._responses.pop(0)

    def get(self, url, headers=None, **kwargs):
        return self.request("GET", url, headers=headers, **kwargs)

    def head(self, url, headers=None, **kwargs):
        return self.request("HEAD", url, headers=headers, **kwargs)

    async def close(self):
        return None


def _build_downloader(responses) -> Downloader:
    downloader = Downloader()
    fake_session = _FakeSession(responses)
    downloader._session = fake_session  # pyright: ignore[reportAttributeAccessIssue]
    downloader._session_created_at = datetime.now()
    downloader._proxy_url = None

    async def _noop_create_session():
        downloader._session = fake_session  # pyright: ignore[reportAttributeAccessIssue]
        downloader._session_created_at = datetime.now()
        downloader._proxy_url = None

    downloader._create_session = _noop_create_session  # type: ignore[assignment]
    return downloader


async def test_make_request_waits_out_429_then_resends(monkeypatch):
    _patch_gate_settings(
        monkeypatch,
        rate_limit_gate_enabled=True,
        rate_limit_min_interval_seconds=0.0,
        rate_limit_max_wait_seconds=5.0,
    )
    downloader = _build_downloader(
        [
            _FakeResponse(429, headers={"Retry-After": "1"}),
            _FakeResponse(200, payload={"ok": True}),
        ]
    )

    start = time.monotonic()
    success, payload = await downloader.make_request(
        "GET", "https://api.example.com/models/1"
    )
    elapsed = time.monotonic() - start

    assert success is True
    assert payload == {"ok": True}
    assert len(downloader._session.requests) == 2
    assert elapsed >= 0.9


async def test_make_request_paces_consecutive_calls(monkeypatch):
    _patch_gate_settings(
        monkeypatch,
        rate_limit_gate_enabled=True,
        rate_limit_min_interval_seconds=0.15,
        rate_limit_max_wait_seconds=5.0,
    )
    downloader = _build_downloader(
        [_FakeResponse(200, payload={}), _FakeResponse(200, payload={})]
    )

    start = time.monotonic()
    await downloader.make_request("GET", "https://api.example.com/a")
    await downloader.make_request("GET", "https://api.example.com/b")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.14


async def test_make_request_gate_disabled_returns_429_immediately(monkeypatch):
    _patch_gate_settings(monkeypatch, rate_limit_gate_enabled=False)
    downloader = _build_downloader(
        [_FakeResponse(429, headers={"Retry-After": "30"})]
    )

    start = time.monotonic()
    success, payload = await downloader.make_request(
        "GET", "https://api.example.com/models/1"
    )
    elapsed = time.monotonic() - start

    assert success is False
    assert isinstance(payload, RateLimitError)
    assert payload.retry_after == 30.0
    # Gate was off: the error is NOT marked, so retry helpers keep their
    # legacy behavior.
    assert getattr(payload, "gate_handled", False) is False
    assert len(downloader._session.requests) == 1
    assert elapsed < 1.0


async def test_make_request_refuses_wait_beyond_cap(monkeypatch):
    _patch_gate_settings(
        monkeypatch,
        rate_limit_gate_enabled=True,
        rate_limit_min_interval_seconds=0.0,
        rate_limit_max_wait_seconds=0.2,
    )
    downloader = _build_downloader(
        [_FakeResponse(429, headers={"Retry-After": "3600"})]
    )

    start = time.monotonic()
    success, payload = await downloader.make_request(
        "GET", "https://api.example.com/models/1"
    )
    elapsed = time.monotonic() - start

    assert success is False
    assert isinstance(payload, RateLimitError)
    assert payload.gate_handled is True
    assert len(downloader._session.requests) == 1
    assert elapsed < 1.0


# ----------------------------------------------------------------------
# FallbackMetadataProvider failover semantics (Fix C)


def _stub_provider(*, result=None, error=None, exc: Exception | None = None):
    if exc is not None:
        call = AsyncMock(side_effect=exc)
    else:
        call = AsyncMock(return_value=(result, error))
    return SimpleNamespace(get_model_by_hash=call)


async def test_fallback_does_not_fail_over_to_network_provider_on_429(monkeypatch):
    # The stub error is not gate_handled, so the retry helper would sleep
    # retry_after between attempts; patch it out (the helper's own behavior
    # is covered by the double-wait tests below).
    monkeypatch.setattr(
        "py.services.model_metadata_provider.asyncio.sleep", AsyncMock()
    )
    civitai = _stub_provider(exc=RateLimitError("limited", retry_after=30))
    civarchive = _stub_provider(result={"id": 1}, error=None)
    sqlite = _stub_provider(result=None, error="not in archive")

    fallback = FallbackMetadataProvider(
        [
            ("civitai_api", civitai),
            ("civarchive_api", civarchive),
            ("sqlite", sqlite),
        ]
    )

    result, error = await fallback.get_model_by_hash("deadbeef")

    assert result is None
    assert error == "Rate limited"
    civarchive.get_model_by_hash.assert_not_called()  # no network failover
    sqlite.get_model_by_hash.assert_called_once()  # local last resort kept


async def test_fallback_still_fails_over_on_not_found():
    civitai = _stub_provider(result=None, error="Model not found")
    civarchive = _stub_provider(result={"id": 1}, error=None)

    fallback = FallbackMetadataProvider(
        [("civitai_api", civitai), ("civarchive_api", civarchive)]
    )

    result, _ = await fallback.get_model_by_hash("deadbeef")

    assert result == {"id": 1}
    civarchive.get_model_by_hash.assert_called_once()


async def test_fallback_404_failover_still_works_after_rate_limit_change():
    """A 404 from the first network provider still reaches the second."""
    civitai = _stub_provider(result=None, error="Resource not found")
    civarchive = _stub_provider(result={"id": 2}, error=None)

    fallback = FallbackMetadataProvider(
        [("civitai_api", civitai), ("civarchive_api", civarchive)]
    )

    result, _ = await fallback.get_model_by_hash("deadbeef")
    assert result == {"id": 2}


# ----------------------------------------------------------------------
# _RateLimitRetryHelper double-wait fix


async def test_retry_helper_does_not_sleep_for_gate_handled_errors():
    calls = 0

    async def failing():
        nonlocal calls
        calls += 1
        error = RateLimitError("limited", retry_after=30)
        error.gate_handled = True
        raise error

    helper = _RateLimitRetryHelper()
    start = time.monotonic()
    with pytest.raises(RateLimitError) as excinfo:
        await helper.run("civitai_api", failing)
    elapsed = time.monotonic() - start

    assert calls == 1  # propagated immediately, no retry loop
    assert elapsed < 1.0
    assert excinfo.value.provider == "civitai_api"


async def test_retry_helper_keeps_legacy_retry_for_ungated_errors():
    calls = 0

    async def failing():
        nonlocal calls
        calls += 1
        raise RateLimitError("limited", retry_after=None)

    helper = _RateLimitRetryHelper(
        retry_limit=2, base_delay=0.01, max_delay=0.05, jitter_ratio=0.0
    )
    with pytest.raises(RateLimitError):
        await helper.run("civitai_api", failing)

    assert calls == 2  # legacy retry behavior unchanged


# ----------------------------------------------------------------------
# Download-path 429 registration (Phase 2)


class _FakeDownloadResponse(_FakeResponse):
    async def read(self):
        return b"data"


async def test_download_to_memory_429_registers_cooldown(monkeypatch):
    _patch_gate_settings(
        monkeypatch,
        rate_limit_gate_enabled=True,
        rate_limit_min_interval_seconds=0.0,
    )
    downloader = _build_downloader(
        [_FakeDownloadResponse(429, headers={"Retry-After": "120"})]
    )

    success, error, _ = await downloader.download_to_memory(
        "https://api.example.com/preview.png"
    )

    assert success is False
    assert "Rate limited" in error
    coordinator = await RateLimitCoordinator.get_instance()
    remaining = coordinator.remaining_seconds("api.example.com")
    assert 110.0 < remaining <= 120.0


async def test_get_response_headers_429_registers_cooldown(monkeypatch):
    _patch_gate_settings(
        monkeypatch,
        rate_limit_gate_enabled=True,
        rate_limit_min_interval_seconds=0.0,
    )
    downloader = _build_downloader(
        [_FakeResponse(429, headers={"Retry-After": "60"})]
    )

    success, error = await downloader.get_response_headers(
        "https://api.example.com/model/file.safetensors"
    )

    assert success is False
    assert "rate limited" in error.lower()
    coordinator = await RateLimitCoordinator.get_instance()
    remaining = coordinator.remaining_seconds("api.example.com")
    assert 50.0 < remaining <= 60.0
