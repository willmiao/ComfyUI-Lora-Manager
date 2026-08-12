"""Tests for sort parsing and the seeded random sort mode."""

import asyncio

import pytest

from py.services.model_cache import ModelCache
from py.services.model_query import ModelCacheRepository, SortParams


def _make_cache(items):
    return ModelCache(
        raw_data=[
            {
                "file_path": f"/models/{name}.safetensors",
                "file_name": f"{name}.safetensors",
                "model_name": name,
                "folder": "",
                "size": 100,
                "modified": 0.0,
            }
            for name in items
        ],
        folders=[],
    )


class TestParseSort:
    def test_random_with_seed(self):
        params = ModelCacheRepository.parse_sort("random:abc123")
        assert params == SortParams(key="random", order="asc", seed="abc123")

    def test_random_without_seed(self):
        params = ModelCacheRepository.parse_sort("random")
        assert params == SortParams(key="random", order="asc", seed=None)

    def test_random_empty_seed_falls_back_to_none(self):
        params = ModelCacheRepository.parse_sort("random:")
        assert params.seed is None

    def test_regular_sorts_unaffected(self):
        params = ModelCacheRepository.parse_sort("name:desc")
        assert params == SortParams(key="name", order="desc", seed=None)


class TestRandomShuffle:
    @pytest.mark.asyncio
    async def test_same_seed_yields_same_order(self):
        cache = _make_cache(["a", "b", "c", "d", "e"])
        await asyncio.sleep(0)  # allow background resort task to run

        first = await cache.get_sorted_data("random", "asc", "seed1")
        second = await cache.get_sorted_data("random", "asc", "seed1")

        assert [item["model_name"] for item in first] == [
            item["model_name"] for item in second
        ]

    @pytest.mark.asyncio
    async def test_different_seeds_yield_different_orders(self):
        cache = _make_cache([f"m{i}" for i in range(20)])
        await asyncio.sleep(0)

        first = await cache.get_sorted_data("random", "asc", "seed-a")
        second = await cache.get_sorted_data("random", "asc", "seed-b")

        assert [item["model_name"] for item in first] != [
            item["model_name"] for item in second
        ]

    @pytest.mark.asyncio
    async def test_shuffle_is_a_permutation(self):
        cache = _make_cache(["a", "b", "c", "d", "e"])
        await asyncio.sleep(0)

        shuffled = await cache.get_sorted_data("random", "asc", "seed")

        assert sorted(item["model_name"] for item in shuffled) == [
            "a",
            "b",
            "c",
            "d",
            "e",
        ]
        assert len({item["file_path"] for item in shuffled}) == 5

    @pytest.mark.asyncio
    async def test_missing_seed_is_stable(self):
        cache = _make_cache(["a", "b", "c", "d", "e"])
        await asyncio.sleep(0)

        first = await cache.get_sorted_data("random", "asc")
        second = await cache.get_sorted_data("random", "asc")

        assert [item["model_name"] for item in first] == [
            item["model_name"] for item in second
        ]
