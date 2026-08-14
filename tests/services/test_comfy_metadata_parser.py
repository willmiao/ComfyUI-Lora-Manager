import pytest
import json
from py.recipes.parsers.comfy import ComfyMetadataParser


class LocalRecipeScanner:
    class LoraScanner:
        @staticmethod
        def has_hash(model_hash):
            return False

    def __init__(self, models):
        self.models = models
        self.queries = []
        self._lora_scanner = self.LoraScanner()

    async def get_local_lora(self, name):
        self.queries.append(name)
        return self.models.get(name)


def local_lora(file_name):
    return {
        "file_path": f"/models/loras/{file_name}.safetensors",
        "file_name": file_name.rsplit("/", 1)[-1],
        "model_name": file_name.rsplit("/", 1)[-1],
        "sha256": file_name[0] * 64,
        "size": 4096,
        "base_model": "SDXL 1.0",
        "preview_url": "",
        "civitai": None,
    }


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
async def test_parse_metadata_resolves_standard_and_manager_local_loras(monkeypatch):
    async def fake_metadata_provider():
        class Provider:
            async def get_model_version_info(self, version_id):
                raise AssertionError("Local LoRAs must not query Civitai")

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.comfy.get_default_metadata_provider",
        fake_metadata_provider,
    )
    scanner = LocalRecipeScanner({
        "styles/standard.safetensors": local_lora("standard"),
        "manager": local_lora("manager"),
    })
    metadata_json = {
        "1": {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "styles/standard.safetensors",
                "strength_model": 0.55,
            },
        },
        "2": {
            "class_type": "LoraLoaderLM",
            "inputs": {
                "loras": {
                    "__value__": [
                        {"name": "manager", "strength": "0.80", "active": True},
                        {"name": "disabled", "strength": 1.0, "active": False},
                        {"name": "dummy", "strength": 1.0, "active": True, "_isDummy": True},
                    ]
                }
            },
        },
    }

    result = await ComfyMetadataParser().parse_metadata(json.dumps(metadata_json), scanner)

    assert [entry["file_name"] for entry in result["loras"]] == ["standard", "manager"]
    assert [entry["weight"] for entry in result["loras"]] == [0.55, 0.8]
    assert all(isinstance(entry["weight"], float) for entry in result["loras"])
    assert all(entry["existsLocally"] is True for entry in result["loras"])
    assert all(entry["isDeleted"] is False for entry in result["loras"])
    assert scanner.queries == ["styles/standard.safetensors", "manager"]


@pytest.mark.asyncio
async def test_parse_metadata_keeps_civitai_urn_with_local_lora(monkeypatch):
    remote_info = {
        "id": 456,
        "modelId": 123,
        "model": {"name": "Remote LoRA", "type": "LORA"},
        "name": "v1",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "name": "remote.safetensors",
                "hashes": {"SHA256": "c" * 64},
            }
        ],
    }

    async def fake_metadata_provider():
        class Provider:
            async def get_model_version_info(self, version_id):
                assert version_id == "456"
                return remote_info, None

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.comfy.get_default_metadata_provider",
        fake_metadata_provider,
    )
    scanner = LocalRecipeScanner({"local": local_lora("local")})
    metadata_json = {
        "1": {
            "class_type": "LoraLoader",
            "inputs": {"lora_name": "local", "strength_model": 0.4},
        },
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "urn:air:sdxl:lora:civitai:123@456",
                "strength_model": 0.9,
            },
        },
    }

    result = await ComfyMetadataParser().parse_metadata(json.dumps(metadata_json), scanner)

    assert [entry["name"] for entry in result["loras"]] == ["local", "Remote LoRA"]
    assert [entry["weight"] for entry in result["loras"]] == [0.4, 0.9]
    assert result["loras"][0]["existsLocally"] is True
    assert result["loras"][1]["id"] == 456


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
