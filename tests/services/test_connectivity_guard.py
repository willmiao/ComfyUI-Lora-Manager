import asyncio
import errno
from datetime import datetime, timedelta

import pytest

from py.services.connectivity_guard import (
    OFFLINE_COOLDOWN_ERROR,
    ConnectivityGuard,
)
from py.services.downloader import Downloader


@pytest.fixture(autouse=True)
def reset_connectivity_guard_singleton():
    ConnectivityGuard._instance = None
    yield
    ConnectivityGuard._instance = None


async def test_connectivity_guard_enters_cooldown_after_threshold():
    guard = await ConnectivityGuard.get_instance()

    assert guard.online is True
    assert guard.should_block_request() is False

    guard.register_network_failure(OSError(errno.ENETUNREACH, "unreachable"))
    guard.register_network_failure(asyncio.TimeoutError("timeout"))

    assert guard.should_block_request() is False
    assert guard.failure_count == 2

    guard.register_network_failure(ConnectionRefusedError("refused"))

    assert guard.online is False
    assert guard.failure_count == 3
    assert guard.should_block_request() is True
    assert guard.cooldown_remaining_seconds() > 0


async def test_connectivity_guard_recovers_after_success():
    guard = await ConnectivityGuard.get_instance()
    guard.online = False
    guard.failure_count = 5
    guard.cooldown_until = datetime.now() + timedelta(seconds=90)

    guard.register_success()

    assert guard.online is True
    assert guard.failure_count == 0
    assert guard.cooldown_until is None
    assert guard.should_block_request() is False


async def test_downloader_short_circuits_all_request_helpers_during_cooldown():
    guard = await ConnectivityGuard.get_instance()
    guard.cooldown_until = datetime.now() + timedelta(seconds=30)
    guard.online = False
    guard.failure_count = 3

    downloader = Downloader()

    ok, payload = await downloader.make_request("GET", "https://example.invalid")
    assert ok is False
    assert payload == OFFLINE_COOLDOWN_ERROR

    ok, payload, headers = await downloader.download_to_memory("https://example.invalid")
    assert ok is False
    assert payload == OFFLINE_COOLDOWN_ERROR
    assert headers is None

    ok, payload = await downloader.get_response_headers("https://example.invalid")
    assert ok is False
    assert payload == OFFLINE_COOLDOWN_ERROR
