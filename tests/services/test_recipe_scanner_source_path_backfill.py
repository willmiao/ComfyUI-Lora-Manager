"""Tests for the one-shot source_path backfill in RecipeScanner."""

import json
from pathlib import Path

import pytest

from py.services.persistent_recipe_cache import PersistentRecipeCache
from py.services.recipe_scanner import RecipeScanner


@pytest.fixture
def scanner_with_cache(tmp_path: Path):
    """RecipeScanner instance backed by a real persistent cache in tmp_path."""
    cache = PersistentRecipeCache(db_path=str(tmp_path / "recipe_cache.sqlite"))
    scanner = RecipeScanner.__new__(RecipeScanner)
    scanner._persistent_cache = cache
    return scanner, cache


def _write_recipe_json(path: Path, recipe_id: str, source_path: str | None = None) -> None:
    data = {"id": recipe_id}
    if source_path is not None:
        data["source_path"] = source_path
    path.write_text(json.dumps(data), encoding="utf-8")


def test_backfill_processes_recipes_when_marker_absent(scanner_with_cache, tmp_path: Path):
    """Without the completion marker, missing source_path values are backfilled."""
    scanner, cache = scanner_with_cache

    json_with_source = tmp_path / "r1.recipe.json"
    _write_recipe_json(json_with_source, "r1", source_path="https://civitai.com/images/1")
    json_without_source = tmp_path / "r2.recipe.json"
    _write_recipe_json(json_without_source, "r2")

    recipes = [
        {"id": "r1", "source_path": ""},
        {"id": "r2", "source_path": ""},
        {"id": "r3", "source_path": "https://civitai.com/images/3"},
    ]
    json_paths = {"r1": str(json_with_source), "r2": str(json_without_source)}

    updated = scanner._backfill_source_path_if_needed(recipes, json_paths)

    assert updated is True
    assert recipes[0]["source_path"] == "https://civitai.com/images/1"
    # JSON legitimately has no source_path: stays empty, no error
    assert recipes[1]["source_path"] == ""
    assert recipes[2]["source_path"] == "https://civitai.com/images/3"
    # The run records the completion marker
    assert (
        cache.get_metadata_value(RecipeScanner._SOURCE_PATH_BACKFILL_MARKER) == "1"
    )


def test_backfill_is_skipped_once_marker_is_set(scanner_with_cache, tmp_path: Path, monkeypatch):
    """The second initialization must not re-read recipe JSON files."""
    scanner, cache = scanner_with_cache

    json_path = tmp_path / "r1.recipe.json"
    _write_recipe_json(json_path, "r1", source_path="https://civitai.com/images/1")

    recipes = [{"id": "r1", "source_path": ""}]
    json_paths = {"r1": str(json_path)}

    # First run: backfills and records the marker
    assert scanner._backfill_source_path_if_needed(recipes, json_paths) is True
    assert recipes[0]["source_path"] == "https://civitai.com/images/1"

    # Second run: simulate a fresh startup where the cache still lacks
    # source_path. Under the old behavior the file would be re-read and
    # re-parsed; now the marker must suppress any file access.
    recipes = [{"id": "r1", "source_path": ""}]

    import os

    real_exists = os.path.exists

    def _failing_exists(path):
        if str(path).endswith(".recipe.json"):
            raise AssertionError("backfill touched the filesystem despite marker")
        return real_exists(path)

    monkeypatch.setattr(os.path, "exists", _failing_exists)

    updated = scanner._backfill_source_path_if_needed(recipes, json_paths)

    assert updated is False
    assert recipes[0]["source_path"] == ""


def test_backfill_marker_does_not_suppress_reconcile_parsed_source_path(scanner_with_cache):
    """The marker only gates the backfill; parsed recipes keep their source_path."""
    scanner, cache = scanner_with_cache
    cache.set_metadata_value(RecipeScanner._SOURCE_PATH_BACKFILL_MARKER, "1")

    # A recipe that arrived from the normal parse path with a source_path is
    # left untouched by the (skipped) backfill.
    recipes = [{"id": "r1", "source_path": "https://civitai.com/images/9"}]
    updated = scanner._backfill_source_path_if_needed(recipes, {})

    assert updated is False
    assert recipes[0]["source_path"] == "https://civitai.com/images/9"
