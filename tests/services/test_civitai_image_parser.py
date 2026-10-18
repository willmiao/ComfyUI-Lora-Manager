import pytest

from py.config import config
from py.recipes.base import RecipeMetadataParser
from py.recipes.parsers.civitai_image import CivitaiApiMetadataParser


@pytest.mark.asyncio
async def test_parse_metadata_creates_loras_from_hashes(monkeypatch):
    async def fake_metadata_provider():
        return None

    monkeypatch.setattr(
        "py.recipes.parsers.civitai_image.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = CivitaiApiMetadataParser()

    metadata = {
        "Size": "1536x2688",
        "seed": 3766932689,
        "Model": "indexed_v1",
        "steps": 30,
        "hashes": {
            "model": "692186a14a",
            "LORA:Jedst1": "fb4063c470",
            "LORA:HassaKu_style": "3ce00b926b",
            "LORA:DetailedEyes_V3": "2c1c3f889f",
            "LORA:jiaocha_illustriousXL": "35d3e6f8b0",
            "LORA:绪儿 厚涂构图光影质感增强V3": "d9b5900a59",
        },
        "prompt": "test",
        "Version": "ComfyUI",
        "sampler": "er_sde_ays_30",
        "cfgScale": 5,
        "clipSkip": 2,
        "resources": [
            {
                "hash": "692186a14a",
                "name": "indexed_v1",
                "type": "model",
            }
        ],
        "Model hash": "692186a14a",
        "negativePrompt": "bad",
        "username": "LumaRift",
        "baseModel": "Illustrious",
    }

    result = await parser.parse_metadata(metadata)

    assert result["base_model"] == "Illustrious"
    assert len(result["loras"]) == 5
    assert all(lora["weight"] == 1.0 for lora in result["loras"])
    assert {lora["name"] for lora in result["loras"]} == {
        "Jedst1",
        "HassaKu_style",
        "DetailedEyes_V3",
        "jiaocha_illustriousXL",
        "绪儿 厚涂构图光影质感增强V3",
    }


@pytest.mark.asyncio
async def test_parse_metadata_handles_nested_meta_and_lowercase_hashes(monkeypatch):
    async def fake_metadata_provider():
        return None

    monkeypatch.setattr(
        "py.recipes.parsers.civitai_image.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = CivitaiApiMetadataParser()

    metadata = {
        "id": 106706587,
        "meta": {
            "prompt": "An enigmatic silhouette",
            "hashes": {
                "model": "ee75fd24a4",
                "lora:mj": "de49e1e98c",
                "LORA:Another_Earth_2": "dc11b64a8b",
            },
            "resources": [
                {
                    "hash": "ee75fd24a4",
                    "name": "stoiqoNewrealityFLUXSD35_f1DAlphaTwo",
                    "type": "model",
                }
            ],
        },
    }

    assert parser.is_metadata_matching(metadata)  # pyright: ignore[reportArgumentType]

    result = await parser.parse_metadata(metadata)

    assert result["gen_params"]["prompt"] == "An enigmatic silhouette"
    assert {l["name"] for l in result["loras"]} == {"mj", "Another_Earth_2"}
    assert {l["hash"] for l in result["loras"]} == {"de49e1e98c", "dc11b64a8b"}


@pytest.mark.asyncio
async def test_parse_metadata_populates_checkpoint_and_rewrites_thumbnails(monkeypatch):
    checkpoint_info = {
        "id": 222,
        "modelId": 111,
        "model": {"name": "Checkpoint Example", "type": "checkpoint"},
        "name": "Checkpoint Version",
        "images": [{"url": "https://image.civitai.com/checkpoints/original=true"}],
        "baseModel": "Illustrious",
        "downloadUrl": "https://civitai.com/checkpoint/download",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 1024,
                "name": "Checkpoint Example.safetensors",
                "hashes": {"SHA256": "FFAA0011"},
            }
        ],
    }

    lora_info = {
        "id": 444,
        "modelId": 333,
        "model": {"name": "Example Lora Model", "type": "lora"},
        "name": "Example Lora Version",
        "images": [{"url": "https://image.civitai.com/loras/original=true"}],
        "baseModel": "Illustrious",
        "downloadUrl": "https://civitai.com/lora/download",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 512,
                "hashes": {"SHA256": "abc123"},
            }
        ],
    }

    async def fake_metadata_provider():
        class Provider:
            async def get_model_version_info(self, version_id):
                if version_id == "222":
                    return checkpoint_info, None
                if version_id == "444":
                    return lora_info, None
                return None, "Model not found"

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.civitai_image.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = CivitaiApiMetadataParser()

    metadata = {
        "prompt": "test prompt",
        "negativePrompt": "test negative prompt",
        "civitaiResources": [
            {
                "type": "checkpoint",
                "modelId": 111,
                "modelVersionId": 222,
                "modelName": "Checkpoint Example",
                "modelVersionName": "Checkpoint Version",
            },
            {
                "type": "lora",
                "modelId": 333,
                "modelVersionId": 444,
                "modelName": "Example Lora",
                "modelVersionName": "Lora Version",
                "weight": 0.7,
            },
        ],
    }

    result = await parser.parse_metadata(metadata)

    assert result["model"] is not None
    assert result["model"]["name"] == "Checkpoint Example"
    assert result["model"]["type"] == "checkpoint"
    assert (
        result["model"]["thumbnailUrl"]
        == "https://image.civitai.com/checkpoints/width=450,optimized=true"
    )
    assert result["model"]["modelId"] == 111
    assert result["model"]["size"] == 1024 * 1024
    assert result["model"]["hash"] == "ffaa0011"
    assert result["model"]["file_name"] == "Checkpoint Example"

    assert result["loras"]
    assert result["loras"][0]["name"] == "Example Lora Model"
    assert (
        result["loras"][0]["thumbnailUrl"]
        == "https://image.civitai.com/loras/width=450,optimized=true"
    )
    assert result["loras"][0]["hash"] == "abc123"


