"""Tests for ModelScanner.move_model robustness.

Covers the failure mode from issue #1126: a move whose source file is
already gone (previous move succeeded but cache/metadata were left stale,
or a duplicate/concurrent move request arrived) must not fail with a raw
FileNotFoundError and leave the model card pointing at empty paths.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from py import config as config_module
from py.services.checkpoint_scanner import CheckpointScanner
from py.services.model_cache import ModelCache
from py.services.model_hash_index import ModelHashIndex
from py.utils.models import CheckpointMetadata


def _normalize(path) -> str:
    return str(path).replace(os.sep, "/")


def _make_scanner(roots) -> CheckpointScanner:
    """Create a CheckpointScanner wired for move tests without async init."""
    scanner = object.__new__(CheckpointScanner)
    scanner.model_type = "checkpoint"
    scanner.model_class = CheckpointMetadata
    scanner.file_extensions = {".safetensors"}
    scanner._cache = None
    scanner._cache_version = 0
    scanner._hash_index = ModelHashIndex()
    scanner._tags_count = {}
    scanner._excluded_models = []
    scanner._is_initializing = False
    scanner._persistent_cache = MagicMock()
    scanner._name_display_mode = "model_name"
    scanner._cancel_requested = False
    scanner._move_locks = {}
    scanner._all_folders_backfill_running = False
    scanner.get_model_roots = lambda: [_normalize(r) for r in roots]
    return scanner


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "checkpoints"
    root.mkdir()
    monkeypatch.setattr(config_module.config, "checkpoints_roots", [str(root)])
    monkeypatch.setattr(config_module.config, "unet_roots", [])
    monkeypatch.setattr(config_module.config, "extra_checkpoints_roots", [])
    monkeypatch.setattr(config_module.config, "extra_unet_roots", [])
    return root


def _cache_entry(file_path: str, name: str) -> dict:
    return {
        "file_path": file_path,
        "file_name": name,
        "model_name": name,
        "folder": "",
        "sha256": "abc123",
        "sub_type": "checkpoint",
        "tags": [],
    }


def _write_metadata(sidecar: Path, file_path: str, name: str) -> None:
    sidecar.write_text(
        json.dumps(
            {
                "file_path": file_path,
                "file_name": name,
                "model_name": name,
                "sha256": "abc123",
                "sub_type": "checkpoint",
                "hash_status": "completed",
                "tags": [],
            }
        )
    )


@pytest.mark.asyncio
async def test_move_reconciles_when_source_already_moved(library: Path):
    """Source missing but the file sits at the natural target: repair cache
    and metadata instead of failing with WinError 2."""
    old_dir = library / "old"
    old_dir.mkdir()
    new_dir = library / "new"
    new_dir.mkdir()

    old_path = _normalize(old_dir / "model.safetensors")
    moved = new_dir / "model.safetensors"
    moved.write_bytes(b"weights")
    _write_metadata(new_dir / "model.metadata.json", old_path, "model")

    scanner = _make_scanner([library])
    scanner._cache = ModelCache(raw_data=[_cache_entry(old_path, "model")], folders=[""])

    result = await scanner.move_model(old_path, _normalize(new_dir))

    assert result is not None
    assert result["new_path"] == _normalize(moved)

    cache = await scanner.get_cached_data()
    assert [item["file_path"] for item in cache.raw_data] == [_normalize(moved)]

    saved = json.loads((new_dir / "model.metadata.json").read_text())
    assert saved["file_path"] == _normalize(moved)


@pytest.mark.asyncio
async def test_move_reconciles_via_hash_index_when_file_elsewhere(library: Path):
    """Source missing and the file is NOT at the requested target (a previous
    move took it elsewhere): the hash index locates it, and the stale cache
    entry is reused when no sidecar exists at the new location."""
    old_dir = library / "old"
    old_dir.mkdir()
    elsewhere = library / "elsewhere"
    elsewhere.mkdir()
    moved = elsewhere / "model.safetensors"
    moved.write_bytes(b"weights")

    old_path = _normalize(old_dir / "model.safetensors")

    scanner = _make_scanner([library])
    scanner._cache = ModelCache(raw_data=[_cache_entry(old_path, "model")], folders=[""])
    scanner._hash_index.add_entry("abc123", _normalize(moved))

    result = await scanner.move_model(old_path, _normalize(library / "target"))

    assert result is not None
    assert result["new_path"] == _normalize(moved)

    cache = await scanner.get_cached_data()
    entries = [item for item in cache.raw_data]
    assert [item["file_path"] for item in entries] == [_normalize(moved)]
    # Card data preserved from the stale cache entry
    assert entries[0]["model_name"] == "model"
    assert entries[0]["sha256"] == "abc123"


@pytest.mark.asyncio
async def test_move_returns_none_when_source_missing_and_nowhere_found(library: Path):
    """Source gone and no trace of the file anywhere: fail with a clear
    error, leaving the cache untouched (a rescan will clean it up)."""
    old_path = _normalize(library / "ghost.safetensors")

    scanner = _make_scanner([library])
    scanner._cache = ModelCache(raw_data=[_cache_entry(old_path, "ghost")], folders=[""])

    result = await scanner.move_model(old_path, _normalize(library / "target"))

    assert result is None
    cache = await scanner.get_cached_data()
    assert [item["file_path"] for item in cache.raw_data] == [old_path]


@pytest.mark.asyncio
async def test_concurrent_moves_of_same_source_are_serialized(library: Path):
    """Two simultaneous move requests for the same file: one performs the
    move, the other reconciles — no FileNotFoundError, no duplicate cache
    entries."""
    source_file = library / "model.safetensors"
    source_file.write_bytes(b"weights")
    source = _normalize(source_file)
    _write_metadata(library / "model.metadata.json", source, "model")

    target_dir = library / "target"
    target_file = target_dir / "model.safetensors"

    scanner = _make_scanner([library])
    scanner._cache = ModelCache(raw_data=[_cache_entry(source, "model")], folders=[""])

    results = await asyncio.gather(
        scanner.move_model(source, _normalize(target_dir)),
        scanner.move_model(source, _normalize(target_dir)),
    )

    assert all(r is not None for r in results)
    assert target_file.exists()
    assert not source_file.exists()

    cache = await scanner.get_cached_data()
    paths = [item["file_path"] for item in cache.raw_data]
    assert paths == [_normalize(target_file)]

    saved = json.loads((target_dir / "model.metadata.json").read_text())
    assert saved["file_path"] == _normalize(target_file)


@pytest.mark.asyncio
async def test_move_through_symlinked_directory(library: Path, tmp_path: Path):
    """Moving a model that lives under a symlinked directory uses the
    business path: the file leaves the physical directory, the symlink
    itself stays intact, and the cache records the unresolved path."""
    real_dir = tmp_path / "real_root"
    real_dir.mkdir()
    link_dir = library / "linked"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    model = real_dir / "model.safetensors"
    model.write_bytes(b"weights")
    source = _normalize(link_dir / "model.safetensors")
    _write_metadata(real_dir / "model.metadata.json", source, "model")

    target_dir = library / "target"
    target_file = target_dir / "model.safetensors"

    scanner = _make_scanner([library])
    scanner._cache = ModelCache(raw_data=[_cache_entry(source, "model")], folders=[""])

    result = await scanner.move_model(source, _normalize(target_dir))

    assert result is not None
    assert result["new_path"] == _normalize(target_file)
    assert target_file.exists()
    assert not model.exists()
    assert link_dir.is_symlink()

    cache = await scanner.get_cached_data()
    assert [item["file_path"] for item in cache.raw_data] == [_normalize(target_file)]
