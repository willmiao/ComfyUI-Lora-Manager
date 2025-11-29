import pytest

from py.recipes.parsers.meta_format import MetaFormatParser


@pytest.mark.asyncio
async def test_meta_format_parser_extracts_checkpoint_from_model_hash(monkeypatch):
    checkpoint_info = {
        "id": 222333,
        "modelId": 999888,
        "model": {"name": "Fluxmania V5P", "type": "checkpoint"},
        "name": "v5p",
        "images": [{"url": "https://image.civitai.com/checkpoints/original=true"}],
        "baseModel": "flux",
        "downloadUrl": "https://civitai.com/api/download/checkpoint",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "sizeKB": 1024,
                "name": "Fluxmania_V5P.safetensors",
                "hashes": {"SHA256": "8AE0583B06"},
            }
        ],
    }

    async def fake_metadata_provider():
        class Provider:
            async def get_model_by_hash(self, model_hash):
                assert model_hash == "8ae0583b06"
                return checkpoint_info, None

        return Provider()

    monkeypatch.setattr(
        "py.recipes.parsers.meta_format.get_default_metadata_provider",
        fake_metadata_provider,
    )

    parser = MetaFormatParser()

    metadata_text = (
        "Shimmering metal forms\n"
        "Negative prompt: flat color\n"
        "Steps: 25, Sampler: dpmpp_2m_sgm_uniform, Seed: 471889513588087, "
        "Model: Fluxmania V5P.safetensors, Model hash: 8ae0583b06, VAE: ae.sft, "
        "Lora_0 Model name: ArtVador I.safetensors, Lora_0 Model hash: 08f7133a58, "
        "Lora_0 Strength model: 0.65, Lora_0 Strength clip: 0.65"
    )

    result = await parser.parse_metadata(metadata_text)

    checkpoint = result.get("checkpoint")
    assert checkpoint is not None
    assert checkpoint["hash"] == "8ae0583b06"
    assert checkpoint["name"] == "Fluxmania V5P"
    assert checkpoint["version"] == "v5p"
    assert checkpoint["file_name"] == "Fluxmania_V5P"
    assert result["model"] == checkpoint
    assert result["base_model"] == "flux"
    assert len(result["loras"]) == 1
