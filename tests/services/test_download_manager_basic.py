"""Core functionality tests for DownloadManager."""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from py.services.download_manager import DownloadManager
from py.services import download_manager
from py.services import aria2_transfer_state
from py.services.service_registry import ServiceRegistry
from py.services.settings_manager import SettingsManager, get_settings_manager


@pytest.fixture(autouse=True)
def reset_download_manager():
    """Ensure each test operates on a fresh singleton."""
    DownloadManager._instance = None
    yield
    DownloadManager._instance = None


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch, tmp_path):
    """Point settings writes at a temporary directory to avoid touching real files."""
    manager = get_settings_manager()
    default_settings = manager._get_default_settings()
    default_settings.update(
        {
            "default_lora_root": str(tmp_path),
            "default_checkpoint_root": str(tmp_path / "checkpoints"),
            "default_embedding_root": str(tmp_path / "embeddings"),
            "download_path_templates": {
                "lora": "{base_model}/{first_tag}",
                "checkpoint": "{base_model}/{first_tag}",
                "embedding": "{base_model}/{first_tag}",
            },
            "base_model_path_mappings": {"BaseModel": "MappedModel"},
            "skip_previously_downloaded_model_versions": False,
            "download_skip_base_models": [],
        }
    )
    monkeypatch.setattr(manager, "settings", default_settings)
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)


@pytest.fixture(autouse=True)
def isolate_aria2_state(monkeypatch, tmp_path):
    state_path = tmp_path / "cache" / "aria2" / "downloads.json"
    monkeypatch.setattr(
        aria2_transfer_state,
        "get_aria2_state_path",
        lambda: str(state_path),
    )


@pytest.fixture(autouse=True)
def stub_metadata(monkeypatch):
    class _StubMetadata:
        def __init__(self, save_path: str):
            self.file_path = save_path
            self.sha256 = "sha256"
            self.file_name = Path(save_path).stem

    def _factory(save_path: str):
        return _StubMetadata(save_path)

    def _make_class():
        @staticmethod
        def from_civitai_info(_version_info, _file_info, save_path):
            return _factory(save_path)

        return type("StubMetadata", (), {"from_civitai_info": from_civitai_info})

    stub_class = _make_class()
    monkeypatch.setattr(download_manager, "LoraMetadata", stub_class)
    monkeypatch.setattr(download_manager, "CheckpointMetadata", stub_class)
    monkeypatch.setattr(download_manager, "EmbeddingMetadata", stub_class)


class DummyScanner:
    def __init__(self, exists: bool = False):
        self.exists = exists
        self.calls = []

    async def check_model_version_exists(self, version_id):
        self.calls.append(version_id)
        return self.exists


@pytest.fixture
def scanners(monkeypatch):
    lora_scanner = DummyScanner()
    checkpoint_scanner = DummyScanner()
    embedding_scanner = DummyScanner()

    monkeypatch.setattr(
        ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=lora_scanner)
    )
    monkeypatch.setattr(
        ServiceRegistry,
        "get_checkpoint_scanner",
        AsyncMock(return_value=checkpoint_scanner),
    )
    monkeypatch.setattr(
        ServiceRegistry,
        "get_embedding_scanner",
        AsyncMock(return_value=embedding_scanner),
    )

    return SimpleNamespace(
        lora=lora_scanner,
        checkpoint=checkpoint_scanner,
        embedding=embedding_scanner,
    )


@pytest.fixture
def metadata_provider(monkeypatch):
    class DummyProvider:
        def __init__(self):
            self.calls = []

        async def get_model_version(self, model_id, model_version_id):
            self.calls.append((model_id, model_version_id))
            return {
                "id": 42,
                "model": {"type": "LoRA", "tags": ["fantasy"]},
                "baseModel": "BaseModel",
                "creator": {"username": "Author"},
                "files": [
                    {
                        "type": "Model",
                        "primary": True,
                        "downloadUrl": "https://example.invalid/file.safetensors",
                        "name": "file.safetensors",
                    }
                ],
            }

    provider = DummyProvider()
    monkeypatch.setattr(
        download_manager,
        "get_default_metadata_provider",
        AsyncMock(return_value=provider),
    )
    return provider


@pytest.fixture(autouse=True)
def noop_cleanup(monkeypatch):
    async def _cleanup(self, task_id):
        if task_id in self._active_downloads:
            self._active_downloads[task_id]["cleaned"] = True

    monkeypatch.setattr(DownloadManager, "_cleanup_download_record", _cleanup)


