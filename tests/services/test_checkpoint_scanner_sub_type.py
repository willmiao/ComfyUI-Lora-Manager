"""Tests for CheckpointScanner sub_type resolution."""

import json
import os
import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from py.services.checkpoint_scanner import CheckpointScanner
from py.services.model_cache import ModelCache
from py.services.model_hash_index import ModelHashIndex
from py.utils.models import CheckpointMetadata


class TestCheckpointScannerSubType:
    """Test CheckpointScanner sub_type resolution logic."""

    def create_scanner(self):
        """Create scanner with no async initialization."""
        # Create scanner without calling __init__ to avoid async issues
        scanner = object.__new__(CheckpointScanner)
        scanner.model_type = "checkpoint"
        scanner.model_class = CheckpointMetadata
        scanner.file_extensions = {'.ckpt', '.safetensors'}
        scanner._hash_index = MagicMock()
        return scanner

    def test_resolve_sub_type_checkpoint_root(self):
        """_resolve_sub_type should return 'checkpoint' for checkpoints_roots."""
        scanner = self.create_scanner()
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        original_unet_roots = getattr(config_module.config, 'unet_roots', None)
        
        try:
            config_module.config.checkpoints_roots = ["/models/checkpoints"]
            config_module.config.unet_roots = ["/models/unet"]
            
            result = scanner._resolve_sub_type("/models/checkpoints")
            assert result == "checkpoint"
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots
            if original_unet_roots is not None:
                config_module.config.unet_roots = original_unet_roots

    def test_resolve_sub_type_unet_root(self):
        """_resolve_sub_type should return 'diffusion_model' for unet_roots."""
        scanner = self.create_scanner()
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        original_unet_roots = getattr(config_module.config, 'unet_roots', None)
        
        try:
            config_module.config.checkpoints_roots = ["/models/checkpoints"]
            config_module.config.unet_roots = ["/models/unet"]
            
            result = scanner._resolve_sub_type("/models/unet")
            assert result == "diffusion_model"
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots
            if original_unet_roots is not None:
                config_module.config.unet_roots = original_unet_roots

    def test_resolve_sub_type_none_root(self):
        """_resolve_sub_type should return None for None input."""
        scanner = self.create_scanner()
        result = scanner._resolve_sub_type(None)
        assert result is None

    def test_resolve_sub_type_unknown_root(self):
        """_resolve_sub_type should return None for unknown root."""
        scanner = self.create_scanner()
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        original_unet_roots = getattr(config_module.config, 'unet_roots', None)
        
        try:
            config_module.config.checkpoints_roots = ["/models/checkpoints"]
            config_module.config.unet_roots = ["/models/unet"]
            
            result = scanner._resolve_sub_type("/models/unknown")
            assert result is None
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots
            if original_unet_roots is not None:
                config_module.config.unet_roots = original_unet_roots

    def test_adjust_metadata_sets_sub_type(self):
        """adjust_metadata should set sub_type on metadata."""
        scanner = self.create_scanner()
        
        metadata = CheckpointMetadata(
            file_name="test",
            model_name="Test",
            file_path="/models/checkpoints/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
        )
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        
        try:
            config_module.config.checkpoints_roots = ["/models/checkpoints"]
            config_module.config.unet_roots = []
            
            result = scanner.adjust_metadata(metadata, "/models/checkpoints/model.safetensors", "/models/checkpoints")
            assert result.sub_type == "checkpoint"
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots

    def test_adjust_cached_entry_sets_sub_type(self):
        """adjust_cached_entry should set sub_type on entry."""
        scanner = self.create_scanner()
        # Mock get_model_roots to return the expected roots
        scanner.get_model_roots = lambda: ["/models/unet"]
        
        entry = {
            "file_path": "/models/unet/model.safetensors",
            "model_name": "Test",
        }
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        original_unet_roots = getattr(config_module.config, 'unet_roots', None)
        
        try:
            config_module.config.checkpoints_roots = []
            config_module.config.unet_roots = ["/models/unet"]
            
            result = scanner.adjust_cached_entry(entry)
            assert result["sub_type"] == "diffusion_model"
            assert "model_type" not in result  # Removed in refactoring
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots
            if original_unet_roots is not None:
                config_module.config.unet_roots = original_unet_roots


