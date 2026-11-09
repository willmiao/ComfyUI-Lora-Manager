from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils import example_images_download_manager as download_module
from py.utils.example_images_processor import ImageDownloadOutcome


class RecordingWebSocketManager:
    """Collects broadcast payloads for assertions."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def broadcast(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


class StubScanner:
    """Scanner double returning predetermined cache contents."""

    def __init__(self, models: list[dict[str, Any]]) -> None:
        self._cache = SimpleNamespace(raw_data=models)
        self.sync_calls: list[tuple[str, dict[str, Any]]] = []

    async def get_cached_data(self):
        return self._cache

    async def update_single_model_cache(self, _old_path, _new_path, metadata):
        # Replace the cached entry with the updated metadata for assertions.
        for index, model in enumerate(self._cache.raw_data):
            if model.get("file_path") == metadata.get("file_path"):
                self._cache.raw_data[index] = metadata
                break
        return True

    async def sync_cache_from_metadata(self, file_path: str, metadata: dict[str, Any]) -> bool:
        self.sync_calls.append((file_path, metadata))
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


def test_limiter_factory_uses_probe_ceiling(
    monkeypatch: pytest.MonkeyPatch, settings_manager
):
    manager = download_module.DownloadManager(
        ws_manager=RecordingWebSocketManager()
    )
    monkeypatch.setitem(
        settings_manager.settings, "example_images_download_concurrency", 6
    )
    monkeypatch.setitem(
        settings_manager.settings, "example_images_download_max_concurrency", 8
    )

    limiter = manager._create_media_download_limiter(True)
    assert limiter.max_concurrency == 6
    assert limiter.probe_max_concurrency == 8

    original_limiter = manager._create_media_download_limiter(False)
    assert original_limiter.max_concurrency == 2
    assert original_limiter.probe_max_concurrency == 2


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
async def test_get_status_compact_replaces_hash_lists_with_counts():
    manager = download_module.DownloadManager(
        ws_manager=RecordingWebSocketManager()
    )
    manager._is_downloading = True
    manager._progress.update(
        total=3,
        completed=2,
        processed_models={"a", "b"},
        failed_models={"c"},
        rate_limited_models={"d"},
    )

    full = await manager.get_status(SimpleNamespace(query={}))
    # The progress sets are unordered, so only their contents are contractual.
    assert set(full["status"]["processed_models"]) == {"a", "b"}
    assert set(full["status"]["failed_models"]) == {"c"}

    compact = await manager.get_status(
        SimpleNamespace(query={"compact": "1"})
    )
    assert "processed_models" not in compact["status"]
    assert "failed_models" not in compact["status"]
    assert compact["status"]["processed_count"] == 2
    assert compact["status"]["failed_count"] == 1
    assert compact["status"]["rate_limited_count"] == 1
    assert compact["status"]["total"] == 3


@pytest.mark.usefixtures("tmp_path")
async def test_progress_is_persisted_for_downloaded_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """The periodic save must run on the normal download path.

    It used to live inside ``_process_model`` after a branch that returned
    early whenever a model had Civitai images, so a long run never refreshed
    ``.download_progress.json`` and a crash lost every processed/failed entry.
    """

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    models = [
        {
            "sha256": f"hash-{index}",
            "model_name": f"Model {index}",
            "file_path": str(tmp_path / f"model-{index}.safetensors"),
            "file_name": f"model-{index}.safetensors",
            "civitai": {"images": [{"url": f"https://example.com/{index}.png"}]},
        }
        for index in range(11)
    ]
    _patch_scanner(monkeypatch, StubScanner(models))

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    async def fake_update_metadata(*_args, **_kwargs):
        return True

    async def fake_get_updated_model(model_hash, _scanner):
        return next(model for model in models if model["sha256"] == model_hash)

    async def fake_download_model_images(*_args, **_kwargs):
        return ImageDownloadOutcome()

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
    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "get_updated_model",
        staticmethod(fake_get_updated_model),
    )
    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "download_model_images_with_tracking",
        staticmethod(fake_download_model_images),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)

    saved_at: list[int] = []
    original_save = manager._save_progress

    def recording_save(output_dir):
        saved_at.append(manager._progress["completed"])
        original_save(output_dir)

    monkeypatch.setattr(manager, "_save_progress", recording_save)

    await manager.start_download({"model_types": ["lora"], "delay": 0})
    await asyncio.wait_for(manager._download_task, timeout=2)

    assert 10 in saved_at

    progress_files = list(Path(tmp_path).rglob(".download_progress.json"))
    assert len(progress_files) == 1
    progress = json.loads(progress_files[0].read_text(encoding="utf-8"))
    assert len(progress["processed_models"]) == 11


@pytest.mark.usefixtures("tmp_path")
async def test_pause_resume_blocks_processing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "example_images_model_concurrency", 1)

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
        return ImageDownloadOutcome()

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
async def test_model_pipeline_overlaps_across_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Two models may have media jobs in flight at the same time."""

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "example_images_model_concurrency", 2)

    models = [
        {
            "sha256": "a" * 64,
            "model_name": "Pipeline One",
            "file_path": str(tmp_path / "one.safetensors"),
            "file_name": "one.safetensors",
            "civitai": {"images": [{"url": "https://example.com/one.png"}]},
        },
        {
            "sha256": "b" * 64,
            "model_name": "Pipeline Two",
            "file_path": str(tmp_path / "two.safetensors"),
            "file_name": "two.safetensors",
            "civitai": {"images": [{"url": "https://example.com/two.png"}]},
        },
    ]
    _patch_scanner(monkeypatch, StubScanner(models))

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    started: set[str] = set()
    both_started = asyncio.Event()
    release = asyncio.Event()

    async def fake_download_model_images(model_hash, *_args, **_kwargs):
        started.add(model_hash)
        if len(started) == 2:
            both_started.set()
        await release.wait()
        return ImageDownloadOutcome()

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

    await manager.start_download({"model_types": ["lora"], "delay": 0})
    try:
        await asyncio.wait_for(both_started.wait(), timeout=1)
    finally:
        release.set()
    if manager._download_task is not None:
        await asyncio.wait_for(manager._download_task, timeout=1)

    assert manager._progress["completed"] == 2
    assert started == {"a" * 64, "b" * 64}
    assert manager._progress["status"] == "completed"


