"""Tests for SuiImageParamsParser."""

import pytest
import json
from py.recipes.parsers import SuiImageParamsParser


class TestSuiImageParamsParser:
    """Test cases for SuiImageParamsParser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = SuiImageParamsParser()

    def test_is_metadata_matching_positive(self):
        """Test that parser correctly identifies SuiImage metadata format."""
        metadata = {
            "sui_image_params": {
                "prompt": "test prompt",
                "model": "test_model"
            }
        }
        metadata_str = json.dumps(metadata)
        assert self.parser.is_metadata_matching(metadata_str) is True

    def test_is_metadata_matching_negative(self):
        """Test that parser rejects non-SuiImage metadata."""
        # Missing sui_image_params key
        metadata = {
            "other_params": {
                "prompt": "test prompt"
            }
        }
        metadata_str = json.dumps(metadata)
        assert self.parser.is_metadata_matching(metadata_str) is False

    def test_is_metadata_matching_invalid_json(self):
        """Test that parser handles invalid JSON gracefully."""
        metadata_str = "not valid json"
        assert self.parser.is_metadata_matching(metadata_str) is False

    @pytest.mark.asyncio
    async def test_parse_metadata_extracts_basic_fields(self):
        """Test parsing basic fields from SuiImage metadata."""
        metadata = {
            "sui_image_params": {
                "prompt": "beautiful landscape",
                "negativeprompt": "ugly, blurry",
                "steps": 30,
                "seed": 12345,
                "cfgscale": 7.5,
                "width": 512,
                "height": 768,
                "sampler": "Euler a",
                "scheduler": "normal"
            },
            "sui_models": [],
            "sui_extra_data": {}
        }
        metadata_str = json.dumps(metadata)
        result = await self.parser.parse_metadata(metadata_str)

        assert result.get('gen_params', {}).get('prompt') == "beautiful landscape"
        assert result.get('gen_params', {}).get('negative_prompt') == "ugly, blurry"
        assert result.get('gen_params', {}).get('steps') == 30
        assert result.get('gen_params', {}).get('seed') == 12345
        assert result.get('gen_params', {}).get('cfg_scale') == 7.5
        assert result.get('gen_params', {}).get('width') == 512
        assert result.get('gen_params', {}).get('height') == 768
        assert result.get('gen_params', {}).get('size') == "512x768"
        assert result.get('loras') == []

    @pytest.mark.asyncio
    async def test_parse_metadata_extracts_checkpoint(self):
        """Test parsing checkpoint from sui_models."""
        metadata = {
            "sui_image_params": {
                "prompt": "test prompt",
                "model": "checkpoint_model"
            },
            "sui_models": [
                {
                    "name": "test_checkpoint.safetensors",
                    "param": "model",
                    "hash": "0x1234567890abcdef"
                }
            ],
            "sui_extra_data": {}
        }
        metadata_str = json.dumps(metadata)
        result = await self.parser.parse_metadata(metadata_str)

        checkpoint = result.get('checkpoint')
        assert checkpoint is not None
        assert checkpoint['type'] == 'checkpoint'
        assert checkpoint['name'] == 'test_checkpoint'
        assert checkpoint['hash'] == '1234567890abcdef'

    @pytest.mark.asyncio
    async def test_parse_metadata_extracts_lora(self):
        """Test parsing LoRA from sui_models."""
        metadata = {
            "sui_image_params": {
                "prompt": "test prompt"
            },
            "sui_models": [
                {
                    "name": "test_lora.safetensors",
                    "param": "lora",
                    "hash": "0xabcdef1234567890"
                }
            ],
            "sui_extra_data": {}
        }
        metadata_str = json.dumps(metadata)
        result = await self.parser.parse_metadata(metadata_str)

        loras = result.get('loras')
        assert len(loras) == 1
        assert loras[0]['type'] == 'lora'
        assert loras[0]['name'] == 'test_lora'
        assert loras[0]['file_name'] == 'test_lora.safetensors'
        assert loras[0]['hash'] == 'abcdef1234567890'

    @pytest.mark.asyncio
    async def test_parse_metadata_handles_lora_in_name(self):
        """Test that LoRA is detected by 'lora' in name."""
        metadata = {
            "sui_image_params": {
                "prompt": "test prompt"
            },
            "sui_models": [
                {
                    "name": "style_lora_v2.safetensors",
                    "param": "some_other_param",
                    "hash": "0x1111111111111111"
                }
            ],
            "sui_extra_data": {}
        }
        metadata_str = json.dumps(metadata)
        result = await self.parser.parse_metadata(metadata_str)

        loras = result.get('loras')
        assert len(loras) == 1
        assert loras[0]['type'] == 'lora'

    @pytest.mark.asyncio
    async def test_parse_metadata_empty_models(self):
        """Test parsing with empty sui_models array."""
        metadata = {
            "sui_image_params": {
                "prompt": "test prompt",
                "steps": 20
            },
            "sui_models": [],
            "sui_extra_data": {
                "date": "2024-01-01"
            }
        }
        metadata_str = json.dumps(metadata)
        result = await self.parser.parse_metadata(metadata_str)

        assert result.get('loras') == []
        assert result.get('checkpoint') is None
        assert result.get('gen_params', {}).get('prompt') == "test prompt"
        assert result.get('gen_params', {}).get('steps') == 20

    @pytest.mark.asyncio
    async def test_parse_metadata_alternative_field_names(self):
        """Test parsing with alternative field names."""
        metadata = {
            "sui_image_params": {
                "prompt": "test prompt",
                "negative_prompt": "bad quality",  # Using underscore variant
                "cfg_scale": 6.0  # Using underscore variant
            },
            "sui_models": [],
            "sui_extra_data": {}
        }
        metadata_str = json.dumps(metadata)
        result = await self.parser.parse_metadata(metadata_str)

        assert result.get('gen_params', {}).get('negative_prompt') == "bad quality"
        assert result.get('gen_params', {}).get('cfg_scale') == 6.0

    @pytest.mark.asyncio
    async def test_parse_metadata_error_handling(self):
        """Test that parser handles malformed data gracefully."""
        # Missing required fields
        metadata = {
            "sui_image_params": {},
            "sui_models": [],
            "sui_extra_data": {}
        }
        metadata_str = json.dumps(metadata)
        result = await self.parser.parse_metadata(metadata_str)

        assert 'error' not in result
        assert result.get('loras') == []
        # Empty params result in empty gen_params dict
        assert result.get('gen_params') == {}