@pytest.mark.asyncio
async def test_parse_metadata_handles_modelVersionIds(monkeypatch):
    """Test that modelVersionIds from Civitai image API are properly processed."""
    lora_info_1 = {
        "id": 2398829,
        "modelId": 123456,
        "model": {"name": "Dance LoRA 1", "type": "lora"},
        "name": "Version 1.0",
        "images": [{"url": "https://image.civitai.com/lora1/original=true"}],
        "baseModel": "SDXL",
        "downloadUrl": "https://civitai.com/lora1/download",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 10240,
                "name": "dance_lora_1.safetensors",
                "hashes": {"SHA256": "aabbccdd0011"},
            }
        ],
    }

    lora_info_2 = {
        "id": 2398838,
        "modelId": 123457,
        "model": {"name": "Style LoRA 2", "type": "lora"},
        "name": "Version 2.0",
        "images": [{"url": "https://image.civitai.com/lora2/original=true"}],
        "baseModel": "SDXL",
        "downloadUrl": "https://civitai.com/lora2/download",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 20480,
                "name": "style_lora_2.safetensors",
                "hashes": {"SHA256": "aabbccdd0022"},
            }
        ],
    }

    async def fake_metadata_provider():
        class Provider:
            async def get_model_version_info(self, version_id):
                if version_id == "2398829":
                    return lora_info_1, None
                if version_id == "2398838":
                    return lora_info_2, None
                return None, "Model not found"

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.civitai_image.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = CivitaiApiMetadataParser()

    # This simulates the metadata from Civitai image API where modelVersionIds
    # is at the root level and meta only contains basic prompt info
    metadata = {
        "id": 109882763,
        "meta": {
            "id": 109882763,
            "meta": {"prompt": "A woman does the hip bump dance."},
        },
        "modelVersionIds": [2398829, 2398838],
    }

    assert parser.is_metadata_matching(metadata)  # pyright: ignore[reportArgumentType]

    result = await parser.parse_metadata(metadata)

    # Verify both LoRAs were created from modelVersionIds
    assert len(result["loras"]) == 2

    # Check first LoRA
    lora1 = result["loras"][0]
    assert lora1["id"] == 2398829
    assert lora1["name"] == "Dance LoRA 1"
    assert lora1["type"] == "lora"
    assert lora1["hash"] == "aabbccdd0011"
    assert lora1["baseModel"] == "SDXL"
    assert (
        lora1["thumbnailUrl"]
        == "https://image.civitai.com/lora1/width=450,optimized=true"
    )

    # Check second LoRA
    lora2 = result["loras"][1]
    assert lora2["id"] == 2398838
    assert lora2["name"] == "Style LoRA 2"
    assert lora2["type"] == "lora"
    assert lora2["hash"] == "aabbccdd0022"
    assert lora2["baseModel"] == "SDXL"