@pytest.mark.usefixtures("tmp_path")
async def test_existing_folder_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"default": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "default")

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
    (legacy_folder / download_module.COMPLETION_MARKER_FILENAME).write_text(
        '{"version": 1}', encoding="utf-8"
    )

    process_called = False
    download_called = False

    async def fake_process_local_examples(*_args, **_kwargs):
        nonlocal process_called
        process_called = True
        return False

    async def fake_download_model_images(*_args, **_kwargs):
        nonlocal download_called
        download_called = True
        return ImageDownloadOutcome()

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

    assert legacy_folder.exists()
    assert not process_called
    assert not download_called
    assert model_hash in manager._progress["processed_models"]


@pytest.mark.usefixtures("tmp_path")
async def test_existing_progress_file_is_used(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"default": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "default")

    model_hash = "e" * 64
    model_path = tmp_path / "model-two.safetensors"
    model_path.write_text("data", encoding="utf-8")

    legacy_progress = tmp_path / ".download_progress.json"
    legacy_progress.write_text(json.dumps({"processed_models": [model_hash], "failed_models": []}), encoding="utf-8")

    legacy_folder = tmp_path / model_hash
    legacy_folder.mkdir()
    (legacy_folder / "image_0.png").write_text("data", encoding="utf-8")
    (legacy_folder / download_module.COMPLETION_MARKER_FILENAME).write_text(
        '{"version": 1}', encoding="utf-8"
    )

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
        raise AssertionError("Remote download should not be attempted for processed models")

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

    assert model_hash in manager._progress["processed_models"]
    assert legacy_progress.exists()
    contents = json.loads(legacy_progress.read_text(encoding="utf-8"))
    assert model_hash in contents.get("processed_models", [])


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

    model_metadata: dict[str, Any] = {
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
    # Pre-existing file collides with the valid image index (1) so the
    # pre-download existence check must skip it without a network request
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
    assert scanner.sync_calls
    assert len(scanner.sync_calls) == 1
    assert scanner.sync_calls[0][0] == str(model_path)

    remaining_images = model_metadata["civitai"]["images"]
    assert remaining_images == [
        {"url": missing_url, "downloadFailed": True, "downloadError": "not_found"},
        {"url": valid_url},
    ]

    files = sorted(
        p.name
        for p in model_dir.iterdir()
        if p.name != download_module.COMPLETION_MARKER_FILENAME
    )
    assert files == ["image_1.png"]
    assert (model_dir / "image_1.png").read_bytes() == b"second"
    assert (model_dir / download_module.COMPLETION_MARKER_FILENAME).exists()


async def test_failed_models_retried_when_explicitly_targeted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    images_root = tmp_path / "examples"
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(images_root))

    model_hash = "a" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("data", encoding="utf-8")

    model_metadata = {
        "sha256": model_hash,
        "model_name": "Failed Example",
        "file_path": str(model_path),
        "file_name": "model.safetensors",
        "civitai": {"images": [{"url": "https://example.com/valid.png"}]},
    }

    scanner = StubScanner([model_metadata.copy()])
    _patch_scanner(monkeypatch, scanner)

    # Persist a previous failure so the skip path is exercised
    images_root.mkdir(parents=True, exist_ok=True)
    (images_root / ".download_progress.json").write_text(
        json.dumps(
            {
                "failed_models": [model_hash],
                "processed_models": [],
                "rate_limited_models": [],
            }
        ),
        encoding="utf-8",
    )

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    async def fake_get_updated_model(model_hash_arg, _scanner):
        return model_metadata

    class DownloaderStub:
        def __init__(self):
            self.calls: list[str] = []

        async def download_to_memory(self, url, *_args, **_kwargs):
            self.calls.append(url)
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
        "get_updated_model",
        staticmethod(fake_get_updated_model),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)

    # Without explicit hashes the previously failed model is skipped
    skipped_manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    result = await skipped_manager.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True
    if skipped_manager._download_task is not None:
        await asyncio.wait_for(skipped_manager._download_task, timeout=1)
    assert downloader.calls == []

    # With explicit hashes the previously failed model is retried and cleared
    result = await manager.start_download(
        {"model_types": ["lora"], "delay": 0, "model_hashes": [model_hash]}
    )
    assert result["success"] is True
    if manager._download_task is not None:
        await asyncio.wait_for(manager._download_task, timeout=1)
    assert downloader.calls == ["https://example.com/valid.png"]
    assert manager._progress["failed_models"] == set()
    assert model_hash in manager._progress["processed_models"]