@pytest.mark.asyncio
async def test_download_requires_identifier():
    """Test that download fails when no identifier is provided."""
    manager = DownloadManager()
    result = await manager.download_from_civitai()
    assert result == {
        "success": False,
        "error": "Either model_id or model_version_id must be provided",
    }


@pytest.mark.asyncio
async def test_successful_download_uses_defaults(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """Test successful download with default settings."""
    manager = DownloadManager()

    captured = {}

    async def fake_execute_download(
        self,
        *,
        download_urls,
        save_dir,
        metadata,
        version_info,
        relative_path,
        progress_callback,
        model_type,
        download_id,
        transfer_backend=None,
    ):
        captured.update(
            {
                "download_urls": download_urls,
                "save_dir": Path(save_dir),
                "relative_path": relative_path,
                "progress_callback": progress_callback,
                "model_type": model_type,
                "download_id": download_id,
                "metadata_path": metadata.file_path,
            }
        )
        return {"success": True}

    monkeypatch.setattr(
        DownloadManager, "_execute_download", fake_execute_download, raising=False
    )

    result = await manager.download_from_civitai(
        model_version_id=99,
        save_dir=str(tmp_path),
        use_default_paths=True,
        progress_callback=None,
        source=None,
    )

    assert result["success"] is True
    assert "download_id" in result
    assert manager._download_tasks == {}
    assert manager._active_downloads[result["download_id"]]["status"] == "completed"

    assert captured["relative_path"] == "MappedModel/fantasy"
    expected_dir = (
        Path(get_settings_manager().get("default_lora_root"))
        / "MappedModel"
        / "fantasy"
    )
    assert captured["save_dir"] == expected_dir
    assert captured["model_type"] == "lora"
    assert captured["download_urls"] == ["https://example.invalid/file.safetensors"]


@pytest.mark.asyncio
async def test_successful_download_schedules_auto_example_images(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    manager = DownloadManager()
    scheduled = []

    async def fake_execute_download(
        self,
        *,
        download_urls,
        save_dir,
        metadata,
        version_info,
        relative_path,
        progress_callback,
        model_type,
        download_id,
        transfer_backend=None,
    ):
        return {"success": True}

    async def fake_schedule(self, *, metadata, model_type):
        scheduled.append({"metadata": metadata, "model_type": model_type})

    monkeypatch.setattr(
        DownloadManager, "_execute_download", fake_execute_download, raising=False
    )
    monkeypatch.setattr(
        DownloadManager,
        "_schedule_auto_example_images_download",
        fake_schedule,
        raising=False,
    )

    result = await manager.download_from_civitai(
        model_version_id=99,
        save_dir=str(tmp_path),
        use_default_paths=True,
        progress_callback=None,
        source=None,
    )

    assert result["success"] is True
    assert len(scheduled) == 1
    assert scheduled[0]["model_type"] == "lora"
    assert scheduled[0]["metadata"].sha256 == "sha256"


@pytest.mark.asyncio
async def test_auto_example_images_download_uses_settings_payload(
    monkeypatch, tmp_path
):
    manager = DownloadManager()
    settings = get_settings_manager()
    settings.settings["auto_download_example_images"] = True
    settings.settings["example_images_path"] = str(tmp_path / "examples")
    settings.settings["optimize_example_images"] = False

    calls = []

    class DummyExampleImagesManager:
        async def start_force_download(self, payload):
            calls.append(payload)
            return {"success": True}

    from py.utils import example_images_download_manager

    monkeypatch.setattr(
        ServiceRegistry,
        "get_websocket_manager",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        example_images_download_manager,
        "get_default_download_manager",
        lambda _ws_manager: DummyExampleImagesManager(),
    )

    metadata = SimpleNamespace(sha256="ABCDEF", file_path="model.safetensors")
    await manager._schedule_auto_example_images_download(
        metadata=metadata,
        model_type="lora",
    )

    for _ in range(10):
        if calls:
            break
        await asyncio.sleep(0)

    assert calls == [
        {
            "model_hashes": ["abcdef"],
            "optimize": False,
            "model_types": ["lora"],
            "delay": 0,
        }
    ]


@pytest.mark.asyncio
async def test_auto_example_images_download_skips_without_configuration(
    monkeypatch, tmp_path
):
    manager = DownloadManager()
    settings = get_settings_manager()
    settings.settings["auto_download_example_images"] = True
    settings.settings["example_images_path"] = ""

    get_ws_manager = AsyncMock(return_value=object())
    monkeypatch.setattr(ServiceRegistry, "get_websocket_manager", get_ws_manager)

    await manager._schedule_auto_example_images_download(
        metadata=SimpleNamespace(sha256="abcdef", file_path="model.safetensors"),
        model_type="lora",
    )
    await asyncio.sleep(0)

    get_ws_manager.assert_not_called()

    settings.settings["example_images_path"] = str(tmp_path / "examples")
    await manager._schedule_auto_example_images_download(
        metadata=SimpleNamespace(sha256="", file_path="model.safetensors"),
        model_type="lora",
    )
    await asyncio.sleep(0)

    get_ws_manager.assert_not_called()


@pytest.mark.asyncio
async def test_download_uses_active_mirrors(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """Test that active mirrors are used when available."""
    manager = DownloadManager()

    metadata_with_mirrors = {
        "id": 42,
        "model": {"type": "LoRA", "tags": ["fantasy"]},
        "baseModel": "BaseModel",
        "creator": {"username": "Author"},
        "files": [
            {
                "type": "Model",
                "primary": True,
                "downloadUrl": "https://example.invalid/file.safetensors",
                "mirrors": [
                    {
                        "url": "https://mirror.example/file.safetensors",
                        "deletedAt": None,
                    },
                    {
                        "url": "https://mirror.example/old.safetensors",
                        "deletedAt": "2024-01-01",
                    },
                ],
                "name": "file.safetensors",
            }
        ],
    }

    metadata_provider.get_model_version = AsyncMock(return_value=metadata_with_mirrors)

    captured = {}

    async def fake_execute_download(
        self,
        *,
        download_urls,
        save_dir,
        metadata,
        version_info,
        relative_path,
        progress_callback,
        model_type,
        download_id,
        transfer_backend=None,
    ):
        captured["download_urls"] = download_urls
        return {"success": True}

    monkeypatch.setattr(
        DownloadManager, "_execute_download", fake_execute_download, raising=False
    )

    result = await manager.download_from_civitai(
        model_version_id=99,
        save_dir=str(tmp_path),
        use_default_paths=True,
        progress_callback=None,
        source=None,
    )

    assert result["success"] is True
    assert captured["download_urls"] == ["https://mirror.example/file.safetensors"]


@pytest.mark.asyncio
async def test_pause_resume_cancel_delegate_to_aria2_backend(monkeypatch):
    manager = DownloadManager()

    task = asyncio.create_task(asyncio.sleep(60))
    manager._download_tasks["download-1"] = task
    manager._pause_events["download-1"] = download_manager.DownloadStreamControl()
    manager._active_downloads["download-1"] = {
        "transfer_backend": "aria2",
        "status": "downloading",
    }

    class DummyAria2Downloader:
        def __init__(self):
            self.calls = []

        async def pause_download(self, download_id):
            self.calls.append(("pause", download_id))
            return {"success": True, "message": "paused"}

        async def resume_download(self, download_id):
            self.calls.append(("resume", download_id))
            return {"success": True, "message": "resumed"}

        async def cancel_download(self, download_id):
            self.calls.append(("cancel", download_id))
            return {"success": True, "message": "cancelled"}

        async def has_transfer(self, download_id):
            self.calls.append(("has_transfer", download_id))
            return True

    dummy_aria2 = DummyAria2Downloader()
    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=dummy_aria2),
    )

    pause_result = await manager.pause_download("download-1")
    assert pause_result["success"] is True
    assert manager._active_downloads["download-1"]["status"] == "paused"

    resume_result = await manager.resume_download("download-1")
    assert resume_result["success"] is True
    assert manager._active_downloads["download-1"]["status"] == "downloading"

    cancel_result = await manager.cancel_download("download-1")
    assert cancel_result["success"] is True
    assert task.cancelled() or task.done()
    assert dummy_aria2.calls == [
        ("has_transfer", "download-1"),
        ("pause", "download-1"),
        ("has_transfer", "download-1"),
        ("resume", "download-1"),
        ("cancel", "download-1"),
    ]


@pytest.mark.asyncio
async def test_cancel_allows_queued_aria2_task_without_transfer(monkeypatch):
    manager = DownloadManager()

    started = asyncio.Event()

    async def blocked_task():
        started.set()
        await asyncio.sleep(60)

    task = asyncio.create_task(blocked_task())
    await started.wait()

    manager._download_tasks["download-queued"] = task
    manager._active_downloads["download-queued"] = {
        "transfer_backend": "aria2",
        "status": "queued",
    }

    class DummyAria2Downloader:
        async def cancel_download(self, download_id):
            return {"success": False, "error": "Download task not found"}

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    result = await manager.cancel_download("download-queued")

    assert result["success"] is True
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_pause_resume_queued_aria2_task_without_transfer(monkeypatch):
    manager = DownloadManager()

    task = asyncio.create_task(asyncio.sleep(60))
    manager._download_tasks["download-queued"] = task
    manager._pause_events["download-queued"] = download_manager.DownloadStreamControl()
    manager._active_downloads["download-queued"] = {
        "transfer_backend": "aria2",
        "status": "waiting",
        "bytes_per_second": 12.0,
    }

    class DummyAria2Downloader:
        def __init__(self):
            self.calls = []

        async def has_transfer(self, download_id):
            self.calls.append(("has_transfer", download_id))
            return False

        async def pause_download(self, download_id):
            self.calls.append(("pause", download_id))
            return {"success": True, "message": "paused"}

        async def resume_download(self, download_id):
            self.calls.append(("resume", download_id))
            return {"success": True, "message": "resumed"}

    dummy_aria2 = DummyAria2Downloader()
    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=dummy_aria2),
    )

    pause_result = await manager.pause_download("download-queued")
    assert pause_result == {"success": True, "message": "Download paused successfully"}
    assert manager._active_downloads["download-queued"]["status"] == "paused"
    assert manager._pause_events["download-queued"].is_paused() is True

    resume_result = await manager.resume_download("download-queued")
    assert resume_result == {"success": True, "message": "Download resumed successfully"}
    assert manager._active_downloads["download-queued"]["status"] == "downloading"
    assert manager._pause_events["download-queued"].is_set() is True
    assert dummy_aria2.calls == [
        ("has_transfer", "download-queued"),
        ("has_transfer", "download-queued"),
    ]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_resume_download_restores_persisted_aria2_task(monkeypatch, tmp_path):
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    save_path = save_dir / "file.safetensors"
    save_path.write_text("partial")
    (save_dir / "file.safetensors.aria2").write_text("control")

    await manager._aria2_state_store.upsert(
        "download-1",
        {
            "download_id": "download-1",
            "transfer_backend": "aria2",
            "status": "paused",
            "save_dir": str(save_dir),
            "relative_path": "",
            "use_default_paths": False,
            "save_path": str(save_path),
            "file_path": str(save_path),
            "model_id": 12,
            "model_version_id": 34,
        },
    )

    created = {}

    async def fake_download_with_semaphore(
        self,
        task_id,
        model_id,
        model_version_id,
        save_dir,
        relative_path,
        progress_callback=None,
        use_default_paths=False,
        source=None,
        file_params=None,
    ):
        created.update(
            {
                "task_id": task_id,
                "model_id": model_id,
                "model_version_id": model_version_id,
                "save_dir": save_dir,
            }
        )
        return {"success": True}

    class DummyAria2Downloader:
        def __init__(self):
            self.calls = []

        async def get_status_by_gid(self, gid):
            return None

        async def has_transfer(self, download_id):
            self.calls.append(("has_transfer", download_id))
            return False

        async def resume_download(self, download_id):
            self.calls.append(("resume", download_id))
            return {"success": True, "message": "resumed"}

        async def restore_transfer(self, download_id, gid, save_path):
            self.calls.append(("restore_transfer", download_id, gid, save_path))

    dummy_aria2 = DummyAria2Downloader()
    monkeypatch.setattr(
        download_manager, "_download_with_semaphore", None, raising=False
    )
    monkeypatch.setattr(
        DownloadManager,
        "_download_with_semaphore",
        fake_download_with_semaphore,
    )
    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=dummy_aria2),
    )

    result = await manager.resume_download("download-1")
    await asyncio.sleep(0)

    assert result == {"success": True, "message": "Download resumed successfully"}
    assert created["task_id"] == "download-1"
    assert created["model_version_id"] == 34
    assert manager._active_downloads["download-1"]["status"] == "downloading"
    assert manager._pause_events["download-1"].is_set() is True


