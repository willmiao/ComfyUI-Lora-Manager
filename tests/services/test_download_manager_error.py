"""Error handling and execution tests for DownloadManager."""

import asyncio
import os
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
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


@pytest.mark.asyncio
async def test_execute_download_retries_urls(monkeypatch, tmp_path):
    """Test that download retries multiple URLs on failure."""
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
    monkeypatch.setattr(
        download_manager, "get_downloader", AsyncMock(return_value=dummy_downloader)
    )

    class DummyScanner:
        def __init__(self):
            self.calls = []

        async def add_model_to_cache(self, metadata_dict, relative_path):
            self.calls.append((metadata_dict, relative_path))

    dummy_scanner = DummyScanner()
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
    )
    monkeypatch.setattr(
        DownloadManager,
        "_get_checkpoint_scanner",
        AsyncMock(return_value=dummy_scanner),
    )
    monkeypatch.setattr(
        ServiceRegistry, "get_embedding_scanner", AsyncMock(return_value=dummy_scanner)
    )

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


@pytest.mark.asyncio
async def test_execute_download_adjusts_checkpoint_sub_type(monkeypatch, tmp_path):
    """Test that checkpoint sub_type is adjusted during download."""
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
            self.sub_type = "checkpoint"

        def generate_unique_filename(self, *_args, **_kwargs):
            return os.path.basename(self.file_path)

        def update_file_info(self, updated_path):
            self.file_path = Path(updated_path).as_posix()

        def to_dict(self):
            return {
                "file_path": self.file_path,
                "sub_type": self.sub_type,
                "sha256": self.sha256,
            }

    metadata = DummyMetadata(target_path)
    version_info = {"images": []}
    download_urls = ["https://example.invalid/model.safetensors"]

    class DummyDownloader:
        async def download_file(
            self, _url, path, progress_callback=None, use_auth=None
        ):
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

        def adjust_metadata(
            self, metadata_obj, _file_path: str, root_path: Optional[str]
        ):
            if root_path:
                metadata_obj.sub_type = "diffusion_model"
            return metadata_obj

        def adjust_cached_entry(self, entry):
            if entry.get("file_path", "").startswith(self.root):
                entry["sub_type"] = "diffusion_model"
            return entry

        async def add_model_to_cache(self, metadata_dict, relative_path):
            self.add_calls.append((metadata_dict, relative_path))
            return True

    dummy_scanner = DummyCheckpointScanner(root_dir)
    monkeypatch.setattr(
        DownloadManager,
        "_get_checkpoint_scanner",
        AsyncMock(return_value=dummy_scanner),
    )
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
    assert metadata.sub_type == "diffusion_model"
    saved_metadata = MetadataManager.save_metadata.await_args.args[1]
    assert saved_metadata.sub_type == "diffusion_model"
    assert dummy_scanner.add_calls
    cached_entry, _ = dummy_scanner.add_calls[0]
    assert cached_entry["sub_type"] == "diffusion_model"


@pytest.mark.asyncio
async def test_execute_download_extracts_zip_single_model(monkeypatch, tmp_path):
    """Test extraction of single model from ZIP file."""
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    zip_path = save_dir / "bundle.zip"

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = str(path)
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None

        def generate_unique_filename(self, *_args, **_kwargs):
            return os.path.basename(self.file_path)

        def update_file_info(self, updated_path):
            self.file_path = str(updated_path)
            self.file_name = Path(updated_path).stem

        def to_dict(self):
            return {"file_path": self.file_path}

    metadata = DummyMetadata(zip_path)
    version_info = {"images": []}
    download_urls = ["https://example.invalid/model.zip"]

    class DummyDownloader:
        async def download_file(self, *_args, **_kwargs):
            with zipfile.ZipFile(str(zip_path), "w") as archive:
                archive.writestr("inner/model.safetensors", b"model")
                archive.writestr("docs/readme.txt", b"ignore")
            return True, "ok"

    monkeypatch.setattr(
        download_manager, "get_downloader", AsyncMock(return_value=DummyDownloader())
    )
    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
    )
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))
    hash_calculator = AsyncMock(return_value="hash-single")
    monkeypatch.setattr(download_manager, "calculate_sha256", hash_calculator)

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
    assert not zip_path.exists()
    extracted = save_dir / "model.safetensors"
    assert extracted.exists()
    assert hash_calculator.await_args.args[0] == str(extracted)
    saved_call = MetadataManager.save_metadata.await_args
    assert saved_call.args[0] == str(extracted)
    assert saved_call.args[1].sha256 == "hash-single"
    assert dummy_scanner.add_model_to_cache.await_count == 1


