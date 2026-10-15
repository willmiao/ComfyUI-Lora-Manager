from __future__ import annotations

import logging

import pytest

from py.utils.gc_utils import freeze_long_lived_objects


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
