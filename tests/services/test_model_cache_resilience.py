import asyncio

import pytest

from py.services.model_cache import ModelCache
from py.services.model_query import SearchStrategy


@pytest.mark.asyncio
async def test_model_cache_handles_missing_string_fields():
    cache = ModelCache(
        raw_data=[
            {
                "file_path": "/models/example.safetensors",
                "file_name": None,
                "model_name": None,
                "folder": None,
                "size": 0,
                "modified": 0.0,
            }
        ],
        folders=[],
    )

    await asyncio.sleep(0)  # allow background resort task to run
    sorted_data = await cache.get_sorted_data("name", "asc")

    assert sorted_data[0]["model_name"] == ""
    assert sorted_data[0]["file_name"] == ""
    assert cache.folders == [""]


def test_search_strategy_handles_non_string_candidates():
    strategy = SearchStrategy()
    options = strategy.normalize_options(None)

    data = [
        {
            "file_name": "example.safetensors",
            "model_name": None,
            "tags": ["test"],
        }
    ]

    results = strategy.apply(data, "example", options)

    assert data[0] in results