@pytest.mark.asyncio
async def test_execute_download_extracts_zip_multiple_models(monkeypatch, tmp_path):
    """Test extraction of multiple models from ZIP file."""
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    zip_path = save_dir / "bundle.zip"

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = str(path)
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None

        def generate_unique_filename(self, *_args, **_kwargs):
            return os.path.basename(self.file_path)

        def update_file_info(self, updated_path):
            self.file_path = str(updated_path)
            self.file_name = Path(updated_path).stem

        def to_dict(self):
            return {"file_path": self.file_path}

    metadata = DummyMetadata(zip_path)
    version_info = {"images": []}
    download_urls = ["https://example.invalid/model.zip"]

    class DummyDownloader:
        async def download_file(self, *_args, **_kwargs):
            with zipfile.ZipFile(str(zip_path), "w") as archive:
                archive.writestr("first/model-one.safetensors", b"one")
                archive.writestr("second/model-two.safetensors", b"two")
                archive.writestr("readme.md", b"ignore")
            return True, "ok"

    monkeypatch.setattr(
        download_manager, "get_downloader", AsyncMock(return_value=DummyDownloader())
    )
    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
    )
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))
    hash_calculator = AsyncMock(side_effect=["hash-one", "hash-two"])
    monkeypatch.setattr(download_manager, "calculate_sha256", hash_calculator)

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
    assert not zip_path.exists()
    extracted_one = save_dir / "model-one.safetensors"
    extracted_two = save_dir / "model-two.safetensors"
    assert extracted_one.exists()
    assert extracted_two.exists()

    assert hash_calculator.await_count == 2
    assert MetadataManager.save_metadata.await_count == 2
    assert dummy_scanner.add_model_to_cache.await_count == 2

    metadata_calls = MetadataManager.save_metadata.await_args_list
    assert metadata_calls[0].args[0] == str(extracted_one)
    assert metadata_calls[0].args[1].sha256 == "hash-one"
    assert metadata_calls[1].args[0] == str(extracted_two)
    assert metadata_calls[1].args[1].sha256 == "hash-two"


@pytest.mark.asyncio
async def test_execute_download_extracts_zip_pt_embedding(monkeypatch, tmp_path):
    """Test extraction of .pt embedding files from ZIP."""
    manager = DownloadManager()
    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    zip_path = save_dir / "bundle.zip"

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = str(path)
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None

        def generate_unique_filename(self, *_args, **_kwargs):
            return os.path.basename(self.file_path)

        def update_file_info(self, updated_path):
            self.file_path = str(updated_path)
            self.file_name = Path(updated_path).stem

        def to_dict(self):
            return {"file_path": self.file_path}

    metadata = DummyMetadata(zip_path)
    version_info = {"images": []}
    download_urls = ["https://example.invalid/model.zip"]

    class DummyDownloader:
        async def download_file(self, *_args, **_kwargs):
            with zipfile.ZipFile(str(zip_path), "w") as archive:
                archive.writestr("inner/embedding.pt", b"embedding")
                archive.writestr("docs/readme.txt", b"ignore")
            return True, "ok"

    monkeypatch.setattr(
        download_manager, "get_downloader", AsyncMock(return_value=DummyDownloader())
    )
    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        ServiceRegistry, "get_embedding_scanner", AsyncMock(return_value=dummy_scanner)
    )
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))
    hash_calculator = AsyncMock(return_value="hash-pt")
    monkeypatch.setattr(download_manager, "calculate_sha256", hash_calculator)

    result = await manager._execute_download(
        download_urls=download_urls,
        save_dir=str(save_dir),
        metadata=metadata,
        version_info=version_info,
        relative_path="",
        progress_callback=None,
        model_type="embedding",
        download_id=None,
    )

    assert result == {"success": True}
    assert not zip_path.exists()
    extracted = save_dir / "embedding.pt"
    assert extracted.exists()
    assert hash_calculator.await_args.args[0] == str(extracted)
    saved_call = MetadataManager.save_metadata.await_args
    assert saved_call.args[0] == str(extracted)
    assert saved_call.args[1].sha256 == "hash-pt"
    assert dummy_scanner.add_model_to_cache.await_count == 1


@pytest.mark.asyncio
async def test_pause_download_updates_state():
    """Test that pause_download updates download state correctly."""
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


@pytest.mark.asyncio
async def test_pause_download_rejects_unknown_task():
    """Test that pause_download rejects unknown download tasks."""
    manager = DownloadManager()

    result = await manager.pause_download("missing")

    assert result == {"success": False, "error": "Download task not found"}


@pytest.mark.asyncio
async def test_resume_download_sets_event_and_status():
    """Test that resume_download sets event and updates status."""
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


@pytest.mark.asyncio
async def test_resume_download_requests_reconnect_for_stalled_stream():
    """Test that resume_download requests reconnect for stalled streams."""
    manager = DownloadManager()

    download_id = "dl"
    pause_control = DownloadStreamControl(stall_timeout=40)
    pause_control.pause()
    pause_control.last_progress_timestamp = datetime.now().timestamp() - 120
    manager._pause_events[download_id] = pause_control
    manager._active_downloads[download_id] = {
        "status": "paused",
        "bytes_per_second": 0.0,
    }

    result = await manager.resume_download(download_id)

    assert result == {"success": True, "message": "Download resumed successfully"}
    assert pause_control.is_set() is True
    assert pause_control.has_reconnect_request() is True


@pytest.mark.asyncio
async def test_resume_download_rejects_when_not_paused():
    """Test that resume_download rejects when download is not paused."""
    manager = DownloadManager()

    download_id = "dl"
    pause_control = DownloadStreamControl()
    manager._pause_events[download_id] = pause_control

    result = await manager.resume_download(download_id)

    assert result == {"success": False, "error": "Download is not paused"}