@pytest.mark.asyncio
async def test_get_active_downloads_restores_persisted_aria2_entries(monkeypatch, tmp_path):
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    save_path = save_dir / "file.safetensors"
    save_path.write_text("partial")
    (save_dir / "file.safetensors.aria2").write_text("control")

    await manager._aria2_state_store.upsert(
        "download-1",
        {
            "download_id": "download-1",
            "transfer_backend": "aria2",
            "status": "paused",
            "save_path": str(save_path),
            "file_path": str(save_path),
            "model_id": 12,
            "model_version_id": 34,
        },
    )

    class DummyAria2Downloader:
        async def get_status_by_gid(self, gid):
            return None

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    downloads = await manager.get_active_downloads()

    assert downloads["downloads"] == [
        {
            "download_id": "download-1",
            "model_id": 12,
            "model_version_id": 34,
            "progress": 0,
            "status": "paused",
            "error": None,
            "bytes_downloaded": 0,
            "total_bytes": None,
            "bytes_per_second": 0.0,
        }
    ]


@pytest.mark.asyncio
async def test_get_active_downloads_restores_orphaned_aria2_partial_as_paused(
    monkeypatch, tmp_path
):
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    save_path = save_dir / "file.safetensors"
    save_path.write_text("partial")
    (save_dir / "file.safetensors.aria2").write_text("control")

    await manager._aria2_state_store.upsert(
        "download-1",
        {
            "download_id": "download-1",
            "transfer_backend": "aria2",
            "status": "downloading",
            "save_path": str(save_path),
            "file_path": str(save_path),
            "model_id": 12,
            "model_version_id": 34,
            "gid": "missing-gid",
        },
    )

    class DummyAria2Downloader:
        async def get_status_by_gid(self, gid):
            return None

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    downloads = await manager.get_active_downloads()
    persisted = await manager._aria2_state_store.get("download-1")

    assert downloads["downloads"] == [
        {
            "download_id": "download-1",
            "model_id": 12,
            "model_version_id": 34,
            "progress": 0,
            "status": "paused",
            "error": None,
            "bytes_downloaded": 0,
            "total_bytes": None,
            "bytes_per_second": 0.0,
        }
    ]
    assert manager._pause_events["download-1"].is_paused() is True
    assert persisted["status"] == "paused"


