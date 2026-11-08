from __future__ import annotations

import asyncio
import time

import pytest

from py.utils.example_images_processor import MediaDownloadLimiter


@pytest.mark.asyncio
async def test_limiter_bounds_in_flight_requests() -> None:
    limiter = MediaDownloadLimiter(max_concurrency=2)

    await limiter.acquire()
    await limiter.acquire()

    waiting = asyncio.create_task(limiter.acquire())
    await asyncio.sleep(0)
    assert waiting.done() is False

    await limiter.release()
    await asyncio.wait_for(waiting, timeout=1)

    await limiter.release()
    await limiter.release()


@pytest.mark.asyncio
async def test_limiter_parks_every_worker_during_shared_cooldown() -> None:
    limiter = MediaDownloadLimiter(
        max_concurrency=2, min_cooldown=0.0, default_cooldown=0.01
    )

    await limiter.report_rate_limit(0.05)
    started = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - started

    assert elapsed >= 0.04
    await limiter.release()


@pytest.mark.asyncio
async def test_limiter_halves_on_429_and_recovers_one_slot_at_a_time() -> None:
    limiter = MediaDownloadLimiter(
        max_concurrency=4,
        min_cooldown=0.0,
        default_cooldown=0.01,
        recovery_successes=2,
    )

    await limiter.report_rate_limit(0.01)
    assert limiter.limit == 2

    await limiter.report_success()
    assert limiter.limit == 2
    await limiter.report_success()
    assert limiter.limit == 3

    await limiter.report_success()
    await limiter.report_success()
    assert limiter.limit == 4


def test_limiter_reset_restores_initial_limit() -> None:
    limiter = MediaDownloadLimiter(max_concurrency=3)
    limiter._limit = 1
    limiter._in_flight = 1
    limiter._cooldown_until = time.monotonic() + 30

    limiter.reset()

    assert limiter.limit == 3
    assert limiter._in_flight == 0
    assert limiter._cooldown_until == 0.0
