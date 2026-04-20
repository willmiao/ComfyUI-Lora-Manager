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
from py.services import aria2_transfer_state
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
def isolate_aria2_state(monkeypatch, tmp_path):
    state_path = tmp_path / "cache" / "aria2" / "downloads.json"
    monkeypatch.setattr(
        aria2_transfer_state,
        "get_aria2_state_path",
        lambda: str(state_path),
    )


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
async def test_execute_download_uses_aria2_backend_for_model_files(monkeypatch, tmp_path):
    manager = DownloadManager()
    settings = get_settings_manager()
    settings.settings["download_backend"] = "aria2"
    settings.settings["civitai_api_key"] = "secret-key"

    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    target_path = save_dir / "file.safetensors"

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

    class DummyAria2Downloader:
        def __init__(self):
            self.calls = []

        async def download_file(
            self,
            url,
            save_path,
            *,
            download_id,
            progress_callback=None,
            headers=None,
        ):
            self.calls.append(
                {
                    "url": url,
                    "save_path": save_path,
                    "download_id": download_id,
                    "headers": headers,
                }
            )
            Path(save_path).write_text("content")
            return True, save_path

    dummy_aria2 = DummyAria2Downloader()

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=dummy_aria2),
    )
    monkeypatch.setattr(
        download_manager,
        "get_downloader",
        AsyncMock(side_effect=AssertionError("python downloader should not be used")),
    )

    class DummyScanner:
        async def add_model_to_cache(self, metadata_dict, relative_path):
            return {"metadata": metadata_dict, "relative_path": relative_path}

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
        download_urls=["https://civitai.com/api/download/models/1"],
        save_dir=str(save_dir),
        metadata=DummyMetadata(target_path),
        version_info={"images": []},
        relative_path="",
        progress_callback=None,
        model_type="lora",
        download_id="download-1",
    )

    assert result == {"success": True}
    assert dummy_aria2.calls == [
        {
            "url": "https://civitai.com/api/download/models/1",
            "save_path": str(target_path),
            "download_id": "download-1",
            "headers": {"Authorization": "Bearer secret-key"},
        }
    ]


@pytest.mark.asyncio
async def test_execute_download_allows_anonymous_civitai_with_aria2(
    monkeypatch, tmp_path
):
    manager = DownloadManager()
    settings = get_settings_manager()
    settings.settings["download_backend"] = "aria2"
    settings.settings["civitai_api_key"] = ""

    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    target_path = save_dir / "file.safetensors"

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

    class DummyAria2Downloader:
        def __init__(self):
            self.calls = []

        async def download_file(
            self,
            url,
            save_path,
            *,
            download_id,
            progress_callback=None,
            headers=None,
        ):
            self.calls.append({"url": url, "headers": headers, "download_id": download_id})
            Path(save_path).write_text("content")
            return True, save_path

    dummy_aria2 = DummyAria2Downloader()
    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=dummy_aria2),
    )

    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
    )
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))

    result = await manager._execute_download(
        download_urls=["https://civitai.com/api/download/models/1"],
        save_dir=str(save_dir),
        metadata=DummyMetadata(target_path),
        version_info={"images": []},
        relative_path="",
        progress_callback=None,
        model_type="lora",
        download_id="download-2",
    )

    assert result == {"success": True}
    assert dummy_aria2.calls == [
        {
            "url": "https://civitai.com/api/download/models/1",
            "headers": None,
            "download_id": "download-2",
        }
    ]


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

    class ImmediateLoop:
        async def run_in_executor(self, executor, func, *args):
            return func(*args)

    monkeypatch.setattr(download_manager.asyncio, "get_running_loop", lambda: ImmediateLoop())

    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
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
    assert not zip_path.exists()
    extracted = save_dir / "model.safetensors"
    assert extracted.exists()
    saved_call = MetadataManager.save_metadata.await_args
    assert saved_call.args[0] == str(extracted)
    # SHA256 comes from metadata (API value), not recalculated
    assert saved_call.args[1].sha256 == "sha256"
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

    class ImmediateLoop:
        async def run_in_executor(self, executor, func, *args):
            return func(*args)

    monkeypatch.setattr(download_manager.asyncio, "get_running_loop", lambda: ImmediateLoop())

    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
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
    assert not zip_path.exists()
    extracted_one = save_dir / "model-one.safetensors"
    extracted_two = save_dir / "model-two.safetensors"
    assert extracted_one.exists()
    assert extracted_two.exists()

    assert MetadataManager.save_metadata.await_count == 2
    assert dummy_scanner.add_model_to_cache.await_count == 2

    metadata_calls = MetadataManager.save_metadata.await_args_list
    assert metadata_calls[0].args[0] == str(extracted_one)
    # SHA256 comes from metadata (API value), not recalculated
    assert metadata_calls[0].args[1].sha256 == "sha256"
    assert metadata_calls[1].args[0] == str(extracted_two)
    assert metadata_calls[1].args[1].sha256 == "sha256"


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

    class ImmediateLoop:
        async def run_in_executor(self, executor, func, *args):
            return func(*args)

    monkeypatch.setattr(download_manager.asyncio, "get_running_loop", lambda: ImmediateLoop())

    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
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
        model_type="embedding",
        download_id=None,
    )

    assert result == {"success": True}
    assert not zip_path.exists()
    extracted = save_dir / "embedding.pt"
    assert extracted.exists()
    saved_call = MetadataManager.save_metadata.await_args
    assert saved_call.args[0] == str(extracted)
    # SHA256 comes from metadata (API value), not recalculated
    assert saved_call.args[1].sha256 == "sha256"
    assert dummy_scanner.add_model_to_cache.await_count == 1


