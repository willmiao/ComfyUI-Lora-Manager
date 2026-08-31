import json
import logging
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import piexif  # pyright: ignore[reportMissingTypeStubs]
import pytest
from PIL import Image, PngImagePlugin

from py.services.recipes.analysis_service import RecipeAnalysisService
from py.services.recipes.errors import (
    RecipeDownloadError,
    RecipeNotFoundError,
    RecipeValidationError,
)
from py.services.recipes.persistence_service import RecipePersistenceService
from py.services.model_scanner import ModelScanner
from py.recipes.parsers.civitai_image import CivitaiApiMetadataParser
from py.utils.exif_utils import ExifUtils


class DummyExifUtils:
    def __init__(self):
        self.appended = None
        self.optimized_calls = 0
        self.workflow_value = None

    def optimize_image(self, image_data, target_width, format, quality, preserve_metadata):
        self.optimized_calls += 1
        return image_data, ".webp"

    def append_recipe_metadata(self, image_path, recipe_data, pixel_preserving=False):
        self.appended = (image_path, recipe_data, pixel_preserving)

    def extract_image_metadata(self, path):
        return {}

    def _load_structured_metadata(self, image_path):
        return {
            "parameters": None,
            "prompt": None,
            "workflow": self.workflow_value,
            "comment": None,
        }


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
async def test_save_recipe_skip_optimize_preserves_image_bytes(tmp_path):
    """Local re-import sources are already-optimized recipe images; saving them
    must keep the bytes verbatim instead of re-compressing, while the recipe
    metadata block is still embedded via a pixel-preserving EXIF update."""
    exif_utils = DummyExifUtils()

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root / "recipes")

        async def add_recipe(self, recipe_data):
            return None

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    image_bytes = b"\x89PNG-not-optimized-again"
    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=image_bytes,
        image_base64=None,
        name="Re-imported",
        tags=[],
        metadata={"gen_params": {"steps": 20}, "base_model": "SDXL", "loras": []},
        extension=".webp",
        skip_optimize=True,
    )

    assert result.payload["image_path"].endswith(".webp")
    assert Path(result.payload["image_path"]).read_bytes() == image_bytes
    assert exif_utils.optimized_calls == 0, "Optimization should be bypassed"
    # Metadata is still embedded, but through the pixel-preserving path.
    assert exif_utils.appended is not None
    assert exif_utils.appended[2] is True


@pytest.mark.asyncio
async def test_save_recipe_skip_optimize_default_optimizes(tmp_path):
    """Normal saves must keep optimizing; only re-import opts out."""
    exif_utils = DummyExifUtils()

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root / "recipes")

        async def add_recipe(self, recipe_data):
            return None

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=b"raw-image",
        image_base64=None,
        name="Normal",
        tags=[],
        metadata={"gen_params": {"steps": 20}, "base_model": "SDXL", "loras": []},
        extension=".webp",
    )

    assert exif_utils.optimized_calls == 1
    assert exif_utils.appended is not None
    assert exif_utils.appended[2] is False


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
async def test_save_recipe_records_has_workflow(tmp_path):
    exif_utils = DummyExifUtils()
    exif_utils.workflow_value = '{"nodes": []}'

    class DummyCache:
        def __init__(self):
            self.raw_data = []

        async def resort(self):
            pass

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root)
            self._cache = DummyCache()

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

        async def add_recipe(self, recipe_data):
            self._cache.raw_data.append(recipe_data)

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=b"image-bytes",
        image_base64=None,
        name="Workflow Recipe",
        tags=[],
        metadata={"base_model": "sd", "loras": []},
    )

    stored = json.loads(Path(result.payload["json_path"]).read_text())
    assert stored["has_workflow"] is True
    assert scanner._cache.raw_data[0]["has_workflow"] is True


@pytest.mark.asyncio
async def test_save_recipe_records_no_workflow(tmp_path):
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

    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=b"image-bytes",
        image_base64=None,
        name="Plain Recipe",
        tags=[],
        metadata={"base_model": "sd", "loras": []},
    )

    stored = json.loads(Path(result.payload["json_path"]).read_text())
    assert stored["has_workflow"] is False


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
async def test_save_recipe_strips_non_persistable_gen_params(tmp_path):
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

    metadata = {
        "base_model": "Flux",
        "loras": [],
        "gen_params": {
            "prompt": "hello world",
            "negative_prompt": "bad hands",
            "cfg_scale": 7,
            "raw_metadata": {"prompt": "should not persist"},
            "Version": "ComfyUI",
            "RNG": "cpu",
            "Schedule type": "karras",
            "Discard penultimate sigma": True,
            "eps_scaling_factor": 0.1,
        },
    }

    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=b"img",
        image_base64=None,
        name="Sanitized",
        tags=[],
        metadata=metadata,
    )

    stored = json.loads(Path(result.payload["json_path"]).read_text())
    assert stored["gen_params"] == {
        "prompt": "hello world",
        "negative_prompt": "bad hands",
        "cfg_scale": 7,
    }


@pytest.mark.asyncio
async def test_save_recipe_derives_allowed_fields_from_raw_metadata(tmp_path):
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

    metadata = {
        "base_model": "Flux",
        "loras": [],
        "raw_metadata": {
            "prompt": "hello world",
            "negative_prompt": "bad hands",
            "steps": 30,
            "sampler": "Euler",
            "cfg_scale": 7,
            "seed": 123,
            "size": "1024x1024",
            "clip_skip": 2,
            "Version": "ComfyUI",
            "raw_metadata": {"nested": True},
        },
    }

    result = await service.save_recipe(
        recipe_scanner=scanner,
        image_bytes=b"img",
        image_base64=None,
        name="Derived",
        tags=[],
        metadata=metadata,
    )

    stored = json.loads(Path(result.payload["json_path"]).read_text())
    assert stored["gen_params"] == {
        "prompt": "hello world",
        "negative_prompt": "bad hands",
        "steps": 30,
        "sampler": "Euler",
        "cfg_scale": 7,
        "seed": 123,
        "size": "1024x1024",
        "clip_skip": 2,
    }


