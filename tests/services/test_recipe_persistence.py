"""Tests for recipe delete staging in :mod:`py.services.recipes.persistence_service`.

Covers the delete-undo wiring (plan todo 4): ``delete_recipe`` and
``bulk_delete`` stage recipe JSON + preview image into the global pending-delete
staging dir when undo is enabled, fall back to the existing hard delete when it
is disabled, and expose the batch field(s) in the result payload. Merge failure
falls back to a ``batch_ids`` array (same no-merge contract as the model bulk
path).

Deterministic time control: no real sleeps - the re-anchored ``expires_at`` is
compared against a loose before/after window instead.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from py.services.pending_delete_service import (
    PENDING_DELETE_DIR_NAME,
    PENDING_DELETE_TTL_SECONDS,
    _reset_pending_delete_service,
)
from py.services.recipes.persistence_service import (
    PersistenceResult,
    RecipePersistenceService,
)
from py.utils import settings_paths


class DummyExifUtils:
    """Exif double matching the persistence service constructor contract."""

    def __init__(self) -> None:
        self.appended = None
        self.optimized_calls = 0

    def optimize_image(self, image_data, target_width, format, quality, preserve_metadata):
        self.optimized_calls += 1
        return image_data, ".webp"

    def append_recipe_metadata(self, image_path, recipe_data):
        self.appended = (image_path, recipe_data)

    def extract_image_metadata(self, path):
        return {}


class RecipeScannerStub:
    """Scanner double exposing the persistence methods used by delete flows."""

    def __init__(self, root: Path) -> None:
        self.recipes_dir = str(root)
        self.removed: List[str] = []
        self.bulk_removed: List[str] = []
        self._json_paths: Dict[str, str] = {}

    def register_recipe(self, recipe_id: str, json_path: Path) -> None:
        self._json_paths[str(recipe_id)] = str(json_path)

    async def get_recipe_json_path(self, recipe_id: str) -> Optional[str]:
        return self._json_paths.get(str(recipe_id))

    async def remove_recipe(self, recipe_id: str) -> bool:
        self.removed.append(str(recipe_id))
        return True

    async def bulk_remove(self, recipe_ids) -> int:
        self.bulk_removed.extend(str(recipe_id) for recipe_id in recipe_ids)
        return len(list(recipe_ids))


@pytest.fixture(autouse=True)
def _reset_service_singleton() -> Iterator[None]:
    """Reset the pending-delete singleton before and after each test."""
    _reset_pending_delete_service()
    yield
    _reset_pending_delete_service()


@pytest.fixture(autouse=True)
def _stub_scanner_registry(monkeypatch) -> None:
    """Prevent purge enumeration from instantiating real scanner singletons."""
    from py.services.service_registry import ServiceRegistry

    async def _none(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _none)
    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _none)
    monkeypatch.setattr(ServiceRegistry, "get_embedding_scanner", _none)


def _make_service() -> RecipePersistenceService:
    return RecipePersistenceService(
        exif_utils=DummyExifUtils(),
        card_preview_width=512,
        logger=logging.getLogger("test"),
    )


def _write_recipe(root: Path, recipe_id: str) -> tuple[Path, Path, Dict[str, Any]]:
    """Write a recipe JSON + preview image; return (json_path, image_path, data)."""
    recipes_dir = root / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)
    image_path = recipes_dir / f"{recipe_id}.webp"
    image_path.write_bytes(f"{recipe_id}-image".encode())
    json_path = recipes_dir / f"{recipe_id}.recipe.json"
    recipe_data: Dict[str, Any] = {
        "id": recipe_id,
        "title": f"Recipe {recipe_id}",
        "file_path": str(image_path),
        "loras": [],
    }
    json_path.write_text(json.dumps(recipe_data), encoding="utf-8")
    return json_path, image_path, recipe_data


def _write_json_only_recipe(root: Path, recipe_id: str) -> tuple[Path, Dict[str, Any]]:
    """Write a recipe JSON whose preview image does NOT exist."""
    recipes_dir = root / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)
    json_path = recipes_dir / f"{recipe_id}.recipe.json"
    recipe_data: Dict[str, Any] = {
        "id": recipe_id,
        "title": f"Recipe {recipe_id}",
        "file_path": str(recipes_dir / f"{recipe_id}.missing.webp"),
        "loras": [],
    }
    json_path.write_text(json.dumps(recipe_data), encoding="utf-8")
    return json_path, recipe_data


def _staging_parent() -> Path:
    # Resolve through the module namespace so the conftest settings-dir
    # isolation patch takes effect at call time.
    return Path(settings_paths.get_settings_dir()) / PENDING_DELETE_DIR_NAME


def _batch_dirs() -> List[Path]:
    parent = _staging_parent()
    if not parent.is_dir():
        return []
    return [p for p in parent.iterdir() if p.is_dir()]


# ---------------------------------------------------------------------------
# (1) delete_recipe with undo enabled -> staged JSON + image, originals gone,
#     payload batch_id set, manifest recipe_snapshot present
# ---------------------------------------------------------------------------
async def test_delete_recipe_stages_json_and_image(tmp_path: Path) -> None:
    scanner = RecipeScannerStub(tmp_path)
    json_path, image_path, recipe_data = _write_recipe(tmp_path, "r1")
    scanner.register_recipe("r1", json_path)
    json_bytes = json_path.read_bytes()
    image_bytes = image_path.read_bytes()

    result = await _make_service().delete_recipe(
        recipe_scanner=scanner, recipe_id="r1"
    )

    assert isinstance(result, PersistenceResult)
    batch_id = result.payload["batch_id"]
    assert batch_id is not None

    # JSON + image exist in the global staging dir; originals removed.
    batch_dir = _staging_parent() / batch_id
    assert batch_dir.is_dir()
    assert not json_path.exists()
    assert not image_path.exists()

    # QA: staged copies match the original bytes.
    assert (batch_dir / json_path.name).read_bytes() == json_bytes
    assert (batch_dir / image_path.name).read_bytes() == image_bytes

    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["batch_id"] == batch_id
    assert manifest["kind"] == "recipe"
    assert manifest["model_type"] is None
    assert manifest["state"] == "staged"
    assert manifest["recipe_snapshot"] == recipe_data
    assert manifest["model_snapshot"] is None
    assert len(manifest["entries"]) == 2
    originals = {entry["original"] for entry in manifest["entries"]}
    assert originals == {str(json_path), str(image_path)}

    # Scanner cache removal still runs.
    assert scanner.removed == ["r1"]


# ---------------------------------------------------------------------------
# (2) recipe with missing preview image -> only JSON staged, no crash
# ---------------------------------------------------------------------------
async def test_delete_recipe_skips_missing_preview_image(tmp_path: Path) -> None:
    scanner = RecipeScannerStub(tmp_path)
    json_path, recipe_data = _write_json_only_recipe(tmp_path, "r2")
    scanner.register_recipe("r2", json_path)

    result = await _make_service().delete_recipe(
        recipe_scanner=scanner, recipe_id="r2"
    )

    batch_id = result.payload["batch_id"]
    assert batch_id is not None
    batch_dir = _staging_parent() / batch_id
    assert batch_dir.is_dir()
    assert (batch_dir / "r2.recipe.json").read_text(encoding="utf-8") == json.dumps(
        recipe_data
    )

    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["entries"]) == 1
    assert manifest["recipe_snapshot"] == recipe_data

    assert not json_path.exists()
    assert scanner.removed == ["r2"]


# ---------------------------------------------------------------------------
# (4) bulk_delete with 2 ids -> single batch_id, merged manifest holds all
#     recipes, re-anchored expires_at; manifest-only merge: each staged copy
#     stays in ITS OWN batch dir (loser dir retained as storage)
# ---------------------------------------------------------------------------
async def test_bulk_delete_merges_into_single_batch(tmp_path: Path) -> None:
    scanner = RecipeScannerStub(tmp_path)
    json_a, img_a, data_a = _write_recipe(tmp_path, "ra")
    json_b, img_b, data_b = _write_recipe(tmp_path, "rb")
    scanner.register_recipe("ra", json_a)
    scanner.register_recipe("rb", json_b)
    json_a_bytes = json_a.read_bytes()
    image_a_bytes = img_a.read_bytes()
    json_b_bytes = json_b.read_bytes()
    image_b_bytes = img_b.read_bytes()
    before = int(time.time())

    result = await _make_service().bulk_delete(
        recipe_scanner=scanner, recipe_ids=["ra", "rb"]
    )

    batch_id = result.payload["batch_id"]
    assert batch_id is not None
    assert "batch_ids" not in result.payload
    # Manifest-only merge: the winner batch dir plus the loser storage dir
    # (stamped merged_into) both remain.
    assert len(_batch_dirs()) == 2

    batch_dir = _staging_parent() / batch_id
    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["batch_id"] == batch_id
    assert len(manifest["entries"]) == 4
    loser_dir = _staging_parent() / next(
        d for d in _batch_dirs() if d.name != batch_id
    )

    # Re-anchored expires_at: now + TTL at merge time (not the earlier of the
    # two staged expiries). Loose window avoids any timing flakiness.
    assert (
        before + PENDING_DELETE_TTL_SECONDS - 2
        <= manifest["expires_at"]
        <= int(time.time()) + PENDING_DELETE_TTL_SECONDS + 2
    )

    # Both recipes' staged copies live under their OWN batch dirs, byte-
    # identical to the originals - no file was ever moved.
    winner_files = {
        f.name
        for f in batch_dir.iterdir()
        if f.is_file() and f.name != "manifest.json"
    }
    loser_files = {
        f.name
        for f in loser_dir.iterdir()
        if f.is_file() and f.name != "manifest.json"
    }
    assert winner_files == {"ra.recipe.json", "ra.webp"}
    assert loser_files == {"rb.recipe.json", "rb.webp"}
    assert (batch_dir / "ra.recipe.json").read_bytes() == json_a_bytes
    assert (batch_dir / "ra.webp").read_bytes() == image_a_bytes
    assert (loser_dir / "rb.recipe.json").read_bytes() == json_b_bytes
    assert (loser_dir / "rb.webp").read_bytes() == image_b_bytes
    assert manifest.get("merged_sources") == [str(loser_dir)]

    # Originals removed; both snapshots present.
    assert not json_a.exists()
    assert not json_b.exists()
    assert manifest["recipe_snapshot"] in (data_a, data_b)
    assert all(entry["restored"] is False for entry in manifest["entries"])

    assert scanner.bulk_removed == ["ra", "rb"]


# ---------------------------------------------------------------------------
# (5) merge failure fallback -> batch_ids array of length 2, batches intact
# ---------------------------------------------------------------------------
async def test_bulk_delete_merge_failure_falls_back_to_batch_ids(
    tmp_path: Path, monkeypatch
) -> None:
    scanner = RecipeScannerStub(tmp_path)
    json_a, _img_a, _data_a = _write_recipe(tmp_path, "ra")
    json_b, _img_b, _data_b = _write_recipe(tmp_path, "rb")
    scanner.register_recipe("ra", json_a)
    scanner.register_recipe("rb", json_b)

    # Simulate a merge that cannot resolve the winner batch (the only real
    # failure mode since the merge no longer moves files): the caller must
    # fall back to the constituent batch_ids array.
    from py.services.pending_delete_service import get_pending_delete_service

    service = await get_pending_delete_service()

    async def _merge_unresolvable(_ids) -> None:
        return None

    monkeypatch.setattr(service, "merge_batches", _merge_unresolvable)

    result = await _make_service().bulk_delete(
        recipe_scanner=scanner, recipe_ids=["ra", "rb"]
    )

    batch_ids = result.payload["batch_ids"]
    assert "batch_id" not in result.payload
    assert len(batch_ids) == 2
    assert len(_batch_dirs()) == 2, "both constituent batches stay intact"

    # Each constituent batch is complete and individually undoable.
    for batch_id in batch_ids:
        batch_dir = _staging_parent() / batch_id
        assert batch_dir.is_dir()
        assert (batch_dir / "manifest.json").exists()
        assert any(entry["original"] == str(json_a) or entry["original"] == str(json_b) for entry in json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))["entries"])

    assert not json_a.exists()
    assert not json_b.exists()
    assert scanner.bulk_removed == ["ra", "rb"]
