"""Tests for PersistentRecipeCache."""

import json
import os
import tempfile
from typing import Dict, List

import pytest

from py.services.persistent_recipe_cache import PersistentRecipeCache, PersistedRecipeData


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)
    # Also clean up WAL files
    for suffix in ["-wal", "-shm"]:
        wal_path = path + suffix
        if os.path.exists(wal_path):
            os.unlink(wal_path)


@pytest.fixture
def sample_recipes() -> List[Dict]:
    """Create sample recipe data."""
    return [
        {
            "id": "recipe-001",
            "file_path": "/path/to/image1.png",
            "title": "Test Recipe 1",
            "folder": "folder1",
            "base_model": "SD1.5",
            "fingerprint": "abc123",
            "created_date": 1700000000.0,
            "modified": 1700000100.0,
            "favorite": True,
            "repair_version": 3,
            "preview_nsfw_level": 1,
            "loras": [
                {"hash": "hash1", "file_name": "lora1", "strength": 0.8},
                {"hash": "hash2", "file_name": "lora2", "strength": 1.0},
            ],
            "checkpoint": {"name": "model.safetensors", "hash": "cphash"},
            "gen_params": {"prompt": "test prompt", "negative_prompt": "bad"},
            "tags": ["tag1", "tag2"],
        },
        {
            "id": "recipe-002",
            "file_path": "/path/to/image2.png",
            "title": "Test Recipe 2",
            "folder": "",
            "base_model": "SDXL",
            "fingerprint": "def456",
            "created_date": 1700000200.0,
            "modified": 1700000300.0,
            "favorite": False,
            "repair_version": 2,
            "preview_nsfw_level": 0,
            "loras": [{"hash": "hash3", "file_name": "lora3", "strength": 0.5}],
            "gen_params": {"prompt": "another prompt"},
            "tags": [],
        },
    ]


