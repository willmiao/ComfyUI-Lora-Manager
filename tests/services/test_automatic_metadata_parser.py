import pytest

from py.recipes.parsers.automatic import AutomaticMetadataParser


@pytest.mark.asyncio
async def test_parse_metadata_extracts_checkpoint_from_civitai_resources(monkeypatch):
    checkpoint_info = {
        "id": 2442439,
        "modelId": 123456,
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
                assert version_id == "2442439"
                return checkpoint_info, None

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.automatic.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = AutomaticMetadataParser()

    metadata_text = (
        "Negative space, fog, BLACK blue color GRADIENT BACKGROUND, a vintage car in the middle, "
        "FOG, and a silhouetted figure near the car, in the style of the Blade Runner movie "
        "Negative prompt: Steps: 23, Sampler: Undefined, CFG scale: 3.5, Seed: 1760020955, "
        "Size: 832x1216, Clip skip: 2, Created Date: 2025-11-28T09:18:43.5269343Z, "
        'Civitai resources: [{"type":"checkpoint","modelVersionId":2442439,"modelName":"Z Image","modelVersionName":"Turbo"}], '
        "Civitai metadata: {}"
    )

    result = await parser.parse_metadata(metadata_text)

    checkpoint = result.get("checkpoint")
    assert checkpoint is not None
    assert checkpoint["name"] == "Z Image"
    assert checkpoint["version"] == "Turbo"
    assert checkpoint["type"] == "checkpoint"
    assert checkpoint["modelId"] == 123456
    assert checkpoint["hash"] == "abc123ff"
    assert checkpoint["file_name"] == "Z_Image_Turbo"
    assert checkpoint["thumbnailUrl"].endswith("width=450,optimized=true")
    assert result["model"] == checkpoint
    assert result["base_model"] == "sdxl"
    assert result["loras"] == []


@pytest.mark.asyncio
async def test_parse_metadata_merges_lora_hashes_over_empty_hashes_json(monkeypatch):
    """When Hashes JSON has empty lora hashes but Lora hashes text field has
    real ones, the real hashes should be used and those LoRAs resolved
    correctly; entries with empty hashes in both sources should be skipped."""
    lora_version_info = {
        "id": 947620,
        "modelId": 98765,
        "model": {"name": "cfg_scale_boost", "type": "LORA"},
        "name": "v1",
        "images": [{"url": "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/original=true"}],
        "baseModel": "illustrious",
        "downloadUrl": "https://civitai.com/api/download/models/947620",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 1024,
                "name": "cfg_scale_boost.safetensors",
                "hashes": {"SHA256": "4605b2de07"},
            }
        ],
    }

    async def fake_metadata_provider():
        class Provider:
            async def get_model_by_hash(self, model_hash):
                assert model_hash == "4605b2de07"
                return lora_version_info, None

            async def get_model_version_info(self, version_id):
                raise AssertionError("get_model_version_info should not be called")

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.automatic.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = AutomaticMetadataParser()

    metadata_text = (
        "a cyberpunk portrait <lora:cfg_scale_boost:0.6>\n"
        "Negative prompt: low quality\n"
        "Steps: 20, Sampler: Euler a, CFG scale: 7, Seed: 123456, Size: 512x768, "
        "Model hash: abc123, Model: test.safetensors, "
        'Lora hashes: "cfg_scale_boost: 4605b2de07, EmptyLora: ", '
        'Hashes: {"model": "abc123", "lora:cfg_scale_boost": "", "lora:EmptyLora": "", "lora:UnusedLora": ""}'
    )

    result = await parser.parse_metadata(metadata_text)

    # cfg_scale_boost should be resolved (hash from Lora hashes overrode empty Hashes JSON)
    loras = result.get("loras", [])
    assert len(loras) == 1, f"Expected 1 LoRA, got {len(loras)}"
    lora = loras[0]
    assert lora["name"] == "cfg_scale_boost", f"Expected cfg_scale_boost, got {lora['name']}"
    assert lora["hash"] == "4605b2de07", f"Expected hash 4605b2de07, got {lora['hash']}"
    assert lora.get("isDeleted") in (None, False), f"LoRA should not be deleted"
    assert lora["weight"] == 0.6, f"Expected weight 0.6, got {lora['weight']}"

    # EmptyLora and UnusedLora should be skipped (no hash in either source)
    lora_names = [l["name"] for l in loras]
    assert "EmptyLora" not in lora_names, "EmptyLora should have been skipped"
    assert "UnusedLora" not in lora_names, "UnusedLora should have been skipped"


@pytest.mark.asyncio
async def test_parse_metadata_extracts_checkpoint_from_model_hash(monkeypatch):
    checkpoint_info = {
        "id": 98765,
        "modelId": 654321,
        "model": {"name": "Flux Illustrious", "type": "checkpoint"},
        "name": "v1",
        "images": [{"url": "https://image.civitai.com/checkpoints/original=true"}],
        "baseModel": "flux",
        "downloadUrl": "https://civitai.com/api/download/checkpoint",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 1024,
                "name": "FluxIllustrious_v1.safetensors",
                "hashes": {"SHA256": "C3688EE04C"},
            }
        ],
    }

    async def fake_metadata_provider():
        class Provider:
            async def get_model_by_hash(self, model_hash):
                assert model_hash == "c3688ee04c"
                return checkpoint_info, None

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.automatic.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = AutomaticMetadataParser()

    metadata_text = (
        "A cyberpunk portrait with neon highlights.\n"
        "Negative prompt: low quality\n"
        "Steps: 20, Sampler: Euler a, CFG scale: 7, Seed: 123456, Size: 832x1216, "
        "Model hash: c3688ee04c, Model: models/waiNSFWIllustrious_v110.safetensors"
    )

    result = await parser.parse_metadata(metadata_text)

    checkpoint = result.get("checkpoint")
    assert checkpoint is not None
    assert checkpoint["hash"] == "c3688ee04c"
    assert checkpoint["name"] == "Flux Illustrious"
    assert checkpoint["version"] == "v1"
    assert checkpoint["file_name"] == "FluxIllustrious_v1"
    assert result["model"] == checkpoint
    assert result["base_model"] == "flux"
    assert result["loras"] == []