@pytest.mark.asyncio
async def test_get_active_downloads_restarts_from_resume_context_for_active_restored_aria2(
    monkeypatch, tmp_path
):
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    save_path = save_dir / "file.safetensors"
    save_path.write_text("partial")

    await manager._aria2_state_store.upsert(
        "download-1",
        {
            "download_id": "download-1",
            "transfer_backend": "aria2",
            "status": "downloading",
            "save_path": str(save_path),
            "file_path": str(save_path),
            "model_id": 12,
            "model_version_id": 34,
            "gid": "gid-1",
            "resume_context": {
                "version_info": {
                    "id": 34,
                    "modelId": 12,
                    "model": {"id": 12, "type": "LoRA", "tags": ["fantasy"]},
                    "images": [],
                },
                "file_info": {
                    "name": "file.safetensors",
                    "type": "Model",
                    "primary": True,
                    "downloadUrl": "https://example.com/file.safetensors",
                },
                "model_type": "lora",
                "relative_path": "",
                "save_dir": str(save_dir),
                "download_urls": ["https://example.com/file.safetensors"],
            },
        },
    )

    restarted = {}

    class DummyAria2Downloader:
        async def get_status_by_gid(self, gid):
            return {"gid": gid, "status": "active"}

        async def restore_transfer(self, download_id, gid, restored_path):
            return None

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    async def fake_resume_restored_aria2_download(self, download_id, record):
        restarted.update(
            {
                "download_id": download_id,
                "model_id": record.get("model_id"),
                "model_version_id": record.get("model_version_id"),
                "save_dir": record.get("save_dir"),
                "resume_context": record.get("resume_context"),
            }
        )
        return {"success": True}

    monkeypatch.setattr(
        DownloadManager,
        "_resume_restored_aria2_download",
        fake_resume_restored_aria2_download,
    )
    execute_original = AsyncMock(side_effect=AssertionError("should not refetch metadata"))
    monkeypatch.setattr(
        DownloadManager,
        "_execute_original_download",
        execute_original,
    )

    downloads = await manager.get_active_downloads()
    assert downloads["downloads"][0]["status"] == "downloading"
    restarted_task = manager._download_tasks["download-1"]
    await restarted_task

    assert restarted["download_id"] == "download-1"
    assert restarted["model_id"] == 12
    assert restarted["model_version_id"] == 34
    assert restarted["save_dir"] is None
    assert restarted["resume_context"]["model_type"] == "lora"
    assert execute_original.await_count == 0


