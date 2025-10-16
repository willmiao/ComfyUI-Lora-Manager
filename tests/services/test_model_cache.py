import pytest

from py.services.model_cache import ModelCache


@pytest.mark.asyncio
async def test_name_sort_respects_file_name_display():
    items = [
        {"model_name": "Bravo", "file_name": "zulu", "folder": "", "size": 1, "modified": 1},
        {"model_name": "Alpha", "file_name": "alpha", "folder": "", "size": 1, "modified": 1},
        {"model_name": "Charlie", "file_name": "echo", "folder": "", "size": 1, "modified": 1},
    ]

    cache = ModelCache(raw_data=items, folders=[], name_display_mode="file_name")

    sorted_items = await cache.get_sorted_data("name", "asc")

    assert [item["file_name"] for item in sorted_items] == [
        "alpha",
        "echo",
        "zulu",
    ]


@pytest.mark.asyncio
async def test_update_name_display_mode_resorts_cached_name_order():
    items = [
        {"model_name": "Zulu", "file_name": "alpha", "folder": "", "size": 1, "modified": 1},
        {"model_name": "Alpha", "file_name": "zulu", "folder": "", "size": 1, "modified": 1},
    ]

    cache = ModelCache(raw_data=items, folders=[], name_display_mode="model_name")

    initial = await cache.get_sorted_data("name", "asc")
    assert [item["model_name"] for item in initial] == ["Alpha", "Zulu"]

    await cache.update_name_display_mode("file_name")

    # The cached name sort should refresh immediately based on the new mode
    updated = await cache.get_sorted_data("name", "asc")
    assert [item["file_name"] for item in updated] == ["alpha", "zulu"]
