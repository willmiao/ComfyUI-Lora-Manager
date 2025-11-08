"""Tests for license-based filtering functionality."""

import pytest
from unittest.mock import Mock, AsyncMock

from py.services.base_model_service import BaseModelService
from py.utils.civitai_utils import build_license_flags


class DummyModelService(BaseModelService):
    """Dummy implementation of BaseModelService for testing."""
    
    def __init__(self):
        # Mock the required attributes
        self.model_type = "test"
        self.scanner = Mock()
        self.metadata_class = Mock()
        self.settings = Mock()
        self.cache_repository = Mock()
        self.filter_set = Mock()
        self.search_strategy = Mock()
        
        # Mock the scanner's get_cached_data to return a mock cache
        async def mock_get_cached_data():
            cache_mock = Mock()
            cache_mock.get_sorted_data = AsyncMock(return_value=[])
            return cache_mock
        
        self.scanner.get_cached_data = mock_get_cached_data

    async def format_response(self, model_data: dict) -> dict:
        """Required abstract method implementation."""
        return model_data


@pytest.mark.asyncio
async def test_credit_required_filter():
    """Test the credit required filtering logic."""
    service = DummyModelService()
    
    # Create test data with different license flags
    test_data = [
        # Model requiring credit (allowNoCredit = False)
        {"file_path": "model1.safetensors", "license_flags": build_license_flags({"allowNoCredit": False})},
        # Model not requiring credit (allowNoCredit = True) 
        {"file_path": "model2.safetensors", "license_flags": build_license_flags({"allowNoCredit": True})},
        # Model with default license flags (allowNoCredit = True by default)
        {"file_path": "model3.safetensors", "license_flags": build_license_flags(None)},
    ]
    
    # Test credit_required=True (should return models that require credit - allowNoCredit=False)
    filtered = await service._apply_credit_required_filter(test_data, credit_required=True)
    assert len(filtered) == 1
    assert filtered[0]["file_path"] == "model1.safetensors"
    
    # Test credit_required=False (should return models that don't require credit - allowNoCredit=True)
    filtered = await service._apply_credit_required_filter(test_data, credit_required=False)
    assert len(filtered) == 2
    file_paths = {item["file_path"] for item in filtered}
    assert file_paths == {"model2.safetensors", "model3.safetensors"}


@pytest.mark.asyncio
async def test_allow_selling_filter():
    """Test the allow selling generated content filtering logic."""
    service = DummyModelService()
    
    # Create test data with different license flags
    test_data = [
        # Model allowing selling (contains Image in allowCommercialUse)
        {"file_path": "model1.safetensors", "license_flags": build_license_flags({"allowCommercialUse": ["Image"]})},
        # Model not allowing selling (doesn't contain Image in allowCommercialUse)
        {"file_path": "model2.safetensors", "license_flags": build_license_flags({"allowCommercialUse": ["RentCivit"]})},
        # Model with default license flags (includes Sell by default, which implies Image)
        {"file_path": "model3.safetensors", "license_flags": build_license_flags(None)},
        # Model allowing selling (contains Sell in allowCommercialUse, which implies Image)
        {"file_path": "model4.safetensors", "license_flags": build_license_flags({"allowCommercialUse": ["Sell"]})},
        # Model with empty allowCommercialUse (doesn't allow selling)
        {"file_path": "model5.safetensors", "license_flags": build_license_flags({"allowCommercialUse": []})},
    ]
    
    # Test allow_selling=True (should return models that allow selling - have Image permission)
    # Default and Sell permissions both include Image, so model3 and model4 will be included
    filtered = await service._apply_allow_selling_filter(test_data, allow_selling=True)
    assert len(filtered) == 3  # model1, model3 (default includes Sell which implies Image), model4
    file_paths = {item["file_path"] for item in filtered}
    assert file_paths == {"model1.safetensors", "model3.safetensors", "model4.safetensors"}
    
    # Test allow_selling=False (should return models that don't allow selling - don't have Image permission)
    filtered = await service._apply_allow_selling_filter(test_data, allow_selling=False)
    assert len(filtered) == 2  # model2 and model5
    file_paths = {item["file_path"] for item in filtered}
    assert file_paths == {"model2.safetensors", "model5.safetensors"}


@pytest.mark.asyncio
async def test_combined_filters():
    """Test combining both credit required and allow selling filters."""
    service = DummyModelService()
    
    # Create test data
    test_data = [
        # Requires credit AND allows selling
        {"file_path": "model1.safetensors", "license_flags": build_license_flags({
            "allowNoCredit": False,
            "allowCommercialUse": ["Image"]
        })},
        # Requires credit AND doesn't allow selling
        {"file_path": "model2.safetensors", "license_flags": build_license_flags({
            "allowNoCredit": False,
            "allowCommercialUse": ["Rent"]
        })},
        # Doesn't require credit AND allows selling
        {"file_path": "model3.safetensors", "license_flags": build_license_flags({
            "allowNoCredit": True,
            "allowCommercialUse": ["Image"]
        })},
        # Doesn't require credit AND doesn't allow selling
        {"file_path": "model4.safetensors", "license_flags": build_license_flags({
            "allowNoCredit": True,
            "allowCommercialUse": ["Rent"]
        })},
    ]
    
    # First apply credit_required=True filter (requires credit)
    filtered = await service._apply_credit_required_filter(test_data, credit_required=True)
    assert len(filtered) == 2
    file_paths = {item["file_path"] for item in filtered}
    assert file_paths == {"model1.safetensors", "model2.safetensors"}
    
    # Then apply allow_selling=True filter (allows selling) to the result
    filtered = await service._apply_allow_selling_filter(filtered, allow_selling=True)
    assert len(filtered) == 1
    assert filtered[0]["file_path"] == "model1.safetensors"
    
    # Test the other combination
    # First apply credit_required=False filter (doesn't require credit)
    filtered = await service._apply_credit_required_filter(test_data, credit_required=False)
    assert len(filtered) == 2
    file_paths = {item["file_path"] for item in filtered}
    assert file_paths == {"model3.safetensors", "model4.safetensors"}
    
    # Then apply allow_selling=False filter (doesn't allow selling) to the result
    filtered = await service._apply_allow_selling_filter(filtered, allow_selling=False)
    assert len(filtered) == 1
    assert filtered[0]["file_path"] == "model4.safetensors"