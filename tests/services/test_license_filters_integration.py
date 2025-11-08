"""Integration tests for license-based filtering in BaseModelService."""

import pytest
from unittest.mock import Mock, AsyncMock

from py.services.base_model_service import BaseModelService
from py.utils.civitai_utils import build_license_flags
from py.services.model_query import ModelCacheRepository, ModelFilterSet, SearchStrategy, SortParams


class DummyModelService(BaseModelService):
    """Dummy implementation of BaseModelService for testing."""
    
    def __init__(self):
        # Mock the required attributes
        self.model_type = "test"
        self.scanner = Mock()
        self.metadata_class = Mock()
        self.settings = Mock()
        self.update_service = None  # Add the missing attribute
        
        # Mock the cache repository
        self.cache_repository = ModelCacheRepository(self.scanner)
        self.filter_set = ModelFilterSet(self.settings)
        self.search_strategy = SearchStrategy()
        
        # Mock the scanner's get_cached_data to return a mock cache
        self.cache_mock = Mock()
        self.cache_mock.get_sorted_data = AsyncMock(return_value=[])
        
        async def mock_get_cached_data():
            return self.cache_mock
        
        self.scanner.get_cached_data = mock_get_cached_data

    async def format_response(self, model_data: dict) -> dict:
        """Required abstract method implementation."""
        return model_data


@pytest.mark.asyncio
async def test_get_paginated_data_with_license_filters():
    """Test that license filters are applied in get_paginated_data."""
    service = DummyModelService()
    
    # Create test data with different license flags
    test_data = [
        # Model requiring credit AND allowing selling
        {"file_path": "model1.safetensors", "license_flags": build_license_flags({
            "allowNoCredit": False,
            "allowCommercialUse": ["Image"]
        })},
        # Model requiring credit AND not allowing selling
        {"file_path": "model2.safetensors", "license_flags": build_license_flags({
            "allowNoCredit": False,
            "allowCommercialUse": ["Rent"]
        })},
        # Model not requiring credit AND allowing selling
        {"file_path": "model3.safetensors", "license_flags": build_license_flags({
            "allowNoCredit": True,
            "allowCommercialUse": ["Image"]
        })},
        # Model not requiring credit AND not allowing selling
        {"file_path": "model4.safetensors", "license_flags": build_license_flags({
            "allowNoCredit": True,
            "allowCommercialUse": ["Rent"]
        })},
    ]
    
    # Mock the sorted data
    service.cache_mock.get_sorted_data = AsyncMock(return_value=test_data)
    
    # Test with credit_required=True
    result = await service.get_paginated_data(
        page=1, 
        page_size=10, 
        credit_required=True
    )
    assert len(result["items"]) == 2
    file_paths = {item["file_path"] for item in result["items"]}
    assert file_paths == {"model1.safetensors", "model2.safetensors"}
    
    # Test with credit_required=False
    result = await service.get_paginated_data(
        page=1, 
        page_size=10, 
        credit_required=False
    )
    assert len(result["items"]) == 2
    file_paths = {item["file_path"] for item in result["items"]}
    assert file_paths == {"model3.safetensors", "model4.safetensors"}
    
    # Test with allow_selling_generated_content=True
    result = await service.get_paginated_data(
        page=1, 
        page_size=10, 
        allow_selling_generated_content=True
    )
    assert len(result["items"]) == 2
    file_paths = {item["file_path"] for item in result["items"]}
    assert file_paths == {"model1.safetensors", "model3.safetensors"}
    
    # Test with allow_selling_generated_content=False
    result = await service.get_paginated_data(
        page=1, 
        page_size=10, 
        allow_selling_generated_content=False
    )
    assert len(result["items"]) == 2
    file_paths = {item["file_path"] for item in result["items"]}
    assert file_paths == {"model2.safetensors", "model4.safetensors"}
    
    # Test with both filters
    result = await service.get_paginated_data(
        page=1, 
        page_size=10, 
        credit_required=True,
        allow_selling_generated_content=True
    )
    assert len(result["items"]) == 1
    assert result["items"][0]["file_path"] == "model1.safetensors"