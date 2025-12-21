import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from py.services.recipes.analysis_service import RecipeAnalysisService
from py.services.recipes.errors import RecipeDownloadError, RecipeNotFoundError
from py.services.recipes.persistence_service import RecipePersistenceService


class DummyExifUtils:
    def __init__(self):
        self.appended = None
        self.optimized_calls = 0

    def optimize_image(self, image_data, target_width, format, quality, preserve_metadata):
        self.optimized_calls += 1
        return image_data, ".webp"

    def append_recipe_metadata(self, image_path, recipe_data):
        self.appended = (image_path, recipe_data)

    def extract_image_metadata(self, path):
        return {}


@pytest.mark.asyncio
async def test_save_recipe_video_bypasses_optimization(tmp_path):
    exif_utils = DummyExifUtils()

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root)

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

        async def add_recipe(self, recipe_data):
            return None

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    metadata = {"base_model": "Flux", "loras": []}
    video_bytes = b"mp4-content"

    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=video_bytes,
        image_base64=None,
        name="Video Recipe",
        tags=[],
        metadata=metadata,
        extension=".mp4",
    )

    assert result.payload["image_path"].endswith(".mp4")
    assert Path(result.payload["image_path"]).read_bytes() == video_bytes
    assert exif_utils.optimized_calls == 0, "Optimization should be bypassed for video"
    assert exif_utils.appended is None, "Metadata embedding should be bypassed for video"


@pytest.mark.asyncio
async def test_analyze_remote_image_download_failure_cleans_temp(tmp_path, monkeypatch):
    exif_utils = DummyExifUtils()

    class DummyFactory:
        def create_parser(self, metadata):
            return None

    async def downloader_factory():
        class Downloader:
            async def download_file(self, url, path, use_auth=False):
                return False, "failure"

        return Downloader()

    service = RecipeAnalysisService(
        exif_utils=exif_utils,
        recipe_parser_factory=DummyFactory(),
        downloader_factory=downloader_factory,
        metadata_collector=None,
        metadata_processor_cls=None,
        metadata_registry_cls=None,
        standalone_mode=False,
        logger=logging.getLogger("test"),
    )

    temp_path = tmp_path / "temp.jpg"

    def create_temp_path(suffix=".jpg"):
        temp_path.write_bytes(b"")
        return str(temp_path)

    monkeypatch.setattr(service, "_create_temp_path", create_temp_path)

    with pytest.raises(RecipeDownloadError):
        await service.analyze_remote_image(
            url="https://example.com/image.jpg",
            recipe_scanner=SimpleNamespace(),
            civitai_client=SimpleNamespace(),
        )

    assert not temp_path.exists(), "temporary file should be cleaned after failure"


@pytest.mark.asyncio
async def test_analyze_local_image_missing_file(tmp_path):
    async def downloader_factory():
        return SimpleNamespace()

    service = RecipeAnalysisService(
        exif_utils=DummyExifUtils(),
        recipe_parser_factory=SimpleNamespace(create_parser=lambda metadata: None),
        downloader_factory=downloader_factory,
        metadata_collector=None,
        metadata_processor_cls=None,
        metadata_registry_cls=None,
        standalone_mode=False,
        logger=logging.getLogger("test"),
    )

    with pytest.raises(RecipeNotFoundError):
        await service.analyze_local_image(
            file_path=str(tmp_path / "missing.png"),
            recipe_scanner=SimpleNamespace(),
        )


@pytest.mark.asyncio
async def test_save_recipe_reports_duplicates(tmp_path):
    exif_utils = DummyExifUtils()

    class DummyCache:
        def __init__(self):
            self.raw_data = []

        async def resort(self):
            pass

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root)
            self._cache = DummyCache()
            self.last_fingerprint = None

        async def find_recipes_by_fingerprint(self, fingerprint):
            self.last_fingerprint = fingerprint
            return ["existing"]

        async def add_recipe(self, recipe_data):
            self._cache.raw_data.append(recipe_data)
            await self._cache.resort()

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    metadata = {
        "base_model": "sd",
        "loras": [
            {
                "file_name": "sample",
                "hash": "abc123",
                "weight": 0.5,
                "id": 1,
                "name": "Sample",
                "version": "v1",
                "isDeleted": False,
                "exclude": False,
            }
        ],
    }

    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=b"image-bytes",
        image_base64=None,
        name="My Recipe",
        tags=["tag"],
        metadata=metadata,
    )

    assert result.payload["matching_recipes"] == ["existing"]
    assert scanner.last_fingerprint is not None
    assert os.path.exists(result.payload["json_path"])
    assert scanner._cache.raw_data

    stored = json.loads(Path(result.payload["json_path"]).read_text())
    expected_image_path = os.path.normpath(result.payload["image_path"])
    assert stored["file_path"] == expected_image_path
    assert service._exif_utils.appended[0] == expected_image_path


