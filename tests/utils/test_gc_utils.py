from __future__ import annotations

import asyncio
import logging

import pytest

from py.utils import gc_utils
from py.utils.gc_utils import (
    freeze_long_lived_objects,
    schedule_refreeze,
    schedule_refreeze_after_rebuild,
)


@pytest.fixture(autouse=True)
def reset_pending_refreeze(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gc_utils, "_pending_refreeze", None)


def test_freeze_collects_then_freezes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("gc.collect", lambda: calls.append("collect") or 0)
    monkeypatch.setattr("gc.freeze", lambda: calls.append("freeze"))

    freeze_long_lived_objects("test")

    assert calls == ["collect", "freeze"]


def test_freeze_logs_collected_count(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("gc.collect", lambda: 42)
    monkeypatch.setattr("gc.freeze", lambda: None)

    with caplog.at_level(logging.DEBUG, logger="py.utils.gc_utils"):
        freeze_long_lived_objects("cache initialization")

    assert "cache initialization" in caplog.text
    assert "42" in caplog.text


def test_freeze_swallows_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom() -> int:
        raise RuntimeError("gc unavailable")

    monkeypatch.setattr("gc.collect", boom)

    with caplog.at_level(logging.WARNING, logger="py.utils.gc_utils"):
        freeze_long_lived_objects("cache initialization")

    assert "failed to freeze" in caplog.text


def test_schedule_refreeze_is_noop_without_running_loop() -> None:
    schedule_refreeze_after_rebuild("test", delay=0.01)

    assert gc_utils._pending_refreeze is None


async def test_schedule_refreeze_fires_after_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fired: list[str] = []
    monkeypatch.setattr(
        gc_utils, "freeze_long_lived_objects", lambda reason: fired.append(reason)
    )

    schedule_refreeze_after_rebuild("rebuild", delay=0.01)
    assert fired == []

    await asyncio.sleep(0.1)

    assert fired == ["rebuild"]


async def test_schedule_refreeze_debounces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fired: list[str] = []
    monkeypatch.setattr(
        gc_utils, "freeze_long_lived_objects", lambda reason: fired.append(reason)
    )

    schedule_refreeze_after_rebuild("first", delay=0.05)
    schedule_refreeze_after_rebuild("second", delay=0.05)
    await asyncio.sleep(0.2)

    assert fired == ["second"]


async def test_schedule_refreeze_waits_for_idle_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fired: list[str] = []
    monkeypatch.setattr(
        gc_utils, "freeze_long_lived_objects", lambda reason: fired.append(reason)
    )
    idle = {"value": False}
    monkeypatch.setattr(
        gc_utils, "_comfyui_queue_is_idle", lambda: idle["value"]
    )

    schedule_refreeze("download", delay=0.02)
    await asyncio.sleep(0.07)
    assert fired == []

    idle["value"] = True
    await asyncio.sleep(0.1)

    assert fired == ["download"]


async def test_schedule_refreeze_gives_up_after_max_retries(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fired: list[str] = []
    monkeypatch.setattr(
        gc_utils, "freeze_long_lived_objects", lambda reason: fired.append(reason)
    )
    monkeypatch.setattr(gc_utils, "_comfyui_queue_is_idle", lambda: False)

    with caplog.at_level(logging.DEBUG, logger="py.utils.gc_utils"):
        schedule_refreeze("download", delay=0.01, _retries_left=2)
        await asyncio.sleep(0.2)

    assert fired == []
    assert "skipped GC re-freeze" in caplog.text