class TestPersistentRecipeCache:
    """Tests for PersistentRecipeCache class."""

    def test_init_creates_db(self, temp_db_path):
        """Test that initialization creates the database."""
        cache = PersistentRecipeCache(db_path=temp_db_path)
        assert cache.is_enabled()
        assert os.path.exists(temp_db_path)

    def test_save_and_load_roundtrip(self, temp_db_path, sample_recipes):
        """Test save and load cycle preserves data."""
        cache = PersistentRecipeCache(db_path=temp_db_path)

        # Save recipes
        json_paths = {
            "recipe-001": "/path/to/recipe-001.recipe.json",
            "recipe-002": "/path/to/recipe-002.recipe.json",
        }
        cache.save_cache(sample_recipes, json_paths)

        # Load recipes
        loaded = cache.load_cache()
        assert loaded is not None
        assert len(loaded.raw_data) == 2

        # Verify first recipe
        r1 = next(r for r in loaded.raw_data if r["id"] == "recipe-001")
        assert r1["title"] == "Test Recipe 1"
        assert r1["folder"] == "folder1"
        assert r1["base_model"] == "SD1.5"
        assert r1["fingerprint"] == "abc123"
        assert r1["favorite"] is True
        assert r1["repair_version"] == 3
        assert len(r1["loras"]) == 2
        assert r1["loras"][0]["hash"] == "hash1"
        assert r1["checkpoint"]["name"] == "model.safetensors"
        assert r1["gen_params"]["prompt"] == "test prompt"
        assert r1["tags"] == ["tag1", "tag2"]

        # Verify second recipe
        r2 = next(r for r in loaded.raw_data if r["id"] == "recipe-002")
        assert r2["title"] == "Test Recipe 2"
        assert r2["folder"] == ""
        assert r2["favorite"] is False

    def test_empty_cache_returns_none(self, temp_db_path):
        """Test that loading empty cache returns None."""
        cache = PersistentRecipeCache(db_path=temp_db_path)
        loaded = cache.load_cache()
        assert loaded is None

    def test_update_single_recipe(self, temp_db_path, sample_recipes):
        """Test updating a single recipe."""
        cache = PersistentRecipeCache(db_path=temp_db_path)
        cache.save_cache(sample_recipes)

        # Update a recipe
        updated_recipe = dict(sample_recipes[0])
        updated_recipe["title"] = "Updated Title"
        updated_recipe["favorite"] = False
        cache.update_recipe(updated_recipe, "/path/to/recipe-001.recipe.json")

        # Load and verify
        loaded = cache.load_cache()
        r1 = next(r for r in loaded.raw_data if r["id"] == "recipe-001")
        assert r1["title"] == "Updated Title"
        assert r1["favorite"] is False

    def test_remove_recipe(self, temp_db_path, sample_recipes):
        """Test removing a recipe."""
        cache = PersistentRecipeCache(db_path=temp_db_path)
        cache.save_cache(sample_recipes)

        # Remove a recipe
        cache.remove_recipe("recipe-001")

        # Load and verify
        loaded = cache.load_cache()
        assert len(loaded.raw_data) == 1
        assert loaded.raw_data[0]["id"] == "recipe-002"

    def test_get_indexed_recipe_ids(self, temp_db_path, sample_recipes):
        """Test getting all indexed recipe IDs."""
        cache = PersistentRecipeCache(db_path=temp_db_path)
        cache.save_cache(sample_recipes)

        ids = cache.get_indexed_recipe_ids()
        assert ids == {"recipe-001", "recipe-002"}

    def test_get_recipe_count(self, temp_db_path, sample_recipes):
        """Test getting recipe count."""
        cache = PersistentRecipeCache(db_path=temp_db_path)
        assert cache.get_recipe_count() == 0

        cache.save_cache(sample_recipes)
        assert cache.get_recipe_count() == 2

        cache.remove_recipe("recipe-001")
        assert cache.get_recipe_count() == 1

    def test_file_stats(self, temp_db_path, sample_recipes):
        """Test file stats tracking."""
        cache = PersistentRecipeCache(db_path=temp_db_path)

        json_paths = {
            "recipe-001": "/path/to/recipe-001.recipe.json",
            "recipe-002": "/path/to/recipe-002.recipe.json",
        }
        cache.save_cache(sample_recipes, json_paths)

        stats = cache.get_file_stats()
        # File stats will be (0.0, 0) since files don't exist
        assert len(stats) == 2

    def test_disabled_cache(self, temp_db_path, sample_recipes, monkeypatch):
        """Test that disabled cache returns None."""
        monkeypatch.setenv("LORA_MANAGER_DISABLE_PERSISTENT_CACHE", "1")

        cache = PersistentRecipeCache(db_path=temp_db_path)
        assert not cache.is_enabled()
        cache.save_cache(sample_recipes)
        assert cache.load_cache() is None

    def test_invalid_recipe_skipped(self, temp_db_path):
        """Test that recipes without ID are skipped."""
        cache = PersistentRecipeCache(db_path=temp_db_path)

        recipes = [
            {"title": "No ID recipe"},  # Missing ID
            {"id": "valid-001", "title": "Valid recipe"},
        ]
        cache.save_cache(recipes)

        loaded = cache.load_cache()
        assert len(loaded.raw_data) == 1
        assert loaded.raw_data[0]["id"] == "valid-001"

    def test_get_default_singleton(self, monkeypatch):
        """Test singleton behavior."""
        # Use temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("LORA_MANAGER_RECIPE_CACHE_DB", os.path.join(tmpdir, "test.sqlite"))

            PersistentRecipeCache.clear_instances()
            cache1 = PersistentRecipeCache.get_default("test_lib")
            cache2 = PersistentRecipeCache.get_default("test_lib")
            assert cache1 is cache2

            cache3 = PersistentRecipeCache.get_default("other_lib")
            assert cache1 is not cache3

            PersistentRecipeCache.clear_instances()

    def test_loras_json_handling(self, temp_db_path):
        """Test that complex loras data is preserved."""
        cache = PersistentRecipeCache(db_path=temp_db_path)

        recipes = [
            {
                "id": "complex-001",
                "title": "Complex Loras",
                "loras": [
                    {
                        "hash": "abc123",
                        "file_name": "test_lora",
                        "strength": 0.75,
                        "modelVersionId": 12345,
                        "modelName": "Test Model",
                        "isDeleted": False,
                    },
                    {
                        "hash": "def456",
                        "file_name": "another_lora",
                        "strength": 1.0,
                        "clip_strength": 0.8,
                    },
                ],
            }
        ]
        cache.save_cache(recipes)

        loaded = cache.load_cache()
        loras = loaded.raw_data[0]["loras"]
        assert len(loras) == 2
        assert loras[0]["modelVersionId"] == 12345
        assert loras[1]["clip_strength"] == 0.8