@pytest.mark.asyncio
async def test_parse_metadata_extracts_checkpoint_from_resources_model_type(monkeypatch):
    """resources entries with type:"model" should be captured as the checkpoint,
    not skipped (which was the old buggy behavior), and not mixed into loras."""
    captured_hashes = []

    async def fake_metadata_provider():
        class Provider:
            async def get_model_by_hash(self, model_hash):
                captured_hashes.append(model_hash)
                if model_hash == "a1b2c3d4e5":
                    return ({
                        "id": 999,
                        "modelId": 888,
                        "name": "v1.0",
                        "model": {"name": "Real Checkpoint", "type": "Checkpoint"},
                        "baseModel": "SDXL 1.0",
                        "images": [{"url": "https://image.civitai.com/cp/original=true"}],
                        "files": [{"type": "Model", "primary": True, "sizeKB": 1024, "name": "cp.safetensors"}]
                    }, None)
                return None, "Model not found"

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.civitai_image.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = CivitaiApiMetadataParser()

    metadata = {
        "prompt": "test",
        "resources": [
            {"hash": "a1b2c3d4e5", "name": "Real Checkpoint", "type": "model"},
            {"hash": "f6g7h8i9j0", "name": "Some LoRA", "type": "lora", "weight": 0.8},
        ],
        "Model hash": "a1b2c3d4e5",
    }

    result = await parser.parse_metadata(metadata)

    # The type:"model" resource should be in result["model"], not in result["loras"]
    assert result["model"] is not None, "checkpoint model should be extracted"
    assert result["model"]["name"] == "Real Checkpoint"
    assert result["model"]["hash"] == "a1b2c3d4e5"
    assert result["model"]["type"] == "model"

    # The LoRA resource should be in result["loras"]
    assert len(result["loras"]) == 1
    assert result["loras"][0]["name"] == "Some LoRA"

    # The checkpoint hash should have triggered a lookup
    assert "a1b2c3d4e5" in captured_hashes


@pytest.mark.asyncio
async def test_parse_metadata_resources_model_type_does_not_duplicate_checkpoint_in_loras(monkeypatch):
    """When a resources entry has type:"model", it should NOT also appear in loras.
    Regression test for the bug where the checkpoint model appeared in both places."""
    async def fake_metadata_provider():
        class Provider:
            async def get_model_by_hash(self, model_hash):
                if model_hash == "cp123hash":
                    return ({
                        "id": 100,
                        "modelId": 200,
                        "name": "v2",
                        "model": {"name": "My Checkpoint", "type": "Checkpoint"},
                        "baseModel": "SDXL",
                        "files": [{"type": "Model", "primary": True, "sizeKB": 1024, "name": "cp.safetensors"}]
                    }, None)
                if model_hash == "lora1hash":
                    return ({
                        "id": 300,
                        "modelId": 400,
                        "name": "v1",
                        "model": {"name": "Style LoRA", "type": "LORA"},
                        "baseModel": "SDXL",
                        "files": [{"type": "Model", "primary": True, "sizeKB": 512, "name": "style.safetensors"}]
                    }, None)
                return None, "Model not found"

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.civitai_image.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = CivitaiApiMetadataParser()
    metadata = {
        "resources": [
            {"hash": "cp123hash", "name": "My Checkpoint", "type": "model"},
            {"hash": "lora1hash", "name": "Style LoRA", "type": "lora", "weight": 0.5},
        ],
    }

    result = await parser.parse_metadata(metadata)

    # Checkpoint must NOT appear in loras
    lora_names = {l["name"] for l in result["loras"]}
    assert "My Checkpoint" not in lora_names
    assert "Style LoRA" in lora_names

    # Checkpoint must be in result["model"]
    assert result["model"] is not None
    assert result["model"]["name"] == "My Checkpoint"


