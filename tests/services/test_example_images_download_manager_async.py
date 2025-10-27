from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from py.services.settings_manager import SettingsManager, get_settings_manager
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

    async def update_single_model_cache(self, _old_path, _new_path, metadata):
        # Replace the cached entry with the updated metadata for assertions.
        for index, model in enumerate(self._cache.raw_data):
            if model.get("file_path") == metadata.get("file_path"):
                self._cache.raw_data[index] = metadata
                break
        return True


def _patch_scanner(monkeypatch: pytest.MonkeyPatch, scanner: StubScanner) -> None:
    async def _get_lora_scanner(cls):
        return scanner

    monkeypatch.setattr(
        download_module.ServiceRegistry,
        "get_lora_scanner",
        classmethod(_get_lora_scanner),
    )


@pytest.mark.usefixtures("tmp_path")
async def test_start_download_rejects_parallel_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

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
async def test_pause_resume_blocks_processing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

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
        return True, False, []

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
        "download_model_images_with_tracking",
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


@pytest.mark.usefixtures("tmp_path")
async def test_legacy_folder_migrated_and_skipped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"default": {}, "extra": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "extra")

    model_hash = "d" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("data", encoding="utf-8")

    model = {
        "sha256": model_hash,
        "model_name": "Migrated Model",
        "file_path": str(model_path),
        "file_name": "model.safetensors",
        "civitai": {"images": [{"url": "https://example.com/image.png"}]},
    }

    _patch_scanner(monkeypatch, StubScanner([model]))

    legacy_folder = tmp_path / model_hash
    legacy_folder.mkdir()
    (legacy_folder / "image_0.png").write_text("data", encoding="utf-8")

    process_called = False
    download_called = False

    async def fake_process_local_examples(*_args, **_kwargs):
        nonlocal process_called
        process_called = True
        return False

    async def fake_download_model_images(*_args, **_kwargs):
        nonlocal download_called
        download_called = True
        return True, False, []

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
        download_module.ExampleImagesProcessor,
        "download_model_images_with_tracking",
        staticmethod(fake_download_model_images),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)

    try:
        result = await manager.start_download({"model_types": ["lora"], "delay": 0})
        assert result["success"] is True

        if manager._download_task is not None:
            await asyncio.wait_for(manager._download_task, timeout=1)
    finally:
        if manager._download_task is not None and not manager._download_task.done():
            await asyncio.wait_for(manager._download_task, timeout=1)

    library_root = tmp_path / "extra"
    migrated_folder = library_root / model_hash

    assert migrated_folder.exists()
    assert not legacy_folder.exists()
    assert not process_called
    assert not download_called
    assert model_hash in manager._progress["processed_models"]


@pytest.mark.usefixtures("tmp_path")
async def test_legacy_progress_file_migrates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"default": {}, "extra": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "extra")

    model_hash = "e" * 64
    model_path = tmp_path / "model-two.safetensors"
    model_path.write_text("data", encoding="utf-8")

    legacy_progress = tmp_path / ".download_progress.json"
    legacy_progress.write_text(json.dumps({"processed_models": [model_hash], "failed_models": []}), encoding="utf-8")

    legacy_folder = tmp_path / model_hash
    legacy_folder.mkdir()
    (legacy_folder / "existing.png").write_text("data", encoding="utf-8")

    model = {
        "sha256": model_hash,
        "model_name": "Legacy Progress Model",
        "file_path": str(model_path),
        "file_name": "model-two.safetensors",
        "civitai": {"images": [{"url": "https://example.com/image.png"}]},
    }

    _patch_scanner(monkeypatch, StubScanner([model]))

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    async def fake_download_model_images(*_args, **_kwargs):
        raise AssertionError("Remote download should not be attempted when progress is migrated")

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
        download_module.ExampleImagesProcessor,
        "download_model_images_with_tracking",
        staticmethod(fake_download_model_images),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)

    result = await manager.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True

    if manager._download_task is not None:
        await asyncio.wait_for(manager._download_task, timeout=1)

    new_progress = (tmp_path / "extra") / ".download_progress.json"

    assert model_hash in manager._progress["processed_models"]
    assert not legacy_progress.exists()
    assert new_progress.exists()
    contents = json.loads(new_progress.read_text(encoding="utf-8"))
    assert model_hash in contents.get("processed_models", [])