async def test_unmarked_partial_folder_is_repaired_then_skipped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()

    images_root = tmp_path / "examples"
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(images_root))

    model_hash = "b" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("data", encoding="utf-8")

    model_metadata = {
        "sha256": model_hash,
        "model_name": "Partial Example",
        "file_path": str(model_path),
        "file_name": "model.safetensors",
        "civitai": {
            "images": [
                {"url": "https://example.com/first.png"},
                {"url": "https://example.com/second.png"},
            ]
        },
    }

    scanner = StubScanner([model_metadata.copy()])
    _patch_scanner(monkeypatch, scanner)

    # Simulate a partially populated folder: index 0 already downloaded
    model_dir = images_root / model_hash
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "image_0.png").write_bytes(b"existing")

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    async def fake_get_updated_model(model_hash_arg, _scanner):
        return model_metadata

    class DownloaderStub:
        def __init__(self):
            self.calls: list[str] = []

        async def download_to_memory(self, url, *_args, **_kwargs):
            self.calls.append(url)
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
        "get_updated_model",
        staticmethod(fake_get_updated_model),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)

    # A populated folder without a completion marker is unverified: the
    # untargeted run fills the missing index instead of treating it as done.
    # Even a previously failed model must be re-checked when it has files but
    # no marker.
    (images_root / ".download_progress.json").write_text(
        json.dumps({"failed_models": [model_hash], "failure_reasons": {model_hash: "unavailable"}}),
        encoding="utf-8",
    )
    untargeted = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    result = await untargeted.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True
    if untargeted._download_task is not None:
        await asyncio.wait_for(untargeted._download_task, timeout=1)
    assert downloader.calls == ["https://example.com/second.png"]
    assert (model_dir / download_module.COMPLETION_MARKER_FILENAME).exists()
    assert model_hash not in untargeted._progress["failed_models"]

    # The marker now records completion; the next untargeted pass skips it.
    downloader.calls.clear()
    verified = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    result = await verified.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True
    if verified._download_task is not None:
        await asyncio.wait_for(verified._download_task, timeout=1)
    assert downloader.calls == []

    # Explicit targets still bypass the marker, but the per-image check skips
    # both existing files, so there is no network request either.
    targeted = download_module.DownloadManager(ws_manager=ws_manager)
    result = await targeted.start_download(
        {"model_types": ["lora"], "delay": 0, "model_hashes": [model_hash]}
    )
    assert result["success"] is True
    if targeted._download_task is not None:
        await asyncio.wait_for(targeted._download_task, timeout=1)
    assert downloader.calls == []
    assert (model_dir / "image_1.png").exists()
    assert (model_dir / "image_0.png").read_bytes() == b"existing"


