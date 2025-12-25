"""Tests for the LoraCycler and LoraRandomizer nodes."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import copy

from py.nodes.lora_cycler import LoraCycler, LoraRandomizer, _execution_counters


# Sample LoRA data for testing
SAMPLE_LORA_DATA = [
    {
        'file_name': 'lora_alpha',
        'model_name': 'LoRA Alpha',
        'file_path': '/loras/folder1/lora_alpha.safetensors',
        'folder': 'folder1',
        'base_model': 'SDXL 1.0',
        'tags': ['character', 'anime'],
        'civitai': {'trainedWords': ['alpha_trigger', 'character_alpha']},
        'exclude': False,
    },
    {
        'file_name': 'lora_beta',
        'model_name': 'LoRA Beta',
        'file_path': '/loras/folder1/lora_beta.safetensors',
        'folder': 'folder1',
        'base_model': 'SDXL 1.0',
        'tags': ['style'],
        'civitai': {'trainedWords': ['beta_style']},
        'exclude': False,
    },
    {
        'file_name': 'lora_gamma',
        'model_name': 'LoRA Gamma',
        'file_path': '/loras/folder2/lora_gamma.safetensors',
        'folder': 'folder2',
        'base_model': 'Pony',
        'tags': ['character', 'pony'],
        'civitai': {'trainedWords': ['gamma_pony']},
        'exclude': False,
    },
    {
        'file_name': 'excluded_lora',
        'model_name': 'Excluded LoRA',
        'file_path': '/loras/folder1/excluded.safetensors',
        'folder': 'folder1',
        'base_model': 'SDXL 1.0',
        'tags': [],
        'civitai': {},
        'exclude': True,  # Should be filtered out
    },
]


class _DummyLoraScanner:
    """Mock LoRA scanner for testing."""

    def __init__(self, data):
        self._data = data

    async def get_cached_data(self):
        mock_cache = MagicMock()
        mock_cache.raw_data = self._data
        return mock_cache

    def clone(self):
        """Return a copy of this scanner for isolated testing."""
        return _DummyLoraScanner(copy.deepcopy(self._data))


@pytest.fixture
def mock_scanner():
    """Fixture to provide mock LoRA scanner."""
    return _DummyLoraScanner(SAMPLE_LORA_DATA)


@pytest.fixture
def mock_config():
    """Fixture to mock config with lora roots."""
    with patch('py.nodes.lora_cycler.config') as mock:
        mock.loras_roots = ['/loras']
        yield mock


@pytest.fixture(autouse=True)
def reset_counters():
    """Reset execution counters before each test."""
    _execution_counters.clear()
    yield
    _execution_counters.clear()


def test_lora_cycler_node_registration():
    """Test that LoraCycler has correct node metadata."""
    assert LoraCycler.NAME == "Lora Cycler (LoraManager)"
    assert LoraCycler.CATEGORY == "Lora Manager/utils"
    assert "LORA_STACK" in LoraCycler.RETURN_TYPES
    assert "trigger_words" in LoraCycler.RETURN_NAMES


def test_lora_randomizer_node_registration():
    """Test that LoraRandomizer has correct node metadata."""
    assert LoraRandomizer.NAME == "Lora Randomizer (LoraManager)"
    input_types = LoraRandomizer.INPUT_TYPES()
    # Random should be the first/default option
    assert input_types["required"]["selection_mode"][0][0] == "random"


def test_lora_cycler_input_types():
    """Test that input types are correctly defined."""
    input_types = LoraCycler.INPUT_TYPES()

    assert "required" in input_types
    assert "optional" in input_types

    required = input_types["required"]
    assert "selection_mode" in required
    assert "index" in required
    assert "seed" in required
    assert "model_strength" in required
    assert "clip_strength" in required

    optional = input_types["optional"]
    assert "folder_filter" in optional
    assert "base_model_filter" in optional
    assert "tag_filter" in optional
    assert "name_filter" in optional
    assert "lora_stack" in optional


def test_is_changed_fixed_mode():
    """Test that IS_CHANGED returns consistent value for fixed mode."""
    result1 = LoraCycler.IS_CHANGED(
        selection_mode="fixed",
        index=0,
        seed=0,
        model_strength=1.0,
        clip_strength=1.0,
    )
    result2 = LoraCycler.IS_CHANGED(
        selection_mode="fixed",
        index=0,
        seed=0,
        model_strength=1.0,
        clip_strength=1.0,
    )
    assert result1 == result2


def test_is_changed_fixed_mode_changes_with_index():
    """Test that IS_CHANGED changes when index changes for fixed mode."""
    result1 = LoraCycler.IS_CHANGED(
        selection_mode="fixed",
        index=0,
        seed=0,
        model_strength=1.0,
        clip_strength=1.0,
    )
    result2 = LoraCycler.IS_CHANGED(
        selection_mode="fixed",
        index=1,
        seed=0,
        model_strength=1.0,
        clip_strength=1.0,
    )
    assert result1 != result2


def test_is_changed_random_with_seed_zero():
    """Test that IS_CHANGED returns NaN for random mode with seed 0."""
    import math

    result = LoraCycler.IS_CHANGED(
        selection_mode="random",
        index=0,
        seed=0,
        model_strength=1.0,
        clip_strength=1.0,
    )
    # NaN is never equal to itself
    assert math.isnan(result)


def test_is_changed_random_with_specific_seed():
    """Test that IS_CHANGED returns consistent value for random mode with specific seed."""
    result1 = LoraCycler.IS_CHANGED(
        selection_mode="random",
        index=0,
        seed=12345,
        model_strength=1.0,
        clip_strength=1.0,
    )
    result2 = LoraCycler.IS_CHANGED(
        selection_mode="random",
        index=0,
        seed=12345,
        model_strength=1.0,
        clip_strength=1.0,
    )
    assert result1 == result2 == 12345


def test_cycle_loras_with_lora_stack_input(mock_config):
    """Test cycling with a pre-defined lora_stack input."""
    node = LoraCycler()

    # Provide a lora_stack directly
    input_stack = [
        ('folder1/lora_alpha.safetensors', 0.8, 0.9),
        ('folder2/lora_beta.safetensors', 1.0, 1.0),
    ]

    # Mock get_lora_info to return trigger words
    with patch('py.nodes.lora_cycler.get_lora_info') as mock_info:
        mock_info.side_effect = lambda name: (
            f'{name}.safetensors',
            [f'{name}_trigger']
        )

        result = node.cycle_loras(
            selection_mode="fixed",
            index=0,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="test_node_1",
        )

        output_stack, trigger_words, selected_lora, total_count, current_index = result

        assert total_count == 2
        assert current_index == 0
        assert len(output_stack) == 1
        # First lora should be selected
        assert "lora_alpha" in selected_lora


def test_cycle_loras_increment_mode():
    """Test that increment mode advances through LoRAs."""
    node = LoraCycler()

    # Create mock input stack
    input_stack = [
        ('lora_a.safetensors', 1.0, 1.0),
        ('lora_b.safetensors', 1.0, 1.0),
        ('lora_c.safetensors', 1.0, 1.0),
    ]

    with patch('py.nodes.lora_cycler.get_lora_info') as mock_info:
        mock_info.side_effect = lambda name: (f'{name}.safetensors', [])

        # First execution
        _, _, _, _, idx1 = node.cycle_loras(
            selection_mode="increment",
            index=0,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="increment_test",
        )

        # Second execution
        _, _, _, _, idx2 = node.cycle_loras(
            selection_mode="increment",
            index=0,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="increment_test",
        )

        # Third execution
        _, _, _, _, idx3 = node.cycle_loras(
            selection_mode="increment",
            index=0,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="increment_test",
        )

        # Fourth execution (should wrap)
        _, _, _, _, idx4 = node.cycle_loras(
            selection_mode="increment",
            index=0,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="increment_test",
        )

        assert idx1 == 0
        assert idx2 == 1
        assert idx3 == 2
        assert idx4 == 0  # Wrapped back to start


def test_cycle_loras_decrement_mode():
    """Test that decrement mode goes backwards through LoRAs."""
    node = LoraCycler()

    input_stack = [
        ('lora_a.safetensors', 1.0, 1.0),
        ('lora_b.safetensors', 1.0, 1.0),
        ('lora_c.safetensors', 1.0, 1.0),
    ]

    with patch('py.nodes.lora_cycler.get_lora_info') as mock_info:
        mock_info.side_effect = lambda name: (f'{name}.safetensors', [])

        # Start at index 2
        _execution_counters["decrement_test"] = 2

        # First execution
        _, _, _, _, idx1 = node.cycle_loras(
            selection_mode="decrement",
            index=2,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="decrement_test",
        )

        # Second execution
        _, _, _, _, idx2 = node.cycle_loras(
            selection_mode="decrement",
            index=2,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="decrement_test",
        )

        # Third execution
        _, _, _, _, idx3 = node.cycle_loras(
            selection_mode="decrement",
            index=2,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="decrement_test",
        )

        assert idx1 == 1  # Decremented from 2 to 1
        assert idx2 == 0
        assert idx3 == 2  # Wrapped to end


def test_cycle_loras_random_with_seed():
    """Test that random mode with specific seed produces consistent results."""
    node = LoraCycler()

    input_stack = [
        ('lora_a.safetensors', 1.0, 1.0),
        ('lora_b.safetensors', 1.0, 1.0),
        ('lora_c.safetensors', 1.0, 1.0),
        ('lora_d.safetensors', 1.0, 1.0),
    ]

    with patch('py.nodes.lora_cycler.get_lora_info') as mock_info:
        mock_info.side_effect = lambda name: (f'{name}.safetensors', [])

        # Same seed should produce same result
        _, _, _, _, idx1 = node.cycle_loras(
            selection_mode="random",
            index=0,
            seed=42,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="random_test_1",
        )

        _, _, _, _, idx2 = node.cycle_loras(
            selection_mode="random",
            index=0,
            seed=42,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="random_test_2",
        )

        assert idx1 == idx2


def test_cycle_loras_trigger_words_output():
    """Test that trigger words are correctly output for selected LoRA."""
    node = LoraCycler()

    input_stack = [
        ('lora_alpha.safetensors', 1.0, 1.0),
        ('lora_beta.safetensors', 1.0, 1.0),
    ]

    with patch('py.nodes.lora_cycler.get_lora_info') as mock_info:
        def mock_get_info(name):
            if 'alpha' in name:
                return (f'{name}.safetensors', ['alpha_word1', 'alpha_word2'])
            return (f'{name}.safetensors', ['beta_word'])

        mock_info.side_effect = mock_get_info

        _, trigger_words, _, _, _ = node.cycle_loras(
            selection_mode="fixed",
            index=0,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=input_stack,
            unique_id="trigger_test",
        )

        # Should use ',, ' separator for group mode compatibility
        assert 'alpha_word1' in trigger_words
        assert 'alpha_word2' in trigger_words
        assert ',, ' in trigger_words


def test_cycle_loras_strength_output():
    """Test that strength values are correctly included in output."""
    node = LoraCycler()

    input_stack = [
        ('lora_test.safetensors', 1.0, 1.0),
    ]

    with patch('py.nodes.lora_cycler.get_lora_info') as mock_info:
        mock_info.return_value = ('lora_test.safetensors', [])

        # Same strength
        _, _, selected_lora, _, _ = node.cycle_loras(
            selection_mode="fixed",
            index=0,
            seed=0,
            model_strength=0.8,
            clip_strength=0.8,
            lora_stack=input_stack,
            unique_id="strength_test_1",
        )
        assert ':0.8>' in selected_lora
        assert ':0.8:0.8>' not in selected_lora  # Should not duplicate

        # Different strengths
        _, _, selected_lora, _, _ = node.cycle_loras(
            selection_mode="fixed",
            index=0,
            seed=0,
            model_strength=0.8,
            clip_strength=0.6,
            lora_stack=input_stack,
            unique_id="strength_test_2",
        )
        assert ':0.8:0.6>' in selected_lora


def test_cycle_loras_empty_list():
    """Test behavior with empty LoRA list."""
    node = LoraCycler()

    with patch('py.nodes.lora_cycler.get_lora_info') as mock_info:
        mock_info.return_value = ('', [])

        result = node.cycle_loras(
            selection_mode="fixed",
            index=0,
            seed=0,
            model_strength=1.0,
            clip_strength=1.0,
            lora_stack=[],
            unique_id="empty_test",
        )

        output_stack, trigger_words, selected_lora, total_count, current_index = result

        assert total_count == 0
        assert output_stack == []
        assert trigger_words == ""
        assert selected_lora == ""


def test_lora_stack_output_format():
    """Test that LORA_STACK output has correct format."""
    node = LoraCycler()

    input_stack = [
        ('folder/lora_test.safetensors', 1.0, 1.0),
    ]

    with patch('py.nodes.lora_cycler.get_lora_info') as mock_info:
        mock_info.return_value = ('folder/lora_test.safetensors', [])

        output_stack, _, _, _, _ = node.cycle_loras(
            selection_mode="fixed",
            index=0,
            seed=0,
            model_strength=0.75,
            clip_strength=0.85,
            lora_stack=input_stack,
            unique_id="format_test",
        )

        # Should be a list with one tuple
        assert len(output_stack) == 1
        path, model_str, clip_str = output_stack[0]
        assert 'lora_test' in path
        assert model_str == 0.75
        assert clip_str == 0.85
