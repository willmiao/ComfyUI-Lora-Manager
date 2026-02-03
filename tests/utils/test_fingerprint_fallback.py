"""Test for modelVersionId fallback in fingerprint calculation."""
import pytest
from py.utils.utils import calculate_recipe_fingerprint


def test_calculate_fingerprint_with_model_version_id_fallback():
    """Test that fingerprint uses modelVersionId when hash is empty, even when not deleted."""
    loras = [
        {
            "hash": "",
            "strength": 1.0,
            "modelVersionId": 2639467,
            "isDeleted": False,
            "exclude": False
        }
    ]
    fingerprint = calculate_recipe_fingerprint(loras)
    assert fingerprint == "2639467:1.0"


def test_calculate_fingerprint_with_multiple_model_version_ids():
    """Test fingerprint with multiple loras using modelVersionId fallback."""
    loras = [
        {
            "hash": "",
            "strength": 1.0,
            "modelVersionId": 2639467,
            "isDeleted": False,
            "exclude": False
        },
        {
            "hash": "",
            "strength": 0.8,
            "modelVersionId": 1234567,
            "isDeleted": False,
            "exclude": False
        }
    ]
    fingerprint = calculate_recipe_fingerprint(loras)
    assert fingerprint == "1234567:0.8|2639467:1.0"


def test_calculate_fingerprint_with_deleted_lora():
    """Test that deleted loras with modelVersionId are still included."""
    loras = [
        {
            "hash": "",
            "strength": 1.0,
            "modelVersionId": 2639467,
            "isDeleted": True,
            "exclude": False
        }
    ]
    fingerprint = calculate_recipe_fingerprint(loras)
    assert fingerprint == "2639467:1.0"


def test_calculate_fingerprint_with_excluded_lora():
    """Test that excluded loras are skipped even with modelVersionId."""
    loras = [
        {
            "hash": "",
            "strength": 1.0,
            "modelVersionId": 2639467,
            "isDeleted": False,
            "exclude": True
        }
    ]
    fingerprint = calculate_recipe_fingerprint(loras)
    assert fingerprint == ""


def test_calculate_fingerprint_prefers_hash_over_version_id():
    """Test that hash is used even when modelVersionId is present."""
    loras = [
        {
            "hash": "abc123",
            "strength": 1.0,
            "modelVersionId": 2639467,
            "isDeleted": False,
            "exclude": False
        }
    ]
    fingerprint = calculate_recipe_fingerprint(loras)
    assert fingerprint == "abc123:1.0"


def test_calculate_fingerprint_without_hash_or_version_id():
    """Test that loras without hash or modelVersionId are skipped."""
    loras = [
        {
            "hash": "",
            "strength": 1.0,
            "modelVersionId": 0,
            "isDeleted": False,
            "exclude": False
        }
    ]
    fingerprint = calculate_recipe_fingerprint(loras)
    assert fingerprint == ""