def _make_move_scanner(ckpt_root: Path, unet_root: Path) -> CheckpointScanner:
    """Create a CheckpointScanner wired for move/sync tests without async init."""
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
    scanner._all_folders_backfill_running = False
    roots = [str(ckpt_root), str(unet_root)]
    scanner.get_model_roots = lambda: roots
    return scanner


def _set_config_roots(monkeypatch, ckpt_root: Path, unet_root: Path) -> None:
    from py import config as config_module

    monkeypatch.setattr(
        config_module.config, "checkpoints_roots", [str(ckpt_root)]
    )
    monkeypatch.setattr(config_module.config, "unet_roots", [str(unet_root)])
    monkeypatch.setattr(config_module.config, "extra_checkpoints_roots", [])
    monkeypatch.setattr(config_module.config, "extra_unet_roots", [])


def _write_model(root: Path, name: str, sub_type: str) -> str:
    model_path = root / f"{name}.safetensors"
    model_path.write_bytes(b"fake")
    (root / f"{name}.metadata.json").write_text(
        json.dumps(
            {
                "file_path": str(model_path).replace(os.sep, "/"),
                "file_name": name,
                "model_name": name,
                "sha256": "abc123",
                "sub_type": sub_type,
                "hash_status": "completed",
                "tags": [],
            }
        )
    )
    return str(model_path).replace(os.sep, "/")


@pytest.mark.asyncio
async def test_move_to_unet_root_updates_sub_type_in_cache_and_metadata(
    tmp_path, monkeypatch
):
    """Moving a checkpoint into a unet root must recalculate sub_type and
    persist it into the moved .metadata.json, so later metadata-driven cache
    syncs cannot revert the cache entry to the stale sub_type."""
    ckpt_root = tmp_path / "checkpoints"
    unet_root = tmp_path / "unet"
    ckpt_root.mkdir()
    unet_root.mkdir()
    _set_config_roots(monkeypatch, ckpt_root, unet_root)

    scanner = _make_move_scanner(ckpt_root, unet_root)
    source = _write_model(ckpt_root, "mymodel", "checkpoint")

    scanner._cache = ModelCache(
        raw_data=[
            {
                "file_path": source,
                "file_name": "mymodel",
                "model_name": "mymodel",
                "folder": "",
                "sha256": "abc123",
                "sub_type": "checkpoint",
                "tags": [],
            }
        ],
        folders=[""],
    )

    result = await scanner.move_model(source, str(unet_root).replace(os.sep, "/"))
    assert result is not None

    cache = await scanner.get_cached_data()
    entry = next(
        (e for e in cache.raw_data if e.get("file_name") == "mymodel"), None
    )
    assert entry is not None
    assert entry["sub_type"] == "diffusion_model"

    moved_metadata = json.loads(
        (unet_root / "mymodel.metadata.json").read_text()
    )
    assert moved_metadata["sub_type"] == "diffusion_model"


@pytest.mark.asyncio
async def test_sync_cache_from_metadata_does_not_revert_sub_type(
    tmp_path, monkeypatch
):
    """An opportunistic sync from a stale .metadata.json (sub_type predating a
    cross-root move) must not overwrite the location-derived cache sub_type."""
    ckpt_root = tmp_path / "checkpoints"
    unet_root = tmp_path / "unet"
    ckpt_root.mkdir()
    unet_root.mkdir()
    _set_config_roots(monkeypatch, ckpt_root, unet_root)

    scanner = _make_move_scanner(ckpt_root, unet_root)
    file_path = _write_model(unet_root, "mymodel", "diffusion_model")

    scanner._cache = ModelCache(
        raw_data=[
            {
                "file_path": file_path,
                "file_name": "mymodel",
                "model_name": "mymodel",
                "folder": "",
                "sha256": "abc123",
                "sub_type": "diffusion_model",
                "tags": [],
            }
        ],
        folders=[""],
    )

    # Stale metadata snapshot: still says 'checkpoint' (as before a move).
    stale_metadata = {
        "file_path": file_path,
        "file_name": "mymodel",
        "model_name": "mymodel Renamed",
        "sha256": "abc123",
        "sub_type": "checkpoint",
        "hash_status": "completed",
        "tags": [],
    }

    changed = await scanner.sync_cache_from_metadata(file_path, stale_metadata)
    assert changed is True  # other fields (model_name) did change

    entry = scanner._cache.raw_data[0]
    assert entry["sub_type"] == "diffusion_model"
    assert entry["model_name"] == "mymodel Renamed"