@pytest.mark.asyncio
async def test_save_recipe_preserves_workflow_when_png_is_converted_to_webp(tmp_path):
    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root)

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

        async def add_recipe(self, recipe_data):
            return None

    png_info = PngImagePlugin.PngInfo()
    png_info.add_text("parameters", "prompt text\nSteps: 20")
    png_info.add_text("workflow", '{"nodes":[{"id":1}]}')

    image_buffer = BytesIO()
    Image.new("RGB", (96, 48), color="purple").save(
        image_buffer, format="PNG", pnginfo=png_info
    )

    service = RecipePersistenceService(
        exif_utils=ExifUtils,
        card_preview_width=64,
        logger=logging.getLogger("test"),
    )

    result = await service.save_recipe(
        recipe_scanner=DummyScanner(tmp_path),
        image_bytes=image_buffer.getvalue(),
        image_base64=None,
        name="Workflow Recipe",
        tags=["workflow"],
        metadata={"base_model": "sd", "loras": []},
        extension=".png",
    )

    image_path = Path(result.payload["image_path"])
    exif_dict = piexif.load(str(image_path))
    assert exif_dict is not None
    exif_0th = exif_dict["0th"]
    assert exif_0th is not None
    assert (
        exif_0th[piexif.ImageIFD.ImageDescription].decode("utf-8")
        == 'Workflow:{"nodes":[{"id":1}]}'
    )

    exif_section = exif_dict["Exif"]
    assert exif_section is not None
    user_comment = exif_section[piexif.ExifIFD.UserComment]
    decoded_comment = user_comment[8:].decode("utf-16be")
    assert "prompt text" in decoded_comment
    assert "Recipe metadata:" in decoded_comment


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

        async def get_local_checkpoint(self, name):
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
    assert stored["checkpoint"] == {
        "type": "checkpoint",
        "name": "base-model.safetensors",
        "file_name": "base-model",
        "hash": "",
    }
    assert scanner.added and scanner.added[0]["loras"] == []


@pytest.mark.asyncio
async def test_save_recipe_from_widget_enriches_checkpoint_from_local_cache(tmp_path):
    exif_utils = DummyExifUtils()

    class DummyScanner:
        def __init__(self, root):
            self.recipes_dir = str(root)
            self.added = []
            self.checkpoint_queries = []

        async def get_local_lora(self, name):  # pragma: no cover - no loras
            return None

        async def get_local_checkpoint(self, name):
            self.checkpoint_queries.append(name)
            if name != "matched-model":
                return None
            return {
                "file_name": "matched-model",
                "file_path": "/models/checkpoints/folder/matched-model.safetensors",
                "sha256": "ABC123",
                "base_model": "Illustrious",
                "civitai": {
                    "id": 456,
                    "name": "v1.0",
                    "baseModel": "Illustrious",
                    "model": {
                        "id": 123,
                        "name": "Matched Model",
                    },
                },
            }

        async def add_recipe(self, recipe_data):
            self.added.append(recipe_data)

    scanner = DummyScanner(tmp_path)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    result = await service.save_recipe_from_widget(
        recipe_scanner=scanner,
        metadata={
            "loras": "",
            "checkpoint": "folder/matched-model.safetensors",
            "prompt": "a calm scene",
        },
        image_bytes=b"image-bytes",
    )

    stored = json.loads(Path(result.payload["json_path"]).read_text())

    assert scanner.checkpoint_queries == [
        "folder/matched-model.safetensors",
        "matched-model.safetensors",
        "matched-model",
    ]
    assert stored["base_model"] == "Illustrious"
    assert stored["checkpoint"] == {
        "type": "checkpoint",
        "modelId": 123,
        "modelVersionId": 456,
        "name": "Matched Model",
        "version": "v1.0",
        "hash": "abc123",
        "file_name": "matched-model",
        "modelName": "Matched Model",
        "modelVersionName": "v1.0",
        "baseModel": "Illustrious",
    }


