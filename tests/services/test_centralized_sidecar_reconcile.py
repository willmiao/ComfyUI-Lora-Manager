from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from py.config import config
from py.services import model_scanner
from py.services.lora_scanner import LoraScanner
from py.services.model_cache import ModelCache
from py.services.model_scanner import ModelScanner
from py.services.persistent_model_cache import PersistentModelCache
from py.services.settings_manager import get_settings_manager
from py.utils import metadata_manager
from py.utils.sidecar_paths import get_metadata_path, reset_root_map_cache


def _normalize(path: Path | str) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture(autouse=True)
def _reset_scanner_state():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    reset_root_map_cache()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    reset_root_map_cache()


def _configure_root(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for attr in (
        "base_models_roots",
        "checkpoints_roots",
        "embeddings_roots",
        "other_roots",
        "workflows_roots",
        "wildcards_roots",
        "extra_loras_roots",
        "extra_checkpoints_roots",
        "extra_unet_roots",
        "extra_embeddings_roots",
    ):
        monkeypatch.setattr(config, attr, [], raising=False)
    monkeypatch.setattr(config, "loras_roots", [_normalize(root)], raising=False)


async def _prepare_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
):
    root.mkdir(parents=True)
    _configure_root(root, monkeypatch)
    settings = get_settings_manager()
    settings.set("sidecar_storage_mode", "centralized")
    settings.set("sidecar_storage_path", str(tmp_path / "sidecars"))
    reset_root_map_cache()

    model = root / "model.safetensors"
    model.write_bytes(b"weights")
    scanner = LoraScanner()
    await scanner._process_model_file(_normalize(model), _normalize(root))

    sidecar = Path(get_metadata_path(_normalize(model)))
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    preview = sidecar.parent / "model.preview.webp"
    preview.write_bytes(b"preview")
    payload.update(
        {
            "model_name": "Custom name",
            "notes": "keep me",
            "tags": ["custom-tag"],
            "favorite": True,
            "preview_url": _normalize(preview),
            "custom_field": "preserve",
            "civitai": {"id": 123, "modelId": 456, "custom_remote": "keep"},
        }
    )
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    entry = scanner._build_cache_entry(payload, folder="")
    scanner._cache = ModelCache(raw_data=[entry], folders=[""], all_folders=[])
    scanner._persistent_cache = PersistentModelCache(
        library_name="test",
        db_path=str(tmp_path / "models.sqlite"),
    )
    scanner._hash_index.add_entry(entry["sha256"], entry["file_path"])
    scanner._tags_count = {"custom-tag": 1}
    return scanner, model, sidecar, preview


def _count_hashes(monkeypatch: pytest.MonkeyPatch):
    calls = []
    real_calculate = model_scanner.calculate_sha256

    async def counting(path):
        calls.append(path)
        return await real_calculate(path)

    monkeypatch.setattr(model_scanner, "calculate_sha256", counting)
    monkeypatch.setattr(metadata_manager, "calculate_sha256", counting)
    return calls


@pytest.mark.asyncio
async def test_reconcile_external_move_preserves_centralized_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "library" / "loras"
    scanner, model, old_sidecar, old_preview = await _prepare_library(
        tmp_path, monkeypatch, root
    )
    target = root / "organized" / "renamed.safetensors"
    target.parent.mkdir()
    shutil.move(str(model), str(target))
    hash_calls = _count_hashes(monkeypatch)

    summary = await scanner._reconcile_cache()

    new_sidecar = Path(get_metadata_path(_normalize(target)))
    new_preview = new_sidecar.parent / "renamed.preview.webp"
    payload = json.loads(new_sidecar.read_text(encoding="utf-8"))
    assert summary["added"] == 1
    assert summary["removed"] == 1
    assert len(hash_calls) == 1
    assert payload["file_path"] == _normalize(target)
    assert payload["file_name"] == "renamed"
    assert payload["model_name"] == "Custom name"
    assert payload["notes"] == "keep me"
    assert payload["tags"] == ["custom-tag"]
    assert payload["favorite"] is True
    assert payload["custom_field"] == "preserve"
    assert payload["civitai"]["custom_remote"] == "keep"
    assert payload["preview_url"] == _normalize(new_preview)
    assert new_preview.read_bytes() == b"preview"
    assert not old_sidecar.exists()
    assert not old_preview.exists()
    assert len(scanner._cache.raw_data) == 1
    assert scanner._cache.raw_data[0]["notes"] == "keep me"
    assert scanner._cache.raw_data[0]["file_path"] == _normalize(target)


@pytest.mark.asyncio
async def test_reconcile_renamed_flat_root_preserves_centralized_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    old_root = tmp_path / "old" / "loras"
    scanner, model, old_sidecar, _old_preview = await _prepare_library(
        tmp_path, monkeypatch, old_root
    )
    new_root = tmp_path / "new" / "renamed-library"
    new_root.parent.mkdir(parents=True)
    shutil.move(str(old_root), str(new_root))
    monkeypatch.setattr(config, "loras_roots", [_normalize(new_root)], raising=False)
    reset_root_map_cache()
    hash_calls = _count_hashes(monkeypatch)

    await scanner._reconcile_cache()

    target = new_root / "model.safetensors"
    new_sidecar = Path(get_metadata_path(_normalize(target)))
    payload = json.loads(new_sidecar.read_text(encoding="utf-8"))
    assert len(hash_calls) == 1
    assert new_sidecar != old_sidecar
    assert not old_sidecar.exists()
    assert payload["notes"] == "keep me"
    assert payload["custom_field"] == "preserve"
    assert scanner._cache.raw_data[0]["file_path"] == _normalize(target)
    assert scanner._cache.raw_data[0]["notes"] == "keep me"


@pytest.mark.asyncio
async def test_reconcile_same_size_unrelated_file_hashes_once_without_relinking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "loras"
    scanner, model, old_sidecar, _old_preview = await _prepare_library(
        tmp_path, monkeypatch, root
    )
    model.unlink()
    unrelated = root / "unrelated.safetensors"
    unrelated.write_bytes(b"1234567")
    old_payload = json.loads(old_sidecar.read_text(encoding="utf-8"))
    assert unrelated.stat().st_size == old_payload["size"]
    hash_calls = _count_hashes(monkeypatch)

    await scanner._reconcile_cache()

    assert len(hash_calls) == 1
    assert json.loads(old_sidecar.read_text(encoding="utf-8"))["notes"] == "keep me"
    new_sidecar = Path(get_metadata_path(_normalize(unrelated)))
    assert json.loads(new_sidecar.read_text(encoding="utf-8"))["notes"] == ""


@pytest.mark.asyncio
async def test_reconcile_clean_library_does_not_hash_for_move_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "loras"
    scanner, _model, _sidecar, _preview = await _prepare_library(
        tmp_path, monkeypatch, root
    )

    async def fail_hash(_path):
        raise AssertionError("clean reconcile must not calculate hashes")

    monkeypatch.setattr(model_scanner, "calculate_sha256", fail_hash)
    monkeypatch.setattr(metadata_manager, "calculate_sha256", fail_hash)

    summary = await scanner._reconcile_cache()

    assert summary["added"] == 0
    assert summary["removed"] == 0