@pytest.mark.asyncio
async def test_get_active_downloads_restores_persisted_aria2_without_initial_save_path(
    monkeypatch, tmp_path
):
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    save_path = save_dir / "file.safetensors"
    save_path.write_text("partial")
    (save_dir / "file.safetensors.aria2").write_text("control")

    await manager._aria2_state_store.upsert(
        "download-1",
        {
            "download_id": "download-1",
            "transfer_backend": "aria2",
            "status": "paused",
            "model_id": 12,
            "model_version_id": 34,
            "resume_context": {
                "version_info": {
                    "id": 34,
                    "modelId": 12,
                    "model": {"id": 12, "type": "LoRA"},
                    "images": [],
                },
                "file_info": {
                    "name": "file.safetensors",
                    "type": "Model",
                    "primary": True,
                    "downloadUrl": "https://example.com/file.safetensors",
                },
                "model_type": "lora",
                "relative_path": "",
                "save_dir": str(save_dir),
                "download_urls": ["https://example.com/file.safetensors"],
            },
        },
    )

    class DummyAria2Downloader:
        async def get_status_by_gid(self, gid):
            return None

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    downloads = await manager.get_active_downloads()
    persisted = await manager._aria2_state_store.get("download-1")

    assert downloads["downloads"] == [
        {
            "download_id": "download-1",
            "model_id": 12,
            "model_version_id": 34,
            "progress": 0,
            "status": "paused",
            "error": None,
            "bytes_downloaded": 0,
            "total_bytes": None,
            "bytes_per_second": 0.0,
        }
    ]
    assert manager._active_downloads["download-1"]["file_path"] == str(save_path)
    assert persisted["save_path"] == str(save_path)
    assert persisted["file_path"] == str(save_path)