@pytest.mark.asyncio
async def test_move_recipe_updates_paths(tmp_path):
    exif_utils = DummyExifUtils()
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    recipe_id = "move-me"
    image_path = recipes_dir / f"{recipe_id}.webp"
    json_path = recipes_dir / f"{recipe_id}.recipe.json"

    image_path.write_bytes(b"img")
    json_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": str(image_path),
                "title": "Recipe",
                "loras": [],
                "gen_params": {},
                "created_date": 0,
                "modified": 0,
            }
        )
    )

    class MoveScanner:
        def __init__(self, root: Path):
            self.recipes_dir = str(root)
            self.recipe = {
                "id": recipe_id,
                "file_path": str(image_path),
                "title": "Recipe",
                "loras": [],
                "gen_params": {},
                "created_date": 0,
                "modified": 0,
                "folder": "",
            }

        async def get_recipe_by_id(self, target_id: str):
            return self.recipe if target_id == recipe_id else None

        async def get_recipe_json_path(self, target_id: str):
            matches = list(Path(self.recipes_dir).rglob(f"{target_id}.recipe.json"))
            return str(matches[0]) if matches else None

        async def update_recipe_metadata(self, target_id: str, metadata: Dict[str, Any]):
            if target_id != recipe_id:
                return False
            self.recipe.update(metadata)
            target_path = await self.get_recipe_json_path(target_id)
            if not target_path:
                return False
            existing = json.loads(Path(target_path).read_text())
            existing.update(metadata)
            Path(target_path).write_text(json.dumps(existing))
            return True

        async def get_cached_data(self, force_refresh: bool = False):  # noqa: ARG002 - signature parity
            return SimpleNamespace(raw_data=[self.recipe])

    scanner = MoveScanner(recipes_dir)
    service = RecipePersistenceService(
        exif_utils=exif_utils,
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    target_folder = recipes_dir / "nested"
    result = await service.move_recipe(
        recipe_scanner=scanner, recipe_id=recipe_id, target_path=str(target_folder)
    )

    assert result.payload["folder"] == "nested"
    assert Path(result.payload["json_path"]).parent == target_folder
    assert Path(result.payload["new_file_path"]).parent == target_folder
    assert not json_path.exists()

    stored = json.loads(Path(result.payload["json_path"]).read_text())
    assert stored["folder"] == "nested"
    assert stored["file_path"] == result.payload["new_file_path"]


@pytest.mark.asyncio
async def test_update_recipe_accepts_gen_params() -> None:
    class DummyScanner:
        def __init__(self):
            self.calls = []

        async def update_recipe_metadata(self, recipe_id: str, updates: dict[str, object]):
            self.calls.append((recipe_id, updates))
            return True

    scanner = DummyScanner()
    service = RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    updates = {"gen_params": {"prompt": "updated prompt", "steps": 28}}
    result = await service.update_recipe(
        recipe_scanner=scanner,
        recipe_id="recipe-1",
        updates=updates,
    )

    assert result.payload["success"] is True
    assert scanner.calls == [("recipe-1", updates)]


@pytest.mark.asyncio
async def test_update_recipe_rejects_non_object_gen_params() -> None:
    service = RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    with pytest.raises(RecipeValidationError, match="gen_params must be an object"):
        await service.update_recipe(
            recipe_scanner=SimpleNamespace(),
            recipe_id="recipe-1",
            updates={"gen_params": "invalid"},
        )


@pytest.mark.asyncio
async def test_analyze_remote_video(tmp_path):
    exif_utils = DummyExifUtils()

    class DummyFactory:
        def create_parser(self, metadata):
            async def parse_metadata(m, recipe_scanner=None, civitai_client=None):
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
        async def get_image_info(self, image_id, source_url=None):
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


@pytest.mark.asyncio
async def test_analyze_remote_image_supports_civitai_red():
    exif_utils = DummyExifUtils()

    class DummyFactory:
        def create_parser(self, metadata):
            async def parse_metadata(m, recipe_scanner=None, civitai_client=None):
                return {"loras": [], "gen_params": {"prompt": "red prompt"}}

            return SimpleNamespace(parse_metadata=parse_metadata)

    async def downloader_factory():
        class Downloader:
            async def download_file(self, url, path, use_auth=False):
                Path(path).write_bytes(b"fake-image")
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
        def __init__(self):
            self.calls = []

        async def get_image_info(self, image_id, source_url=None):
            self.calls.append((image_id, source_url))
            return {
                "url": "https://image.civitai.com/x/y/original=true/sample.jpeg",
                "type": "image",
                "meta": {"prompt": "red prompt"},
            }

    class DummyScanner:
        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    client = DummyClient()
    result = await service.analyze_remote_image(
        url="https://civitai.red/images/123",
        recipe_scanner=DummyScanner(),
        civitai_client=client,
    )

    assert client.calls == [("123", "https://civitai.red/images/123")]
    assert result.payload["loras"] == []


def _exif_utils_returning(metadata):
    class MetadataExifUtils(DummyExifUtils):
        def extract_image_metadata(self, path):
            return metadata

    return MetadataExifUtils()


def _make_analysis_service(parser_factory, exif_utils):
    async def downloader_factory():
        return SimpleNamespace()

    return RecipeAnalysisService(
        exif_utils=exif_utils,
        recipe_parser_factory=parser_factory,
        downloader_factory=downloader_factory,
        metadata_collector=None,
        metadata_processor_cls=None,
        metadata_registry_cls=None,
        standalone_mode=False,
        logger=logging.getLogger("test"),
    )


@pytest.mark.asyncio
async def test_analyze_local_image_civitai_parser_receives_local_cache(tmp_path):
    metadata = {
        "resources": [{"type": "lora", "name": "SomeLora", "hash": "abc123456789"}],
        "prompt": "test",
    }
    local_cache = {
        "abc123456789": {
            "sha256": "0" * 64,
            "file_path": "/models/loras/some.safetensors",
        }
    }

    class SpyParser(CivitaiApiMetadataParser):
        def __init__(self):
            super().__init__()
            self.local_cache_received = None

        async def parse_metadata(self, user_comment, recipe_scanner=None, civitai_client=None, local_cache=None):
            self.local_cache_received = local_cache
            return {
                "loras": [
                    {
                        "name": "SomeLora",
                        "hash": "abc123456789",
                        "weight": 1.0,
                        "existsLocally": False,
                    }
                ],
                "base_model": "Illustrious",
            }

    class DummyFactory:
        def __init__(self):
            self.parser = None

        def create_parser(self, metadata):
            self.parser = SpyParser()
            return self.parser

    class CacheScanner:
        def __init__(self):
            self.cache_builds = 0

        async def build_local_hash_cache(self):
            self.cache_builds += 1
            return local_cache

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"fake-image")

    scanner = CacheScanner()
    factory = DummyFactory()
    service = _make_analysis_service(factory, _exif_utils_returning(metadata))

    result = await service.analyze_local_image(
        file_path=str(image_path), recipe_scanner=scanner
    )

    assert factory.parser is not None
    assert factory.parser.local_cache_received is local_cache
    assert scanner.cache_builds == 1
    assert result.payload["fingerprint"] == "abc123456789:1.0"
    assert result.payload["matching_recipes"] == []