@pytest.fixture
def settings_manager():
    return get_settings_manager()


async def _run_single_model_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
    model_metadata: dict[str, Any],
    *,
    get_updated_model=None,
):
    """Shared harness: run one download pass over a single lora model."""

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    images_root = tmp_path / "examples"
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(images_root))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"default": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "default")

    scanner = StubScanner([model_metadata.copy()])
    _patch_scanner(monkeypatch, scanner)

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    if get_updated_model is None:
        async def get_updated_model(_hash, _scanner):
            return model_metadata

    async def fake_get_downloader():
        return object()

    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "process_local_examples",
        staticmethod(fake_process_local_examples),
    )
    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "get_updated_model",
        staticmethod(get_updated_model),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)

    result = await manager.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True
    if manager._download_task is not None:
        await asyncio.wait_for(manager._download_task, timeout=1)

    return manager, images_root


async def test_model_without_civitai_metadata_stays_pending(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Metadata not fetched yet is retryable: the model must NOT be blacklisted."""

    model_hash = "c" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("data", encoding="utf-8")

    model_metadata = {
        "sha256": model_hash,
        "model_name": "No Metadata Yet",
        "file_path": str(model_path),
        "file_name": "model.safetensors",
    }

    manager, images_root = await _run_single_model_download(
        monkeypatch, tmp_path, settings_manager, model_metadata
    )

    assert model_hash not in manager._progress["failed_models"]
    assert model_hash not in manager._progress["processed_models"]
    assert model_hash in manager._progress["retryable_models"]

    saved = json.loads((images_root / ".download_progress.json").read_text(encoding="utf-8"))
    assert model_hash not in saved["failed_models"]


async def test_metadata_refresh_timeout_does_not_block_the_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """A hung provider refresh is bounded and the model is still finalized."""

    model_hash = "1" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("data", encoding="utf-8")
    image_url = "https://example.com/missing.png"
    model_metadata = {
        "sha256": model_hash,
        "model_name": "Slow Provider",
        "file_path": str(model_path),
        "file_name": "model.safetensors",
        "civitai": {"images": [{"url": image_url}]},
    }

    async def fake_download(*_args, **_kwargs):
        return ImageDownloadOutcome(failed=[image_url], is_stale=True)

    async def slow_refresh(*_args, **_kwargs):
        await asyncio.sleep(10)

    async def fake_save(*_args, **_kwargs):
        return True

    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "download_model_images_with_tracking",
        staticmethod(fake_download),
    )
    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "refresh_model_metadata",
        staticmethod(slow_refresh),
    )
    monkeypatch.setattr(
        download_module.MetadataManager,
        "save_metadata",
        staticmethod(fake_save),
    )
    monkeypatch.setattr(
        download_module, "METADATA_REFRESH_TIMEOUT_SECONDS", 0.05
    )

    started = asyncio.get_running_loop().time()
    manager, _ = await _run_single_model_download(
        monkeypatch, tmp_path, settings_manager, model_metadata
    )
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 1.0
    assert model_hash in manager._progress["refreshed_models"]
    assert model_hash in manager._progress["failed_models"]
    assert manager._progress.snapshot()["failure_summary"]["unavailable"] == 1


async def test_model_with_imageless_civitai_metadata_marked_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Provider metadata exists but carries no images: permanently failed."""

    model_hash = "d" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("data", encoding="utf-8")

    model_metadata = {
        "sha256": model_hash,
        "model_name": "Imageless Entry",
        "file_path": str(model_path),
        "file_name": "model.safetensors",
        "civitai": {"id": 123, "name": "Imageless Entry"},
    }

    manager, _ = await _run_single_model_download(
        monkeypatch, tmp_path, settings_manager, model_metadata
    )

    assert model_hash in manager._progress["failed_models"]
    assert manager._progress.snapshot()["failure_summary"]["no_media"] == 1


async def test_civitai_deleted_model_marked_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Models confirmed absent from CivitAI stay on the failed list."""

    model_hash = "e" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("data", encoding="utf-8")

    model_metadata = {
        "sha256": model_hash,
        "model_name": "Deleted From CivitAI",
        "file_path": str(model_path),
        "file_name": "model.safetensors",
        "civitai_deleted": True,
        "from_civitai": False,
    }

    manager, _ = await _run_single_model_download(
        monkeypatch, tmp_path, settings_manager, model_metadata
    )

    assert model_hash in manager._progress["failed_models"]


async def test_processing_error_does_not_blacklist_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Transient errors must leave the model pending instead of blacklisting it."""

    model_hash = "f" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("data", encoding="utf-8")

    model_metadata = {
        "sha256": model_hash,
        "model_name": "Transient Error",
        "file_path": str(model_path),
        "file_name": "model.safetensors",
        "civitai": {"images": [{"url": "https://example.com/one.png"}]},
    }

    async def failing_get_updated_model(_hash, _scanner):
        raise RuntimeError("boom")

    manager, _ = await _run_single_model_download(
        monkeypatch,
        tmp_path,
        settings_manager,
        model_metadata,
        get_updated_model=failing_get_updated_model,
    )

    assert model_hash not in manager._progress["failed_models"]
    assert manager._progress["last_error"]


def test_unblock_failed_example_image_models_updates_file_and_memory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    images_root = tmp_path / "examples"
    images_root.mkdir()
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(images_root))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"default": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "default")

    model_hash = "a" * 64
    other_hash = "b" * 64
    progress_file = images_root / ".download_progress.json"
    progress_file.write_text(
        json.dumps(
            {
                "processed_models": [other_hash],
                "failed_models": [model_hash, other_hash],
                "rate_limited_models": [],
            }
        ),
        encoding="utf-8",
    )

    manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    manager._progress["failed_models"] = {model_hash, other_hash}
    monkeypatch.setattr(download_module, "_default_download_manager", manager)

    removed = download_module.unblock_failed_example_image_models([model_hash.upper()])
    assert removed == 1

    saved = json.loads(progress_file.read_text(encoding="utf-8"))
    assert saved["failed_models"] == [other_hash]
    assert saved["processed_models"] == [other_hash]
    assert manager._progress["failed_models"] == {other_hash}

    # Second call is a no-op and does not rewrite the file
    assert download_module.unblock_failed_example_image_models([model_hash]) == 0


