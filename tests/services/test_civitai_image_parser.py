import pytest

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

    assert parser.is_metadata_matching(metadata)

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
    assert result["model"]["thumbnailUrl"] == "https://image.civitai.com/checkpoints/width=450,optimized=true"
    assert result["model"]["modelId"] == 111
    assert result["model"]["size"] == 1024 * 1024
    assert result["model"]["hash"] == "ffaa0011"
    assert result["model"]["file_name"] == "Checkpoint Example"

    assert result["loras"]
    assert result["loras"][0]["name"] == "Example Lora Model"
    assert result["loras"][0]["thumbnailUrl"] == "https://image.civitai.com/loras/width=450,optimized=true"
    assert result["loras"][0]["hash"] == "abc123"
