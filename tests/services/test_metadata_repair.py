"""Metadata repairs: hashes that were computed, previews that are on disk.

Both facts are known to the application but were previously dropped on the
floor: an interrupted or failed CivitAI lookup discarded the hash it had just
spent minutes computing, and a sidecar without ``preview_url`` left the card on
its placeholder although the image was sitting next to it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from py.config import config
from py.services.checkpoint_scanner import CheckpointScanner
from py.services.metadata_sync_service import MetadataSyncService
from py.services.settings_manager import get_settings_manager
from py.utils.sidecar_paths import reset_root_map_cache, resolve_metadata_path, root_mirror_component


def _normalize(path) -> str:
    return str(path).replace(os.sep, "/")


def _write_model(path: Path, content: bytes = b"weights") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _flat_sidecar_payload(model: Path, **overrides) -> dict:
    """Minimal payload that satisfies the required metadata schema."""

    stat = model.stat()
    payload = {
        "file_name": model.stem,
        "model_name": model.stem,
        "file_path": _normalize(model),
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "sha256": "a" * 64,
        "base_model": "Unknown",
        "preview_url": "",
    }
    payload.update(overrides)
    return payload


def _write_sidecar_for(model: Path, payload: dict) -> Path:
    sidecar = Path(resolve_metadata_path(str(model)))
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    return sidecar


def _checkpoint_roots(monkeypatch: pytest.MonkeyPatch, root: Path) -> str:
    normalized_root = _normalize(root)
    monkeypatch.setattr(
        config, "base_models_roots", [normalized_root], raising=False
    )
    monkeypatch.setattr(
        config, "checkpoints_roots", [normalized_root], raising=False
    )
    monkeypatch.setattr(config, "unet_roots", [], raising=False)
    return normalized_root


@pytest.mark.asyncio
async def test_scan_heals_a_missing_preview_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A sidecar without preview_url is repaired from the file on disk."""

    root = tmp_path / "checkpoints"
    root.mkdir()
    model = _write_model(root / "model.safetensors")

    normalized_root = _checkpoint_roots(monkeypatch, root)

    sidecar_root = tmp_path / "sidecars"
    settings = get_settings_manager()
    settings.set("sidecar_storage_mode", "centralized")
    settings.set("sidecar_storage_path", str(sidecar_root))
    reset_root_map_cache()

    try:
        component = root_mirror_component(
            normalized_root, sidecar_root=str(sidecar_root)
        )
        mirror = sidecar_root / component
        mirror.mkdir(parents=True, exist_ok=True)
        (mirror / "model.preview.webp").write_bytes(b"preview")
        stale_payload = _flat_sidecar_payload(model, preview_url="")
        sidecar = mirror / "model.metadata.json"
        sidecar.write_text(json.dumps(stale_payload), encoding="utf-8")

        scanner = CheckpointScanner()
        await scanner._initialize_cache()
        cache = await scanner.get_cached_data()

        entry = next(
            item
            for item in cache.raw_data
            if item["file_path"].endswith("model.safetensors")
        )
        assert entry["preview_url"].endswith("model.preview.webp")

        stored = json.loads(sidecar.read_text(encoding="utf-8"))
        assert stored["preview_url"].endswith("model.preview.webp")
    finally:
        reset_root_map_cache()


@pytest.mark.asyncio
async def test_relink_persists_the_hash_it_computed(tmp_path: Path):
    """The expensive hash survives a relink that never completes."""

    model = _write_model(tmp_path / "model.safetensors", b"x" * 64)
    _write_sidecar_for(model, _flat_sidecar_payload(model, sha256=""))

    payload = await MetadataSyncService._rebuild_relink_payload(
        _normalize(model), {}
    )

    assert payload["sha256"]
    assert payload["hash_status"] == "completed"

    stored = json.loads(
        Path(resolve_metadata_path(str(model))).read_text(encoding="utf-8")
    )
    assert stored["sha256"] == payload["sha256"]
    assert stored["hash_status"] == "completed"


@pytest.mark.asyncio
async def test_relink_does_not_create_a_partial_sidecar_when_none_exists(
    tmp_path: Path,
):
    """A missing sidecar is recreated only by the complete relink update."""

    model = _write_model(tmp_path / "model.safetensors", b"x" * 64)
    sidecar = Path(resolve_metadata_path(str(model)))

    payload = await MetadataSyncService._rebuild_relink_payload(
        _normalize(model), {}
    )

    assert payload["sha256"]
    assert payload["hash_status"] == "completed"
    assert not sidecar.exists()
