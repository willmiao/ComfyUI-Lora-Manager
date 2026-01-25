"""Tests for LoraRandomizerLM roll_mode functionality"""

from unittest.mock import AsyncMock

import pytest

from py.nodes.lora_randomizer import LoraRandomizerLM
from py.services import service_registry


@pytest.fixture
def randomizer_node():
    """Create a LoraRandomizerLM instance for testing"""
    return LoraRandomizerLM()


@pytest.fixture
def sample_loras():
    """Sample loras input"""
    return [
        {
            "name": "lora1.safetensors",
            "strength": 0.8,
            "clipStrength": 0.8,
            "active": True,
            "expanded": False,
            "locked": True,
        },
        {
            "name": "lora2.safetensors",
            "strength": 0.6,
            "clipStrength": 0.6,
            "active": True,
            "expanded": False,
            "locked": False,
        },
    ]


@pytest.fixture
def randomizer_config_fixed():
    """Randomizer config with roll_mode='fixed'"""
    return {
        "count_mode": "fixed",
        "count_fixed": 3,
        "count_min": 2,
        "count_max": 5,
        "model_strength_min": 0.5,
        "model_strength_max": 1.0,
        "use_same_clip_strength": True,
        "clip_strength_min": 0.5,
        "clip_strength_max": 1.0,
        "roll_mode": "fixed",
        "use_recommended_strength": False,
        "recommended_strength_scale_min": 0.5,
        "recommended_strength_scale_max": 1.0,
    }


@pytest.fixture
def randomizer_config_always():
    """Randomizer config with roll_mode='always'"""
    return {
        "count_mode": "fixed",
        "count_fixed": 3,
        "count_min": 2,
        "count_max": 5,
        "model_strength_min": 0.5,
        "model_strength_max": 1.0,
        "use_same_clip_strength": True,
        "clip_strength_min": 0.5,
        "clip_strength_max": 1.0,
        "roll_mode": "always",
        "use_recommended_strength": False,
        "recommended_strength_scale_min": 0.5,
        "recommended_strength_scale_max": 1.0,
    }


@pytest.mark.asyncio
async def test_roll_mode_fixed_returns_input_loras(
    randomizer_node, sample_loras, randomizer_config_fixed, mock_scanner, monkeypatch
):
    """Test that fixed mode returns input loras as ui_loras"""
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    mock_scanner._cache.raw_data = [
        {
            "file_name": "new_lora.safetensors",
            "file_path": "/path/to/new_lora.safetensors",
            "folder": "",
        }
    ]

    result = await randomizer_node.randomize(
        randomizer_config_fixed, sample_loras, pool_config=None
    )

    assert "result" in result
    assert "ui" in result
    assert "loras" in result["ui"]
    assert "last_used" in result["ui"]

    ui_loras = result["ui"]["loras"]
    last_used = result["ui"]["last_used"]

    assert ui_loras == sample_loras
    assert last_used == sample_loras


@pytest.mark.asyncio
async def test_roll_mode_always_generates_new_loras(
    randomizer_node, sample_loras, randomizer_config_always, mock_scanner, monkeypatch
):
    """Test that always mode generates new random loras"""
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    mock_scanner._cache.raw_data = [
        {
            "file_name": "random_lora1.safetensors",
            "file_path": "/path/to/random_lora1.safetensors",
            "folder": "",
        },
        {
            "file_name": "random_lora2.safetensors",
            "file_path": "/path/to/random_lora2.safetensors",
            "folder": "",
        },
    ]

    result = await randomizer_node.randomize(
        randomizer_config_always, sample_loras, pool_config=None
    )

    ui_loras = result["ui"]["loras"]
    last_used = result["ui"]["last_used"]

    assert last_used == sample_loras
    assert ui_loras != sample_loras


@pytest.mark.asyncio
async def test_roll_mode_always_preserves_locked_loras(
    randomizer_node, sample_loras, randomizer_config_always, mock_scanner, monkeypatch
):
    """Test that always mode preserves locked loras from input"""
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    mock_scanner._cache.raw_data = [
        {
            "file_name": "random_lora.safetensors",
            "file_path": "/path/to/random_lora.safetensors",
            "folder": "",
        }
    ]

    result = await randomizer_node.randomize(
        randomizer_config_always, sample_loras, pool_config=None
    )

    ui_loras = result["ui"]["loras"]

    locked_lora = next((l for l in ui_loras if l.get("locked")), None)
    assert locked_lora is not None
    assert locked_lora["name"] == "lora1.safetensors"
    assert locked_lora["strength"] == 0.8


@pytest.mark.asyncio
async def test_last_used_always_input_loras(
    randomizer_node, sample_loras, randomizer_config_fixed, mock_scanner, monkeypatch
):
    """Test that last_used is always set to input loras"""
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    mock_scanner._cache.raw_data = [
        {
            "file_name": "new_lora.safetensors",
            "file_path": "/path/to/new_lora.safetensors",
            "folder": "",
        }
    ]

    result = await randomizer_node.randomize(
        randomizer_config_fixed, sample_loras, pool_config=None
    )

    last_used = result["ui"]["last_used"]
    assert last_used == sample_loras


