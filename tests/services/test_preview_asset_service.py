from pathlib import Path
from typing import Any

import pytest

from py.services import preview_asset_service
from py.services.preview_asset_service import PreviewAssetService


class StubMetadataManager:
    async def save_metadata(self, *_args: Any, **_kwargs: Any) -> bool:  # pragma: no cover - helper
        return True


class RecordingExifUtils:
    def __init__(self) -> None:
        self.called = False

    def optimize_image(self, **kwargs):
        self.called = True
        return kwargs["image_data"], {}


@pytest.mark.asyncio
async def test_ensure_preview_prefers_rewritten_civitai_image(tmp_path):
    metadata_path = tmp_path / "model.metadata.json"
    metadata_path.write_text("{}")
    local_metadata: dict[str, Any] = {}

    class Downloader:
        def __init__(self):
            self.file_calls: list[tuple[str, str]] = []
            self.memory_calls = 0

        async def download_file(self, url, path, use_auth=False):
            self.file_calls.append((url, path))
            if "width=450,optimized=true" in url:
                Path(path).write_bytes(b"image-data")
                return True, None
            return False, "fail"

        async def download_to_memory(self, *_args, **_kwargs):
            self.memory_calls += 1
            return False, b"", {}

    downloader = Downloader()

    async def downloader_factory():
        return downloader

    exif_utils = RecordingExifUtils()
    service = PreviewAssetService(
        metadata_manager=StubMetadataManager(),
        downloader_factory=downloader_factory,
        exif_utils=exif_utils,
    )

    images = [
        {
            "url": "https://image.civitai.com/container/example/original=true/sample.jpeg",
            "type": "image",
            "nsfwLevel": 3,
        }
    ]

    await service.ensure_preview_for_metadata(str(metadata_path), local_metadata, images)

    assert downloader.memory_calls == 0
    assert exif_utils.called is False
    assert len(downloader.file_calls) == 1
    assert "width=450,optimized=true" in downloader.file_calls[0][0]
    preview_path = Path(local_metadata["preview_url"])
    assert preview_path.exists()
    assert preview_path.suffix == ".jpeg"
    assert local_metadata["preview_nsfw_level"] == 3


@pytest.mark.asyncio
async def test_ensure_preview_falls_back_to_webp_when_rewrite_fails(tmp_path):
    metadata_path = tmp_path / "model.metadata.json"
    metadata_path.write_text("{}")
    local_metadata: dict[str, Any] = {}

    class Downloader:
        def __init__(self):
            self.file_calls: list[tuple[str, str]] = []
            self.memory_calls = 0

        async def download_file(self, url, path, use_auth=False):
            self.file_calls.append((url, path))
            return False, "fail"

        async def download_to_memory(self, *_args, **_kwargs):
            self.memory_calls += 1
            return True, b"raw-image", {}

    downloader = Downloader()

    async def downloader_factory():
        return downloader

    class ExifUtils:
        def __init__(self):
            self.calls = 0

        def optimize_image(self, **kwargs):
            self.calls += 1
            return b"webp-data", {}

    exif_utils = ExifUtils()

    service = PreviewAssetService(
        metadata_manager=StubMetadataManager(),
        downloader_factory=downloader_factory,
        exif_utils=exif_utils,
    )

    images = [
        {
            "url": "https://image.civitai.com/container/example/original=true/sample.png",
            "type": "image",
            "nsfwLevel": 1,
        }
    ]

    await service.ensure_preview_for_metadata(str(metadata_path), local_metadata, images)

    assert downloader.memory_calls == 1
    assert exif_utils.calls == 1
    preview_path = Path(local_metadata["preview_url"])
    assert preview_path.exists()
    assert preview_path.suffix == ".webp"


@pytest.mark.asyncio
async def test_ensure_preview_rewrites_civitai_video(tmp_path):
    metadata_path = tmp_path / "model.metadata.json"
    metadata_path.write_text("{}")
    local_metadata: dict[str, Any] = {}

    class Downloader:
        def __init__(self):
            self.file_calls: list[tuple[str, str]] = []

        async def download_file(self, url, path, use_auth=False):
            self.file_calls.append((url, path))
            if "transcode=true,width=450,optimized=true" in url:
                Path(path).write_bytes(b"video-data")
                return True, None
            if url.endswith(".mp4"):
                return False, "fail"
            return False, "unexpected"

        async def download_to_memory(self, *_args, **_kwargs):
            pytest.fail("download_to_memory should not be used for video previews")

    downloader = Downloader()

    async def downloader_factory():
        return downloader

    service = PreviewAssetService(
        metadata_manager=StubMetadataManager(),
        downloader_factory=downloader_factory,
        exif_utils=RecordingExifUtils(),
    )

    images = [
        {
            "url": "https://image.civitai.com/container/example/original=true/sample.mp4",
            "type": "video",
            "nsfwLevel": 2,
        }
    ]

    await service.ensure_preview_for_metadata(str(metadata_path), local_metadata, images)

    assert len(downloader.file_calls) >= 1
    assert any("transcode=true,width=450,optimized=true" in url for url, _ in downloader.file_calls)
    preview_path = Path(local_metadata["preview_url"])
    assert preview_path.exists()
    assert preview_path.suffix == ".mp4"
    assert local_metadata["preview_nsfw_level"] == 2


@pytest.mark.asyncio
async def test_ensure_preview_respects_blur_setting(monkeypatch, tmp_path):
    metadata_path = tmp_path / "model.metadata.json"
    metadata_path.write_text("{}")
    local_metadata: dict[str, Any] = {}

    class Downloader:
        def __init__(self):
            self.file_calls: list[tuple[str, str]] = []

        async def download_file(self, url, path, use_auth=False):
            self.file_calls.append((url, path))
            Path(path).write_bytes(b"image-data")
            return True, None

        async def download_to_memory(self, *_args, **_kwargs):
            pytest.fail("download_to_memory should not be used when download_file succeeds")

    downloader = Downloader()

    async def downloader_factory():
        return downloader

    class StubSettingsManager:
        def __init__(self, blur: bool) -> None:
            self.blur = blur

        def get(self, key: str, default=None):
            if key == "blur_mature_content":
                return self.blur
            return default

    monkeypatch.setattr(
        preview_asset_service,
        "get_settings_manager",
        lambda: StubSettingsManager(True),
    )

    service = PreviewAssetService(
        metadata_manager=StubMetadataManager(),
        downloader_factory=downloader_factory,
        exif_utils=RecordingExifUtils(),
    )

    images = [
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
    ]

    await service.ensure_preview_for_metadata(str(metadata_path), local_metadata, images)

    assert len(downloader.file_calls) == 1
    requested_url = downloader.file_calls[0][0]
    assert "safe.jpeg" in requested_url
    assert local_metadata["preview_nsfw_level"] == 1