def test_unblock_failed_example_image_models_without_progress_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    images_root = tmp_path / "examples"
    images_root.mkdir()
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(images_root))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"default": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "default")

    assert download_module.unblock_failed_example_image_models(["a" * 64]) == 0


async def _run_single_outcome(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
    outcome: ImageDownloadOutcome,
    *,
    force: bool = False,
):
    model_hash = "a" * 64
    model_path = tmp_path / "model.safetensors"
    model = {
        "sha256": model_hash,
        "model_name": "Outcome Model",
        "file_path": str(model_path),
        "file_name": "model.safetensors",
        "civitai": {"images": [{"url": "https://img.genur.art/sig/x/y"}]},
    }
    _patch_scanner(monkeypatch, StubScanner([model]))
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    captured: dict[str, Any] = {}

    async def fake_download(*_args, **kwargs):
        captured.update(kwargs)
        return outcome

    async def fake_get_downloader():
        return object()

    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "process_local_examples",
        staticmethod(fake_process_local_examples),
    )
    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "download_model_images_with_tracking",
        staticmethod(fake_download),
    )
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)

    manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    await manager.start_download(
        {"model_types": ["lora"], "delay": 0, "force": force}
    )
    if manager._download_task is not None:
        await asyncio.wait_for(manager._download_task, timeout=2)
    return manager, model_hash, captured


@pytest.mark.asyncio
async def test_transient_failure_leaves_model_retryable(
    monkeypatch: pytest.MonkeyPatch, tmp_path, settings_manager
) -> None:
    outcome = ImageDownloadOutcome(transient=["https://img.genur.art/sig/x/y"])
    manager, model_hash, _ = await _run_single_outcome(
        monkeypatch, tmp_path, settings_manager, outcome
    )

    assert model_hash in manager._progress["retryable_models"]
    assert model_hash not in manager._progress["processed_models"]
    assert model_hash not in manager._progress["failed_models"]