@pytest.mark.asyncio
async def test_analyze_local_image_non_civitai_parser_without_local_cache(tmp_path):
    metadata = {"prompt": "test", "negative_prompt": ""}

    class NonCivitaiParser:
        def __init__(self):
            self.called_with = None

        # Signature mirrors RecipeFormatParser: no local_cache parameter.
        async def parse_metadata(self, user_comment, recipe_scanner=None):
            self.called_with = {"recipe_scanner": recipe_scanner}
            return {"loras": [], "base_model": "Illustrious"}

    class DummyFactory:
        def __init__(self):
            self.parser = None

        def create_parser(self, metadata):
            self.parser = NonCivitaiParser()
            return self.parser

    class CacheScanner:
        def __init__(self):
            self.cache_builds = 0

        async def build_local_hash_cache(self):
            self.cache_builds += 1
            return {}

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"fake-image")

    scanner = CacheScanner()
    factory = DummyFactory()
    service = _make_analysis_service(factory, _exif_utils_returning(metadata))

    result = await service.analyze_local_image(
        file_path=str(image_path), recipe_scanner=scanner
    )

    assert scanner.cache_builds == 0, "non-Civitai parser must not build the cache"
    assert factory.parser is not None
    assert factory.parser.called_with is not None
    assert "local_cache" not in factory.parser.called_with
    assert result.payload["loras"] == []


@pytest.mark.asyncio
async def test_analyze_local_image_fingerprint_and_matching_recipes_unaffected(tmp_path):
    metadata = {"prompt": "test", "resources": []}

    class SpyParser(CivitaiApiMetadataParser):
        def __init__(self):
            super().__init__()
            self.local_cache_received = None

        async def parse_metadata(self, user_comment, recipe_scanner=None, civitai_client=None, local_cache=None):
            self.local_cache_received = local_cache
            return {
                "loras": [
                    {"name": "B", "hash": "bbb222", "weight": 0.5},
                    {"name": "A", "hash": "aaa111", "weight": 0.5},
                ],
                "base_model": "Illustrious",
            }

    class DummyFactory:
        def __init__(self):
            self.parser = None

        def create_parser(self, metadata):
            self.parser = SpyParser()
            return self.parser

    class CacheScanner:
        def __init__(self):
            self.last_fingerprint = None

        async def build_local_hash_cache(self):
            return {"abc123456789": {"sha256": "0" * 64}}

        async def find_recipes_by_fingerprint(self, fingerprint):
            self.last_fingerprint = fingerprint
            return ["recipe-1"]

    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"fake-image")

    scanner = CacheScanner()
    factory = DummyFactory()
    service = _make_analysis_service(factory, _exif_utils_returning(metadata))

    result = await service.analyze_local_image(
        file_path=str(image_path), recipe_scanner=scanner
    )

    assert factory.parser is not None
    assert factory.parser.local_cache_received is not None
    assert result.payload["fingerprint"] == "aaa111:0.5|bbb222:0.5"
    assert scanner.last_fingerprint == "aaa111:0.5|bbb222:0.5"
    assert result.payload["matching_recipes"] == ["recipe-1"]


@pytest.mark.asyncio
async def test_analyze_local_image_fingerprint_uses_sha256_normalized_hash(tmp_path, monkeypatch):
    # Regression pin: a lora matched via local_cache gets its entry hash
    # rewritten to the sha256 by _populate_entry_from_cache, so the
    # fingerprint is computed from the normalized sha256, not the raw hash.
    sha256 = "a1b2c3d4e5f60718293a4b5c6d7e8f901a2b3c4d5e6f708192a3b4c5d6e7f809"
    local_cache = {
        "abc123456789": {
            "sha256": sha256,
            "file_path": "/models/loras/some.safetensors",
            "model_name": "SomeLora",
            "base_model": "Illustrious",
            "civitai": {"id": 123, "modelId": 456, "name": "v1.0"},
        }
    }
    metadata = {
        "resources": [{"type": "lora", "name": "SomeLora", "hash": "abc123456789"}],
        "prompt": "test",
        "baseModel": "Illustrious",
    }

    class DummyFactory:
        def create_parser(self, metadata):
            return CivitaiApiMetadataParser()

    class CacheScanner:
        async def build_local_hash_cache(self):
            return local_cache

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    async def fake_metadata_provider():
        class StubProvider:
            async def get_model_by_hash(self, model_hash):
                raise AssertionError("local cache hit must skip the API call")

        return StubProvider()

    monkeypatch.setattr(
        "py.recipes.parsers.civitai_image.get_default_metadata_provider",
        fake_metadata_provider,
    )

    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"fake-image")

    service = _make_analysis_service(DummyFactory(), _exif_utils_returning(metadata))

    result = await service.analyze_local_image(
        file_path=str(image_path), recipe_scanner=CacheScanner()
    )

    assert result.payload["loras"][0]["hash"] == sha256
    assert result.payload["fingerprint"] == f"{sha256}:1.0"


@pytest.mark.asyncio
async def test_reconnect_lora_distinguishes_ambiguous_mismatched_and_missing(tmp_path):
    service = RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    models = [
        {
            "file_name": "style.safetensors",
            "folder": "sd15",
            "file_path": "/models/loras/sd15/style.safetensors",
            "base_model": "SD 1.5",
        },
        {
            "file_name": "style.safetensors",
            "folder": "sdxl",
            "file_path": "/models/loras/sdxl/style.safetensors",
            "base_model": "SDXL 1.0",
        },
    ]

    class DummyScanner:
        def __init__(self, recipe_path):
            self._recipe_path = recipe_path

        async def get_recipe_json_path(self, recipe_id):
            return str(self._recipe_path)

        async def get_local_lora(self, name, base_model=None):
            matches = ModelScanner.find_matching_models(models, name, base_model=base_model)
            return matches[0] if len(matches) == 1 else None

        async def find_local_loras_by_name(self, name, base_model=None):
            return ModelScanner.find_matching_models(models, name, base_model=base_model)

    def write_recipe(base_model):
        recipe_path = tmp_path / "recipe.json"
        recipe_path.write_text(
            json.dumps({"id": "r1", "base_model": base_model, "loras": []})
        )
        return DummyScanner(recipe_path)

    # Ambiguous bare name: two candidates survive (recipe base model unknown)
    scanner = write_recipe("")
    with pytest.raises(RecipeValidationError, match="include the folder path"):
        await service.reconnect_lora(
            recipe_scanner=scanner, recipe_id="r1", lora_index=0, target_name="style"
        )

    # Confident base-model mismatch: the only candidate belongs to another family
    scanner = write_recipe("SD 1.5")
    with pytest.raises(RecipeValidationError, match="different base model"):
        await service.reconnect_lora(
            recipe_scanner=scanner,
            recipe_id="r1",
            lora_index=0,
            target_name="sdxl/style",
        )

    # No candidate at all
    scanner = write_recipe("SDXL 1.0")
    with pytest.raises(RecipeNotFoundError, match="not found"):
        await service.reconnect_lora(
            recipe_scanner=scanner, recipe_id="r1", lora_index=0, target_name="missing"
        )


