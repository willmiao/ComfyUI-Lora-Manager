"""Elapsed-time accounting for the example-image download status payload."""

from __future__ import annotations

import pytest

from py.utils import example_images_download_manager as download_module
from py.utils.example_images_download_manager import DownloadManager, _DownloadProgress


class _RecordingWebSocket:
    def __init__(self) -> None:
        self.payloads = []

    async def broadcast(self, payload):
        self.payloads.append(payload)


def test_active_elapsed_without_start_is_zero():
    assert _DownloadProgress().active_elapsed() == 0.0


def test_active_elapsed_subtracts_closed_pauses(monkeypatch):
    progress = _DownloadProgress()
    progress["start_time"] = 100.0
    progress["paused_total"] = 30.0

    monkeypatch.setattr(download_module.time, "time", lambda: 200.0)

    assert progress.active_elapsed() == 70.0
    assert progress.snapshot()["elapsed_seconds"] == 70.0


def test_active_elapsed_subtracts_open_pause(monkeypatch):
    progress = _DownloadProgress()
    progress["start_time"] = 100.0
    progress["paused_total"] = 10.0
    progress["paused_at"] = 150.0

    monkeypatch.setattr(download_module.time, "time", lambda: 200.0)

    # 100s wall clock - 10s closed pause - 50s current pause.
    assert progress.active_elapsed() == 40.0


def test_active_elapsed_freezes_at_end_time(monkeypatch):
    progress = _DownloadProgress()
    progress["start_time"] = 100.0
    progress["end_time"] = 150.0
    progress["paused_total"] = 20.0

    monkeypatch.setattr(download_module.time, "time", lambda: 1000.0)

    assert progress.active_elapsed() == 30.0


async def test_pause_and_resume_exclude_the_paused_interval(monkeypatch):
    manager = DownloadManager(ws_manager=_RecordingWebSocket())
    manager._is_downloading = True
    manager._progress["status"] = "running"
    manager._progress["start_time"] = 100.0

    clock = {"now": 110.0}
    monkeypatch.setattr(download_module.time, "time", lambda: clock["now"])

    await manager.pause_download({})
    assert manager._progress["paused_at"] == 110.0

    clock["now"] = 140.0
    await manager.resume_download({})
    assert manager._progress["paused_at"] is None
    assert manager._progress["paused_total"] == 30.0

    clock["now"] = 150.0
    assert manager._progress.snapshot()["elapsed_seconds"] == 20.0


async def test_stop_while_paused_folds_the_pause(monkeypatch):
    manager = DownloadManager(ws_manager=_RecordingWebSocket())
    manager._is_downloading = True
    manager._progress["status"] = "running"
    manager._progress["start_time"] = 100.0

    clock = {"now": 110.0}
    monkeypatch.setattr(download_module.time, "time", lambda: clock["now"])

    await manager.pause_download({})
    clock["now"] = 120.0
    await manager.stop_download({})

    assert manager._progress["paused_at"] is None
    assert manager._progress["paused_total"] == 10.0
    assert manager._progress["status"] == "stopping"


def test_failure_summary_counts_reasons():
    progress = _DownloadProgress()
    progress.mark_failed("a", "unavailable")
    progress.mark_failed("b", "no_media")
    # Idempotent: marking the same model twice must not double-count it.
    progress.mark_failed("b", "no_media")
    progress.mark_failed("c", "unknown")
    progress.clear_failed("c")

    assert progress.failure_summary() == {
        "unavailable": 1,
        "no_media": 1,
        "total": 2,
    }
    assert progress.snapshot()["failure_summary"]["total"] == 2


def test_failure_reasons_roundtrip_through_progress_file(tmp_path):
    manager = DownloadManager(ws_manager=_RecordingWebSocket())
    model_hash = "a" * 64
    manager._progress["total"] = 1
    manager._progress.mark_failed(model_hash, "unavailable")
    manager._save_progress(str(tmp_path))

    _, _, failed, _, reasons = manager._load_progress_file_sync(str(tmp_path))

    assert failed == {model_hash}
    assert reasons == {model_hash: "unavailable"}
