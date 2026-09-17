"""Regression tests for the recipe empty-prune guard (issue #1116).

A scan that finds no recipe files at all is not a trustworthy deletion signal:
an unmounted drive, a ``recipes_path`` that silently fell back to another LoRA
root, or a cache shared with a second instance all look identical to a real
wipe. Before this guard, such a scan overwrote the persistent cache with an
empty one, destroying the user's only record of their recipes.

Covered contracts:

1. ``_reconcile_recipe_cache`` reports the "every persisted file vanished"
   condition and does not treat an empty directory as a trustworthy prune.
2. ``_initialize_recipe_cache_sync`` keeps the stored cache in that case
   instead of persisting the empty result.
3. A partial orphan (some files still present) still prunes normally, so
   ordinary manual deletions keep working.
4. ``PersistentRecipeCache.save_cache(skip_if_empty=True)`` is the
   storage-level backstop and a manual rebuild can still clear the cache.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from py.config import config
from py.services import recipe_scanner as recipe_scanner_module
from py.services import settings_manager as settings_manager_module
from py.services.persistent_recipe_cache import (
    PersistedRecipeData,
    PersistentRecipeCache,
)
from py.services.recipe_cache import RecipeCache
from py.services.recipe_scanner import RecipeScanner


def _write_recipe_json(path: Path, recipe_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": str(path.with_suffix(".png")),
                "title": f"Recipe {recipe_id}",
                "modified": 0.0,
                "created_date": 0.0,
                "loras": [],
            }
        ),
        encoding="utf-8",
    )


def _persisted_for(paths: list[Path]) -> PersistedRecipeData:
    """Build persisted cache state describing *paths* as known recipe files."""
    raw_data = []
    file_stats = {}
    for path in paths:
        recipe_id = path.name[: -len(".recipe.json")]
        raw_data.append({"id": recipe_id, "title": f"Recipe {recipe_id}"})
        stat = path.stat()
        file_stats[str(path)] = (stat.st_mtime, stat.st_size)
    return PersistedRecipeData(
        raw_data=raw_data, file_stats=file_stats, image_id_map={}
    )


@pytest.fixture
def guard_scanner(tmp_path: Path, monkeypatch):
    """RecipeScanner wired to a real persistent cache, without a ComfyUI app."""
    RecipeScanner._instance = None
    settings_manager_module.reset_settings_manager()
    monkeypatch.setattr(config, "loras_roots", [str(tmp_path / "loras-root")])

    scanner = RecipeScanner.__new__(RecipeScanner)
    scanner._persistent_cache = PersistentRecipeCache(
        db_path=str(tmp_path / "recipe_cache.sqlite")
    )
    scanner._cache = None
    scanner._json_path_map = {}
    scanner._lora_scanner = SimpleNamespace()

    yield scanner, scanner._persistent_cache

    RecipeScanner._instance = None
    settings_manager_module.reset_settings_manager()


def test_reconcile_flags_prune_when_every_persisted_file_is_gone(
    guard_scanner, tmp_path: Path
):
    """An empty recipes dir must not be reported as a trustworthy prune."""
    scanner, _cache = guard_scanner
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir()

    # The files used to live at another root (a changed recipes_path) and are
    # all gone from the directory the scanner resolved this time.
    old_files = [tmp_path / "elsewhere" / f"r{idx}.recipe.json" for idx in range(3)]
    for path in old_files:
        _write_recipe_json(path, path.name[: -len(".recipe.json")])
    persisted = _persisted_for(old_files)
    for path in old_files:
        path.unlink()

    recipes, changed, json_paths, skipped_prune_reason = (
        scanner._reconcile_recipe_cache(persisted, str(recipes_dir))
    )

    assert recipes == []
    assert json_paths == {}
    assert changed is True
    assert skipped_prune_reason is not None
    assert str(recipes_dir) in skipped_prune_reason
    assert "3" in skipped_prune_reason


def test_reconcile_prunes_normally_when_only_some_files_disappear(
    guard_scanner, tmp_path: Path
):
    """A partial orphan is an ordinary deletion and keeps its old behaviour."""
    scanner, _cache = guard_scanner
    recipes_dir = tmp_path / "recipes"

    survivor = recipes_dir / "survivor.recipe.json"
    _write_recipe_json(survivor, "survivor")
    vanished = recipes_dir / "vanished.recipe.json"
    _write_recipe_json(vanished, "vanished")
    persisted = _persisted_for([survivor, vanished])
    vanished.unlink()

    recipes, changed, _json_paths, skipped_prune_reason = (
        scanner._reconcile_recipe_cache(persisted, str(recipes_dir))
    )

    assert skipped_prune_reason is None
    assert changed is True
    assert [recipe["id"] for recipe in recipes] == ["survivor"]


def test_reconcile_ignores_empty_persisted_cache(guard_scanner, tmp_path: Path):
    """A genuinely empty cache has nothing to lose and must not be guarded."""
    scanner, _cache = guard_scanner
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir()

    persisted = PersistedRecipeData(raw_data=[], file_stats={}, image_id_map={})

    _recipes, changed, _json_paths, skipped_prune_reason = (
        scanner._reconcile_recipe_cache(persisted, str(recipes_dir))
    )

    assert changed is False
    assert skipped_prune_reason is None


def test_reconcile_prunes_when_stored_metadata_is_inconsistent(
    guard_scanner, tmp_path: Path
):
    """A stale row set must not masquerade as a fresh mass disappearance.

    Leftover rows (rows without a recorded file stat) mean the stored cache is
    already out of date; guarding them would preserve orphans forever.
    """
    scanner, _cache = guard_scanner
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir()

    gone = tmp_path / "old-location" / "kept.recipe.json"
    _write_recipe_json(gone, "kept")
    persisted = _persisted_for([gone])
    gone.unlink()
    # A row with no matching file record: the cache diverged at some point.
    persisted.raw_data.append({"id": "orphan-row", "title": "Orphan"})

    recipes, changed, _json_paths, skipped_prune_reason = (
        scanner._reconcile_recipe_cache(persisted, str(recipes_dir))
    )

    assert recipes == []
    assert changed is True
    assert skipped_prune_reason is None


def test_sync_init_keeps_stored_cache_when_scan_finds_nothing(
    guard_scanner, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """The startup path must not overwrite the stored cache with an empty one."""
    scanner, cache = guard_scanner
    recipes_dir = Path(config.loras_roots[0]) / "recipes"
    gone = tmp_path / "old-location" / "kept.recipe.json"
    _write_recipe_json(gone, "kept")

    assert cache.save_cache(
        [{"id": "kept", "title": "Recipe kept"}], {"kept": str(gone)}
    )
    gone.unlink()

    with caplog.at_level(logging.WARNING, logger=recipe_scanner_module.__name__):
        scanner._initialize_recipe_cache_sync()

    assert "Recipe cache prune skipped" in caplog.text
    assert scanner._prune_skipped is True
    # The stored cache survived, so the recipes remain recoverable.
    persisted = cache.load_cache()
    assert persisted is not None
    assert [recipe["id"] for recipe in persisted.raw_data] == ["kept"]


def test_skipped_prune_leaves_fts_index_untouched(guard_scanner, tmp_path: Path):
    """A skipped prune must not rebuild the FTS index from the empty view."""
    scanner, cache = guard_scanner
    gone = tmp_path / "old-location" / "kept.recipe.json"
    _write_recipe_json(gone, "kept")
    assert cache.save_cache(
        [{"id": "kept", "title": "Recipe kept"}], {"kept": str(gone)}
    )
    gone.unlink()

    schedule_calls = []
    scanner._schedule_fts_index_build = lambda: schedule_calls.append(True)

    scanner._initialize_recipe_cache_sync()

    assert scanner._prune_skipped is True
    assert schedule_calls == []


def test_sync_init_persists_when_recipes_are_found(guard_scanner, tmp_path: Path):
    """The guard must not block a normal successful scan."""
    scanner, cache = guard_scanner
    recipes_dir = Path(config.loras_roots[0]) / "recipes"
    _write_recipe_json(recipes_dir / "fresh.recipe.json", "fresh")

    scanner._initialize_recipe_cache_sync()

    persisted = cache.load_cache()
    assert persisted is not None
    assert [recipe["id"] for recipe in persisted.raw_data] == ["fresh"]


def test_force_refresh_scan_persists_an_empty_result(guard_scanner, tmp_path: Path):
    """A manual rebuild stays the escape hatch from a skipped prune.

    The startup guard deliberately keeps a stale cache, which leaves the in-memory
    view empty until the files come back. An explicit rebuild must be able to land
    on the real (empty) filesystem state instead, otherwise there is no way out.
    The route to it is `refresh_cache(force=True)`, which clears the stored cache
    first and then does a full directory scan.
    """
    scanner, cache = guard_scanner
    gone = tmp_path / "old-location" / "kept.recipe.json"
    _write_recipe_json(gone, "kept")
    assert cache.save_cache(
        [{"id": "kept", "title": "Recipe kept"}], {"kept": str(gone)}
    )
    gone.unlink()

    # Simulate the explicit rebuild: clear the stored cache, then full scan.
    assert cache.save_cache([], {}) is True
    scanner._initialize_recipe_cache_sync()

    assert scanner._prune_skipped is False
    persisted = cache.load_cache()
    assert persisted is None or persisted.raw_data == []


def test_save_cache_skip_if_empty_preserves_existing_rows(tmp_path: Path):
    """The storage-level backstop refuses to empty a populated cache."""
    cache = PersistentRecipeCache(db_path=str(tmp_path / "recipe_cache.sqlite"))
    assert cache.save_cache([{"id": "r1", "title": "One"}], {"r1": "/tmp/r1.json"})

    written = cache.save_cache([], {}, skip_if_empty=True)

    assert written is False
    persisted = cache.load_cache()
    assert persisted is not None
    assert [recipe["id"] for recipe in persisted.raw_data] == ["r1"]


def test_save_cache_skip_if_empty_allows_clearing_an_empty_cache(tmp_path: Path):
    """Nothing to protect: an already-empty cache still returns success."""
    cache = PersistentRecipeCache(db_path=str(tmp_path / "recipe_cache.sqlite"))

    assert cache.save_cache([], {}, skip_if_empty=True) is True


def test_save_cache_default_still_allows_intentional_full_clear(tmp_path: Path):
    """A manual rebuild passes skip_if_empty=False and must clear the cache."""
    cache = PersistentRecipeCache(db_path=str(tmp_path / "recipe_cache.sqlite"))
    assert cache.save_cache([{"id": "r1", "title": "One"}], {"r1": "/tmp/r1.json"})

    assert cache.save_cache([], {}) is True

    persisted = cache.load_cache()
    assert persisted is None or persisted.raw_data == []