@pytest.mark.asyncio
async def test_reconnect_lora_family_compatible_succeeds_with_warning(tmp_path):
    service = RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    pony_item = {
        "file_name": "style.safetensors",
        "folder": "",
        "file_path": "/models/loras/style.safetensors",
        "base_model": "Pony",
        "sha256": "ab" * 32,
    }

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps({"id": "r1", "base_model": "Illustrious", "loras": [{}]})
    )

    class DummyScanner:
        async def get_recipe_json_path(self, recipe_id):
            return str(recipe_path)

        async def find_local_loras_by_name(self, name, base_model=None):
            return [pony_item]

        async def update_lora_entry(self, recipe_id, lora_index, *, target_name, target_lora):
            assert target_lora is pony_item
            return ({"id": "r1"}, {"file_name": target_lora["file_name"]})

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    result = await service.reconnect_lora(
        recipe_scanner=DummyScanner(), recipe_id="r1", lora_index=0, target_name="style"
    )

    assert result.payload["success"] is True
    assert result.payload["base_model_mismatch"] == {
        "recipe_base_model": "Illustrious",
        "lora_base_model": "Pony",
    }


@pytest.mark.asyncio
async def test_reconnect_lora_exact_base_model_has_no_warning(tmp_path):
    service = RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    item = {
        "file_name": "style.safetensors",
        "folder": "",
        "file_path": "/models/loras/style.safetensors",
        "base_model": "SDXL 1.0",
        "sha256": "ab" * 32,
    }

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps({"id": "r1", "base_model": "SDXL 1.0", "loras": [{}]})
    )

    class DummyScanner:
        async def get_recipe_json_path(self, recipe_id):
            return str(recipe_path)

        async def find_local_loras_by_name(self, name, base_model=None):
            return [item]

        async def update_lora_entry(self, recipe_id, lora_index, *, target_name, target_lora):
            return ({"id": "r1"}, {"file_name": target_lora["file_name"]})

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    result = await service.reconnect_lora(
        recipe_scanner=DummyScanner(), recipe_id="r1", lora_index=0, target_name="style"
    )

    assert result.payload["success"] is True
    assert "base_model_mismatch" not in result.payload


@pytest.mark.asyncio
async def test_get_reconnect_suggestions_loads_entry_and_delegates(tmp_path):
    service = RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "id": "r1",
                "base_model": "SD 1.5",
                "loras": [
                    {"file_name": "a.safetensors", "hash": "aaa"},
                    {"file_name": "b.safetensors", "hash": "bbb", "isDeleted": True},
                ],
            }
        )
    )

    class DummyScanner:
        def __init__(self):
            self.calls = []

        async def get_recipe_json_path(self, recipe_id):
            assert recipe_id == "r1"
            return str(recipe_path)

        async def suggest_reconnect_candidates(
            self, *, entry, recipe_base_model, query=None, limit=5
        ):
            self.calls.append(
                {
                    "entry": entry,
                    "recipe_base_model": recipe_base_model,
                    "query": query,
                }
            )
            return [
                {
                    "file_name": "b.safetensors",
                    "score": 1.0,
                    "match_reason": "same_hash",
                    "target_name": "b",
                }
            ]

    scanner = DummyScanner()
    result = await service.get_reconnect_suggestions(
        recipe_scanner=scanner, recipe_id="r1", lora_index=1, query="b"
    )

    assert result.payload["success"] is True
    assert result.payload["suggestions"][0]["target_name"] == "b"
    assert scanner.calls == [
        {
            "entry": {"file_name": "b.safetensors", "hash": "bbb", "isDeleted": True},
            "recipe_base_model": "SD 1.5",
            "query": "b",
        }
    ]


@pytest.mark.asyncio
async def test_get_reconnect_suggestions_validates_recipe_and_index(tmp_path):
    service = RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    class MissingScanner:
        async def get_recipe_json_path(self, recipe_id):
            return str(tmp_path / "missing.json")

    with pytest.raises(RecipeNotFoundError):
        await service.get_reconnect_suggestions(
            recipe_scanner=MissingScanner(), recipe_id="nope", lora_index=0
        )

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(json.dumps({"id": "r1", "loras": []}))

    class EmptyScanner:
        async def get_recipe_json_path(self, recipe_id):
            return str(recipe_path)

    with pytest.raises(RecipeValidationError, match="lora_index"):
        await service.get_reconnect_suggestions(
            recipe_scanner=EmptyScanner(), recipe_id="r1", lora_index=0
        )


@pytest.mark.asyncio
async def test_mark_lora_hash_invalid_delegates_and_reports(tmp_path):
    service = RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    class DummyScanner:
        async def set_lora_entry_hash_invalid(self, recipe_id, lora_index, hash_invalid):
            assert recipe_id == "r1"
            assert lora_index == 0
            assert hash_invalid is True
            return (
                {"id": "r1", "loras": [{"file_name": "m", "hashInvalid": True}]},
                {"file_name": "m", "hashInvalid": True},
            )

    result = await service.mark_lora_hash_invalid(
        recipe_scanner=DummyScanner(), recipe_id="r1", lora_index=0
    )

    assert result.payload["success"] is True
    assert result.payload["recipe_id"] == "r1"
    assert result.payload["hash_invalid"] is True
    assert result.payload["updated_lora"]["hashInvalid"] is True


