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


async def test_connectivity_guard_scopes_cooldown_to_destination():
    guard = await ConnectivityGuard.get_instance()

    destination_a = "civitai.com"
    destination_b = "api.github.com"

    guard.register_network_failure(
        OSError(errno.ENETUNREACH, "unreachable"),
        destination_a,
    )
    guard.register_network_failure(asyncio.TimeoutError("timeout"), destination_a)
    guard.register_network_failure(ConnectionRefusedError("refused"), destination_a)

    assert guard.should_block_request(destination_a) is True
    assert guard.should_block_request(destination_b) is False

    guard.register_success(destination_a)
    assert guard.should_block_request(destination_a) is False


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
    destination = "example.invalid"
    guard.register_network_failure(
        OSError(errno.ENETUNREACH, "unreachable"),
        destination,
    )
    guard.register_network_failure(asyncio.TimeoutError("timeout"), destination)
    guard.register_network_failure(
        ConnectionRefusedError("refused"),
        destination,
    )

    downloader = Downloader()

    ok, payload = await downloader.make_request("GET", f"https://{destination}")
    assert ok is False
    assert payload == OFFLINE_COOLDOWN_ERROR

    ok, payload, headers = await downloader.download_to_memory(f"https://{destination}")
    assert ok is False
    assert payload == OFFLINE_COOLDOWN_ERROR
    assert headers is None

    ok, payload = await downloader.get_response_headers(f"https://{destination}")
    assert ok is False
    assert payload == OFFLINE_COOLDOWN_ERROR


async def test_downloader_only_short_circuits_requests_for_same_destination():
    guard = await ConnectivityGuard.get_instance()
    guard.register_network_failure(
        OSError(errno.ENETUNREACH, "unreachable"),
        "example.invalid",
    )
    guard.register_network_failure(asyncio.TimeoutError("timeout"), "example.invalid")
    guard.register_network_failure(
        ConnectionRefusedError("refused"),
        "example.invalid",
    )

    downloader = Downloader()
    ok, payload = await downloader.make_request("GET", "https://example.invalid")
    assert ok is False
    assert payload == OFFLINE_COOLDOWN_ERROR

    assert (
        guard.should_block_request(downloader._guard_destination("https://example.com"))
        is False
    )
