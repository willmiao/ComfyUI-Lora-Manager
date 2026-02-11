"""Concurrent operations and advanced scenarios tests for DownloadManager."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from py.services.download_manager import DownloadManager
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


@pytest.mark.asyncio
async def test_execute_download_uses_rewritten_civitai_preview(monkeypatch, tmp_path):
    """Test that CivitAI preview URLs are rewritten for optimization."""
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
    monkeypatch.setattr(
        download_manager, "get_downloader", AsyncMock(return_value=dummy_downloader)
    )

    optimize_called = {"value": False}

    def fake_optimize_image(**_kwargs):
        optimize_called["value"] = True
        return b"", {}

    monkeypatch.setattr(
        download_manager.ExifUtils, "optimize_image", staticmethod(fake_optimize_image)
    )
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))

    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
    )

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
    preview_urls = [
        url for url, _ in dummy_downloader.file_calls if url.endswith(".jpeg")
    ]
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
    """Test that blur setting filters NSFW images."""
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

    monkeypatch.setattr(
        download_manager, "get_downloader", AsyncMock(return_value=dummy_downloader)
    )
    monkeypatch.setattr(
        download_manager.ExifUtils,
        "optimize_image",
        staticmethod(lambda **_kwargs: (b"", {})),
    )
    monkeypatch.setattr(MetadataManager, "save_metadata", AsyncMock(return_value=True))

    dummy_scanner = SimpleNamespace(add_model_to_cache=AsyncMock(return_value=None))
    monkeypatch.setattr(
        DownloadManager, "_get_lora_scanner", AsyncMock(return_value=dummy_scanner)
    )

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
    preview_urls = [
        url for url, _ in dummy_downloader.file_calls if url.endswith(".jpeg")
    ]
    assert preview_urls
    assert all("nsfw.jpeg" not in url for url in preview_urls)
    assert any("safe.jpeg" in url for url in preview_urls)
    assert metadata.preview_nsfw_level == 1
    stored_preview = manager._active_downloads["dl"].get("preview_path")
    assert stored_preview and stored_preview.endswith(".jpeg")


@pytest.mark.asyncio
async def test_civarchive_source_uses_civarchive_provider(
    monkeypatch, scanners, tmp_path
):
    """Test that civarchive source uses CivArchive provider."""
    manager = DownloadManager()

    captured_providers = []

    class CivArchiveProvider:
        async def get_model_version(self, model_id, model_version_id):
            captured_providers.append("civarchive")
            return {
                "id": 119514,
                "model": {"type": "LoRA", "tags": ["celebrity"]},
                "baseModel": "SD 1.5",
                "creator": {"username": "dogu_cat"},
                "source": "civarchive",
                "files": [
                    {
                        "type": "Model",
                        "primary": True,
                        "mirrors": [
                            {
                                "url": "https://huggingface.co/file.safetensors",
                                "deletedAt": None,
                            },
                            {
                                "url": "https://civitai.com/api/download/models/119514",
                                "deletedAt": "2025-05-23T00:00:00.000Z",
                            },
                        ],
                        "name": "file.safetensors",
                        "hashes": {"SHA256": "abc123"},
                    }
                ],
            }

    class DefaultProvider:
        async def get_model_version(self, model_id, model_version_id):
            captured_providers.append("default")
            return {
                "id": 119514,
                "model": {"type": "LoRA", "tags": ["celebrity"]},
                "baseModel": "SD 1.5",
                "creator": {"username": "dogu_cat"},
                "files": [
                    {
                        "type": "Model",
                        "primary": True,
                        "downloadUrl": "https://civitai.com/api/download/models/119514",
                        "name": "file.safetensors",
                        "hashes": {"SHA256": "abc123"},
                    }
                ],
            }

    async def get_metadata_provider(provider_name):
        if provider_name == "civarchive_api":
            return CivArchiveProvider()
        return None

    async def get_default_metadata_provider():
        return DefaultProvider()

    monkeypatch.setattr(
        download_manager, "get_metadata_provider", get_metadata_provider
    )
    monkeypatch.setattr(
        download_manager, "get_default_metadata_provider", get_default_metadata_provider
    )

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
        captured["version_info"] = version_info
        return {"success": True}

    monkeypatch.setattr(
        DownloadManager, "_execute_download", fake_execute_download, raising=False
    )

    result = await manager.download_from_civitai(
        model_id=110828,
        model_version_id=119514,
        save_dir=str(tmp_path),
        use_default_paths=True,
        progress_callback=None,
        source="civarchive",
    )

    assert result["success"] is True
    assert captured_providers == ["civarchive"]
    assert captured["version_info"]["source"] == "civarchive"


@pytest.mark.asyncio
async def test_civarchive_source_prioritizes_non_civitai_urls(
    monkeypatch, scanners, tmp_path
):
    """Test that civarchive source prioritizes non-CivitAI URLs."""
    manager = DownloadManager()

    class CivArchiveProvider:
        async def get_model_version(self, model_id, model_version_id):
            return {
                "id": 119514,
                "model": {"type": "LoRA", "tags": ["celebrity"]},
                "baseModel": "SD 1.5",
                "creator": {"username": "dogu_cat"},
                "source": "civarchive",
                "files": [
                    {
                        "type": "Model",
                        "primary": True,
                        "mirrors": [
                            {
                                "url": "https://huggingface.co/file.safetensors",
                                "deletedAt": None,
                                "source": "huggingface",
                            },
                            {
                                "url": "https://civitai.com/api/download/models/119514",
                                "deletedAt": None,
                                "source": "civitai",
                            },
                            {
                                "url": "https://another-mirror.org/file.safetensors",
                                "deletedAt": None,
                                "source": "other",
                            },
                        ],
                        "name": "file.safetensors",
                        "hashes": {"SHA256": "abc123"},
                    }
                ],
            }

    async def get_metadata_provider(provider_name):
        if provider_name == "civarchive_api":
            return CivArchiveProvider()
        return None

    monkeypatch.setattr(
        download_manager, "get_metadata_provider", get_metadata_provider
    )

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

    monkeypatch.setattr(
        DownloadManager, "_execute_download", fake_execute_download, raising=False
    )

    result = await manager.download_from_civitai(
        model_id=110828,
        model_version_id=119514,
        save_dir=str(tmp_path),
        use_default_paths=True,
        progress_callback=None,
        source="civarchive",
    )

    assert result["success"] is True
    assert captured["download_urls"] == [
        "https://huggingface.co/file.safetensors",
        "https://another-mirror.org/file.safetensors",
        "https://civitai.com/api/download/models/119514",
    ]
    assert captured["download_urls"][0] == "https://huggingface.co/file.safetensors"
    assert captured["download_urls"][1] == "https://another-mirror.org/file.safetensors"


@pytest.mark.asyncio
async def test_civarchive_source_fallback_to_default_provider(
    monkeypatch, scanners, tmp_path
):
    """Test fallback to default provider when civarchive provider fails."""
    manager = DownloadManager()

    class CivArchiveProvider:
        async def get_model_version(self, model_id, model_version_id):
            return None

    class DefaultProvider:
        async def get_model_version(self, model_id, model_version_id):
            return {
                "id": 119514,
                "model": {"type": "LoRA", "tags": ["celebrity"]},
                "baseModel": "SD 1.5",
                "creator": {"username": "dogu_cat"},
                "files": [
                    {
                        "type": "Model",
                        "primary": True,
                        "downloadUrl": "https://civitai.com/api/download/models/119514",
                        "name": "file.safetensors",
                        "hashes": {"SHA256": "abc123"},
                    }
                ],
            }

    captured_providers = []

    async def get_metadata_provider(provider_name):
        if provider_name == "civarchive_api":
            captured_providers.append("civarchive_api")
            return CivArchiveProvider()
        return None

    async def get_default_metadata_provider():
        captured_providers.append("default")
        return DefaultProvider()

    monkeypatch.setattr(
        download_manager, "get_metadata_provider", get_metadata_provider
    )
    monkeypatch.setattr(
        download_manager, "get_default_metadata_provider", get_default_metadata_provider
    )

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

    monkeypatch.setattr(
        DownloadManager, "_execute_download", fake_execute_download, raising=False
    )

    result = await manager.download_from_civitai(
        model_id=110828,
        model_version_id=119514,
        save_dir=str(tmp_path),
        use_default_paths=True,
        progress_callback=None,
        source="civarchive",
    )

    assert result["success"] is True
    assert captured_providers == ["civarchive_api", "default"]
