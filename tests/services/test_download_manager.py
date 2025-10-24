import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from py.services.download_manager import DownloadManager
from py.services.downloader import DownloadStreamControl
from py.services import download_manager
from py.services.service_registry import ServiceRegistry
from py.services.settings_manager import SettingsManager, get_settings_manager
from py.utils.metadata_manager import MetadataManager


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
        }
    )
    monkeypatch.setattr(manager, "settings", default_settings)
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)


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

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=lora_scanner))
    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", AsyncMock(return_value=checkpoint_scanner))
    monkeypatch.setattr(ServiceRegistry, "get_embedding_scanner", AsyncMock(return_value=embedding_scanner))

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


async def test_download_requires_identifier():
    manager = DownloadManager()
    result = await manager.download_from_civitai()
    assert result == {
        "success": False,
        "error": "Either model_id or model_version_id must be provided",
    }


async def test_successful_download_uses_defaults(monkeypatch, scanners, metadata_provider, tmp_path):
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

    monkeypatch.setattr(DownloadManager, "_execute_download", fake_execute_download, raising=False)

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
    expected_dir = Path(get_settings_manager().get("default_lora_root")) / "MappedModel" / "fantasy"
    assert captured["save_dir"] == expected_dir
    assert captured["model_type"] == "lora"
    assert captured["download_urls"] == [
        "https://example.invalid/file.safetensors"
    ]


async def test_download_uses_active_mirrors(monkeypatch, scanners, metadata_provider, tmp_path):
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
                    {"url": "https://mirror.example/file.safetensors", "deletedAt": None},
                    {"url": "https://mirror.example/old.safetensors", "deletedAt": "2024-01-01"},
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
    ):
        captured["download_urls"] = download_urls
        return {"success": True}

    monkeypatch.setattr(DownloadManager, "_execute_download", fake_execute_download, raising=False)

    result = await manager.download_from_civitai(
        model_version_id=99,
        save_dir=str(tmp_path),
        use_default_paths=True,
        progress_callback=None,
        source=None,
    )

    assert result["success"] is True
    assert captured["download_urls"] == ["https://mirror.example/file.safetensors"]


async def test_download_aborts_when_version_exists(monkeypatch, scanners, metadata_provider):
    scanners.lora.exists = True

    manager = DownloadManager()

    execute_mock = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(DownloadManager, "_execute_download", execute_mock)

    result = await manager.download_from_civitai(model_version_id=101, save_dir="/tmp")

    assert result["success"] is False
    assert result["error"] == "Model version already exists in lora library"
    assert "download_id" in result
    assert execute_mock.await_count == 0


async def test_download_handles_metadata_errors(monkeypatch, scanners):
    async def failing_provider(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        download_manager,
        "get_default_metadata_provider",
        AsyncMock(return_value=SimpleNamespace(get_model_version=AsyncMock(return_value=None))),
    )

    manager = DownloadManager()

    result = await manager.download_from_civitai(model_version_id=5, save_dir="/tmp")

    assert result["success"] is False
    assert result["error"] == "Failed to fetch model metadata"
    assert "download_id" in result


async def test_download_rejects_unsupported_model_type(monkeypatch, scanners):
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
    manager = DownloadManager()

    version_info = {
        "baseModel": "Base Model",
        "model": {"tags": ["tag with space"]},
        "creator": {"username": "Author Name"},
    }

    relative_path = manager._calculate_relative_path(version_info, "embedding")

    assert relative_path == "Base_Model/tag_with_space"


def test_relative_path_supports_model_and_version_placeholders():
    manager = DownloadManager()
    settings_manager = get_settings_manager()
    settings_manager.settings["download_path_templates"]["lora"] = "{model_name}/{version_name}"

    version_info = {
        "baseModel": "BaseModel",
        "name": "Version One",
        "model": {"name": "Fancy Model", "tags": []},
    }

    relative_path = manager._calculate_relative_path(version_info, "lora")

    assert relative_path == "Fancy Model/Version One"


def test_relative_path_sanitizes_model_and_version_placeholders():
    manager = DownloadManager()
    settings_manager = get_settings_manager()
    settings_manager.settings["download_path_templates"]["lora"] = "{model_name}/{version_name}"

    version_info = {
        "baseModel": "BaseModel",
        "name": "Version:One?",
        "model": {"name": "Fancy:Model*", "tags": []},
    }

    relative_path = manager._calculate_relative_path(version_info, "lora")

    assert relative_path == "Fancy_Model/Version_One"