def _make_lora_civitai_info(hash_value):
    """Build a minimal Civitai response for populate_lora_from_civitai.

    The files entry carries no SHA256 so the entry hash comes from the
    hash_value fallback, letting each test control the hash form (autov3,
    autov2 prefix, or full sha256) directly.
    """
    return {
        "id": 300,
        "modelId": 400,
        "model": {"name": "Style LoRA", "type": "LORA"},
        "name": "v1",
        "images": [{"url": "https://image.civitai.com/lora/original=true"}],
        "baseModel": "SDXL",
        "downloadUrl": "https://civitai.com/api/download/300",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 512,
                "name": "style.safetensors",
                "hashes": {},
            }
        ],
    }


class _FakeCache:
    def __init__(self, entries):
        self.raw_data = entries


class _FakeLoraScanner:
    def __init__(self, cache, local_path):
        self._cache = cache
        self._local_path = local_path

    def has_hash(self, sha256):
        return True

    def get_path_by_hash(self, sha256):
        return self._local_path

    async def get_cached_data(self):
        return self._cache


class _FakeRecipeScanner:
    def __init__(self, lora_scanner):
        self._lora_scanner = lora_scanner


async def _run_backfill(cached_items, hash_value, local_path="/loras/style.safetensors"):
    """Drive populate_lora_from_civitai through the local-exists backfill block."""
    lora_scanner = _FakeLoraScanner(_FakeCache(cached_items), local_path)
    lora_entry = {"file_name": "style"}
    return await RecipeMetadataParser.populate_lora_from_civitai(
        lora_entry,
        _make_lora_civitai_info(hash_value),
        recipe_scanner=_FakeRecipeScanner(lora_scanner),
        hash_value=hash_value,
    )


@pytest.mark.asyncio
async def test_backfill_lora_item_by_file_path():
    # The primary resolution: the cache item's file_path equals the local
    # path resolved by get_path_by_hash, so it is found without hashing.
    autov3_hash = "a1b2c3d4e5f6"
    cached_item = {
        "file_path": "/loras/style.safetensors",
        "file_name": "Style LoRA",
        "preview_url": "/previews/style.png",
    }
    result = await _run_backfill([cached_item], autov3_hash)
    assert result is not None
    assert result["existsLocally"] is True
    assert result["localPath"] == "/loras/style.safetensors"
    assert result["thumbnailUrl"] == config.get_preview_static_url(
        cached_item["preview_url"]
    )


@pytest.mark.asyncio
async def test_backfill_lora_item_by_autov3_hash():
    # 12-char autov3 hash that does NOT match the cache item's sha256,
    # but matches its stored autov3 — would fail with the sha256-only lookup.
    autov3_hash = "a1b2c3d4e5f6"
    cached_item = {
        "file_path": "/loras/style_stored.safetensors",
        "file_name": "Style LoRA",
        "sha256": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "autov3": autov3_hash,
        "preview_url": "/previews/style.png",
    }
    result = await _run_backfill([cached_item], autov3_hash)
    assert result is not None
    assert result["existsLocally"] is True
    assert result["localPath"] == "/loras/style.safetensors"
    assert result["thumbnailUrl"] == config.get_preview_static_url(
        cached_item["preview_url"]
    )


