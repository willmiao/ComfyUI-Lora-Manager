"""Regression tests for the reconcile-time ``file_name`` repair (issue #1112).

Libraries already corrupted by the legacy ``.civitai.info`` migration keep the
truncated name in their sidecars and SQLite snapshot: the incremental refresh
skips cached paths and startup hydrates rows as-is, so the wrong name never
heals. A plain Refresh must repair those rows in place, exactly once.
"""

import json
import os
from pathlib import Path

import pytest

from py.services import model_scanner
from py.services.lora_scanner import LoraScanner
from py.services.model_cache import ModelCache
from py.services.model_scanner import ModelScanner
from py.services.persistent_model_cache import PersistentModelCache
from py.utils.metadata_manager import MetadataManager

DOTTED_STEM = "lora-sd1.5-backlight_slider_v10"
TRUNCATED_STEM = "lora-sd1"


def _normalize(path: Path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


async def _prepare_corrupted_library(tmp_path: Path, monkeypatch):
    """Build a library whose sidecar + cache carry the truncated stem."""
    loras_root = tmp_path / "loras"
    loras_root.mkdir()
    model_file = loras_root / f"{DOTTED_STEM}.safetensors"
    model_file.write_text("fake lora weights", encoding="utf-8")

    normalized_root = _normalize(loras_root)
    monkeypatch.setattr(
        model_scanner.config, "loras_roots", [normalized_root], raising=False
    )
    monkeypatch.setattr(
        model_scanner.config, "extra_loras_roots", [], raising=False
    )

    scanner = LoraScanner()
    normalized_file = _normalize(model_file)
    entry = await scanner._process_model_file(normalized_file, normalized_root)
    assert entry is not None

    # Simulate the pre-fix migration output: sidecar and cache both hold the
    # stem cut at the "1.5" dot.
    metadata, _ = await MetadataManager.load_metadata(normalized_file, scanner.model_class)
    metadata.file_name = TRUNCATED_STEM
    await MetadataManager.save_metadata(normalized_file, metadata)
    entry["file_name"] = TRUNCATED_STEM

    scanner._cache = ModelCache(
        raw_data=[entry],
        folders=[],
        all_folders=[],
        name_display_mode="file_name",
    )
    scanner._persistent_cache = PersistentModelCache(
        library_name="test", db_path=str(tmp_path / "models.sqlite")
    )
    return scanner, model_file, entry


@pytest.mark.asyncio
async def test_reconcile_repairs_truncated_file_name(tmp_path, monkeypatch):
    scanner, model_file, entry = await _prepare_corrupted_library(tmp_path, monkeypatch)
    assert entry["file_name"] == TRUNCATED_STEM

    await scanner._reconcile_cache()

    # In-memory cache entry.
    assert entry["file_name"] == DOTTED_STEM

    # On-disk sidecar (repaired by MetadataManager normalization).
    sidecar = model_file.parent / f"{DOTTED_STEM}.metadata.json"
    saved = json.loads(sidecar.read_text(encoding="utf-8"))
    assert saved["file_name"] == DOTTED_STEM

    # Targeted SQL delta, so the fix survives a restart.
    persisted = scanner._persistent_cache.load_cache(scanner.model_type)
    assert persisted is not None
    rows = [i for i in persisted.raw_data if i["file_path"] == _normalize(model_file)]
    assert len(rows) == 1
    assert rows[0]["file_name"] == DOTTED_STEM


@pytest.mark.asyncio
async def test_reconcile_repair_runs_once(tmp_path, monkeypatch):
    scanner, _model_file, _entry = await _prepare_corrupted_library(
        tmp_path, monkeypatch
    )

    calls = {"sync": 0, "load": 0}
    original_sync = scanner._sync_cache_from_metadata_impl
    original_load = MetadataManager.load_metadata

    async def counting_sync(file_path, metadata_dict):
        calls["sync"] += 1
        return await original_sync(file_path, metadata_dict)

    async def counting_load(*args, **kwargs):
        calls["load"] += 1
        return await original_load(*args, **kwargs)

    monkeypatch.setattr(scanner, "_sync_cache_from_metadata_impl", counting_sync)
    monkeypatch.setattr(MetadataManager, "load_metadata", counting_load)

    await scanner._reconcile_cache()
    assert calls == {"sync": 1, "load": 1}

    # The mismatch is gone, so a second refresh must not touch metadata again.
    await scanner._reconcile_cache()
    assert calls == {"sync": 1, "load": 1}


@pytest.mark.asyncio
async def test_reconcile_clean_library_never_reads_metadata(tmp_path, monkeypatch):
    """The repair probe must cost one string compare, not a metadata read."""
    scanner, _model_file, _entry = await _prepare_corrupted_library(
        tmp_path, monkeypatch
    )
    await scanner._reconcile_cache()

    calls = {"load": 0}
    original_load = MetadataManager.load_metadata

    async def counting_load(*args, **kwargs):
        calls["load"] += 1
        return await original_load(*args, **kwargs)

    monkeypatch.setattr(MetadataManager, "load_metadata", counting_load)

    await scanner._reconcile_cache()
    assert calls["load"] == 0