@pytest.mark.asyncio
async def test_extract_model_files_from_archive_uses_executor(monkeypatch, tmp_path):
    manager = DownloadManager()
    archive_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("inner/model.safetensors", b"model")

    captured = {}

    class ImmediateLoop:
        async def run_in_executor(self, executor, func, *args):
            captured["executor"] = executor
            return func(*args)

    monkeypatch.setattr(
        download_manager.asyncio,
        "get_running_loop",
        lambda: ImmediateLoop(),
    )

    extracted = await manager._extract_model_files_from_archive(
        str(archive_path),
        {".safetensors"},
    )

    assert captured["executor"] is manager._archive_executor
    assert len(extracted) == 1
    assert extracted[0].endswith("model.safetensors")


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
async def test_pause_download_reverts_local_pause_when_aria2_pause_fails(monkeypatch):
    manager = DownloadManager()

    download_id = "dl"
    manager._download_tasks[download_id] = object()
    pause_control = DownloadStreamControl()
    manager._pause_events[download_id] = pause_control
    manager._active_downloads[download_id] = {
        "transfer_backend": "aria2",
        "status": "downloading",
        "bytes_per_second": 42.0,
    }

    class DummyAria2Downloader:
        async def has_transfer(self, _download_id):
            return True

        async def pause_download(self, _download_id):
            return {"success": False, "error": "rpc failed"}

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    result = await manager.pause_download(download_id)

    assert result == {"success": False, "error": "rpc failed"}
    assert pause_control.is_set() is True
    assert manager._active_downloads[download_id]["status"] == "downloading"


@pytest.mark.asyncio
async def test_pause_download_reverts_local_pause_when_aria2_probe_raises(monkeypatch):
    manager = DownloadManager()

    download_id = "dl"
    manager._download_tasks[download_id] = object()
    pause_control = DownloadStreamControl()
    manager._pause_events[download_id] = pause_control
    manager._active_downloads[download_id] = {
        "transfer_backend": "aria2",
        "status": "downloading",
        "bytes_per_second": 42.0,
    }

    class DummyAria2Downloader:
        async def has_transfer(self, _download_id):
            raise RuntimeError("rpc unavailable")

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    result = await manager.pause_download(download_id)

    assert result == {"success": False, "error": "rpc unavailable"}
    assert pause_control.is_set() is True
    assert manager._active_downloads[download_id]["status"] == "downloading"


@pytest.mark.asyncio
async def test_resume_download_returns_error_when_aria2_probe_raises(monkeypatch):
    manager = DownloadManager()

    download_id = "dl"
    pause_control = DownloadStreamControl()
    pause_control.pause()
    manager._pause_events[download_id] = pause_control
    manager._active_downloads[download_id] = {
        "transfer_backend": "aria2",
        "status": "paused",
        "bytes_per_second": 0.0,
    }

    class DummyAria2Downloader:
        async def has_transfer(self, _download_id):
            raise RuntimeError("rpc unavailable")

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    result = await manager.resume_download(download_id)

    assert result == {"success": False, "error": "rpc unavailable"}
    assert pause_control.is_paused() is True
    assert manager._active_downloads[download_id]["status"] == "paused"