@pytest.mark.asyncio
async def test_mark_lora_hash_invalid_can_clear_flag(tmp_path):
    service = RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )

    class DummyScanner:
        async def set_lora_entry_hash_invalid(self, recipe_id, lora_index, hash_invalid):
            assert hash_invalid is False
            return (
                {"id": "r1", "loras": [{"file_name": "m", "hashInvalid": False}]},
                {"file_name": "m", "hashInvalid": False},
            )

    result = await service.mark_lora_hash_invalid(
        recipe_scanner=DummyScanner(),
        recipe_id="r1",
        lora_index=0,
        hash_invalid=False,
    )

    assert result.payload["hash_invalid"] is False
    assert result.payload["updated_lora"]["hashInvalid"] is False


@pytest.mark.asyncio
async def test_analyze_remote_image_meta_null_keeps_exif_loras(tmp_path, monkeypatch):
    """When the CivitAI image API meta is null (only modelVersionIds
    present), the EXIF-parsed LoRAs must be merged into the result — they
    were previously dropped because the API-only parse yields a checkpoint
    but no LoRAs."""
    A1111_METADATA = (
        "woman, natural blonde hair, ice blue eyes, <lora:Daphne Blake Cosplay_v1:1> daphne blake cosplay, upper body\n"
        "Negative prompt: low quality\n"
        "Steps: 20, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 4140408634, "
        "Size: 512x768, Model hash: 3c8530cb22, Model: cyberrealistic_v33, "
        'Lora hashes: "Daphne Blake Cosplay_v1: e67ebd5e315f", '
        'Hashes: {"lora:Daphne Blake Cosplay_v1": "a2a12bfa01"}'
    )
    LORA_SHA256 = "533317d3f7d269f9f504bdc432514774d3ada3738ebd80f3f1a37ff848e88276"

    class FakeExif:
        def extract_image_metadata(self, path):
            return A1111_METADATA

    class FakeDownloader:
        async def download_file(self, url, path, use_auth=False):
            with open(path, "wb") as fh:
                fh.write(b"fake-image")
            return True, None

    async def downloader_factory():
        return FakeDownloader()

    class FakeCivitaiClient:
        async def get_image_info(self, image_id, source_url=None):
            return {
                "id": 7076441,
                "url": "https://image.civitai.com/x/original=true/x.jpeg",
                "type": "image",
                "meta": None,
                "modelVersionIds": [138176],
                "browsingLevel": 1,
            }

    async def fake_metadata_provider():
        class Provider:
            async def get_model_version_info(self, version_id):
                if version_id == "138176":
                    return {
                        "id": 138176,
                        "modelId": 15003,
                        "model": {"name": "CyberRealistic", "type": "checkpoint"},
                        "name": "v3.3",
                        "baseModel": "SD 1.5",
                        "files": [
                            {
                                "type": "Model",
                                "primary": True,
                                "name": "cyberrealistic_v33.safetensors",
                                "hashes": {"SHA256": "3c8530cb2239b686d23a94627e29883fe44a1605f31a777727b6709f80d11679"},
                            }
                        ],
                    }, None
                return None, "Model not found"

            async def get_model_by_hash(self, model_hash):
                if model_hash == "e67ebd5e315f":
                    return {
                        "id": 359072,
                        "modelId": 320224,
                        "model": {"name": "Daphne Blake Cosplay (Scooby Doo)", "type": "lora"},
                        "name": "v1.0",
                        "baseModel": "SD 1.5",
                        "downloadUrl": "https://civitai.com/api/download/359072",
                        "files": [
                            {
                                "type": "Model",
                                "primary": True,
                                "name": "Daphne Blake Cosplay_v1.safetensors",
                                "hashes": {"SHA256": LORA_SHA256.upper()},
                            }
                        ],
                    }, None
                return None, "Model not found"

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.automatic.get_default_metadata_provider",
        fake_metadata_provider,
    )

    class DummyScanner:
        async def build_local_hash_cache(self):
            return {}

        async def find_recipes_by_fingerprint(self, fp):
            return []

        async def get_local_lora(self, name, base_model=None):
            return None

        async def get_local_lora_by_hash(self, hash_value):
            return None

    from py.recipes.factory import RecipeParserFactory

    service = RecipeAnalysisService(
        exif_utils=FakeExif(),
        recipe_parser_factory=RecipeParserFactory(),
        downloader_factory=downloader_factory,
        logger=logging.getLogger("test"),
    )

    result = await service.analyze_remote_image(
        url="https://civitai.red/images/7076441",
        recipe_scanner=DummyScanner(),
        civitai_client=FakeCivitaiClient(),
    )
    payload = result.payload

    assert payload.get("error") is None
    loras = payload.get("loras") or []
    assert len(loras) == 1
    assert loras[0]["hash"] == LORA_SHA256
    assert loras[0].get("isDeleted") in (None, False)
    assert "Daphne" in str(payload.get("gen_params", {}).get("prompt"))


# ---------------------------------------------------------------------------
# Checkpoint reconnect chain (manual remediation for recipe.checkpoint)
# ---------------------------------------------------------------------------


def _make_persistence_service():
    return RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )


