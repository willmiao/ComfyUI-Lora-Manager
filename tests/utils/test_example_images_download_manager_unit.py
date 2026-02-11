from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils import example_images_download_manager as download_module


class RecordingWebSocketManager:
    def __init__(self) -> None:
        self.payloads: list[Dict[str, Any]] = []

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        self.payloads.append(payload)


@pytest.fixture(autouse=True)
def restore_settings() -> None:
    manager = get_settings_manager()
    original = manager.settings.copy()
    try:
        yield
    finally:
        manager.settings.clear()
        manager.settings.update(original)


async def test_start_download_requires_configured_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())

    # Ensure example_images_path is not configured
    settings_manager = get_settings_manager()
    settings_manager.settings.pop("example_images_path", None)

    with pytest.raises(download_module.DownloadConfigurationError) as exc_info:
        await manager.start_download({})

    assert "not configured" in str(exc_info.value)

    result = await manager.start_download({"auto_mode": True})
    assert result["success"] is True
    assert "skipping auto download" in result["message"]


async def test_start_download_bootstraps_progress_and_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)
    settings_manager.settings["libraries"] = {"default": {}}
    settings_manager.settings["active_library"] = "default"

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_download(
        self, output_dir, optimize, model_types, delay, library_name, force=False
    ):
        started.set()
        await release.wait()
        async with self._state_lock:
            self._is_downloading = False
            self._download_task = None
        self._progress["status"] = "completed"

    monkeypatch.setattr(
        download_module.DownloadManager,
        "_download_all_example_images",
        fake_download,
    )

    result = await manager.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True
    assert manager._is_downloading is True

    await asyncio.wait_for(started.wait(), timeout=1)
    assert ws_manager.payloads[0]["status"] == "running"

    task = manager._download_task
    assert task is not None
    release.set()
    await asyncio.wait_for(task, timeout=1)
    assert manager._is_downloading is False
    assert manager._progress["status"] == "completed"


async def test_pause_and_resume_flow(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)
    settings_manager.settings["libraries"] = {"default": {}}
    settings_manager.settings["active_library"] = "default"

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_download(self, *_args):
        started.set()
        await release.wait()
        async with self._state_lock:
            self._is_downloading = False
            self._download_task = None

    monkeypatch.setattr(
        download_module.DownloadManager,
        "_download_all_example_images",
        fake_download,
    )

    await manager.start_download({})
    await asyncio.wait_for(started.wait(), timeout=1)

    pause_response = await manager.pause_download(object())
    assert pause_response == {"success": True, "message": "Download paused"}
    assert manager._progress["status"] == "paused"

    resume_response = await manager.resume_download(object())
    assert resume_response == {"success": True, "message": "Download resumed"}
    assert manager._progress["status"] == "running"

    task = manager._download_task
    assert task is not None
    release.set()
    await asyncio.wait_for(task, timeout=1)


async def test_stop_download_transitions_to_stopped(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)
    settings_manager.settings["libraries"] = {"default": {}}
    settings_manager.settings["active_library"] = "default"

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_download(self, *_args):
        started.set()
        await release.wait()
        async with self._state_lock:
            if self._stop_requested and self._progress["status"] == "stopping":
                self._progress["status"] = "stopped"
            else:
                self._progress["status"] = "completed"
            self._progress["end_time"] = time.time()
            self._stop_requested = False
        await self._broadcast_progress(status=self._progress["status"])
        async with self._state_lock:
            self._is_downloading = False
            self._download_task = None

    monkeypatch.setattr(
        download_module.DownloadManager,
        "_download_all_example_images",
        fake_download,
    )

    await manager.start_download({})
    await asyncio.wait_for(started.wait(), timeout=1)

    stop_response = await manager.stop_download(object())
    assert stop_response == {"success": True, "message": "Download stopping"}
    assert manager._progress["status"] == "stopping"

    task = manager._download_task
    assert task is not None
    release.set()
    await asyncio.wait_for(task, timeout=1)

    assert manager._progress["status"] == "stopped"
    assert manager._is_downloading is False
    assert manager._stop_requested is False
    statuses = [payload["status"] for payload in ws_manager.payloads]
    assert "stopping" in statuses
    assert "stopped" in statuses


