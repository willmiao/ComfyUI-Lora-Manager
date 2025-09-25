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

