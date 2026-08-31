import json
from typing import Any, Dict

import pytest

from py.recipes.parsers.recipe_format import RecipeFormatParser
from py.config import config


class _FakeCache:
    def __init__(self, entries, version_index=None):
        self.raw_data = entries
        self.version_index = version_index or {}


class _FakeLoraScanner:
    def __init__(self, entries, version_index=None, has_hash_result=True):
        self._cache = _FakeCache(entries, version_index)
        self._has_hash_result = has_hash_result

    def has_hash(self, sha256):
        return self._has_hash_result

    async def get_cached_data(self):
        return self._cache


class _FakeRecipeScanner:
    def __init__(self, lora_scanner):
        self._lora_scanner = lora_scanner


async def _noop_metadata_provider():
    class Provider:
        async def get_model_version_info(self, version_id):
            return None, None

    return Provider()


def _parse(monkeypatch, recipe_metadata, recipe_scanner):
    monkeypatch.setattr(
        "py.recipes.parsers.recipe_format.get_default_metadata_provider",
        _noop_metadata_provider,
    )
    parser = RecipeFormatParser()
    metadata_text = f"Recipe metadata: {json.dumps(recipe_metadata)}"
    return parser.parse_metadata(metadata_text, recipe_scanner=recipe_scanner)


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
async def test_recipe_format_parser_base_model_defaults_to_none_when_unknown(monkeypatch):
    class _FakeScanner:
        pass

    # No checkpoint and empty base_model -> unknown renders as None (not "")
    result = await _parse(
        monkeypatch,
        {"title": "T", "base_model": "", "loras": [], "gen_params": {}},
        _FakeScanner(),
    )
    assert result["base_model"] is None

    # Missing base_model key behaves the same
    result = await _parse(
        monkeypatch,
        {"title": "T", "loras": [], "gen_params": {}},
        _FakeScanner(),
    )
    assert result["base_model"] is None

    # A real base_model in recipe metadata is kept
    result = await _parse(
        monkeypatch,
        {"title": "T", "base_model": "Illustrious", "loras": [], "gen_params": {}},
        _FakeScanner(),
    )
    assert result["base_model"] == "Illustrious"


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

    cached_entry: Dict[str, Any] = {
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


@pytest.mark.asyncio
async def test_recipe_format_parser_matches_lora_by_autov3_hash(monkeypatch):
    # Cache item is matched by its stored 12-char autov3 hash, even when its
    # full sha256 differs from the recipe hash.
    cached_entry: Dict[str, Any] = {
        "file_path": "/loras/autov3.safetensors",
        "file_name": "AutoV3 LoRA",
        "size": 4096,
        "sha256": "f" * 64,
        "autov3": "AbCdEf123456",
        "preview_url": "/previews/autov3.png",
    }

    recipe_metadata = {
        "title": "Autov3",
        "base_model": "Illustrious",
        "loras": [
            {
                "modelVersionId": 9001,
                "modelName": "AutoV3 LoRA",
                "modelVersionName": "V1",
                "strength": 0.7,
                "hash": "abcdef123456",
            }
        ],
        "gen_params": {"steps": 29},
        "tags": [],
    }

    result = await _parse(
        monkeypatch,
        recipe_metadata,
        recipe_scanner=_FakeRecipeScanner(_FakeLoraScanner([cached_entry])),
    )

    lora_entry = result["loras"][0]
    assert lora_entry["existsLocally"] is True
    assert lora_entry["localPath"] == cached_entry["file_path"]
    assert lora_entry["thumbnailUrl"] == config.get_preview_static_url(
        cached_entry["preview_url"]
    )


@pytest.mark.asyncio
async def test_recipe_format_parser_matches_lora_by_autov2_prefix(monkeypatch):
    # 10-char autov2 recipe hash matches the sha256[:10] prefix of the cache item.
    sha256 = "abcdef0123456789" + "0" * 48
    cached_entry: Dict[str, Any] = {
        "file_path": "/loras/autov2.safetensors",
        "file_name": "AutoV2 LoRA",
        "size": 8192,
        "sha256": sha256,
        "preview_url": "/previews/autov2.png",
    }

    recipe_metadata = {
        "title": "Autov2",
        "base_model": "Illustrious",
        "loras": [
            {
                "modelVersionId": 9002,
                "modelName": "AutoV2 LoRA",
                "modelVersionName": "V1",
                "strength": 0.5,
                "hash": sha256[:10],
            }
        ],
        "gen_params": {"steps": 20},
        "tags": [],
    }

    result = await _parse(
        monkeypatch,
        recipe_metadata,
        recipe_scanner=_FakeRecipeScanner(_FakeLoraScanner([cached_entry])),
    )

    lora_entry = result["loras"][0]
    assert lora_entry["existsLocally"] is True
    assert lora_entry["localPath"] == cached_entry["file_path"]


@pytest.mark.asyncio
async def test_recipe_format_parser_matches_lora_by_full_sha256(monkeypatch):
    # Full 64-char sha256 recipe hash matches exactly as before the cascade change.
    sha256 = "0123456789abcdef" * 4
    cached_entry: Dict[str, Any] = {
        "file_path": "/loras/sha256.safetensors",
        "file_name": "Sha256 LoRA",
        "size": 4096,
        "sha256": sha256,
        "preview_url": "/previews/sha256.png",
    }

    recipe_metadata = {
        "title": "Sha256",
        "base_model": "Illustrious",
        "loras": [
            {
                "modelVersionId": 9003,
                "modelName": "Sha256 LoRA",
                "modelVersionName": "V1",
                "strength": 0.9,
                "hash": sha256.upper(),
            }
        ],
        "gen_params": {"steps": 25},
        "tags": [],
    }

    result = await _parse(
        monkeypatch,
        recipe_metadata,
        recipe_scanner=_FakeRecipeScanner(_FakeLoraScanner([cached_entry])),
    )

    lora_entry = result["loras"][0]
    assert lora_entry["existsLocally"] is True
    assert lora_entry["localPath"] == cached_entry["file_path"]


@pytest.mark.asyncio
async def test_recipe_format_parser_no_hash_match_falls_back_to_version_index(monkeypatch):
    # No hash-form match: falls through to modelVersionId lookup as today.
    version_entry: Dict[str, Any] = {
        "file_path": "/loras/versioned.safetensors",
        "file_name": "Versioned LoRA",
        "size": 4096,
        "sha256": "a" * 64,
        "preview_url": "/previews/versioned.png",
    }
    cache_entry: Dict[str, Any] = {
        "file_path": "/loras/other.safetensors",
        "file_name": "Other LoRA",
        "size": 2048,
        "sha256": "b" * 64,
        "preview_url": "/previews/other.png",
    }

    recipe_metadata = {
        "title": "Versioned",
        "base_model": "Illustrious",
        "loras": [
            {
                "modelVersionId": 9004,
                "modelName": "Versioned LoRA",
                "modelVersionName": "V1",
                "strength": 1.0,
                "hash": "c" * 64,
            }
        ],
        "gen_params": {"steps": 20},
        "tags": [],
    }

    result = await _parse(
        monkeypatch,
        recipe_metadata,
        recipe_scanner=_FakeRecipeScanner(
            _FakeLoraScanner(
                [cache_entry],
                version_index={9004: version_entry},
                has_hash_result=False,
            )
        ),
    )

    lora_entry = result["loras"][0]
    assert lora_entry["existsLocally"] is True
    assert lora_entry["localPath"] == version_entry["file_path"]
    assert lora_entry["file_name"] == version_entry["file_name"]
    assert lora_entry["size"] == version_entry["size"]


@pytest.mark.asyncio
async def test_recipe_format_parser_sha256_less_cache_item_no_keyerror(monkeypatch):
    # A cache item without a sha256 field must not raise KeyError in the lookup.
    cache_entry: Dict[str, Any] = {
        "file_path": "/loras/nohash.safetensors",
        "file_name": "NoHash LoRA",
        "size": 4096,
    }

    recipe_metadata = {
        "title": "NoHash",
        "base_model": "Illustrious",
        "loras": [
            {
                "modelVersionId": 9005,
                "modelName": "NoHash LoRA",
                "modelVersionName": "V1",
                "strength": 1.0,
                "hash": "d" * 64,
            }
        ],
        "gen_params": {"steps": 20},
        "tags": [],
    }

    result = await _parse(
        monkeypatch,
        recipe_metadata,
        recipe_scanner=_FakeRecipeScanner(_FakeLoraScanner([cache_entry])),
    )

    lora_entry = result["loras"][0]
    assert lora_entry["existsLocally"] is False
    assert lora_entry["localPath"] is None