async def test_pause_or_resume_without_running_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())

    with pytest.raises(download_module.DownloadNotRunningError):
        await manager.pause_download(object())

    with pytest.raises(download_module.DownloadNotRunningError):
        await manager.resume_download(object())

    with pytest.raises(download_module.DownloadNotRunningError):
        await manager.stop_download(object())


async def test_download_task_callback_executes_on_completion(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Test that _handle_download_task_done callback is executed when download completes."""
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)
    settings_manager.settings["libraries"] = {"default": {}}
    settings_manager.settings["active_library"] = "default"

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    callback_executed = asyncio.Event()
    original_callback = manager._handle_download_task_done

    def tracking_callback(task, output_dir):
        original_callback(task, output_dir)
        callback_executed.set()

    monkeypatch.setattr(
        manager, "_handle_download_task_done", tracking_callback
    )

    async def fake_download(self, *_args):
        # Simulate successful completion
        async with self._state_lock:
            self._progress["status"] = "completed"
            self._is_downloading = False
            self._download_task = None

    monkeypatch.setattr(
        download_module.DownloadManager,
        "_download_all_example_images",
        fake_download,
    )

    result = await manager.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True

    # Wait for callback to execute
    await asyncio.wait_for(callback_executed.wait(), timeout=1)
    assert manager._progress["status"] == "completed"


async def test_download_task_callback_handles_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Test that _handle_download_task_done properly handles task errors and saves progress."""
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)
    settings_manager.settings["libraries"] = {"default": {}}
    settings_manager.settings["active_library"] = "default"

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    callback_executed = asyncio.Event()
    progress_saved = False
    original_save_progress = manager._save_progress

    def tracking_save_progress(output_dir):
        nonlocal progress_saved
        progress_saved = True
        return original_save_progress(output_dir)

    monkeypatch.setattr(manager, "_save_progress", tracking_save_progress)

    original_callback = manager._handle_download_task_done

    def tracking_callback(task, output_dir):
        original_callback(task, output_dir)
        callback_executed.set()

    monkeypatch.setattr(
        manager, "_handle_download_task_done", tracking_callback
    )

    async def fake_download_with_error(self, *_args):
        raise RuntimeError("Simulated download error")

    monkeypatch.setattr(
        download_module.DownloadManager,
        "_download_all_example_images",
        fake_download_with_error,
    )

    result = await manager.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True

    # Wait for callback to execute (it should handle the error)
    await asyncio.wait_for(callback_executed.wait(), timeout=1)
    # Progress should be saved even on error
    assert progress_saved is True


async def test_get_status_returns_correct_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Test that get_status returns the correct download state."""
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)
    settings_manager.settings["libraries"] = {"default": {}}
    settings_manager.settings["active_library"] = "default"

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    # Test idle state
    status = await manager.get_status(object())
    assert status["success"] is True
    assert status["is_downloading"] is False
    assert status["status"]["status"] == "idle"

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_download(self, *_args):
        started.set()
        await release.wait()
        async with self._state_lock:
            self._is_downloading = False
            self._download_task = None

    monkeypatch.setattr(
        download_module.DownloadManager,
        "_download_all_example_images",
        fake_download,
    )

    # Start download
    result = await manager.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True

    await asyncio.wait_for(started.wait(), timeout=1)

    # Test running state
    status = await manager.get_status(object())
    assert status["success"] is True
    assert status["is_downloading"] is True
    assert status["status"]["status"] == "running"

    # Cleanup
    release.set()
    if manager._download_task:
        await asyncio.wait_for(manager._download_task, timeout=1)
