"""Tests for LoraService pool filtering functionality."""

import pytest
from unittest.mock import Mock, AsyncMock

from py.services.lora_service import LoraService
from py.utils.civitai_utils import build_license_flags


@pytest.fixture
def lora_service():
    """Create a LoraService instance for testing."""
    scanner = Mock()
    cache_mock = Mock()
    cache_mock.raw_data = []
    scanner.get_cached_data = AsyncMock(return_value=cache_mock)
    scanner._hash_index = Mock()
    scanner._hash_index.get_duplicate_hashes = Mock(return_value={})
    scanner._hash_index.get_duplicate_filenames = Mock(return_value={})

    service = LoraService(scanner)
    service.filter_set = Mock()
    service.filter_set.apply = Mock(return_value=None)

    return service


@pytest.fixture
def sample_loras():
    """Sample loras with various license configurations."""
    return [
        {
            "file_name": "credit_required_not_for_selling.safetensors",
            "base_model": "Illustrious",
            "folder": "",
            "license_flags": build_license_flags(
                {"allowNoCredit": False, "allowCommercialUse": ["Rent"]}
            ),
        },
        {
            "file_name": "no_credit_required_for_selling.safetensors",
            "base_model": "Illustrious",
            "folder": "",
            "license_flags": build_license_flags(
                {"allowNoCredit": True, "allowCommercialUse": ["Image"]}
            ),
        },
        {
            "file_name": "credit_required_for_selling.safetensors",
            "base_model": "Illustrious",
            "folder": "",
            "license_flags": build_license_flags(
                {"allowNoCredit": False, "allowCommercialUse": ["Image"]}
            ),
        },
        {
            "file_name": "no_credit_required_not_for_selling.safetensors",
            "base_model": "Illustrious",
            "folder": "",
            "license_flags": build_license_flags(
                {"allowNoCredit": True, "allowCommercialUse": ["Rent"]}
            ),
        },
        {
            "file_name": "default_license.safetensors",
            "base_model": "Illustrious",
            "folder": "",
            "license_flags": build_license_flags(None),
        },
    ]


@pytest.mark.asyncio
async def test_pool_filter_no_credit_required_true(lora_service, sample_loras):
    """Test that no_credit_required=True keeps only models where credit is NOT required."""
    pool_config = {
        "baseModels": [],
        "tags": {"include": [], "exclude": []},
        "folders": {"include": [], "exclude": []},
        "license": {
            "noCreditRequired": True,
            "allowSelling": False,
        },
    }

    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)

    # Should keep models with allowNoCredit=True (bit 0 = 1)
    # Models: no_credit_required_for_selling, no_credit_required_not_for_selling, default_license
    assert len(filtered) == 3
    file_names = {lora["file_name"] for lora in filtered}
    assert file_names == {
        "no_credit_required_for_selling.safetensors",
        "no_credit_required_not_for_selling.safetensors",
        "default_license.safetensors",
    }


@pytest.mark.asyncio
async def test_pool_filter_no_credit_required_false(lora_service, sample_loras):
    """Test that no_credit_required=False keeps all models (no filter applied)."""
    pool_config = {
        "baseModels": [],
        "tags": {"include": [], "exclude": []},
        "folders": {"include": [], "exclude": []},
        "license": {
            "noCreditRequired": False,
            "allowSelling": False,
        },
    }

    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)

    # Should keep all models when no_credit_required=False
    assert len(filtered) == 5


@pytest.mark.asyncio
async def test_pool_filter_allow_selling_true(lora_service, sample_loras):
    """Test that allowSelling=True keeps only models where selling is allowed."""
    pool_config = {
        "baseModels": [],
        "tags": {"include": [], "exclude": []},
        "folders": {"include": [], "exclude": []},
        "license": {
            "noCreditRequired": False,
            "allowSelling": True,
        },
    }

    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)

    # Should keep models with Image permission (allowSelling)
    # Models: no_credit_required_for_selling, credit_required_for_selling, default_license
    assert len(filtered) == 3
    file_names = {lora["file_name"] for lora in filtered}
    assert file_names == {
        "no_credit_required_for_selling.safetensors",
        "credit_required_for_selling.safetensors",
        "default_license.safetensors",
    }


@pytest.mark.asyncio
async def test_pool_filter_allow_selling_false(lora_service, sample_loras):
    """Test that allowSelling=False keeps all models (no filter applied)."""
    pool_config = {
        "baseModels": [],
        "tags": {"include": [], "exclude": []},
        "folders": {"include": [], "exclude": []},
        "license": {
            "noCreditRequired": False,
            "allowSelling": False,
        },
    }

    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)

    # Should keep all models when allowSelling=False
    assert len(filtered) == 5


@pytest.mark.asyncio
async def test_pool_filter_both_license_filters(lora_service, sample_loras):
    """Test combining both no_credit_required and allowSelling filters."""
    pool_config = {
        "baseModels": [],
        "tags": {"include": [], "exclude": []},
        "folders": {"include": [], "exclude": []},
        "license": {
            "noCreditRequired": True,
            "allowSelling": True,
        },
    }

    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)

    # Should keep models where both conditions are met:
    # - allowNoCredit=True (no credit required)
    # - Image permission exists (allow selling)
    # Models: no_credit_required_for_selling, default_license
    assert len(filtered) == 2
    file_names = {lora["file_name"] for lora in filtered}
    assert file_names == {
        "no_credit_required_for_selling.safetensors",
        "default_license.safetensors",
    }