@pytest.mark.usefixtures("tmp_path")
async def test_download_remains_in_initial_library(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"LibraryA": {}, "LibraryB": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "LibraryA")

    state = {"active": "LibraryA"}

    def fake_get_active_library_name(self):
        return state["active"]

    monkeypatch.setattr(SettingsManager, "get_active_library_name", fake_get_active_library_name)

    model_hash = "f" * 64
    model_path = tmp_path / "example-model.safetensors"
    model_path.write_text("data", encoding="utf-8")

    model = {
        "sha256": model_hash,
        "model_name": "Library Switch Model",
        "file_path": str(model_path),
        "file_name": "example-model.safetensors",
    }

    _patch_scanner(monkeypatch, StubScanner([model]))

    async def fake_process_local_examples(
        _file_path,
        _file_name,
        _model_name,
        model_dir,
        _optimize,
    ):
        Path(model_dir).mkdir(parents=True, exist_ok=True)
        (Path(model_dir) / "local.txt").write_text("data", encoding="utf-8")
        state["active"] = "LibraryB"
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

    result = await manager.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True

    if manager._download_task is not None:
        await asyncio.wait_for(manager._download_task, timeout=1)

    library_a_root = tmp_path / "LibraryA"
    library_b_root = tmp_path / "LibraryB"

    progress_file = library_a_root / ".download_progress.json"
    model_dir = library_a_root / model_hash

    assert progress_file.exists()
    assert (model_dir / "local.txt").exists()
    assert not (library_b_root / ".download_progress.json").exists()
    assert not (library_b_root / model_hash).exists()

@pytest.mark.usefixtures("tmp_path")
async def test_not_found_example_images_are_cleaned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    images_root = tmp_path / "examples"
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(images_root))

    model_hash = "f" * 64
    model_path = tmp_path / "missing-model.safetensors"
    model_path.write_text("data", encoding="utf-8")

    missing_url = "https://example.com/missing.png"
    valid_url = "https://example.com/valid.png"

    model_metadata = {
        "sha256": model_hash,
        "model_name": "Missing Example",
        "file_path": str(model_path),
        "file_name": "missing-model.safetensors",
        "civitai": {
            "images": [
                {"url": missing_url},
                {"url": valid_url},
            ]
        },
    }

    scanner = StubScanner([model_metadata.copy()])
    _patch_scanner(monkeypatch, scanner)

    model_dir = images_root / model_hash
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "image_0.png").write_bytes(b"first")
    (model_dir / "image_1.png").write_bytes(b"second")

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    refresh_calls: list[str] = []

    async def fake_refresh(model_hash_arg, *_args, **_kwargs):
        refresh_calls.append(model_hash_arg)
        return True

    async def fake_get_updated_model(model_hash_arg, _scanner):
        assert model_hash_arg == model_hash
        return model_metadata

    async def fake_save_metadata(_path, metadata):
        model_metadata.update(metadata)
        return True

    class DownloaderStub:
        def __init__(self):
            self.calls: list[str] = []

        async def download_to_memory(self, url, *_args, **_kwargs):
            self.calls.append(url)
            if url == missing_url:
                return False, "File not found", None
            return True, b"\x89PNG\r\n\x1a\n", {"content-type": "image/png"}

    downloader = DownloaderStub()

    async def fake_get_downloader():
        return downloader

    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "process_local_examples",
        staticmethod(fake_process_local_examples),
    )
    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "refresh_model_metadata",
        staticmethod(fake_refresh),
    )
    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "get_updated_model",
        staticmethod(fake_get_updated_model),
    )
    monkeypatch.setattr(
        download_module.MetadataManager,
        "save_metadata",
        staticmethod(fake_save_metadata),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)
    monkeypatch.setattr(download_module, "_model_directory_has_files", lambda _path: False)

    result = await manager.start_download({"model_types": ["lora"], "delay": 0, "optimize": False})
    assert result["success"] is True

    if manager._download_task is not None:
        await asyncio.wait_for(manager._download_task, timeout=1)

    assert refresh_calls == [model_hash]
    assert missing_url in downloader.calls
    assert manager._progress["failed_models"] == {model_hash}
    assert model_hash in manager._progress["processed_models"]

    remaining_images = model_metadata["civitai"]["images"]
    assert remaining_images == [
        {"url": missing_url, "downloadFailed": True, "downloadError": "not_found"},
        {"url": valid_url},
    ]

    files = sorted(p.name for p in model_dir.iterdir())
    assert files == ["image_0.png", "image_1.png"]
    assert (model_dir / "image_0.png").read_bytes() == b"first"
    assert (model_dir / "image_1.png").read_bytes() == b"second"


@pytest.fixture
def settings_manager():
    return get_settings_manager()