async def test_execute_download_retries_urls(monkeypatch, tmp_path):
    manager = DownloadManager()

    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    initial_path = save_dir / "file.safetensors"

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = str(path)
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None

        def generate_unique_filename(self, *_args, **_kwargs):
            return os.path.basename(self.file_path)

        def update_file_info(self, _path):
            return None

        def to_dict(self):
            return {"file_path": self.file_path}

    metadata = DummyMetadata(initial_path)
    version_info = {"images": []}
    download_urls = [
        "https://first.example/file.safetensors",
        "https://second.example/file.safetensors",
    ]

    class DummyDownloader:
        def __init__(self):
            self.calls = []

        async def download_file(self, url, path, progress_callback=None, use_auth=None):
            self.calls.append((url, path, use_auth))
            if len(self.calls) == 1:
                return False, "first failed"
            # Create the target file to simulate a successful download
            Path(path).write_text("content")
            return True, "second success"

    dummy_downloader = DummyDownloader()
    monkeypatch.setattr(download_manager, "get_downloader", AsyncMock(return_value=dummy_downloader))

    class DummyScanner:
        def __init__(self):
            self.calls = []

        async def add_model_to_cache(self, metadata_dict, relative_path):
            self.calls.append((metadata_dict, relative_path))

    dummy_scanner = DummyScanner()
    monkeypatch.setattr(DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner))
    monkeypatch.setattr(DownloadManager, "_get_checkpoint_scanner", AsyncMock(return_value=dummy_scanner))
    monkeypatch.setattr(ServiceRegistry, "get_embedding_scanner", AsyncMock(return_value=dummy_scanner))

    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))

    result = await manager._execute_download(
        download_urls=download_urls,
        save_dir=str(save_dir),
        metadata=metadata,
        version_info=version_info,
        relative_path="",
        progress_callback=None,
        model_type="lora",
        download_id=None,
    )

    assert result == {"success": True}
    assert [url for url, *_ in dummy_downloader.calls] == download_urls
    assert dummy_scanner.calls  # ensure cache updated


async def test_execute_download_adjusts_checkpoint_model_type(monkeypatch, tmp_path):
    manager = DownloadManager()

    root_dir = tmp_path / "checkpoints"
    root_dir.mkdir()
    save_dir = root_dir
    target_path = save_dir / "model.safetensors"

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = path.as_posix()
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None
            self.preview_nsfw_level = 0
            self.model_type = "checkpoint"

        def generate_unique_filename(self, *_args, **_kwargs):
            return os.path.basename(self.file_path)

        def update_file_info(self, updated_path):
            self.file_path = Path(updated_path).as_posix()

        def to_dict(self):
            return {
                "file_path": self.file_path,
                "model_type": self.model_type,
                "sha256": self.sha256,
            }

    metadata = DummyMetadata(target_path)
    version_info = {"images": []}
    download_urls = ["https://example.invalid/model.safetensors"]

    class DummyDownloader:
        async def download_file(self, _url, path, progress_callback=None, use_auth=None):
            Path(path).write_text("content")
            return True, "ok"

    monkeypatch.setattr(
        download_manager,
        "get_downloader",
        AsyncMock(return_value=DummyDownloader()),
    )

    class DummyCheckpointScanner:
        def __init__(self, root: Path):
            self.root = root.as_posix()
            self.add_calls = []

        def _find_root_for_file(self, file_path: str):
            return self.root if file_path.startswith(self.root) else None

        def adjust_metadata(self, metadata_obj, _file_path: str, root_path: Optional[str]):
            if root_path:
                metadata_obj.model_type = "diffusion_model"
            return metadata_obj

        def adjust_cached_entry(self, entry):
            if entry.get("file_path", "").startswith(self.root):
                entry["model_type"] = "diffusion_model"
            return entry

        async def add_model_to_cache(self, metadata_dict, relative_path):
            self.add_calls.append((metadata_dict, relative_path))
            return True

    dummy_scanner = DummyCheckpointScanner(root_dir)
    monkeypatch.setattr(DownloadManager, "_get_checkpoint_scanner", AsyncMock(return_value=dummy_scanner))
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))

    result = await manager._execute_download(
        download_urls=download_urls,
        save_dir=str(save_dir),
        metadata=metadata,
        version_info=version_info,
        relative_path="",
        progress_callback=None,
        model_type="checkpoint",
        download_id=None,
    )

    assert result == {"success": True}
    assert metadata.model_type == "diffusion_model"
    saved_metadata = MetadataManager.save_metadata.await_args.args[1]
    assert saved_metadata.model_type == "diffusion_model"
    assert dummy_scanner.add_calls
    cached_entry, _ = dummy_scanner.add_calls[0]
    assert cached_entry["model_type"] == "diffusion_model"