@pytest.mark.asyncio
async def test_backfill_lora_item_by_autov2_prefix():
    # 10-char autov2 hash matches the cache item's sha256 prefix.
    autov2_hash = "0123456789"
    cached_item = {
        "file_path": "/loras/style_stored.safetensors",
        "file_name": "Style LoRA",
        "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "autov3": "",
        "preview_url": "/previews/style.png",
    }
    result = await _run_backfill([cached_item], autov2_hash)
    assert result is not None
    assert result["existsLocally"] is True
    assert result["thumbnailUrl"] == config.get_preview_static_url(
        cached_item["preview_url"]
    )


@pytest.mark.asyncio
async def test_backfill_lora_item_by_full_sha256():
    # Full sha256 hash matches the cache item as before the change.
    sha256_hash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    cached_item = {
        "file_path": "/loras/style_stored.safetensors",
        "file_name": "Style LoRA",
        "sha256": sha256_hash,
        "preview_url": "/previews/style.png",
    }
    result = await _run_backfill([cached_item], sha256_hash)
    assert result is not None
    assert result["existsLocally"] is True
    assert result["thumbnailUrl"] == config.get_preview_static_url(
        cached_item["preview_url"]
    )


@pytest.mark.asyncio
async def test_backfill_lora_cache_item_without_sha256_does_not_crash():
    # Cache item missing the sha256 field: no KeyError, no match, no crash.
    autov3_hash = "a1b2c3d4e5f6"
    cached_item = {
        "file_path": "/loras/unrelated.safetensors",
        "file_name": "Unrelated",
    }
    result = await _run_backfill([cached_item], autov3_hash)
    assert result is not None
    assert result["existsLocally"] is True
    # No match, so thumbnailUrl stays the CivitAI image URL.
    assert result["thumbnailUrl"] != config.get_preview_static_url(
        cached_item.get("preview_url", "/previews/unrelated.png")
    )
    assert result["thumbnailUrl"].startswith("https://image.civitai.com/")


class _RecordingProvider:
    """Metadata provider stub that records get_model_by_hash calls.

    With raise_on_call=True any hash lookup fails the test loudly — used to
    prove that local_cache hits skip the CivitAI API. Otherwise the result
    is returned for the cache-miss path.
    """

    def __init__(self, result=None, raise_on_call=False):
        self.hash_calls = []
        self._result = result
        self._raise_on_call = raise_on_call

    async def get_model_by_hash(self, model_hash):
        self.hash_calls.append(model_hash)
        if self._raise_on_call:
            raise AssertionError(
                f"get_model_by_hash should not be called on local_cache hit, got {model_hash}"
            )
        return self._result

    async def get_model_version_info(self, version_id):
        return None, "Model not found"


def _cache_item(name="Local Style", base_model="SDXL 1.0", model_type="LORA"):
    """Build a scanner cache item shaped like the local hash cache values."""
    return {
        "file_path": f"/loras/{name.lower().replace(' ', '_')}.safetensors",
        "file_name": name,
        "sha256": "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899",
        "autov3": "",
        "preview_url": "/previews/style.png",
        "base_model": base_model,
        "civitai": {
            "id": 300,
            "modelId": 400,
            "name": "v1",
            "model": {"name": name, "type": model_type},
        },
    }


def _make_lora_info(base_model="SDXL 1.0"):
    """Civitai response for a lora hash lookup on the cache-miss path."""
    return {
        "id": 300,
        "modelId": 400,
        "model": {"name": "Style LoRA", "type": "lora"},
        "name": "v1",
        "images": [{"url": "https://image.civitai.com/lora/original=true"}],
        "baseModel": base_model,
        "downloadUrl": "https://civitai.com/api/download/300",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 512,
                "name": "style.safetensors",
                "hashes": {"SHA256": "ff00112233445566778899aabbccddeeff00112233445566778899aabbccddee"},
            }
        ],
    }


