import pytest
from py.services.model_query import ModelFilterSet, FilterCriteria
from py.services.recipe_scanner import RecipeScanner
from pathlib import Path
from py.config import config
import asyncio
from types import SimpleNamespace

class StubSettings:
    def get(self, key, default=None):
        return default

# --- Model Filtering Tests ---

def test_model_filter_set_no_tags_include():
    filter_set = ModelFilterSet(StubSettings())
    data = [
        {"name": "m1", "tags": ["tag1"]},
        {"name": "m2", "tags": []},
        {"name": "m3", "tags": None},
        {"name": "m4", "tags": ["tag2"]},
    ]
    
    # Include __no_tags__
    criteria = FilterCriteria(tags={"__no_tags__": "include"})
    result = filter_set.apply(data, criteria)
    assert len(result) == 2
    assert {item["name"] for item in result} == {"m2", "m3"}

def test_model_filter_set_no_tags_exclude():
    filter_set = ModelFilterSet(StubSettings())
    data = [
        {"name": "m1", "tags": ["tag1"]},
        {"name": "m2", "tags": []},
        {"name": "m3", "tags": None},
        {"name": "m4", "tags": ["tag2"]},
    ]
    
    # Exclude __no_tags__
    criteria = FilterCriteria(tags={"__no_tags__": "exclude"})
    result = filter_set.apply(data, criteria)
    assert len(result) == 2
    assert {item["name"] for item in result} == {"m1", "m4"}

def test_model_filter_set_no_tags_mixed():
    filter_set = ModelFilterSet(StubSettings())
    data = [
        {"name": "m1", "tags": ["tag1"]},
        {"name": "m2", "tags": []},
        {"name": "m3", "tags": None},
        {"name": "m4", "tags": ["tag1", "tag2"]},
    ]
    
    # Include tag1 AND __no_tags__
    criteria = FilterCriteria(tags={"tag1": "include", "__no_tags__": "include"})
    result = filter_set.apply(data, criteria)
    # m1 (tag1), m2 (no tags), m3 (no tags), m4 (tag1)
    assert len(result) == 4

# --- Recipe Filtering Tests ---

class StubLoraScanner:
    def __init__(self):
        self._cache = SimpleNamespace(raw_data=[], version_index={})
    async def get_cached_data(self):
        return self._cache
    async def refresh_cache(self, force=False):
        pass

@pytest.fixture
def recipe_scanner(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "loras_roots", [str(tmp_path)])
    stub = StubLoraScanner()
    scanner = RecipeScanner(lora_scanner=stub)
    return scanner

@pytest.mark.asyncio
async def test_recipe_scanner_no_tags_filter(recipe_scanner):
    scanner = recipe_scanner
    
    # Mock some recipe data
    recipes = [
        {"id": "r1", "tags": ["tag1"], "title": "R1"},
        {"id": "r2", "tags": [], "title": "R2"},
        {"id": "r3", "tags": None, "title": "R3"},
    ]
    
    # We need to inject these into the scanner's cache
    # Since get_paginated_data calls get_cached_data() which we stubbed
    scanner._cache = SimpleNamespace(
        raw_data=recipes,
        sorted_by_date=recipes,
        sorted_by_name=recipes
    )
    
    # Test Include __no_tags__
    result = await scanner.get_paginated_data(page=1, page_size=10, filters={"tags": {"__no_tags__": "include"}})
    assert len(result["items"]) == 2
    assert {item["id"] for item in result["items"]} == {"r2", "r3"}
    
    # Test Exclude __no_tags__
    result = await scanner.get_paginated_data(page=1, page_size=10, filters={"tags": {"__no_tags__": "exclude"}})
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == "r1"
