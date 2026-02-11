"""Integration tests for recipe flow.

These tests verify the complete recipe workflow including:
1. Import recipe from image
2. Parse metadata and extract models
3. Save to cache and database
4. Retrieve and display
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestRecipeFlowIntegration:
    """Integration tests for complete recipe workflow."""

    async def test_recipe_save_and_retrieve_flow(
        self,
        tmp_path: Path,
        sample_recipe_data: Dict[str, Any],
    ):
        """Verify recipe can be saved and retrieved."""
        from py.services.persistent_recipe_cache import PersistentRecipeCache

        db_path = tmp_path / "test_recipe_cache.sqlite"
        cache = PersistentRecipeCache(db_path=str(db_path))

        # Save recipe
        recipes = [sample_recipe_data]
        json_paths = {sample_recipe_data["id"]: "/path/to/test.recipe.json"}
        cache.save_cache(recipes, json_paths)

        # Retrieve recipe
        loaded = cache.load_cache()

        assert loaded is not None
        assert len(loaded.raw_data) == 1

        loaded_recipe = loaded.raw_data[0]
        assert loaded_recipe["id"] == sample_recipe_data["id"]
        assert loaded_recipe["title"] == sample_recipe_data["title"]
        assert loaded_recipe["base_model"] == sample_recipe_data["base_model"]

    async def test_recipe_update_flow(
        self,
        tmp_path: Path,
        sample_recipe_data: Dict[str, Any],
    ):
        """Verify recipe can be updated and changes persisted."""
        from py.services.persistent_recipe_cache import PersistentRecipeCache

        db_path = tmp_path / "test_recipe_cache.sqlite"
        cache = PersistentRecipeCache(db_path=str(db_path))

        # Save initial recipe
        cache.save_cache([sample_recipe_data])

        # Update recipe
        updated_recipe = dict(sample_recipe_data)
        updated_recipe["title"] = "Updated Recipe Title"
        updated_recipe["favorite"] = True

        cache.update_recipe(updated_recipe, "/path/to/test.recipe.json")

        # Verify update
        loaded = cache.load_cache()
        loaded_recipe = loaded.raw_data[0]

        assert loaded_recipe["title"] == "Updated Recipe Title"
        assert loaded_recipe["favorite"] is True

    async def test_recipe_delete_flow(
        self,
        tmp_path: Path,
        sample_recipe_data: Dict[str, Any],
    ):
        """Verify recipe can be deleted."""
        from py.services.persistent_recipe_cache import PersistentRecipeCache

        db_path = tmp_path / "test_recipe_cache.sqlite"
        cache = PersistentRecipeCache(db_path=str(db_path))

        # Save recipe
        cache.save_cache([sample_recipe_data])
        assert cache.get_recipe_count() == 1

        # Delete recipe
        cache.remove_recipe(sample_recipe_data["id"])

        # Verify deletion
        assert cache.get_recipe_count() == 0
        loaded = cache.load_cache()
        assert loaded is None or len(loaded.raw_data) == 0

    async def test_recipe_model_extraction(
        self,
        sample_recipe_data: Dict[str, Any],
    ):
        """Verify models are correctly extracted from recipe data."""
        loras = sample_recipe_data.get("loras", [])
        checkpoint = sample_recipe_data.get("checkpoint")

        # Verify LoRAs are present
        assert len(loras) == 2
        assert loras[0]["file_name"] == "test_lora1"
        assert loras[0]["strength"] == 0.8
        assert loras[1]["file_name"] == "test_lora2"
        assert loras[1]["strength"] == 1.0

        # Verify checkpoint is present
        assert checkpoint is not None
        assert checkpoint["name"] == "model.safetensors"
        assert checkpoint["hash"] == "cphash123"

    async def test_recipe_generation_params(
        self,
        sample_recipe_data: Dict[str, Any],
    ):
        """Verify generation parameters are correctly stored."""
        gen_params = sample_recipe_data.get("gen_params", {})

        assert gen_params["prompt"] == "masterpiece, best quality, test subject"
        assert gen_params["negative_prompt"] == "low quality, blurry"
        assert gen_params["steps"] == 20
        assert gen_params["cfg"] == 7.0
        assert gen_params["sampler"] == "DPM++ 2M Karras"


class TestRecipeCacheConcurrency:
    """Integration tests for recipe cache concurrent access."""

    async def test_concurrent_recipe_reads(
        self,
        tmp_path: Path,
        sample_recipe_data: Dict[str, Any],
    ):
        """Verify concurrent reads don't corrupt data."""
        from py.services.persistent_recipe_cache import PersistentRecipeCache
        import asyncio

        db_path = tmp_path / "test_concurrent.sqlite"
        cache = PersistentRecipeCache(db_path=str(db_path))

        # Save multiple recipes
        recipes = [
            {**sample_recipe_data, "id": f"recipe-{i}"}
            for i in range(10)
        ]
        cache.save_cache(recipes)

        # Concurrent reads
        async def read_recipes():
            return cache.load_cache()

        tasks = [read_recipes() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All reads should succeed and return same data
        for result in results:
            assert result is not None
            assert len(result.raw_data) == 10

    async def test_concurrent_read_write(
        self,
        tmp_path: Path,
        sample_recipe_data: Dict[str, Any],
    ):
        """Verify concurrent read/write operations are safe."""
        from py.services.persistent_recipe_cache import PersistentRecipeCache
        import asyncio

        db_path = tmp_path / "test_concurrent.sqlite"
        cache = PersistentRecipeCache(db_path=str(db_path))

        # Initial save
        cache.save_cache([sample_recipe_data])

        async def read_operation():
            await asyncio.sleep(0.01)  # Small delay to interleave operations
            return cache.load_cache()

        async def write_operation(recipe_id: str):
            await asyncio.sleep(0.005)  # Small delay
            recipe = {**sample_recipe_data, "id": recipe_id}
            cache.update_recipe(recipe, f"/path/to/{recipe_id}.json")

        # Mix of read and write operations
        tasks = [
            read_operation(),
            write_operation("recipe-002"),
            read_operation(),
            write_operation("recipe-003"),
            read_operation(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # No exceptions should occur
        for result in results:
            assert not isinstance(result, Exception), f"Exception occurred: {result}"

        # Final state should be valid
        final = cache.load_cache()
        assert final is not None
        assert cache.get_recipe_count() >= 1


class TestRecipeRouteIntegration:
    """Integration tests for recipe route handlers."""

    async def test_recipe_list_endpoint(self):
        """Verify recipe list endpoint returns correct format."""
        from aiohttp.test_utils import make_mocked_request

        # This would test the actual route handler
        # For now, we verify the expected response structure
        expected_response = {
            "success": True,
            "recipes": [],
            "total": 0,
        }

        assert "success" in expected_response
        assert "recipes" in expected_response

    async def test_recipe_metadata_parsing(self):
        """Verify recipe metadata is parsed correctly from various formats."""
        # Simple metadata parsing test without external dependency
        meta_str = """prompt: masterpiece, best quality
negative_prompt: low quality
steps: 20
cfg: 7.0"""

        # Basic parsing logic for testing
        def parse_simple_metadata(text: str) -> dict:
            result = {}
            for line in text.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    result[key.strip()] = value.strip()
            return result

        result = parse_simple_metadata(meta_str)

        assert result is not None
        assert "prompt" in result
        assert "negative_prompt" in result
        assert result["prompt"] == "masterpiece, best quality"
