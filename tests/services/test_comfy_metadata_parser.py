import pytest
import json
from py.recipes.parsers.comfy import ComfyMetadataParser

@pytest.mark.asyncio
async def test_parse_metadata_without_loras(monkeypatch):
    checkpoint_info = {
        "id": 2224012,
        "modelId": 1908679,
        "model": {"name": "SDXL Checkpoint", "type": "checkpoint"},
        "name": "v1.0",
        "images": [{"url": "https://image.civitai.com/checkpoints/original=true"}],
        "baseModel": "sdxl",
        "downloadUrl": "https://civitai.com/api/download/checkpoint",
    }

    async def fake_metadata_provider():
        class Provider:
            async def get_model_version_info(self, version_id):
                assert version_id == "2224012"
                return checkpoint_info, None
        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.comfy.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = ComfyMetadataParser()

    # User provided metadata
    metadata_json = {
        "resource-stack": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "urn:air:sdxl:checkpoint:civitai:1908679@2224012"}
        },
        "6": {
            "class_type": "smZ CLIPTextEncode",
            "inputs": {"text": "Positive prompt content"},
            "_meta": {"title": "Positive"}
        },
        "7": {
            "class_type": "smZ CLIPTextEncode",
            "inputs": {"text": "Negative prompt content"},
            "_meta": {"title": "Negative"}
        },
        "11": {
            "class_type": "KSampler",
            "inputs": {
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "seed": 904124997,
                "steps": 35,
                "cfg": 6,
                "denoise": 0.1,
                "model": ["resource-stack", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["21", 0]
            },
            "_meta": {"title": "KSampler"}
        },
        "extraMetadata": json.dumps({
            "prompt": "One woman, (solo:1.3), ...",
            "negativePrompt": "lowres, worst quality, ...",
            "steps": 35,
            "cfgScale": 6,
            "sampler": "euler_ancestral",
            "seed": 904124997,
            "width": 1024,
            "height": 1024
        })
    }

    result = await parser.parse_metadata(json.dumps(metadata_json))

    assert "error" not in result
    assert result["loras"] == []
    assert result["checkpoint"] is not None
    assert int(result["checkpoint"]["modelId"]) == 1908679
    assert int(result["checkpoint"]["id"]) == 2224012
    assert result["gen_params"]["prompt"] == "One woman, (solo:1.3), ..."
    assert result["gen_params"]["steps"] == 35
    assert result["gen_params"]["size"] == "1024x1024"
    assert result["from_comfy_metadata"] is True

@pytest.mark.asyncio
async def test_parse_metadata_without_extra_metadata(monkeypatch):
    async def fake_metadata_provider():
        class Provider:
            async def get_model_version_info(self, version_id):
                return {"model": {"name": "Test"}, "id": version_id}, None
        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.comfy.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = ComfyMetadataParser()

    metadata_json = {
        "node_1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "urn:air:sdxl:checkpoint:civitai:123@456"}
        }
    }

    result = await parser.parse_metadata(json.dumps(metadata_json))

    assert "error" not in result
    assert result["loras"] == []
    assert result["checkpoint"]["id"] == "456"