async def _parse_with_cache(monkeypatch, provider, metadata, local_cache=None):
    """Run parse_metadata with a fixed metadata provider and optional local_cache."""
    async def fake_metadata_provider():
        return provider

    monkeypatch.setattr(
        "py.recipes.parsers.civitai_image.get_default_metadata_provider",
        fake_metadata_provider,
    )
    parser = CivitaiApiMetadataParser()
    return await parser.parse_metadata(metadata, local_cache=local_cache)


@pytest.mark.asyncio
async def test_local_cache_hashes_section_populates_from_cache_and_skips_api(monkeypatch):
    """Hashes-section lora whose hash is a local_cache key is populated from
    the cache and the metadata provider is never consulted."""
    provider = _RecordingProvider(raise_on_call=True)
    item = _cache_item(name="Local Style", base_model="SDXL 1.0")
    local_cache = {"a1b2c3d4e5f6": item}
    metadata = {"hashes": {"LORA:Local Style": "A1B2C3D4E5F6"}}

    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache=local_cache)

    assert provider.hash_calls == []
    assert len(result["loras"]) == 1
    lora = result["loras"][0]
    assert lora["existsLocally"] is True
    assert lora["localPath"] == item["file_path"]
    assert lora["hash"] == item["sha256"]
    assert lora["name"] == "Local Style"


@pytest.mark.asyncio
async def test_local_cache_lora_n_section_populates_from_cache_and_skips_api(monkeypatch):
    """Lora_N section lora whose hash is a local_cache key is populated from
    the cache and the metadata provider is never consulted."""
    provider = _RecordingProvider(raise_on_call=True)
    item = _cache_item(name="Lora N Style", base_model="SDXL 1.0")
    local_cache = {"abc123def456": item}
    metadata = {
        "Lora_0 Model hash": "ABC123DEF456",
        "Lora_0 Model name": "Lora N Style",
        "Lora_0 Strength model": 0.7,
    }

    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache=local_cache)

    assert provider.hash_calls == []
    assert len(result["loras"]) == 1
    lora = result["loras"][0]
    assert lora["existsLocally"] is True
    assert lora["localPath"] == item["file_path"]
    assert lora["weight"] == 0.7
    assert lora["hash"] == item["sha256"]


@pytest.mark.asyncio
async def test_local_cache_uppercase_hash_matches_lowercase_key(monkeypatch):
    """Resources lora with an UPPERCASE hash still matches the lowercase key."""
    provider = _RecordingProvider(raise_on_call=True)
    sha256 = "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
    item = _cache_item(name="Upper Case", base_model="SDXL 1.0")
    local_cache = {sha256: item}
    metadata = {
        "resources": [
            {"hash": sha256.upper(), "name": "Upper Case", "type": "lora", "weight": 0.5},
        ],
    }

    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache=local_cache)

    assert provider.hash_calls == []
    assert len(result["loras"]) == 1
    assert result["loras"][0]["existsLocally"] is True
    assert result["loras"][0]["hash"] == sha256


@pytest.mark.asyncio
async def test_local_cache_lora_hits_increment_base_model_counts_for_fallback(monkeypatch):
    """When ALL loras hit the cache, base_model_counts is populated so the
    max(counts) fallback still resolves the base model (parity with the API path)."""
    provider = _RecordingProvider(raise_on_call=True)
    item1 = _cache_item(name="Lora One", base_model="SDXL 1.0")
    item2 = _cache_item(name="Lora Two", base_model="SDXL 1.0")
    local_cache = {"hash1111111111": item1, "hash2222222222": item2}
    metadata = {
        "resources": [
            {"hash": "hash1111111111", "name": "Lora One", "type": "lora"},
            {"hash": "hash2222222222", "name": "Lora Two", "type": "lora"},
        ],
    }

    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache=local_cache)

    assert provider.hash_calls == []
    assert len(result["loras"]) == 2
    assert result["base_model"] == "SDXL 1.0"