@pytest.mark.asyncio
async def test_resume_restored_aria2_download_updates_terminal_status_and_cleanup(monkeypatch):
    manager = DownloadManager()
    manager._active_downloads["download-1"] = {
        "transfer_backend": "aria2",
        "status": "paused",
        "model_id": 12,
        "model_version_id": 34,
        "bytes_per_second": 10.0,
    }

    persist_state = AsyncMock()
    cleanup_record = AsyncMock(return_value=None)
    execute_download = AsyncMock(return_value={"success": True})
    record_history = AsyncMock(return_value=None)
    sync_version = AsyncMock(return_value=None)

    monkeypatch.setattr(manager, "_persist_aria2_state", persist_state)
    monkeypatch.setattr(manager, "_cleanup_download_record", cleanup_record)
    monkeypatch.setattr(manager, "_execute_download", execute_download)
    monkeypatch.setattr(manager, "_record_downloaded_version_history", record_history)
    monkeypatch.setattr(manager, "_sync_downloaded_version", sync_version)

    scheduled_tasks = []
    original_create_task = asyncio.create_task

    def tracking_create_task(coro):
        task = original_create_task(coro)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(download_manager.asyncio, "create_task", tracking_create_task)

    result = await manager._resume_restored_aria2_download(
        "download-1",
        {
            "download_id": "download-1",
            "save_path": "/tmp/file.safetensors",
            "file_path": "/tmp/file.safetensors",
            "model_id": 12,
            "model_version_id": 34,
            "resume_context": {
                "version_info": {
                    "id": 34,
                    "modelId": 12,
                    "model": {"id": 12},
                    "images": [],
                },
                "file_info": {
                    "name": "file.safetensors",
                    "downloadUrl": "https://example.com/file.safetensors",
                },
                "model_type": "lora",
                "relative_path": "",
                "save_dir": "/tmp",
                "download_urls": ["https://example.com/file.safetensors"],
            },
        },
    )

    assert result == {"success": True}
    assert manager._active_downloads["download-1"]["status"] == "completed"
    assert manager._active_downloads["download-1"]["bytes_per_second"] == 0.0
    assert persist_state.await_count == 2
    assert len(scheduled_tasks) == 1
    await asyncio.gather(*scheduled_tasks)
    cleanup_record.assert_awaited_once_with("download-1")