@pytest.mark.asyncio
async def test_resume_download_does_not_spawn_restored_worker_when_aria2_resume_fails(
    monkeypatch, tmp_path
):
    manager = DownloadManager()

    download_id = "dl"
    save_path = tmp_path / "file.safetensors"
    pause_control = DownloadStreamControl()
    pause_control.pause()
    manager._pause_events[download_id] = pause_control
    manager._active_downloads[download_id] = {
        "transfer_backend": "aria2",
        "status": "paused",
        "bytes_per_second": 0.0,
    }

    await manager._aria2_state_store.upsert(
        download_id,
        {
            "download_id": download_id,
            "transfer_backend": "aria2",
            "status": "paused",
            "save_path": str(save_path),
            "file_path": str(save_path),
            "model_id": 12,
            "model_version_id": 34,
            "resume_context": {
                "version_info": {"id": 34, "modelId": 12, "model": {"id": 12}},
                "file_info": {
                    "name": "file.safetensors",
                    "downloadUrl": "https://example.com/file.safetensors",
                },
                "model_type": "lora",
                "relative_path": "",
                "save_dir": str(tmp_path),
                "download_urls": ["https://example.com/file.safetensors"],
            },
        },
    )

    resume_restored = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(manager, "_resume_restored_aria2_download", resume_restored)

    class DummyAria2Downloader:
        async def has_transfer(self, _download_id):
            return True

        async def resume_download(self, _download_id):
            return {"success": False, "error": "rpc unavailable"}

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    result = await manager.resume_download(download_id)

    assert result == {"success": False, "error": "rpc unavailable"}
    assert download_id not in manager._download_tasks
    assert resume_restored.await_count == 0
    assert pause_control.is_paused() is True
    assert manager._active_downloads[download_id]["status"] == "paused"


@pytest.mark.asyncio
async def test_start_background_download_task_cleans_up_finished_restore_task():
    manager = DownloadManager()
    download_id = "download-1"
    manager._pause_events[download_id] = DownloadStreamControl()

    async def finished_restore():
        return {"success": True}

    task = manager._start_background_download_task(download_id, finished_restore())
    await task
    await asyncio.sleep(0)

    assert download_id not in manager._download_tasks
    assert download_id not in manager._pause_events


@pytest.mark.asyncio
async def test_cancel_download_still_cancels_local_task_when_aria2_raises(monkeypatch):
    manager = DownloadManager()

    started = asyncio.Event()

    async def blocked_task():
        started.set()
        await asyncio.sleep(60)

    task = asyncio.create_task(blocked_task())
    await started.wait()

    download_id = "download-queued"
    manager._download_tasks[download_id] = task
    manager._active_downloads[download_id] = {
        "transfer_backend": "aria2",
        "status": "queued",
    }

    class DummyAria2Downloader:
        async def cancel_download(self, _download_id):
            raise RuntimeError("rpc unavailable")

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    result = await manager.cancel_download(download_id)

    assert result["success"] is True
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_cancel_download_preserves_tracking_when_aria2_returns_error(monkeypatch, tmp_path):
    manager = DownloadManager()
    download_id = "download-queued"
    save_path = tmp_path / "file.safetensors"
    save_path.write_text("partial")
    (tmp_path / "file.safetensors.aria2").write_text("control")

    pause_control = DownloadStreamControl()
    manager._pause_events[download_id] = pause_control
    manager._download_tasks[download_id] = object()
    manager._active_downloads[download_id] = {
        "transfer_backend": "aria2",
        "status": "downloading",
        "file_path": str(save_path),
    }

    await manager._aria2_state_store.upsert(
        download_id,
        {
            "download_id": download_id,
            "transfer_backend": "aria2",
            "status": "downloading",
            "save_path": str(save_path),
            "file_path": str(save_path),
        },
    )

    cleanup_files = AsyncMock(return_value=None)
    monkeypatch.setattr(manager, "_cleanup_cancelled_download_files", cleanup_files)

    class DummyAria2Downloader:
        async def cancel_download(self, _download_id):
            return {"success": False, "error": "rpc unavailable"}

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    result = await manager.cancel_download(download_id)

    assert result == {"success": False, "error": "rpc unavailable"}
    assert download_id in manager._download_tasks
    assert download_id in manager._pause_events
    assert await manager._aria2_state_store.get(download_id) is not None
    assert cleanup_files.await_count == 0