@pytest.mark.asyncio
async def test_local_cache_checkpoint_hit_does_not_increment_base_model_counts(monkeypatch):
    """Parity pin: a checkpoint cache hit never contributes to base_model_counts.
    Scenario 1 sets result["base_model"] directly (like the API path); scenario 2
    proves a base_model-less checkpoint added nothing to the counts fallback."""
    provider = _RecordingProvider(raise_on_call=True)

    cp_item = _cache_item(name="My Checkpoint", base_model="CP Base", model_type="Checkpoint")
    lora_item = _cache_item(name="Style LoRA", base_model="Lora Base", model_type="LORA")
    metadata1 = {
        "resources": [
            {"hash": "cp1234567890", "name": "My Checkpoint", "type": "model"},
            {"hash": "lora123456789", "name": "Style LoRA", "type": "lora"},
        ],
    }
    result1 = await _parse_with_cache(
        monkeypatch,
        provider,
        metadata1,
        local_cache={"cp1234567890": cp_item, "lora123456789": lora_item},
    )
    assert result1["base_model"] == "CP Base"

    cp_no_bm = _cache_item(name="No Bm Checkpoint", base_model="", model_type="Checkpoint")
    metadata2 = {
        "resources": [
            {"hash": "cp9999999999", "name": "No Bm Checkpoint", "type": "model"},
            {"hash": "lora123456789", "name": "Style LoRA", "type": "lora"},
        ],
    }
    result2 = await _parse_with_cache(
        monkeypatch,
        provider,
        metadata2,
        local_cache={"cp9999999999": cp_no_bm, "lora123456789": lora_item},
    )
    assert result2["base_model"] == "Lora Base"


@pytest.mark.asyncio
async def test_local_cache_type_gate_skips_checkpoint_cache_item_in_lora_section(monkeypatch):
    """A cache item whose civitai.model.type is a checkpoint is skipped in a
    lora section — no entry is appended for it."""
    provider = _RecordingProvider(raise_on_call=True)
    cp_item = _cache_item(name="Disguised Checkpoint", base_model="CP Base", model_type="Checkpoint")
    lora_item = _cache_item(name="Real Lora", base_model="Lora Base", model_type="LORA")
    metadata = {
        "resources": [
            {"hash": "cp1111111111", "name": "Disguised Checkpoint", "type": "lora"},
            {"hash": "lora111111111", "name": "Real Lora", "type": "lora"},
        ],
    }

    result = await _parse_with_cache(
        monkeypatch,
        provider,
        metadata,
        local_cache={"cp1111111111": cp_item, "lora111111111": lora_item},
    )

    assert provider.hash_calls == []
    assert [l["name"] for l in result["loras"]] == ["Real Lora"]


@pytest.mark.asyncio
async def test_local_cache_type_gate_accepts_uppercase_lora_type(monkeypatch):
    """Cache items storing the type as UPPERCASE 'LORA' must not be skipped
    (false-skip guard — stored types are verbatim, VALID_LORA_TYPES is lowercase)."""
    provider = _RecordingProvider(raise_on_call=True)
    item = _cache_item(name="Uppercase Lora", base_model="SDXL 1.0", model_type="LORA")
    local_cache = {"upcasehash12": item}
    metadata = {
        "resources": [
            {"hash": "upcasehash12", "name": "Uppercase Lora", "type": "lora"},
        ],
    }

    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache=local_cache)

    assert provider.hash_calls == []
    assert len(result["loras"]) == 1
    assert result["loras"][0]["existsLocally"] is True


@pytest.mark.asyncio
async def test_local_cache_type_gate_accepts_item_without_civitai_type(monkeypatch):
    """Local-only cache items without civitai type info are treated as valid."""
    provider = _RecordingProvider(raise_on_call=True)
    item = {
        "file_path": "/loras/local_only.safetensors",
        "file_name": "Local Only",
        "sha256": "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
        "preview_url": "/previews/local_only.png",
        "base_model": "SDXL 1.0",
    }
    local_cache = {"localonly123": item}
    metadata = {
        "resources": [
            {"hash": "localonly123", "name": "Local Only", "type": "lora"},
        ],
    }

    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache=local_cache)

    assert provider.hash_calls == []
    assert len(result["loras"]) == 1
    assert result["loras"][0]["existsLocally"] is True


