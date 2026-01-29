"""Tests for model_query sub_type resolution."""

import pytest
from py.services.model_query import (
    _coerce_to_str,
    normalize_sub_type,
    resolve_sub_type,
    FilterCriteria,
    ModelFilterSet,
)


class TestCoerceToStr:
    """Test _coerce_to_str helper."""

    def test_none_returns_none(self):
        assert _coerce_to_str(None) is None

    def test_string_returns_stripped(self):
        assert _coerce_to_str("  test  ") == "test"

    def test_empty_returns_none(self):
        assert _coerce_to_str("   ") is None

    def test_number_converts_to_str(self):
        assert _coerce_to_str(123) == "123"


class TestNormalizeSubType:
    """Test normalize_sub_type function."""

    def test_normalizes_to_lowercase(self):
        assert normalize_sub_type("LoRA") == "lora"
        assert normalize_sub_type("CHECKPOINT") == "checkpoint"

    def test_strips_whitespace(self):
        assert normalize_sub_type("  LoRA  ") == "lora"

    def test_none_returns_none(self):
        assert normalize_sub_type(None) is None

    def test_empty_returns_none(self):
        assert normalize_sub_type("") is None


class TestResolveSubType:
    """Test resolve_sub_type function priority."""

    def test_priority_1_sub_type_field(self):
        """Priority 1: entry['sub_type'] should be used first."""
        entry = {
            "sub_type": "locon",
            "civitai": {"model": {"type": "dora"}},  # Should be ignored
        }
        assert resolve_sub_type(entry) == "locon"

    def test_priority_2_civitai_model_type(self):
        """Priority 2: civitai.model.type as fallback."""
        entry = {
            "civitai": {"model": {"type": "dora"}},
        }
        assert resolve_sub_type(entry) == "dora"

    def test_priority_3_default(self):
        """Priority 3: default to LORA when nothing found."""
        entry = {}
        assert resolve_sub_type(entry) == "LORA"

    def test_empty_sub_type_falls_back(self):
        """Empty sub_type should fall back to civitai type."""
        entry = {
            "sub_type": "",
            "civitai": {"model": {"type": "checkpoint"}},
        }
        assert resolve_sub_type(entry) == "checkpoint"

    def test_whitespace_sub_type_falls_back(self):
        """Whitespace sub_type should fall back to civitai type."""
        entry = {
            "sub_type": "   ",
            "civitai": {"model": {"type": "checkpoint"}},
        }
        assert resolve_sub_type(entry) == "checkpoint"

    def test_none_entry_returns_default(self):
        """None entry should return default."""
        assert resolve_sub_type(None) == "LORA"

    def test_non_mapping_returns_default(self):
        """Non-mapping entry should return default."""
        assert resolve_sub_type("invalid") == "LORA"


class TestModelFilterSetWithSubType:
    """Test ModelFilterSet applies model_types filtering correctly."""

    def create_mock_settings(self):
        class MockSettings:
            def get(self, key, default=None):
                return default
        return MockSettings()

    def test_filter_by_sub_type(self):
        """Filter should work with sub_type field."""
        settings = self.create_mock_settings()
        filter_set = ModelFilterSet(settings)

        data = [
            {"sub_type": "lora", "model_name": "Model 1"},
            {"sub_type": "locon", "model_name": "Model 2"},
            {"sub_type": "dora", "model_name": "Model 3"},
        ]

        criteria = FilterCriteria(model_types=["lora", "locon"])
        result = filter_set.apply(data, criteria)

        assert len(result) == 2
        assert result[0]["model_name"] == "Model 1"
        assert result[1]["model_name"] == "Model 2"

    def test_filter_uses_civitai_type(self):
        """Filter should use civitai.model.type as fallback."""
        settings = self.create_mock_settings()
        filter_set = ModelFilterSet(settings)

        data = [
            {"civitai": {"model": {"type": "dora"}}, "model_name": "Model 1"},
        ]

        criteria = FilterCriteria(model_types=["dora"])
        result = filter_set.apply(data, criteria)

        assert len(result) == 1

    def test_filter_case_insensitive(self):
        """Filter should be case insensitive."""
        settings = self.create_mock_settings()
        filter_set = ModelFilterSet(settings)

        data = [
            {"sub_type": "LoRA", "model_name": "Model 1"},
        ]

        criteria = FilterCriteria(model_types=["lora"])
        result = filter_set.apply(data, criteria)

        assert len(result) == 1

    def test_filter_no_match_returns_empty(self):
        """Filter with no match should return empty list."""
        settings = self.create_mock_settings()
        filter_set = ModelFilterSet(settings)

        data = [
            {"sub_type": "lora", "model_name": "Model 1"},
        ]

        criteria = FilterCriteria(model_types=["checkpoint"])
        result = filter_set.apply(data, criteria)

        assert len(result) == 0
