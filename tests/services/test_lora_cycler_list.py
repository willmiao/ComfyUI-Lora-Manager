"""Tests for LoraService.get_cycler_list usage_tips exposure."""

import pytest
from unittest.mock import Mock, AsyncMock

from py.services.lora_service import LoraService


@pytest.fixture
def lora_service():
    """Create a LoraService instance with a mocked scanner cache."""
    scanner = Mock()
    cache_mock = Mock()
    cache_mock.raw_data = [
        {
            "file_name": "with_tips.safetensors",
            "folder": "sub",
            "model_name": "With Tips",
            "usage_tips": '{"strength": 0.6, "strength_min": 0.4, "strength_max": 0.8}',
        },
        {
            "file_name": "empty_tips.safetensors",
            "folder": "",
            "model_name": "Empty Tips",
            "usage_tips": "",
        },
        {
            "file_name": "no_tips.safetensors",
            "folder": "",
            "model_name": "No Tips",
        },
    ]
    scanner.get_cached_data = AsyncMock(return_value=cache_mock)
    return LoraService(scanner)


@pytest.mark.asyncio
async def test_cycler_list_includes_usage_tips_when_present(lora_service):
    loras = await lora_service.get_cycler_list()

    with_tips = next(l for l in loras if l["file_name"] == "sub/with_tips.safetensors")
    assert with_tips["usage_tips"] == (
        '{"strength": 0.6, "strength_min": 0.4, "strength_max": 0.8}'
    )


@pytest.mark.asyncio
async def test_cycler_list_omits_usage_tips_when_empty_or_missing(lora_service):
    loras = await lora_service.get_cycler_list()

    empty_tips = next(l for l in loras if l["file_name"] == "empty_tips.safetensors")
    no_tips = next(l for l in loras if l["file_name"] == "no_tips.safetensors")
    assert "usage_tips" not in empty_tips
    assert "usage_tips" not in no_tips


@pytest.mark.asyncio
async def test_cycler_list_keeps_existing_fields(lora_service):
    loras = await lora_service.get_cycler_list()

    with_tips = next(l for l in loras if l["model_name"] == "With Tips")
    assert with_tips["file_name"] == "sub/with_tips.safetensors"
    assert with_tips["folder"] == "sub"
    assert with_tips["model_name"] == "With Tips"