@pytest.mark.asyncio
async def test_cancel_download_rejects_completed_history_entry(tmp_path):
    manager = DownloadManager()
    download_id = "completed-download"
    save_path = tmp_path / "file.safetensors"
    metadata_path = tmp_path / "file.metadata.json"
    preview_path = tmp_path / "file.jpeg"
    save_path.write_text("complete")
    metadata_path.write_text("{}")
    preview_path.write_text("preview")

    manager._active_downloads[download_id] = {
        "transfer_backend": "aria2",
        "status": "completed",
        "file_path": str(save_path),
        "preview_path": str(preview_path),
    }

    result = await manager.cancel_download(download_id)

    assert result == {"success": False, "error": "Download task not found"}
    assert save_path.exists()
    assert metadata_path.exists()
    assert preview_path.exists()


@pytest.mark.asyncio
async def test_cancel_download_removes_preview_and_aria2_control_files(monkeypatch, tmp_path):
    manager = DownloadManager()

    started = asyncio.Event()

    async def blocked_task():
        started.set()
        await asyncio.sleep(60)

    task = asyncio.create_task(blocked_task())
    await started.wait()

    save_path = tmp_path / "file.safetensors"
    save_path.write_text("partial")
    aria2_path = tmp_path / "file.safetensors.aria2"
    aria2_path.write_text("control")
    preview_path = tmp_path / "file.jpeg"
    preview_path.write_text("preview")

    download_id = "download-queued"
    manager._download_tasks[download_id] = task
    manager._active_downloads[download_id] = {
        "transfer_backend": "aria2",
        "status": "queued",
        "file_path": str(save_path),
        "aria2_control_path": str(aria2_path),
        "preview_path": str(preview_path),
    }

    class DummyAria2Downloader:
        async def cancel_download(self, _download_id):
            return {"success": True, "message": "cancelled"}

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    result = await manager.cancel_download(download_id)

    assert result["success"] is True
    assert not save_path.exists()
    assert not aria2_path.exists()
    assert not preview_path.exists()


@pytest.mark.asyncio
async def test_cancel_download_does_not_delete_untracked_same_basename_preview(
    monkeypatch, tmp_path
):
    manager = DownloadManager()

    started = asyncio.Event()

    async def blocked_task():
        started.set()
        await asyncio.sleep(60)

    task = asyncio.create_task(blocked_task())
    await started.wait()

    save_path = tmp_path / "file.safetensors"
    save_path.write_text("partial")
    aria2_path = tmp_path / "file.safetensors.aria2"
    aria2_path.write_text("control")
    manual_preview_path = tmp_path / "file.jpg"
    manual_preview_path.write_text("manual")

    download_id = "download-queued"
    manager._download_tasks[download_id] = task
    manager._active_downloads[download_id] = {
        "transfer_backend": "aria2",
        "status": "queued",
        "file_path": str(save_path),
        "aria2_control_path": str(aria2_path),
    }

    class DummyAria2Downloader:
        async def cancel_download(self, _download_id):
            return {"success": True, "message": "cancelled"}

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    result = await manager.cancel_download(download_id)

    assert result["success"] is True
    assert not save_path.exists()
    assert not aria2_path.exists()
    assert manual_preview_path.exists()


@pytest.mark.asyncio
async def test_cleanup_cancelled_download_files_retries_aria2_control_deletion(
    monkeypatch, tmp_path
):
    manager = DownloadManager()
    download_id = "download-1"

    save_path = tmp_path / "file.safetensors"
    aria2_path = tmp_path / "file.safetensors.aria2"
    save_path.write_text("partial")
    aria2_path.write_text("control")

    original_unlink = os.unlink
    attempts = {"count": 0}

    def flaky_unlink(path):
        if path == str(aria2_path) and attempts["count"] == 0:
            attempts["count"] += 1
            raise PermissionError("still locked")
        return original_unlink(path)

    monkeypatch.setattr(download_manager.os, "unlink", flaky_unlink)
    monkeypatch.setattr("py.services.download_manager.asyncio.sleep", AsyncMock())

    await manager._cleanup_cancelled_download_files(
        download_id,
        {
            "file_path": str(save_path),
            "aria2_control_path": str(aria2_path),
            "transfer_backend": "aria2",
        },
    )

    assert attempts["count"] == 1
    assert not save_path.exists()
    assert not aria2_path.exists()


