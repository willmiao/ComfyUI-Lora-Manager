"""Tests for preset strength behavior in LoraCyclerLM."""

from unittest.mock import AsyncMock

import pytest

from py.nodes.lora_cycler import LoraCyclerLM
from py.services import service_registry


@pytest.fixture
def cycler_node():
    return LoraCyclerLM()


@pytest.fixture
def cycler_config():
    return {
        "current_index": 1,
        "model_strength": 0.8,
        "clip_strength": 0.6,
        "use_same_clip_strength": False,
        "use_preset_strength": True,
        "preset_strength_scale": 1.5,
        "include_no_lora": False,
    }


@pytest.mark.asyncio
async def test_cycler_uses_scaled_preset_strength_when_available(
    cycler_node, cycler_config, mock_scanner, monkeypatch
):
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    mock_scanner._cache.raw_data = [
        {
            "file_name": "preset_lora.safetensors",
            "file_path": "/models/loras/preset_lora.safetensors",
            "folder": "",
            "usage_tips": '{"strength": 0.7, "clipStrength": 0.5}',
        }
    ]

    result = await cycler_node.cycle(cycler_config)

    assert result["result"][0] == [
        ("/models/loras/preset_lora.safetensors", 1.05, 0.75)
    ]


@pytest.mark.asyncio
async def test_cycler_falls_back_to_manual_strength_when_preset_missing(
    cycler_node, cycler_config, mock_scanner, monkeypatch
):
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    mock_scanner._cache.raw_data = [
        {
            "file_name": "manual_lora.safetensors",
            "file_path": "/models/loras/manual_lora.safetensors",
            "folder": "",
            "usage_tips": "",
        }
    ]

    result = await cycler_node.cycle(cycler_config)

    assert result["result"][0] == [
        ("/models/loras/manual_lora.safetensors", 0.8, 0.6)
    ]


@pytest.mark.asyncio
async def test_cycler_syncs_clip_to_model_when_same_clip_strength_enabled(
    cycler_node, cycler_config, mock_scanner, monkeypatch
):
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    mock_scanner._cache.raw_data = [
        {
            "file_name": "preset_lora.safetensors",
            "file_path": "/models/loras/preset_lora.safetensors",
            "folder": "",
            "usage_tips": '{"strength": 0.7, "clipStrength": 0.3}',
        }
    ]

    result = await cycler_node.cycle(
        {
            **cycler_config,
            "use_same_clip_strength": True,
        }
    )

    assert result["result"][0] == [
        ("/models/loras/preset_lora.safetensors", 1.05, 1.05)
    ]