@pytest.mark.asyncio
async def test_local_cache_miss_calls_provider(monkeypatch):
    """A hash absent from local_cache falls through to the provider as before."""
    lora_info = _make_lora_info(base_model="SDXL 1.0")
    provider = _RecordingProvider(result=lora_info)
    metadata = {
        "resources": [
            {"hash": "missedhash123", "name": "Missed LoRA", "type": "lora", "weight": 0.8},
        ],
    }

    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache={})

    assert provider.hash_calls == ["missedhash123"]
    assert len(result["loras"]) == 1
    assert result["loras"][0]["name"] == "Style LoRA"


@pytest.mark.asyncio
async def test_local_cache_dedup_same_hash_produces_one_entry_on_hit(monkeypatch):
    """Repeated same-hash resources produce a single entry on the cache-hit path."""
    provider = _RecordingProvider(raise_on_call=True)
    item = _cache_item(name="Dedup Lora", base_model="SDXL 1.0")
    local_cache = {"deduphash123": item}
    metadata = {
        "resources": [
            {"hash": "deduphash123", "name": "Dedup Lora", "type": "lora"},
            {"hash": "deduphash123", "name": "Dedup Lora", "type": "lora"},
        ],
    }

    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache=local_cache)

    assert provider.hash_calls == []
    assert len(result["loras"]) == 1


@pytest.mark.asyncio
async def test_local_cache_dedup_same_hash_produces_one_entry_on_miss(monkeypatch):
    """Repeated same-hash resources produce a single entry on the cache-miss path."""
    provider = _RecordingProvider(result=_make_lora_info(base_model="SDXL 1.0"))
    metadata = {
        "resources": [
            {"hash": "missdedup123", "name": "Dedup Miss", "type": "lora"},
            {"hash": "missdedup123", "name": "Dedup Miss", "type": "lora"},
        ],
    }

    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache={})

    assert provider.hash_calls == ["missdedup123"]
    assert len(result["loras"]) == 1




@pytest.mark.asyncio
async def test_quote_wrapped_lora_hashes_override_stale_hash(monkeypatch):
    """CivitAI's image API meta parser mangles the A1111 'Lora hashes' text
    field into a quote-wrapped dict entry ('"Daphne Blake Cosplay_v1":
    "e67ebd5e315f"'). The recovered 12-char AutoV3 must override the stale
    10-char value in the hashes dict, so the lora resolves instead of being
    marked deleted."""
    current_sha256 = (
        "533317d3f7d269f9f504bdc432514774d3ada3738ebd80f3f1a37ff848e88276"
    )

    class Provider:
        def __init__(self):
            self.hash_calls = []

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
            self.hash_calls.append(model_hash)
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
                            "hashes": {"SHA256": current_sha256.upper()},
                        }
                    ],
                }, None
            return None, "Model not found"

    metadata = {
        "prompt": "test",
        "steps": 20,
        "sampler": "DPM++ 2M Karras",
        "hashes": {
            "model": "3c8530cb22",
            "lora:Daphne Blake Cosplay_v1": "a2a12bfa01",
        },
        '"Daphne Blake Cosplay_v1': 'e67ebd5e315f"',
        "modelVersionIds": [138176],
        "browsingLevel": 1,
    }

    provider = Provider()
    result = await _parse_with_cache(monkeypatch, provider, metadata, local_cache={})

    assert len(result["loras"]) == 1
    lora = result["loras"][0]
    assert lora["hash"] == current_sha256
    assert lora["id"] == 359072
    assert lora.get("isDeleted") in (None, False)
    assert "e67ebd5e315f" in provider.hash_calls
    assert "a2a12bfa01" not in provider.hash_calls