@pytest.mark.asyncio
async def test_execute_download_waits_for_paused_pre_transfer_gate(monkeypatch, tmp_path):
    manager = DownloadManager()

    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    target_path = save_dir / "file.safetensors"

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

    pause_control = DownloadStreamControl()
    pause_control.pause()
    manager._pause_events["download-1"] = pause_control
    manager._active_downloads["download-1"] = {
        "status": "downloading",
        "bytes_per_second": 42.0,
    }

    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
    )
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))

    started = asyncio.Event()
    allow_finish = asyncio.Event()
    captured = {"calls": 0}

    async def fake_download_model_file(
        self,
        download_url,
        save_path,
        *,
        backend,
        progress_callback,
        use_auth,
        download_id,
        pause_control,
    ):
        captured["calls"] += 1
        started.set()
        await allow_finish.wait()
        Path(save_path).write_text("content")
        return True, save_path

    monkeypatch.setattr(
        DownloadManager,
        "_download_model_file",
        fake_download_model_file,
    )

    task = asyncio.create_task(
        manager._execute_download(
            download_urls=["https://civitai.com/api/download/models/1"],
            save_dir=str(save_dir),
            metadata=DummyMetadata(target_path),
            version_info={"images": []},
            relative_path="",
            progress_callback=None,
            model_type="lora",
            download_id="download-1",
            transfer_backend="aria2",
        )
    )

    await asyncio.sleep(0)
    assert started.is_set() is False
    assert captured["calls"] == 0
    assert manager._active_downloads["download-1"]["status"] == "paused"

    pause_control.resume()
    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert captured["calls"] == 1
    assert manager._active_downloads["download-1"]["status"] == "downloading"

    allow_finish.set()
    result = await task

    assert result == {"success": True}


@pytest.mark.asyncio
async def test_execute_download_reuses_existing_aria2_partial_path(monkeypatch, tmp_path):
    manager = DownloadManager()

    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    target_path = save_dir / "file.safetensors"
    target_path.write_text("partial")
    control_path = save_dir / "file.safetensors.aria2"
    control_path.write_text("control")

    await manager._aria2_state_store.upsert(
        "download-1",
        {
            "download_id": "download-1",
            "transfer_backend": "aria2",
            "save_path": str(target_path),
            "file_path": str(target_path),
            "status": "paused",
        },
    )

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = str(path)
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None

        def generate_unique_filename(self, *_args, **_kwargs):
            return "renamed.safetensors"

        def update_file_info(self, _path):
            return None

        def to_dict(self):
            return {"file_path": self.file_path}

    manager._active_downloads["download-1"] = {"transfer_backend": "aria2"}
    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
    )
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))

    async def fake_download_model_file(
        self,
        download_url,
        save_path,
        *,
        backend,
        progress_callback,
        use_auth,
        download_id,
        pause_control,
    ):
        Path(save_path).write_text("content")
        return True, save_path

    monkeypatch.setattr(DownloadManager, "_download_model_file", fake_download_model_file)

    result = await manager._execute_download(
        download_urls=["https://example.com/file.safetensors"],
        save_dir=str(save_dir),
        metadata=DummyMetadata(target_path),
        version_info={"images": []},
        relative_path="",
        progress_callback=None,
        model_type="lora",
        download_id="download-1",
        transfer_backend="aria2",
    )

    assert result == {"success": True}
    assert manager._active_downloads["download-1"]["file_path"] == str(target_path)
    assert not (save_dir / "renamed.safetensors").exists()


@pytest.mark.asyncio
async def test_execute_download_rejects_conflicting_aria2_partial_path(tmp_path):
    manager = DownloadManager()

    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    target_path = save_dir / "file.safetensors"
    target_path.write_text("partial")
    (save_dir / "file.safetensors.aria2").write_text("control")

    await manager._aria2_state_store.upsert(
        "other-download",
        {
            "download_id": "other-download",
            "transfer_backend": "aria2",
            "save_path": str(target_path),
            "file_path": str(target_path),
            "status": "paused",
        },
    )

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = str(path)
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None

        def generate_unique_filename(self, *_args, **_kwargs):
            raise AssertionError("should not rename")

    result = await manager._execute_download(
        download_urls=["https://example.com/file.safetensors"],
        save_dir=str(save_dir),
        metadata=DummyMetadata(target_path),
        version_info={"images": []},
        relative_path="",
        progress_callback=None,
        model_type="lora",
        download_id="download-1",
        transfer_backend="aria2",
    )

    assert result["success"] is False
    assert "already using" in result["error"]


