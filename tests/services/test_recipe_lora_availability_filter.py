"""Tests for the LoRA availability filter on the recipe listing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from py.config import config
from py.services.recipe_scanner import RecipeScanner


class StubLoraScanner:
    """In-memory lora scanner double exposing the hash/version indexes."""

    def __init__(self, hashes=(), version_index=None):
        self._hashes = {value.lower() for value in hashes}
        self._cache = SimpleNamespace(raw_data=[], version_index=version_index or {})

    def has_hash(self, hash_value):
        return hash_value.lower() in self._hashes

    def get_preview_url_by_hash(self, hash_value):
        return None

    def get_path_by_hash(self, hash_value):
        return None

    async def get_cached_data(self):
        return self._cache

    async def refresh_cache(self, force=False):
        pass


@pytest.fixture
def recipe_scanner(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "loras_roots", [str(tmp_path)])
    lora_scanner = StubLoraScanner(
        hashes={"aaa111"},
        version_index={42: {"file_path": "/loras/from-version.safetensors"}},
    )
    scanner = RecipeScanner(lora_scanner=lora_scanner)  # pyright: ignore[reportArgumentType]

    recipes = [
        # All loras in library (hash matching is case-insensitive) -> ready
        {"id": "r1", "title": "Ready", "loras": [{"hash": "AAA111"}]},
        # One lora not in library -> missing
        {
            "id": "r2",
            "title": "Missing",
            "loras": [{"hash": "aaa111"}, {"hash": "bbb222"}],
        },
        # Lora deleted on Civitai and not in library -> deleted
        {
            "id": "r3",
            "title": "Deleted",
            "loras": [{"hash": "ccc333", "isDeleted": True}],
        },
        # Missing + deleted -> both statuses
        {
            "id": "r4",
            "title": "Mixed",
            "loras": [{"hash": "bbb222"}, {"hash": "ccc333", "isDeleted": True}],
        },
        # No loras at all -> ready
        {"id": "r5", "title": "Empty", "loras": []},
        # Excluded lora is ignored -> ready
        {
            "id": "r6",
            "title": "Excluded",
            "loras": [{"hash": "bbb222", "exclude": True}],
        },
        # modelVersionId resolves via the version index -> ready
        {"id": "r7", "title": "VersionFallback", "loras": [{"modelVersionId": 42}]},
    ]

    scanner._cache = SimpleNamespace(
        raw_data=recipes,
        sorted_by_date=recipes,
        sorted_by_name=recipes,
    )
    return scanner


async def _fetch_ids(scanner, filters=None):
    result = await scanner.get_paginated_data(page=1, page_size=50, filters=filters)
    return {item["id"] for item in result["items"]}


@pytest.mark.asyncio
async def test_availability_filter_ready_only(recipe_scanner):
    ids = await _fetch_ids(recipe_scanner, {"lora_availability": {"ready"}})
    assert ids == {"r1", "r5", "r6", "r7"}


@pytest.mark.asyncio
async def test_availability_filter_missing_only(recipe_scanner):
    ids = await _fetch_ids(recipe_scanner, {"lora_availability": {"missing"}})
    assert ids == {"r2", "r4"}


@pytest.mark.asyncio
async def test_availability_filter_deleted_only(recipe_scanner):
    ids = await _fetch_ids(recipe_scanner, {"lora_availability": {"deleted"}})
    assert ids == {"r3", "r4"}


@pytest.mark.asyncio
async def test_availability_filter_missing_and_deleted(recipe_scanner):
    ids = await _fetch_ids(recipe_scanner, {"lora_availability": {"missing", "deleted"}})
    assert ids == {"r2", "r3", "r4"}


@pytest.mark.asyncio
async def test_availability_filter_all_statuses_disables_filtering(recipe_scanner):
    ids = await _fetch_ids(
        recipe_scanner, {"lora_availability": {"ready", "missing", "deleted"}}
    )
    assert ids == {"r1", "r2", "r3", "r4", "r5", "r6", "r7"}


@pytest.mark.asyncio
async def test_availability_filter_absent_or_invalid_disables_filtering(recipe_scanner):
    assert await _fetch_ids(recipe_scanner) == {"r1", "r2", "r3", "r4", "r5", "r6", "r7"}
    ids = await _fetch_ids(recipe_scanner, {"lora_availability": {"bogus"}})
    assert ids == {"r1", "r2", "r3", "r4", "r5", "r6", "r7"}


@pytest.mark.asyncio
async def test_availability_filter_counts_and_pagination(recipe_scanner):
    # Filtering happens before pagination, so totals reflect the filtered set.
    result = await recipe_scanner.get_paginated_data(
        page=1, page_size=1, filters={"lora_availability": {"ready"}}
    )
    assert result["total"] == 4
    assert result["total_pages"] == 4
    assert len(result["items"]) == 1