@pytest.mark.asyncio
async def test_execution_stack_built_from_input_loras(
    randomizer_node, sample_loras, randomizer_config_fixed, mock_scanner, monkeypatch
):
    """Test that execution stack is always built from input loras (current user selection)"""
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    mock_scanner._cache.raw_data = [
        {
            "file_name": "lora1.safetensors",
            "file_path": "/path/to/lora1.safetensors",
            "folder": "",
        },
        {
            "file_name": "lora2.safetensors",
            "file_path": "/path/to/lora2.safetensors",
            "folder": "",
        },
    ]

    result = await randomizer_node.randomize(
        randomizer_config_fixed, sample_loras, pool_config=None
    )

    execution_stack = result["result"][0]
    ui_loras = result["ui"]["loras"]

    # execution_stack should be built from input loras (sample_loras)
    assert len(execution_stack) == 2
    assert execution_stack[0][1] == 0.8
    assert execution_stack[0][2] == 0.8
    assert execution_stack[1][1] == 0.6
    assert execution_stack[1][2] == 0.6

    # ui_loras matches input loras in fixed mode
    assert ui_loras == sample_loras


@pytest.mark.asyncio
async def test_roll_mode_default_always(
    randomizer_node, sample_loras, mock_scanner, monkeypatch
):
    """Test that default roll_mode is 'always'"""
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    config_without_roll_mode = {
        "count_mode": "fixed",
        "count_fixed": 3,
    }

    mock_scanner._cache.raw_data = [
        {
            "file_name": "random_lora.safetensors",
            "file_path": "/path/to/random_lora.safetensors",
            "folder": "",
        }
    ]

    result = await randomizer_node.randomize(
        config_without_roll_mode, sample_loras, pool_config=None
    )

    ui_loras = result["ui"]["loras"]
    last_used = result["ui"]["last_used"]
    execution_stack = result["result"][0]

    # last_used should always be input loras
    assert last_used == sample_loras
    # ui_loras should be different (new random loras generated)
    assert ui_loras != sample_loras
    # execution_stack should be built from input loras, not ui_loras
    assert len(execution_stack) == 2
    assert execution_stack[0][1] == 0.8
    assert execution_stack[0][2] == 0.8
    assert execution_stack[1][1] == 0.6
    assert execution_stack[1][2] == 0.6


@pytest.mark.asyncio
async def test_execution_stack_always_from_input_loras_not_ui_loras(
    randomizer_node, sample_loras, randomizer_config_always, mock_scanner, monkeypatch
):
    """Test that execution_stack is always built from input loras, even when ui_loras is different"""
    monkeypatch.setattr(
        service_registry.ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=mock_scanner),
    )

    mock_scanner._cache.raw_data = [
        {
            "file_name": "new_random_lora.safetensors",
            "file_path": "/path/to/new_random_lora.safetensors",
            "folder": "",
        }
    ]

    result = await randomizer_node.randomize(
        randomizer_config_always, sample_loras, pool_config=None
    )

    execution_stack = result["result"][0]
    ui_loras = result["ui"]["loras"]

    # ui_loras should be new random loras
    assert ui_loras != sample_loras
    # execution_stack should be built from input loras (sample_loras), not ui_loras
    assert len(execution_stack) == 2
    assert execution_stack[0][1] == 0.8
    assert execution_stack[0][2] == 0.8
    assert execution_stack[1][1] == 0.6
    assert execution_stack[1][2] == 0.6


@pytest.fixture
def randomizer_config_with_recommended_strength():
    """Randomizer config with recommended strength enabled"""
    return {
        "count_mode": "fixed",
        "count_fixed": 3,
        "count_min": 2,
        "count_max": 5,
        "model_strength_min": 0.5,
        "model_strength_max": 1.0,
        "use_same_clip_strength": True,
        "clip_strength_min": 0.5,
        "clip_strength_max": 1.0,
        "roll_mode": "always",
        "use_recommended_strength": True,
        "recommended_strength_scale_min": 0.6,
        "recommended_strength_scale_max": 0.8,
    }


@pytest.mark.asyncio
async def test_recommended_strength_config_passed_to_service(
    randomizer_node,
    sample_loras,
    randomizer_config_with_recommended_strength,
    mock_scanner,
    monkeypatch,
):
    """Test that recommended strength config is passed to service when enabled"""
    from py.services.lora_service import LoraService
    from unittest.mock import AsyncMock, patch

    # Mock LoraService.get_random_loras to verify parameters
    mock_get_random_loras = AsyncMock(
        return_value=[
            {
                "name": "new_lora.safetensors",
                "strength": 0.7,
                "clipStrength": 0.7,
                "active": True,
                "expanded": False,
                "locked": False,
            }
        ]
    )

    with patch.object(LoraService, "__init__", return_value=None):
        with patch.object(LoraService, "get_random_loras", mock_get_random_loras):
            monkeypatch.setattr(
                service_registry.ServiceRegistry,
                "get_lora_scanner",
                AsyncMock(return_value=mock_scanner),
            )

            mock_scanner._cache.raw_data = [
                {
                    "file_name": "new_lora.safetensors",
                    "file_path": "/path/to/new_lora.safetensors",
                    "folder": "",
                }
            ]

            result = await randomizer_node.randomize(
                randomizer_config_with_recommended_strength,
                sample_loras,
                pool_config=None,
            )

            # Verify service was called
            assert mock_get_random_loras.called

            # Verify recommended strength parameters were passed
            call_kwargs = mock_get_random_loras.call_args[1]
            assert call_kwargs["use_recommended_strength"] is True
            assert call_kwargs["recommended_strength_scale_min"] == 0.6
            assert call_kwargs["recommended_strength_scale_max"] == 0.8
