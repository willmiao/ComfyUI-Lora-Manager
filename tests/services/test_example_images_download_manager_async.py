from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from py.services.settings_manager import settings
from py.utils import example_images_download_manager as download_module


class RecordingWebSocketManager:
    """Collects broadcast payloads for assertions."""

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def broadcast(self, payload: dict) -> None:
        self.payloads.append(payload)


class StubScanner:
    """Scanner double returning predetermined cache contents."""

    def __init__(self, models: list[dict]) -> None:
        self._cache = SimpleNamespace(raw_data=models)

    async def get_cached_data(self):
        return self._cache


def _patch_scanner(monkeypatch: pytest.MonkeyPatch, scanner: StubScanner) -> None:
    async def _get_lora_scanner(cls):
        return scanner

    monkeypatch.setattr(
        download_module.ServiceRegistry,
        "get_lora_scanner",
        classmethod(_get_lora_scanner),
    )


@pytest.mark.usefixtures("tmp_path")
async def test_start_download_rejects_parallel_runs(monkeypatch: pytest.MonkeyPatch, tmp_path):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings.settings, "example_images_path", str(tmp_path))

    model = {
        "sha256": "abc123",
        "model_name": "Example",
        "file_path": str(tmp_path / "example.safetensors"),
        "file_name": "example.safetensors",
    }
    _patch_scanner(monkeypatch, StubScanner([model]))

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process_local_examples(*_args, **_kwargs):
        started.set()
        await release.wait()
        return True

    async def fake_update_metadata(*_args, **_kwargs):
        return True

    async def fake_get_downloader():
        return object()

    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "process_local_examples",
        staticmethod(fake_process_local_examples),
    )
    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "update_metadata_from_local_examples",
        staticmethod(fake_update_metadata),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)

    try:
        result = await manager.start_download({"model_types": ["lora"], "delay": 0})
        assert result["success"] is True

        await asyncio.wait_for(started.wait(), timeout=1)

        with pytest.raises(download_module.DownloadInProgressError) as exc:
            await manager.start_download({"model_types": ["lora"], "delay": 0})

        snapshot = exc.value.progress_snapshot
        assert snapshot["status"] == "running"
        assert snapshot["current_model"] == "Example (abc123)"

        statuses = [payload["status"] for payload in ws_manager.payloads]
        assert "running" in statuses

    finally:
        release.set()
        if manager._download_task is not None:
            await asyncio.wait_for(manager._download_task, timeout=1)


@pytest.mark.usefixtures("tmp_path")
async def test_pause_resume_blocks_processing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings.settings, "example_images_path", str(tmp_path))

    models = [
        {
            "sha256": "hash-one",
            "model_name": "Model One",
            "file_path": str(tmp_path / "model-one.safetensors"),
            "file_name": "model-one.safetensors",
            "civitai": {"images": [{"url": "https://example.com/one.png"}]},
        },
        {
            "sha256": "hash-two",
            "model_name": "Model Two",
            "file_path": str(tmp_path / "model-two.safetensors"),
            "file_name": "model-two.safetensors",
            "civitai": {"images": [{"url": "https://example.com/two.png"}]},
        },
    ]
    _patch_scanner(monkeypatch, StubScanner(models))

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    async def fake_update_metadata(*_args, **_kwargs):
        return True

    first_call_started = asyncio.Event()
    first_release = asyncio.Event()
    second_call_started = asyncio.Event()
    call_order: list[str] = []

    async def fake_download_model_images(model_hash, *_args, **_kwargs):
        call_order.append(model_hash)
        if len(call_order) == 1:
            first_call_started.set()
            await first_release.wait()
        else:
            second_call_started.set()
        return True, False

    async def fake_get_downloader():
        class _Downloader:
            async def download_to_memory(self, *_a, **_kw):
                return True, b"", {}

        return _Downloader()

    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "process_local_examples",
        staticmethod(fake_process_local_examples),
    )
    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "update_metadata_from_local_examples",
        staticmethod(fake_update_metadata),
    )
    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "download_model_images",
        staticmethod(fake_download_model_images),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)

    original_sleep = download_module.asyncio.sleep
    pause_gate = asyncio.Event()
    resume_gate = asyncio.Event()

    async def fake_sleep(delay: float):
        if delay == 1:
            pause_gate.set()
            await resume_gate.wait()
        else:
            await original_sleep(delay)

    monkeypatch.setattr(download_module.asyncio, "sleep", fake_sleep)

    try:
        await manager.start_download({"model_types": ["lora"], "delay": 0})

        await asyncio.wait_for(first_call_started.wait(), timeout=1)

        await manager.pause_download({})

        first_release.set()

        await asyncio.wait_for(pause_gate.wait(), timeout=1)
        assert manager._progress["status"] == "paused"
        assert not second_call_started.is_set()

        statuses = [payload["status"] for payload in ws_manager.payloads]
        paused_index = statuses.index("paused")

        await asyncio.sleep(0)
        assert not second_call_started.is_set()

        await manager.resume_download({})
        resume_gate.set()

        await asyncio.wait_for(second_call_started.wait(), timeout=1)

        if manager._download_task is not None:
            await asyncio.wait_for(manager._download_task, timeout=1)

        statuses_after = [payload["status"] for payload in ws_manager.payloads]
        running_after = next(
            i for i, status in enumerate(statuses_after[paused_index + 1 :], start=paused_index + 1) if status == "running"
        )
        assert running_after > paused_index
        assert "completed" in statuses_after[running_after:]
        assert call_order == ["hash-one", "hash-two"]

    finally:
        first_release.set()
        resume_gate.set()
        if manager._download_task is not None:
            await asyncio.wait_for(manager._download_task, timeout=1)
        monkeypatch.setattr(download_module.asyncio, "sleep", original_sleep)