@pytest.mark.asyncio
async def test_pool_filter_base_models(lora_service, sample_loras):
    """Test filtering by base models."""
    pool_config = {
        "baseModels": ["Illustrious"],
        "tags": {"include": [], "exclude": []},
        "folders": {"include": [], "exclude": []},
        "license": {
            "noCreditRequired": False,
            "allowSelling": False,
        },
    }

    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)

    # All sample loras have base_model="Illustrious"
    assert len(filtered) == 5

    # Test with non-matching base model
    pool_config["baseModels"] = ["SD15"]
    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)
    assert len(filtered) == 0


@pytest.mark.asyncio
async def test_pool_filter_folders(lora_service):
    """Test filtering by folders."""
    sample_loras = [
        {
            "file_name": "lora1.safetensors",
            "base_model": "Illustrious",
            "folder": "characters/",
            "license_flags": build_license_flags(None),
        },
        {
            "file_name": "lora2.safetensors",
            "base_model": "Illustrious",
            "folder": "styles/",
            "license_flags": build_license_flags(None),
        },
        {
            "file_name": "lora3.safetensors",
            "base_model": "Illustrious",
            "folder": "concepts/",
            "license_flags": build_license_flags(None),
        },
    ]

    # Test include folders
    pool_config = {
        "baseModels": [],
        "tags": {"include": [], "exclude": []},
        "folders": {"include": ["characters/"], "exclude": []},
        "license": {
            "noCreditRequired": False,
            "allowSelling": False,
        },
    }

    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)
    assert len(filtered) == 1
    assert filtered[0]["file_name"] == "lora1.safetensors"

    # Test exclude folders
    pool_config = {
        "baseModels": [],
        "tags": {"include": [], "exclude": []},
        "folders": {"include": [], "exclude": ["characters/"]},
        "license": {
            "noCreditRequired": False,
            "allowSelling": False,
        },
    }

    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)
    assert len(filtered) == 2
    file_names = {lora["file_name"] for lora in filtered}
    assert file_names == {"lora2.safetensors", "lora3.safetensors"}


@pytest.mark.asyncio
async def test_pool_filter_tags(lora_service):
    """Test filtering by tags."""
    lora_service.filter_set.apply = Mock(side_effect=lambda data, criteria: data)

    sample_loras = [
        {
            "file_name": "lora1.safetensors",
            "base_model": "Illustrious",
            "folder": "",
            "tags": ["anime", "character"],
            "license_flags": build_license_flags(None),
        },
        {
            "file_name": "lora2.safetensors",
            "base_model": "Illustrious",
            "folder": "",
            "tags": ["realistic", "style"],
            "license_flags": build_license_flags(None),
        },
    ]

    pool_config = {
        "baseModels": [],
        "tags": {"include": ["anime"], "exclude": []},
        "folders": {"include": [], "exclude": []},
        "license": {
            "noCreditRequired": False,
            "allowSelling": False,
        },
    }

    filtered = await lora_service._apply_pool_filters(sample_loras, pool_config)

    # Should call filter_set.apply with tag filters
    assert lora_service.filter_set.apply.called
    call_args = lora_service.filter_set.apply.call_args
    assert call_args[0][0] == sample_loras
    assert "anime" in call_args[0][1].tags


@pytest.mark.asyncio
async def test_pool_filter_combined_all_filters(lora_service):
    """Test combining all filter types."""
    test_loras = [
        {
            "file_name": "match_all.safetensors",
            "base_model": "Illustrious",
            "folder": "folder1/",
            "tags": ["tag1"],
            "license_flags": build_license_flags({"allowNoCredit": True}),
        },
        {
            "file_name": "wrong_base_model.safetensors",
            "base_model": "SD15",
            "folder": "folder1/",
            "tags": ["tag1"],
            "license_flags": build_license_flags({"allowNoCredit": True}),
        },
        {
            "file_name": "wrong_folder.safetensors",
            "base_model": "Illustrious",
            "folder": "folder2/",
            "tags": ["tag1"],
            "license_flags": build_license_flags({"allowNoCredit": True}),
        },
        {
            "file_name": "credit_required.safetensors",
            "base_model": "Illustrious",
            "folder": "folder1/",
            "tags": ["tag1"],
            "license_flags": build_license_flags({"allowNoCredit": False}),
        },
    ]

    # Mock tag filter to return all items (simulate tag1 match)
    def mock_tag_filter(data, criteria):
        return data

    lora_service.filter_set.apply = Mock(side_effect=mock_tag_filter)

    pool_config = {
        "baseModels": ["Illustrious"],
        "tags": {"include": ["tag1"], "exclude": []},
        "folders": {"include": ["folder1/"], "exclude": []},
        "license": {
            "noCreditRequired": True,
            "allowSelling": False,
        },
    }

    filtered = await lora_service._apply_pool_filters(test_loras, pool_config)

    # Should apply all filters
    assert lora_service.filter_set.apply.called
    # Only "match_all.safetensors" should match:
    # - base_model: Illustrious ✓
    # - folder: folder1/ ✓
    # - no_credit_required: True ✓ (bit 0 = 1)
    # - tags: tag1 ✓
    assert len(filtered) == 1
    assert filtered[0]["file_name"] == "match_all.safetensors"