@pytest.mark.asyncio
async def test_save_recipe_persists_checkpoint_metadata(tmp_path):
    exif_utils = DummyExifUtils()

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root)

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

        async def add_recipe(self, recipe_data):
            return None

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    checkpoint_meta = {
        "type": "checkpoint",
        "modelId": 10,
        "modelVersionId": 20,
        "modelName": "Flux",
        "modelVersionName": "Dev",
    }

    metadata = {
        "base_model": "Flux",
        "loras": [],
        "checkpoint": checkpoint_meta,
    }

    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=b"img",
        image_base64=None,
        name="Checkpointed",
        tags=[],
        metadata=metadata,
    )

    stored = json.loads(Path(result.payload["json_path"]).read_text())
    assert stored["checkpoint"] == checkpoint_meta
    assert "checkpoint" not in stored["gen_params"]


@pytest.mark.asyncio
async def test_save_recipe_promotes_checkpoint_from_gen_params(tmp_path):
    exif_utils = DummyExifUtils()

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root)

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

        async def add_recipe(self, recipe_data):
            return None

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    checkpoint_meta = {
        "type": "checkpoint",
        "modelId": 10,
        "modelVersionId": 20,
        "modelName": "Flux",
        "modelVersionName": "Dev",
    }

    metadata = {
        "base_model": "Flux",
        "loras": [],
        "gen_params": {
            "checkpoint": checkpoint_meta,
        },
    }

    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=b"img",
        image_base64=None,
        name="Checkpointed",
        tags=[],
        metadata=metadata,
    )

    stored = json.loads(Path(result.payload["json_path"]).read_text())
    assert stored["checkpoint"] == checkpoint_meta
    assert "checkpoint" not in stored["gen_params"]


@pytest.mark.asyncio
async def test_save_recipe_strips_checkpoint_local_fields(tmp_path):
    exif_utils = DummyExifUtils()

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root)

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

        async def add_recipe(self, recipe_data):
            return None

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    checkpoint_meta = {
        "type": "checkpoint",
        "modelId": 10,
        "modelVersionId": 20,
        "modelName": "Flux",
        "modelVersionName": "Dev",
        "existsLocally": False,
        "localPath": "/tmp/foo",
        "thumbnailUrl": "http://example.com",
        "size": 123,
        "downloadUrl": "http://example.com/dl",
    }

    metadata = {
        "base_model": "Flux",
        "loras": [],
        "checkpoint": checkpoint_meta,
    }

    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=b"img",
        image_base64=None,
        name="Checkpointed",
        tags=[],
        metadata=metadata,
    )

    stored = json.loads(Path(result.payload["json_path"]).read_text())
    assert stored["checkpoint"] == {
        "type": "checkpoint",
        "modelId": 10,
        "modelVersionId": 20,
        "modelName": "Flux",
        "modelVersionName": "Dev",
    }


@pytest.mark.asyncio
async def test_save_recipe_from_widget_allows_empty_lora(tmp_path):
    exif_utils = DummyExifUtils()

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root)
            self.added = []

        async def get_local_lora(self, name):  # pragma: no cover - no lookups expected
            return None

        async def add_recipe(self, recipe_data):
            self.added.append(recipe_data)

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    metadata = {
        "loras": "",  # no matches present in the stack
        "checkpoint": "base-model.safetensors",
        "prompt": "a calm scene",
        "negative_prompt": "",
    }

    result = await service.save_recipe_from_widget(
        recipe_scanner=scanner,
        metadata=metadata,
        image_bytes=b"image-bytes",
    )

    stored = json.loads(Path(result.payload["json_path"]).read_text())

    assert stored["loras"] == []
    assert stored["title"] == "recipe"
    assert scanner.added and scanner.added[0]["loras"] == []


@pytest.mark.asyncio
async def test_analyze_remote_video(tmp_path):
    exif_utils = DummyExifUtils()

    class DummyFactory:
        def create_parser(self, metadata):
            async def parse_metadata(m, recipe_scanner):
                return {"loras": []}
            return SimpleNamespace(parse_metadata=parse_metadata)

    async def downloader_factory():
        class Downloader:
            async def download_file(self, url, path, use_auth=False):
                Path(path).write_bytes(b"video-content")
                return True, "success"

        return Downloader()

    service = RecipeAnalysisService(
        exif_utils=exif_utils,
        recipe_parser_factory=DummyFactory(),
        downloader_factory=downloader_factory,
        metadata_collector=None,
        metadata_processor_cls=None,
        metadata_registry_cls=None,
        standalone_mode=False,
        logger=logging.getLogger("test"),
    )

    class DummyClient:
        async def get_image_info(self, image_id):
            return {
                "url": "https://civitai.com/video.mp4",
                "type": "video",
                "meta": {"prompt": "video prompt"},
            }

    class DummyScanner:
        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    result = await service.analyze_remote_image(
        url="https://civitai.com/images/123",
        recipe_scanner=DummyScanner(),
        civitai_client=DummyClient(),
    )

    assert result.payload["is_video"] is True
    assert result.payload["extension"] == ".mp4"
    assert result.payload["image_base64"] is not None