@pytest.mark.asyncio
async def test_download_uses_captured_backend_when_settings_change(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    manager = DownloadManager()
    settings = get_settings_manager()
    settings.settings["download_backend"] = "aria2"

    semaphore = asyncio.Semaphore(0)
    manager._download_semaphore = semaphore

    captured = {}

    async def fake_execute_original_download(
        self,
        model_id,
        model_version_id,
        save_dir,
        relative_path,
        progress_callback,
        use_default_paths,
        download_id=None,
        transfer_backend="python",
        source=None,
        file_params=None,
    ):
        captured["transfer_backend"] = transfer_backend
        return {"success": True}

    monkeypatch.setattr(
        DownloadManager,
        "_execute_original_download",
        fake_execute_original_download,
    )

    download_task = asyncio.create_task(
        manager.download_from_civitai(
            model_version_id=99,
            save_dir=str(tmp_path),
            use_default_paths=True,
            progress_callback=None,
            source=None,
        )
    )

    await asyncio.sleep(0)
    assert len(manager._active_downloads) == 1
    download_id = next(iter(manager._active_downloads))
    assert manager._active_downloads[download_id]["transfer_backend"] == "aria2"

    settings.settings["download_backend"] = "python"
    semaphore.release()

    result = await download_task

    assert result["success"] is True
    assert captured["transfer_backend"] == "aria2"


@pytest.mark.asyncio
async def test_download_aborts_when_version_exists(
    monkeypatch, scanners, metadata_provider
):
    """Test that download aborts when version already exists."""
    scanners.lora.exists = True

    manager = DownloadManager()

    execute_mock = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(DownloadManager, "_execute_download", execute_mock)

    result = await manager.download_from_civitai(model_version_id=101, save_dir="/tmp")

    assert result["success"] is False
    assert result["error"] == "Model version already exists in lora library"
    assert "download_id" in result
    assert execute_mock.await_count == 0


@pytest.mark.asyncio
async def test_download_handles_metadata_errors(monkeypatch, scanners):
    """Test that download handles metadata fetch failures gracefully."""
    async def failing_provider(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        download_manager,
        "get_default_metadata_provider",
        AsyncMock(
            return_value=SimpleNamespace(get_model_version=AsyncMock(return_value=None))
        ),
    )

    manager = DownloadManager()

    result = await manager.download_from_civitai(model_version_id=5, save_dir="/tmp")

    assert result["success"] is False
    assert result["error"] == "Failed to fetch model metadata"
    assert "download_id" in result


@pytest.mark.asyncio
async def test_download_rejects_unsupported_model_type(monkeypatch, scanners):
    """Test that unsupported model types are rejected."""
    class Provider:
        async def get_model_version(self, *_args, **_kwargs):
            return {
                "model": {"type": "Unsupported", "tags": []},
                "files": [],
            }

    monkeypatch.setattr(
        download_manager,
        "get_default_metadata_provider",
        AsyncMock(return_value=Provider()),
    )

    manager = DownloadManager()

    result = await manager.download_from_civitai(model_version_id=5, save_dir="/tmp")

    assert result["success"] is False
    assert result["error"].startswith("Model type")


def test_embedding_relative_path_replaces_spaces():
    """Test that embedding paths replace spaces with underscores."""
    manager = DownloadManager()

    version_info = {
        "baseModel": "Base Model",
        "model": {"tags": ["tag with space"]},
        "creator": {"username": "Author Name"},
    }

    relative_path = manager._calculate_relative_path(version_info, "embedding")

    assert relative_path == "Base_Model/tag_with_space"


def test_relative_path_supports_model_and_version_placeholders():
    """Test that relative path supports {model_name} and {version_name} placeholders."""
    manager = DownloadManager()
    settings_manager = get_settings_manager()
    settings_manager.settings["download_path_templates"]["lora"] = (
        "{model_name}/{version_name}"
    )

    version_info = {
        "baseModel": "BaseModel",
        "name": "Version One",
        "model": {"name": "Fancy Model", "tags": []},
    }

    relative_path = manager._calculate_relative_path(version_info, "lora")

    assert relative_path == "Fancy Model/Version One"


def test_relative_path_sanitizes_model_and_version_placeholders():
    """Test that relative path sanitizes special characters in placeholders."""
    manager = DownloadManager()
    settings_manager = get_settings_manager()
    settings_manager.settings["download_path_templates"]["lora"] = (
        "{model_name}/{version_name}"
    )

    version_info = {
        "baseModel": "BaseModel",
        "name": "Version:One?",
        "model": {"name": "Fancy:Model*", "tags": []},
    }

    relative_path = manager._calculate_relative_path(version_info, "lora")

    assert relative_path == "Fancy_Model/Version_One"


def test_distribute_preview_to_entries_moves_and_copies(tmp_path):
    """Test that preview distribution moves file to first entry and copies to others."""
    manager = DownloadManager()
    preview_file = tmp_path / "bundle.webp"
    preview_file.write_bytes(b"image-data")

    entries = [
        SimpleNamespace(file_path=str(tmp_path / "model-one.safetensors")),
        SimpleNamespace(file_path=str(tmp_path / "model-two.safetensors")),
    ]

    targets = manager._distribute_preview_to_entries(str(preview_file), entries)

    assert targets == [
        str(tmp_path / "model-one.webp"),
        str(tmp_path / "model-two.webp"),
    ]
    assert not preview_file.exists()
    assert Path(targets[0]).read_bytes() == b"image-data"
    assert Path(targets[1]).read_bytes() == b"image-data"


def test_distribute_preview_to_entries_keeps_existing_file(tmp_path):
    """Test that existing preview files are not overwritten."""
    manager = DownloadManager()
    existing_preview = tmp_path / "model-one.webp"
    existing_preview.write_bytes(b"preview")

    entries = [
        SimpleNamespace(file_path=str(tmp_path / "model-one.safetensors")),
        SimpleNamespace(file_path=str(tmp_path / "model-two.safetensors")),
    ]

    targets = manager._distribute_preview_to_entries(str(existing_preview), entries)

    assert targets[0] == str(existing_preview)
    assert Path(targets[1]).read_bytes() == b"preview"



@pytest.mark.asyncio
async def test_download_skips_excluded_base_model(monkeypatch, scanners, metadata_provider):
    manager = DownloadManager()
    get_settings_manager().settings["download_skip_base_models"] = ["SDXL 1.0"]

    metadata_provider.get_model_version = AsyncMock(
        return_value={
            "id": 99,
            "model": {"type": "LoRA", "tags": ["fantasy"]},
            "baseModel": "SDXL 1.0",
            "creator": {"username": "Author"},
            "files": [
                {
                    "type": "Model",
                    "primary": True,
                    "downloadUrl": "https://example.invalid/file.safetensors",
                    "name": "file.safetensors",
                }
            ],
        }
    )

    execute_download = AsyncMock()
    monkeypatch.setattr(
        DownloadManager, "_execute_download", execute_download, raising=False
    )

    result = await manager.download_from_civitai(
        model_version_id=99,
        use_default_paths=True,
        progress_callback=None,
        source=None,
    )

    assert result["success"] is True
    assert result["skipped"] is True
    assert result["status"] == "skipped"
    assert result["reason"] == "base_model_excluded"
    assert result["base_model"] == "SDXL 1.0"
    assert result["file_name"] == "file.safetensors"
    assert "file.safetensors" in result["message"]
    execute_download.assert_not_called()
    assert manager._active_downloads[result["download_id"]]["status"] == "skipped"


@pytest.mark.asyncio
async def test_download_skips_previously_downloaded_version(monkeypatch, scanners, metadata_provider):
    manager = DownloadManager()
    get_settings_manager().settings["skip_previously_downloaded_model_versions"] = True

    metadata_provider.get_model_version = AsyncMock(
        return_value={
            "id": 42,
            "model": {"type": "LoRA", "tags": ["fantasy"]},
            "baseModel": "SDXL 1.0",
            "creator": {"username": "Author"},
            "files": [
                {
                    "type": "Model",
                    "primary": True,
                    "downloadUrl": "https://example.invalid/file.safetensors",
                    "name": "file.safetensors",
                }
            ],
        }
    )

    history_service = AsyncMock()
    history_service.has_been_downloaded = AsyncMock(return_value=True)
    monkeypatch.setattr(
        ServiceRegistry,
        "get_downloaded_version_history_service",
        AsyncMock(return_value=history_service),
    )

    execute_download = AsyncMock()
    monkeypatch.setattr(
        DownloadManager, "_execute_download", execute_download, raising=False
    )

    result = await manager.download_from_civitai(
        model_version_id=99,
        use_default_paths=True,
        progress_callback=None,
        source=None,
    )

    assert result["success"] is True
    assert result["skipped"] is True
    assert result["status"] == "skipped"
    assert result["reason"] == "previously_downloaded_version"
    assert result["model_version_id"] == 99
    assert result["file_name"] == "file.safetensors"
    history_service.has_been_downloaded.assert_awaited_once_with("lora", 99)
    execute_download.assert_not_called()
    assert manager._active_downloads[result["download_id"]]["status"] == "skipped"


@pytest.mark.asyncio
async def test_download_proceeds_when_history_skip_disabled(monkeypatch, scanners, metadata_provider):
    manager = DownloadManager()
    get_settings_manager().settings["skip_previously_downloaded_model_versions"] = False

    metadata_provider.get_model_version = AsyncMock(
        return_value={
            "id": 42,
            "model": {"type": "LoRA", "tags": ["fantasy"]},
            "baseModel": "SDXL 1.0",
            "creator": {"username": "Author"},
            "files": [
                {
                    "type": "Model",
                    "primary": True,
                    "downloadUrl": "https://example.invalid/file.safetensors",
                    "name": "file.safetensors",
                }
            ],
        }
    )

    history_service = AsyncMock()
    history_service.has_been_downloaded = AsyncMock(return_value=True)
    monkeypatch.setattr(
        ServiceRegistry,
        "get_downloaded_version_history_service",
        AsyncMock(return_value=history_service),
    )

    execute_download = AsyncMock(return_value={"success": True, "download_id": "done"})
    monkeypatch.setattr(
        DownloadManager, "_execute_download", execute_download, raising=False
    )

    result = await manager.download_from_civitai(
        model_version_id=99,
        use_default_paths=True,
        progress_callback=None,
        source=None,
    )

    assert result["success"] is True
    assert result.get("skipped") is not True
    history_service.has_been_downloaded.assert_not_called()
    execute_download.assert_awaited_once()