async def test_pause_download_updates_state():
    manager = DownloadManager()

    download_id = "dl"
    manager._download_tasks[download_id] = object()
    pause_control = DownloadStreamControl()
    manager._pause_events[download_id] = pause_control
    manager._active_downloads[download_id] = {
        "status": "downloading",
        "bytes_per_second": 42.0,
    }

    result = await manager.pause_download(download_id)

    assert result == {"success": True, "message": "Download paused successfully"}
    assert download_id in manager._pause_events
    assert manager._pause_events[download_id].is_set() is False
    assert manager._active_downloads[download_id]["status"] == "paused"
    assert manager._active_downloads[download_id]["bytes_per_second"] == 0.0


async def test_pause_download_rejects_unknown_task():
    manager = DownloadManager()

    result = await manager.pause_download("missing")

    assert result == {"success": False, "error": "Download task not found"}


async def test_resume_download_sets_event_and_status():
    manager = DownloadManager()

    download_id = "dl"
    pause_control = DownloadStreamControl()
    pause_control.pause()
    pause_control.mark_progress()
    manager._pause_events[download_id] = pause_control
    manager._active_downloads[download_id] = {
        "status": "paused",
        "bytes_per_second": 0.0,
    }

    result = await manager.resume_download(download_id)

    assert result == {"success": True, "message": "Download resumed successfully"}
    assert manager._pause_events[download_id].is_set() is True
    assert manager._active_downloads[download_id]["status"] == "downloading"


async def test_resume_download_requests_reconnect_for_stalled_stream():
    manager = DownloadManager()

    download_id = "dl"
    pause_control = DownloadStreamControl(stall_timeout=40)
    pause_control.pause()
    pause_control.last_progress_timestamp = (datetime.now().timestamp() - 120)
    manager._pause_events[download_id] = pause_control
    manager._active_downloads[download_id] = {
        "status": "paused",
        "bytes_per_second": 0.0,
    }

    result = await manager.resume_download(download_id)

    assert result == {"success": True, "message": "Download resumed successfully"}
    assert pause_control.is_set() is True
    assert pause_control.has_reconnect_request() is True


async def test_resume_download_rejects_when_not_paused():
    manager = DownloadManager()

    download_id = "dl"
    pause_control = DownloadStreamControl()
    manager._pause_events[download_id] = pause_control

    result = await manager.resume_download(download_id)

    assert result == {"success": False, "error": "Download is not paused"}


@pytest.mark.asyncio
async def test_execute_download_uses_rewritten_civitai_preview(monkeypatch, tmp_path):
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    target_path = save_dir / "file.safetensors"

    manager._active_downloads["dl"] = {}

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = str(path)
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None
            self.preview_nsfw_level = None

        def generate_unique_filename(self, *_args, **_kwargs):
            return os.path.basename(self.file_path)

        def update_file_info(self, _path):
            return None

        def to_dict(self):
            return {"file_path": self.file_path}

    metadata = DummyMetadata(target_path)
    version_info = {
        "images": [
            {
                "url": "https://image.civitai.com/container/example/original=true/sample.jpeg",
                "type": "image",
                "nsfwLevel": 2,
            }
        ]
    }
    download_urls = ["https://example.invalid/file.safetensors"]

    class DummyDownloader:
        def __init__(self):
            self.file_calls: list[tuple[str, str]] = []
            self.memory_calls = 0

        async def download_file(self, url, path, progress_callback=None, use_auth=None):
            self.file_calls.append((url, path))
            if url.endswith(".jpeg"):
                Path(path).write_bytes(b"preview")
                return True, None
            if url.endswith(".safetensors"):
                Path(path).write_bytes(b"model")
                return True, None
            return False, "unexpected url"

        async def download_to_memory(self, *_args, **_kwargs):
            self.memory_calls += 1
            return False, b"", {}

    dummy_downloader = DummyDownloader()
    monkeypatch.setattr(download_manager, "get_downloader", AsyncMock(return_value=dummy_downloader))

    optimize_called = {"value": False}

    def fake_optimize_image(**_kwargs):
        optimize_called["value"] = True
        return b"", {}

    monkeypatch.setattr(download_manager.ExifUtils, "optimize_image", staticmethod(fake_optimize_image))
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))

    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner))

    result = await manager._execute_download(
        download_urls=download_urls,
        save_dir=str(save_dir),
        metadata=metadata,
        version_info=version_info,
        relative_path="",
        progress_callback=None,
        model_type="lora",
        download_id="dl",
    )

    assert result == {"success": True}
    preview_urls = [url for url, _ in dummy_downloader.file_calls if url.endswith(".jpeg")]
    assert any("width=450,optimized=true" in url for url in preview_urls)
    assert dummy_downloader.memory_calls == 0
    assert optimize_called["value"] is False
    assert metadata.preview_url.endswith(".jpeg")
    assert metadata.preview_nsfw_level == 2
    stored_preview = manager._active_downloads["dl"]["preview_path"]
    assert stored_preview.endswith(".jpeg")
    assert Path(stored_preview).exists()