@pytest.mark.asyncio
async def test_reconnect_checkpoint_distinguishes_ambiguous_mismatched_and_missing(tmp_path):
    service = _make_persistence_service()

    models = [
        {
            "file_name": "realistic.safetensors",
            "folder": "sdxl",
            "file_path": "/models/checkpoints/sdxl/realistic.safetensors",
            "base_model": "SDXL 1.0",
        },
        {
            "file_name": "realistic.safetensors",
            "folder": "sd15",
            "file_path": "/models/checkpoints/sd15/realistic.safetensors",
            "base_model": "SD 1.5",
        },
    ]

    class DummyScanner:
        def __init__(self, recipe_path):
            self._recipe_path = recipe_path

        async def get_recipe_json_path(self, recipe_id):
            return str(self._recipe_path)

        async def find_local_checkpoints_by_name(self, name, base_model=None):
            return ModelScanner.find_matching_models(models, name, base_model=base_model)

    def write_recipe(base_model):
        recipe_path = tmp_path / "recipe.json"
        recipe_path.write_text(
            json.dumps({"id": "r1", "base_model": base_model, "checkpoint": {}})
        )
        return DummyScanner(recipe_path)

    # Ambiguous bare name: two candidates survive (recipe base model unknown)
    scanner = write_recipe("")
    with pytest.raises(RecipeValidationError, match="include the folder path"):
        await service.reconnect_checkpoint(
            recipe_scanner=scanner, recipe_id="r1", target_name="realistic"
        )

    # Confident base-model mismatch: the only candidate belongs to another family
    scanner = write_recipe("SD 1.5")
    with pytest.raises(RecipeValidationError, match="different base model"):
        await service.reconnect_checkpoint(
            recipe_scanner=scanner, recipe_id="r1", target_name="sdxl/realistic"
        )

    # No candidate at all
    scanner = write_recipe("SDXL 1.0")
    with pytest.raises(RecipeNotFoundError, match="not found"):
        await service.reconnect_checkpoint(
            recipe_scanner=scanner, recipe_id="r1", target_name="missing"
        )


@pytest.mark.asyncio
async def test_reconnect_checkpoint_family_compatible_succeeds_with_warning(tmp_path):
    service = _make_persistence_service()

    pony_item = {
        "file_name": "main.safetensors",
        "folder": "",
        "file_path": "/models/checkpoints/main.safetensors",
        "base_model": "Pony",
        "sha256": "ab" * 32,
    }

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps({"id": "r1", "base_model": "Illustrious", "checkpoint": {}})
    )

    class DummyScanner:
        async def get_recipe_json_path(self, recipe_id):
            return str(recipe_path)

        async def find_local_checkpoints_by_name(self, name, base_model=None):
            return [pony_item]

        async def update_checkpoint_entry(self, recipe_id, *, target_name, target_checkpoint):
            assert target_checkpoint is pony_item
            return ({"id": "r1"}, {"file_name": target_checkpoint["file_name"]})

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    result = await service.reconnect_checkpoint(
        recipe_scanner=DummyScanner(), recipe_id="r1", target_name="main"
    )

    assert result.payload["success"] is True
    assert result.payload["base_model_mismatch"] == {
        "recipe_base_model": "Illustrious",
        "checkpoint_base_model": "Pony",
    }


@pytest.mark.asyncio
async def test_reconnect_checkpoint_exact_base_model_has_no_warning(tmp_path):
    service = _make_persistence_service()

    item = {
        "file_name": "main.safetensors",
        "folder": "",
        "file_path": "/models/checkpoints/main.safetensors",
        "base_model": "SDXL 1.0",
        "sha256": "ab" * 32,
    }

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps({"id": "r1", "base_model": "SDXL 1.0", "checkpoint": {}})
    )

    class DummyScanner:
        async def get_recipe_json_path(self, recipe_id):
            return str(recipe_path)

        async def find_local_checkpoints_by_name(self, name, base_model=None):
            return [item]

        async def update_checkpoint_entry(self, recipe_id, *, target_name, target_checkpoint):
            return ({"id": "r1"}, {"file_name": target_checkpoint["file_name"]})

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    result = await service.reconnect_checkpoint(
        recipe_scanner=DummyScanner(), recipe_id="r1", target_name="main"
    )

    assert result.payload["success"] is True
    assert "base_model_mismatch" not in result.payload


@pytest.mark.asyncio
async def test_restore_checkpoint_delegates_and_reports(tmp_path):
    service = _make_persistence_service()

    class DummyScanner:
        async def restore_checkpoint_entry(self, recipe_id):
            assert recipe_id == "r1"
            return (
                {"id": "r1", "checkpoint": {"file_name": "old.safetensors"}},
                {"file_name": "old.safetensors"},
            )

        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    result = await service.restore_checkpoint(
        recipe_scanner=DummyScanner(), recipe_id="r1"
    )

    assert result.payload["success"] is True
    assert result.payload["updated_checkpoint"]["file_name"] == "old.safetensors"


@pytest.mark.asyncio
async def test_get_checkpoint_reconnect_suggestions_loads_entry_and_delegates(tmp_path):
    service = _make_persistence_service()

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "id": "r1",
                "base_model": "SD 1.5",
                "checkpoint": {"file_name": "old.safetensors", "hash": "aaa"},
            }
        )
    )

    class DummyScanner:
        def __init__(self):
            self.calls = []

        async def get_recipe_json_path(self, recipe_id):
            assert recipe_id == "r1"
            return str(recipe_path)

        async def suggest_checkpoint_reconnect_candidates(
            self, *, entry, recipe_base_model, query=None, limit=5
        ):
            self.calls.append(
                {
                    "entry": entry,
                    "recipe_base_model": recipe_base_model,
                    "query": query,
                }
            )
            return [
                {
                    "file_name": "new.safetensors",
                    "score": 1.0,
                    "match_reason": "same_hash",
                    "target_name": "new",
                }
            ]

    scanner = DummyScanner()
    result = await service.get_checkpoint_reconnect_suggestions(
        recipe_scanner=scanner, recipe_id="r1", query="new"
    )

    assert result.payload["success"] is True
    assert result.payload["suggestions"][0]["target_name"] == "new"
    assert scanner.calls == [
        {
            "entry": {"file_name": "old.safetensors", "hash": "aaa"},
            "recipe_base_model": "SD 1.5",
            "query": "new",
        }
    ]


