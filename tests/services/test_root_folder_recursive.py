import pytest
from py.services.model_query import ModelFilterSet, FilterCriteria
from py.services.recipe_scanner import RecipeScanner
from types import SimpleNamespace


# Mock settings
class MockSettings:
    def get(self, key, default=None):
        return default


# --- Model Filtering Tests ---


def test_model_filter_set_root_recursive_true():
    filter_set = ModelFilterSet(MockSettings())
    items = [
        {"model_name": "root_item", "folder": ""},
        {"model_name": "sub_item", "folder": "sub"},
    ]
    criteria = FilterCriteria(folder="", search_options={"recursive": True})

    result = filter_set.apply(items, criteria)

    assert len(result) == 2
    assert any(i["model_name"] == "root_item" for i in result)
    assert any(i["model_name"] == "sub_item" for i in result)


def test_model_filter_set_root_recursive_false():
    filter_set = ModelFilterSet(MockSettings())
    items = [
        {"model_name": "root_item", "folder": ""},
        {"model_name": "sub_item", "folder": "sub"},
    ]
    criteria = FilterCriteria(folder="", search_options={"recursive": False})

    result = filter_set.apply(items, criteria)

    assert len(result) == 1
    assert result[0]["model_name"] == "root_item"


def test_model_filter_set_folder_exclude_single():
    filter_set = ModelFilterSet(MockSettings())
    items = [
        {"model_name": "item1", "folder": "characters/"},
        {"model_name": "item2", "folder": "styles/"},
        {"model_name": "item3", "folder": "characters/anime/"},
        {"model_name": "item4", "folder": ""},
    ]
    criteria = FilterCriteria(
        folder_exclude=["characters/"], search_options={"recursive": True}
    )

    result = filter_set.apply(items, criteria)

    assert len(result) == 2
    model_names = {i["model_name"] for i in result}
    assert model_names == {"item2", "item4"}


def test_model_filter_set_folder_exclude_multiple():
    filter_set = ModelFilterSet(MockSettings())
    items = [
        {"model_name": "item1", "folder": "characters/"},
        {"model_name": "item2", "folder": "styles/"},
        {"model_name": "item3", "folder": "concepts/"},
        {"model_name": "item4", "folder": "characters/anime/"},
        {"model_name": "item5", "folder": ""},
    ]
    criteria = FilterCriteria(
        folder_exclude=["characters/", "styles/"], search_options={"recursive": True}
    )

    result = filter_set.apply(items, criteria)

    assert len(result) == 2
    model_names = {i["model_name"] for i in result}
    assert model_names == {"item3", "item5"}


def test_model_filter_set_folder_exclude_with_include():
    filter_set = ModelFilterSet(MockSettings())
    items = [
        {"model_name": "item1", "folder": "characters/"},
        {"model_name": "item2", "folder": "styles/"},
        {"model_name": "item3", "folder": "characters/anime/"},
        {"model_name": "item4", "folder": "styles/painting/"},
        {"model_name": "item5", "folder": "concepts/"},
    ]
    criteria = FilterCriteria(
        folder="characters/",
        folder_exclude=["characters/anime/"],
        search_options={"recursive": True},
    )

    result = filter_set.apply(items, criteria)

    assert len(result) == 1
    assert result[0]["model_name"] == "item1"


# --- Recipe Filtering Tests ---


@pytest.mark.asyncio
async def test_recipe_scanner_root_recursive_true():
    # Mock LoraScanner
    class StubLoraScanner:
        async def get_cached_data(self):
            return SimpleNamespace(raw_data=[])

    scanner = RecipeScanner(lora_scanner=StubLoraScanner())
    # Manually populate cache for testing get_paginated_data logic
    scanner._cache = SimpleNamespace(
        raw_data=[
            {
                "id": "r1",
                "title": "root_recipe",
                "folder": "",
                "modified": 1.0,
                "created_date": 1.0,
                "loras": [],
            },
            {
                "id": "r2",
                "title": "sub_recipe",
                "folder": "sub",
                "modified": 2.0,
                "created_date": 2.0,
                "loras": [],
            },
        ],
        sorted_by_date=[
            {
                "id": "r2",
                "title": "sub_recipe",
                "folder": "sub",
                "modified": 2.0,
                "created_date": 2.0,
                "loras": [],
            },
            {
                "id": "r1",
                "title": "root_recipe",
                "folder": "",
                "modified": 1.0,
                "created_date": 1.0,
                "loras": [],
            },
        ],
        sorted_by_name=[],
        version_index={},
    )

    result = await scanner.get_paginated_data(
        page=1, page_size=10, folder="", recursive=True
    )

    assert len(result["items"]) == 2


@pytest.mark.asyncio
async def test_recipe_scanner_root_recursive_false():
    # Mock LoraScanner
    class StubLoraScanner:
        async def get_cached_data(self):
            return SimpleNamespace(raw_data=[])

    scanner = RecipeScanner(lora_scanner=StubLoraScanner())
    scanner._cache = SimpleNamespace(
        raw_data=[
            {
                "id": "r1",
                "title": "root_recipe",
                "folder": "",
                "modified": 1.0,
                "created_date": 1.0,
                "loras": [],
            },
            {
                "id": "r2",
                "title": "sub_recipe",
                "folder": "sub",
                "modified": 2.0,
                "created_date": 2.0,
                "loras": [],
            },
        ],
        sorted_by_date=[
            {
                "id": "r2",
                "title": "sub_recipe",
                "folder": "sub",
                "modified": 2.0,
                "created_date": 2.0,
                "loras": [],
            },
            {
                "id": "r1",
                "title": "root_recipe",
                "folder": "",
                "modified": 1.0,
                "created_date": 1.0,
                "loras": [],
            },
        ],
        sorted_by_name=[],
        version_index={},
    )

    result = await scanner.get_paginated_data(
        page=1, page_size=10, folder="", recursive=False
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == "r1"
