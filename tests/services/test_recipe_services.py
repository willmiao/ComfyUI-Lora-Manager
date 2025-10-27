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
    def optimize_image(self, image_data, target_width, format, quality, preserve_metadata):
        return image_data, ".webp"

    def append_recipe_metadata(self, image_path, recipe_data):
        self.appended = (image_path, recipe_data)

    def extract_image_metadata(self, path):
        return {}


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

    def create_temp_path():
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
