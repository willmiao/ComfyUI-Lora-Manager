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