@pytest.mark.asyncio
async def test_skipped_flagged_image_is_not_reported_as_recovered(
    monkeypatch: pytest.MonkeyPatch, tmp_path, settings_manager
) -> None:
    outcome = ImageDownloadOutcome(skipped_failed=1)
    manager, model_hash, _ = await _run_single_outcome(
        monkeypatch, tmp_path, settings_manager, outcome
    )

    assert model_hash in manager._progress["failed_models"]
    assert model_hash not in manager._progress["processed_models"]
    assert manager._progress.snapshot()["failure_summary"]["unavailable"] == 1


@pytest.mark.asyncio
async def test_force_passes_retry_failed_to_processor(
    monkeypatch: pytest.MonkeyPatch, tmp_path, settings_manager
) -> None:
    manager, model_hash, captured = await _run_single_outcome(
        monkeypatch,
        tmp_path,
        settings_manager,
        ImageDownloadOutcome(),
        force=True,
    )

    assert captured["retry_failed"] is True
    assert model_hash in manager._progress["processed_models"]


@pytest.mark.asyncio
async def test_clear_recovered_flags_only_touches_matching_images(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    recovered_url = "https://img.genur.art/sig/x/y"
    other_url = "https://image.civitai.com/x/y/original=true/1.jpeg"
    model_data = {
        "file_path": str(tmp_path / "model.safetensors"),
        "civitai": {
            "images": [
                {
                    "url": recovered_url,
                    "type": "image",
                    "downloadFailed": True,
                    "downloadError": "not_found",
                },
                {
                    "url": other_url,
                    "type": "image",
                    "downloadFailed": True,
                    "downloadError": "not_found",
                },
            ]
        },
    }

    async def fake_get_updated_model(*_args, **_kwargs):
        return model_data

    saved: list[dict[str, Any]] = []
    cached: list[dict[str, Any]] = []

    async def fake_save(_path, payload):
        saved.append(payload)
        return True

    async def fake_update_cache(_scanner, _path, payload):
        cached.append(payload)
        return True

    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "get_updated_model",
        staticmethod(fake_get_updated_model),
    )
    monkeypatch.setattr(
        download_module.MetadataManager, "save_metadata", staticmethod(fake_save)
    )
    monkeypatch.setattr(
        download_module, "update_cache_from_metadata", fake_update_cache
    )

    await manager._clear_failed_images_from_metadata(
        "hash", "Model", {recovered_url}, object()
    )

    assert "downloadFailed" not in model_data["civitai"]["images"][0]
    assert "downloadError" not in model_data["civitai"]["images"][0]
    assert model_data["civitai"]["images"][1]["downloadFailed"] is True
    assert saved and "folder" not in saved[0]
    assert cached


@pytest.mark.asyncio
async def test_transient_failure_removes_completion_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path, settings_manager
) -> None:
    """A retryable pass must not leave a marker that hides its missing media."""

    model_hash = "9" * 64
    image_url = "https://example.com/one.png"
    model = {
        "sha256": model_hash,
        "model_name": "Transient Model",
        "file_path": str(tmp_path / "transient.safetensors"),
        "file_name": "transient.safetensors",
        "civitai": {"images": [{"url": image_url}]},
    }
    scanner = StubScanner([model])
    _patch_scanner(monkeypatch, scanner)
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "active_library", "comfyui")

    model_dir = download_module.ExampleImagePathResolver.get_model_folder(
        model_hash, "comfyui"
    )
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    Path(model_dir, "image_0.png").write_bytes(b"existing")
    marker = Path(model_dir, download_module.COMPLETION_MARKER_FILENAME)
    marker.write_text('{"version": 1}', encoding="utf-8")

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    async def fake_get_updated_model(_hash, _scanner):
        return model

    async def fake_download(*_args, **_kwargs):
        return ImageDownloadOutcome(transient=[image_url])

    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "process_local_examples",
        staticmethod(fake_process_local_examples),
    )
    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "get_updated_model",
        staticmethod(fake_get_updated_model),
    )
    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "download_model_images_with_tracking",
        staticmethod(fake_download),
    )

    manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    manager._progress["status"] = "running"

    await manager._process_model(
        "lora",
        model,
        scanner,
        str(tmp_path),
        True,
        object(),
        "comfyui",
        force=True,
    )

    assert marker.exists() is False
    assert model_hash not in manager._progress["processed_models"]
    assert model_hash in manager._progress["retryable_models"]


