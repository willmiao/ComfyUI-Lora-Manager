"""Tests for utils module case sensitivity handling."""

import pytest
from unittest.mock import Mock

from py.utils.utils import calculate_relative_path_for_model
from py.services.settings_manager import SettingsManager


def test_calculate_relative_path_handles_case_insensitive_tags():
    """Test that calculate_relative_path_for_model handles case insensitive tags correctly."""
    # Create a mock settings manager
    mock_settings = Mock(spec=SettingsManager)
    mock_settings.get.return_value = {}  # base_model_path_mappings
    mock_settings.resolve_priority_tag_for_model.return_value = "test"
    mock_settings.get_download_path_template.return_value = "{base_model}/{first_tag}"
    
    # Mock the settings manager function
    import py.utils.utils as utils_module
    original_get_settings_manager = utils_module.get_settings_manager
    utils_module.get_settings_manager = Mock(return_value=mock_settings)
    
    try:
        # Test model data with mixed case tags
        model_data = {
            "base_model": "SDXL",
            "tags": ["Test", "ANOTHER_TAG"],  # Mixed case tags
            "model_name": "Test Model"
        }
        
        model_type = "lora"
        
        # Call the function
        result = calculate_relative_path_for_model(model_data, model_type)
        
        # Verify that resolve_priority_tag_for_model was called with lowercase tags
        called_args = mock_settings.resolve_priority_tag_for_model.call_args[0]
        lowercase_tags = called_args[0]
        
        # Check that tags are converted to lowercase
        assert all(tag == tag.lower() for tag in lowercase_tags)
        assert "test" in lowercase_tags
        assert "another_tag" in lowercase_tags
        
        # Verify the result format
        assert result == "SDXL/test"
        
    finally:
        # Restore original function
        utils_module.get_settings_manager = original_get_settings_manager