@pytest.mark.asyncio
async def test_get_checkpoint_reconnect_suggestions_validates_recipe(tmp_path):
    service = _make_persistence_service()

    class MissingScanner:
        async def get_recipe_json_path(self, recipe_id):
            return str(tmp_path / "missing.json")

    with pytest.raises(RecipeNotFoundError):
        await service.get_checkpoint_reconnect_suggestions(
            recipe_scanner=MissingScanner(), recipe_id="nope"
        )

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(json.dumps({"id": "r1"}))

    class EmptyScanner:
        async def get_recipe_json_path(self, recipe_id):
            return str(recipe_path)

    with pytest.raises(RecipeValidationError, match="checkpoint"):
        await service.get_checkpoint_reconnect_suggestions(
            recipe_scanner=EmptyScanner(), recipe_id="r1"
        )


@pytest.mark.asyncio
async def test_mark_checkpoint_hash_invalid_delegates_and_reports(tmp_path):
    service = _make_persistence_service()

    class DummyScanner:
        async def set_checkpoint_entry_hash_invalid(self, recipe_id, hash_invalid):
            assert recipe_id == "r1"
            assert hash_invalid is True
            return (
                {"id": "r1", "checkpoint": {"file_name": "m", "hashInvalid": True}},
                {"file_name": "m", "hashInvalid": True},
            )

    result = await service.mark_checkpoint_hash_invalid(
        recipe_scanner=DummyScanner(), recipe_id="r1"
    )

    assert result.payload["success"] is True
    assert result.payload["recipe_id"] == "r1"
    assert result.payload["hash_invalid"] is True
    assert result.payload["updated_checkpoint"]["hashInvalid"] is True


@pytest.mark.asyncio
async def test_mark_checkpoint_hash_invalid_can_clear_flag(tmp_path):
    service = _make_persistence_service()

    class DummyScanner:
        async def set_checkpoint_entry_hash_invalid(self, recipe_id, hash_invalid):
            assert hash_invalid is False
            return (
                {"id": "r1", "checkpoint": {"file_name": "m", "hashInvalid": False}},
                {"file_name": "m", "hashInvalid": False},
            )

    result = await service.mark_checkpoint_hash_invalid(
        recipe_scanner=DummyScanner(),
        recipe_id="r1",
        hash_invalid=False,
    )

    assert result.payload["hash_invalid"] is False
    assert result.payload["updated_checkpoint"]["hashInvalid"] is False


@pytest.mark.asyncio
async def test_analyze_local_image_ignore_recipe_metadata_strips_marker(tmp_path):
    """Re-import must re-parse the original embedded metadata, not the
    recipe JSON block appended on save."""
    original = (
        "masterpiece, best quality\n"
        "Negative prompt: lowres\n"
        "Steps: 20, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 1, "
        "Size: 512x768, Model hash: abc123, Model: foo_v1, Clip skip: 2\n"
        ' Recipe metadata: {"title": "Saved", "loras": [], "gen_params": {}}'
    )

    class SpyFactory:
        def __init__(self):
            self.received = None

        def create_parser(self, metadata):
            self.received = metadata
            return _AutomaticMetadataSpyParser()

    class _AutomaticMetadataSpyParser:
        async def parse_metadata(self, user_comment, recipe_scanner=None, civitai_client=None):
            return {"loras": [], "base_model": "Illustrious", "gen_params": {"seed": 1}}

    class DummyScanner:
        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    image_path = tmp_path / "rec.webp"
    image_path.write_bytes(b"fake-image")

    factory = SpyFactory()
    service = _make_analysis_service(factory, _exif_utils_returning(original))

    result = await service.analyze_local_image(
        file_path=str(image_path),
        recipe_scanner=DummyScanner(),
        ignore_recipe_metadata=True,
    )

    # The parser must receive the original A1111 text without the appended
    # recipe metadata block, so it re-parses rather than reusing the snapshot.
    assert factory.received is not None
    assert "Recipe metadata:" not in factory.received
    assert factory.received.startswith("masterpiece, best quality")
    assert '{"title": "Saved"}' not in factory.received
    assert result.payload["parser"] == "_AutomaticMetadataSpyParser"


@pytest.mark.asyncio
async def test_analyze_local_image_ignore_recipe_metadata_only_marker(tmp_path):
    """An image carrying only the recipe metadata block (no original embedded
    metadata) cannot be re-imported; report it instead of reusing the block."""
    original = 'Recipe metadata: {"title": "Saved", "loras": []}'

    class NeverFactory:
        def create_parser(self, metadata):
            raise AssertionError("Parser must not run on stripped metadata")

    image_path = tmp_path / "rec.webp"
    image_path.write_bytes(b"fake-image")

    service = _make_analysis_service(NeverFactory(), _exif_utils_returning(original))

    result = await service.analyze_local_image(
        file_path=str(image_path),
        recipe_scanner=SimpleNamespace(),
        ignore_recipe_metadata=True,
    )

    assert "error" in result.payload
    assert result.payload["diagnostics"]["reason"] == "only_recipe_metadata"


@pytest.mark.asyncio
async def test_analyze_local_image_default_keeps_recipe_metadata_behavior(tmp_path):
    """Normal import path keeps preferring the recipe metadata block."""
    original = (
        "Steps: 20, Sampler: DPM++ 2M Karras, Seed: 1\n"
        ' Recipe metadata: {"title": "Saved", "loras": [], "gen_params": {}}'
    )

    class SpyFactory:
        def __init__(self):
            self.received = None

        def create_parser(self, metadata):
            self.received = metadata
            return _AutomaticMetadataSpyParser()

    class _AutomaticMetadataSpyParser:
        async def parse_metadata(self, user_comment, recipe_scanner=None, civitai_client=None):
            return {"loras": [], "base_model": "Illustrious", "gen_params": {"seed": 1}}

    class DummyScanner:
        async def find_recipes_by_fingerprint(self, fingerprint):
            return []

    image_path = tmp_path / "rec.webp"
    image_path.write_bytes(b"fake-image")

    factory = SpyFactory()
    service = _make_analysis_service(factory, _exif_utils_returning(original))

    result = await service.analyze_local_image(
        file_path=str(image_path),
        recipe_scanner=DummyScanner(),
    )

    assert factory.received == original
    assert "Recipe metadata:" in factory.received