@pytest.mark.asyncio
async def test_specific_download_writes_completion_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path, settings_manager
) -> None:
    """The forced/specific path must also record a verified folder."""

    model_hash = "8" * 64
    model = {
        "sha256": model_hash,
        "model_name": "Specific Model",
        "file_path": str(tmp_path / "specific.safetensors"),
        "file_name": "specific.safetensors",
        "civitai": {"images": [{"url": "https://example.com/one.png"}]},
    }
    scanner = StubScanner([model])
    _patch_scanner(monkeypatch, scanner)
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "active_library", "comfyui")

    model_dir = download_module.ExampleImagePathResolver.get_model_folder(
        model_hash, "comfyui"
    )
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    Path(model_dir, "image_0.png").write_bytes(b"existing")

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    async def fake_get_updated_model(_hash, _scanner):
        return model

    async def fake_download(*_args, **_kwargs):
        return ImageDownloadOutcome()

    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "process_local_examples",
        staticmethod(fake_process_local_examples),
    )
    monkeypatch.setattr(
        download_module.MetadataUpdater,
        "get_updated_model",
        staticmethod(fake_get_updated_model),
    )
    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "download_model_images_with_tracking",
        staticmethod(fake_download),
    )

    manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    manager._progress["status"] = "running"

    result = await manager._process_specific_model(
        "lora",
        model,
        scanner,
        str(tmp_path),
        True,
        object(),
        "comfyui",
    )

    assert result is True
    assert model_hash in manager._progress["processed_models"]
    assert (
        Path(model_dir, download_module.COMPLETION_MARKER_FILENAME).exists()
    )


@pytest.mark.asyncio
async def test_force_bypasses_populated_folder_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path, settings_manager
) -> None:
    model_hash = "b" * 64
    model = {
        "sha256": model_hash,
        "model_name": "Partial Model",
        "file_path": str(tmp_path / "partial.safetensors"),
        "file_name": "partial.safetensors",
        "civitai": {"images": [{"url": "https://img.genur.art/sig/x/y"}]},
    }
    scanner = StubScanner([model])
    _patch_scanner(monkeypatch, scanner)
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "active_library", "comfyui")

    model_dir = download_module.ExampleImagePathResolver.get_model_folder(
        model_hash, "comfyui"
    )
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    Path(model_dir, "image_0.webp").write_bytes(b"existing")

    async def fake_process_local_examples(*_args, **_kwargs):
        return False

    captured: dict[str, Any] = {}

    async def fake_download(*_args, **kwargs):
        captured.update(kwargs)
        return ImageDownloadOutcome()

    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "process_local_examples",
        staticmethod(fake_process_local_examples),
    )
    monkeypatch.setattr(
        download_module.ExampleImagesProcessor,
        "download_model_images_with_tracking",
        staticmethod(fake_download),
    )

    manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    manager._progress["status"] = "running"
    manager._progress["processed_models"].add(model_hash)

    await manager._process_model(
        "lora",
        model,
        scanner,
        str(tmp_path),
        False,
        object(),
        "comfyui",
        force=True,
        explicit_targets=False,
        limiter=None,
    )

    assert captured["retry_failed"] is True


@pytest.mark.asyncio
async def test_clear_recovered_flags_roundtrips_through_sidecar(
    tmp_path, settings_manager
) -> None:
    model_path = tmp_path / "roundtrip.safetensors"
    model_path.write_bytes(b"model")
    model_hash = "c" * 64
    recovered_url = "https://img.genur.art/sig/x/y"
    model_data = {
        "file_name": "roundtrip",
        "model_name": "Roundtrip Model",
        "file_path": str(model_path),
        "sha256": model_hash,
        "size": 1,
        "modified": 0,
        "base_model": "SDXL",
        "preview_url": "",
        "preview_nsfw_level": 0,
        "from_civitai": True,
        "civitai": {
            "images": [
                {
                    "url": recovered_url,
                    "type": "image",
                    "downloadFailed": True,
                    "downloadError": "not_found",
                }
            ]
        },
    }
    assert await download_module.MetadataManager.save_metadata(
        str(model_path), model_data
    )

    scanner = StubScanner([{**model_data, "folder": ""}])
    manager = download_module.DownloadManager(ws_manager=RecordingWebSocketManager())
    await manager._clear_failed_images_from_metadata(
        model_hash, "Roundtrip Model", {recovered_url}, scanner
    )

    loaded, _ = await download_module.MetadataManager.load_metadata(str(model_path))
    assert loaded is not None
    images = loaded.to_dict()["civitai"]["images"]
    assert images[0]["url"] == recovered_url
    assert "downloadFailed" not in images[0]
    assert "downloadError" not in images[0]
