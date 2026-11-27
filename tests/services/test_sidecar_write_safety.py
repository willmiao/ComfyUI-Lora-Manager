"""Sidecar write safety: creation must never destroy existing metadata.

Both failure modes covered here cost a real library its favourites, notes, tags
and CivitAI data: a creation path replacing a sidecar that another writer
materialised while the scan was deciding that none existed, and a migration
letting a freshly regenerated stub win a conflict just because it is newer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from py.config import config
from py.services.checkpoint_scanner import CheckpointScanner
from py.utils.metadata_manager import MetadataManager
from py.utils.sidecar_paths import resolve_metadata_path


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
async def test_exclusive_save_creates_a_missing_sidecar(tmp_path: Path):
    model = _write_model(tmp_path / "model.safetensors")

    created = await MetadataManager.save_metadata_exclusive(
        str(model), _flat_sidecar_payload(model)
    )

    assert created is True
    sidecar = Path(resolve_metadata_path(str(model)))
    assert json.loads(sidecar.read_text(encoding="utf-8"))["file_name"] == "model"


@pytest.mark.asyncio
async def test_exclusive_save_keeps_an_existing_sidecar(tmp_path: Path):
    model = _write_model(tmp_path / "model.safetensors")
    sidecar = _write_sidecar_for(
        model, _flat_sidecar_payload(model, civitai={"id": 7}, notes="keep me")
    )

    created = await MetadataManager.save_metadata_exclusive(
        str(model), _flat_sidecar_payload(model, sha256="b" * 64)
    )

    assert created is False
    stored = json.loads(sidecar.read_text(encoding="utf-8"))
    assert stored["civitai"] == {"id": 7}
    assert stored["notes"] == "keep me"
    assert stored["sha256"] == "a" * 64, "the existing hash must survive"


@pytest.mark.asyncio
async def test_default_metadata_creation_adopts_the_existing_sidecar(tmp_path: Path):
    """A sidecar that appears mid-creation wins over the generated stub."""

    model = _write_model(tmp_path / "model.safetensors")
    sidecar = _write_sidecar_for(
        model,
        _flat_sidecar_payload(
            model, civitai={"id": 1234}, notes="keep me", tags=["portrait"]
        ),
    )

    metadata = await MetadataManager.create_default_metadata(str(model))

    assert metadata is not None
    assert metadata.notes == "keep me"
    assert metadata.civitai == {"id": 1234}

    stored = json.loads(sidecar.read_text(encoding="utf-8"))
    assert stored["notes"] == "keep me"
    assert stored["civitai"] == {"id": 1234}


@pytest.mark.asyncio
async def test_checkpoint_creation_adopts_the_existing_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "checkpoints"
    root.mkdir()
    model = _write_model(root / "model.safetensors")
    _checkpoint_roots(monkeypatch, root)

    sidecar = _write_sidecar_for(
        model,
        _flat_sidecar_payload(
            model, civitai={"id": 4321}, notes="keep me", tags=["anime"]
        ),
    )

    scanner = CheckpointScanner()
    metadata = await scanner._create_default_metadata(_normalize(model))

    assert metadata is not None
    assert metadata.notes == "keep me"
    assert metadata.hash_status == "completed", "the existing hash state must be kept"

    stored = json.loads(sidecar.read_text(encoding="utf-8"))
    assert stored["notes"] == "keep me"
    assert stored["civitai"] == {"id": 4321}
    assert stored["sha256"] == "a" * 64
