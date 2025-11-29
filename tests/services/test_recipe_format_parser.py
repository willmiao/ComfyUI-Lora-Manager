import json
import pytest

from py.recipes.parsers.recipe_format import RecipeFormatParser
from py.config import config


@pytest.mark.asyncio
async def test_recipe_format_parser_populates_checkpoint(monkeypatch):
    checkpoint_info = {
        "id": 777111,
        "modelId": 333222,
        "model": {"name": "Z Image", "type": "checkpoint"},
        "name": "Turbo",
        "images": [{"url": "https://image.civitai.com/checkpoints/original=true"}],
        "baseModel": "sdxl",
        "downloadUrl": "https://civitai.com/api/download/checkpoint",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 2048,
                "name": "Z_Image_Turbo.safetensors",
                "hashes": {"SHA256": "ABC123FF"},
            }
        ],
    }

    async def fake_metadata_provider():
        class Provider:
            async def get_model_version_info(self, version_id):
                assert version_id == "777111"
                return checkpoint_info, None

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.recipe_format.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = RecipeFormatParser()

    recipe_metadata = {
        "title": "Z Recipe",
        "base_model": "",
        "loras": [],
        "gen_params": {"steps": 20},
        "tags": ["test"],
        "checkpoint": {
            "modelVersionId": 777111,
            "modelId": 333222,
            "name": "Z Image",
            "version": "Turbo",
        },
    }

    metadata_text = f"Recipe metadata: {json.dumps(recipe_metadata)}"
    result = await parser.parse_metadata(metadata_text)

    checkpoint = result.get("checkpoint")
    assert checkpoint is not None
    assert checkpoint["name"] == "Z Image"
    assert checkpoint["version"] == "Turbo"
    assert checkpoint["hash"] == "abc123ff"
    assert checkpoint["file_name"] == "Z_Image_Turbo"
    assert result["base_model"] == "sdxl"
    assert result["model"] == checkpoint


@pytest.mark.asyncio
async def test_recipe_format_parser_marks_lora_in_library_by_version(monkeypatch):
    async def fake_metadata_provider():
        class Provider:
            async def get_model_version_info(self, version_id):
                assert version_id == 1244133
                return None, None

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.recipe_format.get_default_metadata_provider",
        fake_metadata_provider,
    )

    cached_entry = {
        "file_path": "/loras/moriimee.safetensors",
        "file_name": "MoriiMee Gothic Niji | LoRA Style",
        "size": 4096,
        "sha256": "abc123",
        "preview_url": "/previews/moriimee.png",
    }

    class FakeCache:
        def __init__(self, entry):
            self.raw_data = [entry]
            self.version_index = {1244133: entry}

    class FakeLoraScanner:
        def __init__(self, entry):
            self._cache = FakeCache(entry)

        def has_hash(self, sha256):
            return False

        async def get_cached_data(self):
            return self._cache

    class FakeRecipeScanner:
        def __init__(self, entry):
            self._lora_scanner = FakeLoraScanner(entry)

    parser = RecipeFormatParser()
    recipe_metadata = {
        "title": "Semi-realism",
        "base_model": "Illustrious",
        "loras": [
            {
                "modelVersionId": 1244133,
                "modelName": "MoriiMee Gothic Niji | LoRA Style",
                "modelVersionName": "V1 Ilustrious",
                "strength": 0.5,
                "hash": "",
            }
        ],
        "gen_params": {"steps": 29},
        "tags": ["woman"],
    }

    metadata_text = f"Recipe metadata: {json.dumps(recipe_metadata)}"
    result = await parser.parse_metadata(
        metadata_text, recipe_scanner=FakeRecipeScanner(cached_entry)
    )

    lora_entry = result["loras"][0]
    assert lora_entry["existsLocally"] is True
    assert lora_entry["inLibrary"] is True
    assert lora_entry["localPath"] == cached_entry["file_path"]
    assert lora_entry["file_name"] == cached_entry["file_name"]
    assert lora_entry["hash"] == cached_entry["sha256"]
    assert lora_entry["size"] == cached_entry["size"]
    assert lora_entry["thumbnailUrl"] == config.get_preview_static_url(
        cached_entry["preview_url"]
    )
