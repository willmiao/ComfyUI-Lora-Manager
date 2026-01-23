"""Tests for RecipeFTSIndex validation methods."""

import os
import tempfile
from typing import Dict, List

import pytest

from py.services.recipe_fts_index import RecipeFTSIndex


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)
    for suffix in ["-wal", "-shm"]:
        wal_path = path + suffix
        if os.path.exists(wal_path):
            os.unlink(wal_path)


@pytest.fixture
def sample_recipes() -> List[Dict]:
    """Create sample recipe data for FTS indexing."""
    return [
        {
            "id": "recipe-001",
            "title": "Anime Character Portrait",
            "tags": ["anime", "portrait", "character"],
            "loras": [
                {"file_name": "anime_style", "modelName": "Anime Style LoRA"},
                {"file_name": "character_v2", "modelName": "Character Design V2"},
            ],
            "gen_params": {
                "prompt": "masterpiece, best quality, 1girl",
                "negative_prompt": "bad quality, worst quality",
            },
        },
        {
            "id": "recipe-002",
            "title": "Landscape Photography",
            "tags": ["landscape", "photography", "nature"],
            "loras": [
                {"file_name": "landscape_lora", "modelName": "Landscape Enhancement"},
            ],
            "gen_params": {
                "prompt": "beautiful landscape, mountains, sunset",
                "negative_prompt": "ugly, blurry",
            },
        },
        {
            "id": "recipe-003",
            "title": "Fantasy Art Scene",
            "tags": ["fantasy", "art"],
            "loras": [],
            "gen_params": {
                "prompt": "fantasy world, dragons, magic",
            },
        },
    ]


class TestFTSIndexValidation:
    """Tests for FTS index validation methods."""

    def test_validate_index_empty_returns_false(self, temp_db_path):
        """Test that validation fails on empty index."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.initialize()

        # Empty index should not validate against non-empty recipe set
        result = fts.validate_index(3, {"recipe-001", "recipe-002", "recipe-003"})
        assert result is False

    def test_validate_index_count_mismatch(self, temp_db_path, sample_recipes):
        """Test validation fails when counts don't match."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.build_index(sample_recipes)

        # Validate with wrong count
        result = fts.validate_index(5, {"recipe-001", "recipe-002", "recipe-003"})
        assert result is False

    def test_validate_index_id_mismatch(self, temp_db_path, sample_recipes):
        """Test validation fails when IDs don't match."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.build_index(sample_recipes)

        # Validate with wrong IDs
        result = fts.validate_index(3, {"recipe-001", "recipe-002", "recipe-999"})
        assert result is False

    def test_validate_index_success(self, temp_db_path, sample_recipes):
        """Test successful validation."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.build_index(sample_recipes)

        # Validate with correct count and IDs
        result = fts.validate_index(3, {"recipe-001", "recipe-002", "recipe-003"})
        assert result is True

    def test_get_indexed_recipe_ids(self, temp_db_path, sample_recipes):
        """Test getting indexed recipe IDs."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.build_index(sample_recipes)

        ids = fts.get_indexed_recipe_ids()
        assert ids == {"recipe-001", "recipe-002", "recipe-003"}

    def test_get_indexed_recipe_ids_empty(self, temp_db_path):
        """Test getting IDs from empty index."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.initialize()

        ids = fts.get_indexed_recipe_ids()
        assert ids == set()

    def test_validate_after_add_recipe(self, temp_db_path, sample_recipes):
        """Test validation after adding a recipe."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.build_index(sample_recipes[:2])  # Only first 2

        # Validation should fail with all 3 IDs
        result = fts.validate_index(3, {"recipe-001", "recipe-002", "recipe-003"})
        assert result is False

        # Add third recipe
        fts.add_recipe(sample_recipes[2])

        # Now validation should pass
        result = fts.validate_index(3, {"recipe-001", "recipe-002", "recipe-003"})
        assert result is True

    def test_validate_after_remove_recipe(self, temp_db_path, sample_recipes):
        """Test validation after removing a recipe."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.build_index(sample_recipes)

        # Remove a recipe
        fts.remove_recipe("recipe-002")

        # Validation should fail with original 3 IDs
        result = fts.validate_index(3, {"recipe-001", "recipe-002", "recipe-003"})
        assert result is False

        # Validation should pass with 2 remaining IDs
        result = fts.validate_index(2, {"recipe-001", "recipe-003"})
        assert result is True

    def test_validate_index_uninitialized(self, temp_db_path):
        """Test validation on uninitialized index."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        # Don't call initialize

        # Should initialize automatically and return False for non-empty set
        result = fts.validate_index(1, {"recipe-001"})
        assert result is False

    def test_indexed_count_after_clear(self, temp_db_path, sample_recipes):
        """Test count after clearing index."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.build_index(sample_recipes)
        assert fts.get_indexed_count() == 3

        fts.clear()
        assert fts.get_indexed_count() == 0

    def test_search_still_works_after_validation(self, temp_db_path, sample_recipes):
        """Test that search works correctly after validation."""
        fts = RecipeFTSIndex(db_path=temp_db_path)
        fts.build_index(sample_recipes)

        # Validate (which checks state)
        fts.validate_index(3, {"recipe-001", "recipe-002", "recipe-003"})

        # Search should still work
        results = fts.search("anime")
        assert "recipe-001" in results