@pytest.mark.asyncio
async def test_execute_download_respects_blur_setting(monkeypatch, tmp_path):
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    target_path = save_dir / "file.safetensors"

    manager._active_downloads["dl"] = {}

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = str(path)
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None
            self.preview_nsfw_level = None

        def generate_unique_filename(self, *_args, **_kwargs):
            return os.path.basename(self.file_path)

        def update_file_info(self, _path):
            return None

        def to_dict(self):
            return {"file_path": self.file_path}

    metadata = DummyMetadata(target_path)
    version_info = {
        "images": [
            {
                "url": "https://image.civitai.com/container/example/original=true/nsfw.jpeg",
                "type": "image",
                "nsfwLevel": 8,
            },
            {
                "url": "https://image.civitai.com/container/example/original=true/safe.jpeg",
                "type": "image",
                "nsfwLevel": 1,
            },
        ],
        "files": [
            {
                "type": "Model",
                "primary": True,
                "downloadUrl": "https://example.invalid/file.safetensors",
                "name": "file.safetensors",
            }
        ],
    }
    download_urls = ["https://example.invalid/file.safetensors"]

    class DummyDownloader:
        def __init__(self):
            self.file_calls: list[tuple[str, str]] = []

        async def download_file(self, url, path, progress_callback=None, use_auth=None):
            self.file_calls.append((url, path))
            if url.endswith(".safetensors"):
                Path(path).write_bytes(b"model")
                return True, None
            if "safe.jpeg" in url:
                Path(path).write_bytes(b"preview")
                return True, None
            return False, "unexpected url"

        async def download_to_memory(self, *_args, **_kwargs):
            return False, b"", {}

    dummy_downloader = DummyDownloader()

    class StubSettingsManager:
        def __init__(self, blur: bool) -> None:
            self.blur = blur

        def get(self, key: str, default=None):
            if key == "blur_mature_content":
                return self.blur
            return default

    monkeypatch.setattr(
        download_manager,
        "get_settings_manager",
        lambda: StubSettingsManager(True),
    )

    monkeypatch.setattr(download_manager, "get_downloader", AsyncMock(return_value=dummy_downloader))
    monkeypatch.setattr(download_manager.ExifUtils, "optimize_image", staticmethod(lambda **_kwargs: (b"", {})))
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))

    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner))

    result = await manager._execute_download(
        download_urls=download_urls,
        save_dir=str(save_dir),
        metadata=metadata,
        version_info=version_info,
        relative_path="",
        progress_callback=None,
        model_type="lora",
        download_id="dl",
    )

    assert result == {"success": True}
    preview_urls = [url for url, _ in dummy_downloader.file_calls if url.endswith(".jpeg")]
    assert preview_urls
    assert all("nsfw.jpeg" not in url for url in preview_urls)
    assert any("safe.jpeg" in url for url in preview_urls)
    assert metadata.preview_nsfw_level == 1
    stored_preview = manager._active_downloads["dl"].get("preview_path")
    assert stored_preview and stored_preview.endswith(".jpeg")