@pytest.mark.asyncio
async def test_execute_download_reassigns_same_aria2_partial_to_new_download_id(
    monkeypatch, tmp_path
):
    manager = DownloadManager()

    save_dir = tmp_path / "downloads"
    save_dir.mkdir()
    target_path = save_dir / "file.safetensors"
    target_path.write_text("partial")
    (save_dir / "file.safetensors.aria2").write_text("control")

    await manager._aria2_state_store.upsert(
        "old-download",
        {
            "download_id": "old-download",
            "transfer_backend": "aria2",
            "save_path": str(target_path),
            "file_path": str(target_path),
            "status": "paused",
            "model_id": 11,
            "model_version_id": 22,
        },
    )

    class DummyMetadata:
        def __init__(self, path: Path):
            self.file_path = str(path)
            self.sha256 = "sha256"
            self.file_name = path.stem
            self.preview_url = None

        def generate_unique_filename(self, *_args, **_kwargs):
            raise AssertionError("should not rename")

        def update_file_info(self, _path):
            return None

        def to_dict(self):
            return {"file_path": self.file_path}

    class DummyAria2Downloader:
        def __init__(self):
            self.calls = []

        async def reassign_transfer(self, previous_download_id, new_download_id):
            self.calls.append(("reassign_transfer", previous_download_id, new_download_id))
            return None

    dummy_aria2 = DummyAria2Downloader()
    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=dummy_aria2),
    )

    manager._active_downloads["old-download"] = {
        "transfer_backend": "aria2",
        "model_id": 11,
        "model_version_id": 22,
        "status": "paused",
    }
    manager._active_downloads["new-download"] = {
        "transfer_backend": "aria2",
        "model_id": 11,
        "model_version_id": 22,
        "status": "queued",
    }

    resolved, path = await manager._resolve_download_target_path(
        str(save_dir),
        DummyMetadata(target_path),
        transfer_backend="aria2",
        download_id="new-download",
    )

    assert resolved is True
    assert path == str(target_path)
    assert "old-download" not in manager._active_downloads
    assert manager._active_downloads["new-download"]["file_path"] == str(target_path)
    assert dummy_aria2.calls == [("reassign_transfer", "old-download", "new-download")]
    assert await manager._aria2_state_store.get("old-download") is None
    assert (await manager._aria2_state_store.get("new-download"))["save_path"] == str(
        target_path
    )


def test_is_same_aria2_download_request_requires_version_id_match():
    manager = DownloadManager()

    assert (
        manager._is_same_aria2_download_request(
            {"model_id": 1, "model_version_id": None},
            {"model_id": 1, "model_version_id": 2},
        )
        is False
    )
    assert (
        manager._is_same_aria2_download_request(
            {"model_id": 1, "model_version_id": 3},
            {"model_id": 1, "model_version_id": None},
        )
        is False
    )


@pytest.mark.asyncio
async def test_adopt_existing_aria2_download_cancels_old_running_task(monkeypatch, tmp_path):
    manager = DownloadManager()
    save_path = tmp_path / "file.safetensors"

    started = asyncio.Event()
    cancelled = asyncio.Event()
    call_order = []

    async def old_download():
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            call_order.append("old-task-cancelled")
            cancelled.set()
            raise

    old_task = asyncio.create_task(old_download())
    await started.wait()

    manager._download_tasks["old-download"] = old_task
    old_pause_control = DownloadStreamControl()
    old_pause_control.pause()
    manager._pause_events["old-download"] = old_pause_control
    manager._active_downloads["old-download"] = {
        "transfer_backend": "aria2",
        "model_id": 11,
        "model_version_id": 22,
        "status": "downloading",
    }
    manager._active_downloads["new-download"] = {
        "transfer_backend": "aria2",
        "model_id": 11,
        "model_version_id": 22,
        "status": "queued",
    }

    await manager._aria2_state_store.upsert(
        "old-download",
        {
            "download_id": "old-download",
            "transfer_backend": "aria2",
            "save_path": str(save_path),
            "file_path": str(save_path),
            "status": "downloading",
            "model_id": 11,
            "model_version_id": 22,
        },
    )

    class DummyAria2Downloader:
        async def reassign_transfer(self, previous_download_id, new_download_id):
            call_order.append("reassign-transfer")
            return None

    monkeypatch.setattr(
        download_manager,
        "get_aria2_downloader",
        AsyncMock(return_value=DummyAria2Downloader()),
    )

    await manager._adopt_existing_aria2_download(
        "old-download",
        "new-download",
        {"model_id": 11, "model_version_id": 22},
        str(save_path),
    )

    assert cancelled.is_set() is True
    assert "old-download" not in manager._download_tasks
    assert call_order == ["reassign-transfer", "old-task-cancelled"]


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
