"""Centralized sidecar storage: lifecycle flows (delete/move/rename/scans)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from py.config import config
from py.services.checkpoint_scanner import CheckpointScanner
from py.services.model_lifecycle_service import (
    ModelLifecycleService,
    delete_model_artifacts,
)
from py.services.pending_delete_service import PendingDeleteService
from py.services.settings_manager import get_settings_manager
from py.utils.metadata_manager import MetadataManager
from py.utils.sidecar_paths import root_mirror_component


def _normalize(path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture
def library_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Single checkpoint root under tmp_path; every other root emptied."""

    root = tmp_path / "checkpoints"
    root.mkdir()
    for attr, value in (
        ("loras_roots", []),
        ("base_models_roots", [str(root)]),
        ("checkpoints_roots", [str(root)]),
        ("embeddings_roots", []),
        ("other_roots", []),
        ("extra_loras_roots", []),
        ("extra_checkpoints_roots", []),
        ("extra_unet_roots", []),
        ("extra_embeddings_roots", []),
    ):
        monkeypatch.setattr(config, attr, value, raising=False)
    return root


@pytest.fixture
def centralized(library_root: Path, tmp_path: Path) -> Path:
    """Enable centralized mode rooted at tmp_path/sidecars."""

    sidecar_root = tmp_path / "sidecars"
    settings = get_settings_manager()
    settings.set("sidecar_storage_mode", "centralized")
    settings.set("sidecar_storage_path", str(sidecar_root))
    return sidecar_root


def _mirror_dir(library_root: Path, sidecar_root: Path, *rel: str) -> Path:
    """Expected mirror directory for a library-relative path."""

    library = get_settings_manager().get_active_library_name()
    component = root_mirror_component(str(library_root))
    return sidecar_root.joinpath(library, component, *rel)


def _write_sidecar(
    mirror_dir: Path,
    stem: str,
    *,
    file_path: str,
    preview_name: str | None = None,
    extra: Dict[str, Any] | None = None,
) -> Path:
    mirror_dir.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "file_name": stem,
        "file_path": _normalize(file_path),
    }
    if preview_name:
        payload["preview_url"] = _normalize(mirror_dir / preview_name)
        (mirror_dir / preview_name).write_bytes(b"preview")
    if extra:
        payload.update(extra)
    metadata_path = mirror_dir / f"{stem}.metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    return metadata_path


@pytest.mark.asyncio
async def test_delete_model_artifacts_centralized(
    library_root: Path, centralized: Path
):
    model = library_root / "model.safetensors"
    model.write_bytes(b"weights")
    mirror = _mirror_dir(library_root, centralized)
    _write_sidecar(mirror, "model", file_path=model, preview_name="model.preview.webp")

    deleted = await delete_model_artifacts(str(library_root), "model")

    assert not model.exists()
    assert not (mirror / "model.metadata.json").exists()
    assert not (mirror / "model.preview.webp").exists()
    assert any(path.endswith("model.safetensors") for path in deleted)
    assert "model.metadata.json" in deleted
    assert "model.preview.webp" in deleted


@pytest.mark.asyncio
async def test_delete_model_artifacts_alongside_still_siblings(
    library_root: Path,
):
    """Alongside mode (default) keeps deleting sidecars next to the model."""

    model = library_root / "model.safetensors"
    model.write_bytes(b"weights")
    sidecar = library_root / "model.metadata.json"
    sidecar.write_text("{}", encoding="utf-8")
    preview = library_root / "model.preview.webp"
    preview.write_bytes(b"preview")

    await delete_model_artifacts(str(library_root), "model")

    assert not model.exists()
    assert not sidecar.exists()
    assert not preview.exists()


def test_enumerate_model_artifacts_centralized(
    library_root: Path, centralized: Path
):
    model = library_root / "model.safetensors"
    model.write_bytes(b"weights")
    mirror = _mirror_dir(library_root, centralized)
    _write_sidecar(mirror, "model", file_path=model, preview_name="model.preview.png")

    service = PendingDeleteService.__new__(PendingDeleteService)
    artifacts = service._enumerate_model_artifacts(
        str(library_root), "model", ".safetensors"
    )

    assert artifacts == [
        os.path.abspath(str(model)),
        os.path.abspath(str(mirror / "model.metadata.json")),
        os.path.abspath(str(mirror / "model.preview.png")),
    ]


class _RecordingScanner:
    def __init__(self):
        self.calls: List[tuple] = []
        self.model_type = "lora"

    async def update_single_model_cache(self, old_path, new_path, metadata):
        self.calls.append((old_path, new_path, metadata))


class _PassthroughMetadataManager:
    async def save_metadata(self, path: str, metadata):
        await MetadataManager.save_metadata(path, metadata)
        return True


async def _json_metadata_loader(path: str) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.asyncio
async def test_rename_model_centralized(library_root: Path, centralized: Path):
    model = library_root / "model.safetensors"
    model.write_bytes(b"weights")
    mirror = _mirror_dir(library_root, centralized)
    _write_sidecar(mirror, "model", file_path=model, preview_name="model.preview.webp")

    service = ModelLifecycleService(
        scanner=_RecordingScanner(),
        metadata_manager=_PassthroughMetadataManager(),
        metadata_loader=_json_metadata_loader,
    )

    result = await service.rename_model(
        file_path=_normalize(model), new_file_name="renamed"
    )

    assert result["success"] is True
    renamed = library_root / "renamed.safetensors"
    assert renamed.exists()
    assert not model.exists()

    # Mirror sidecar/preview renamed with the model; nothing left alongside.
    assert (mirror / "renamed.metadata.json").exists()
    assert (mirror / "renamed.preview.webp").exists()
    assert not (mirror / "model.metadata.json").exists()
    assert not (mirror / "model.preview.webp").exists()
    assert not (library_root / "renamed.metadata.json").exists()
    assert not (library_root / "renamed.preview.webp").exists()

    saved = json.loads((mirror / "renamed.metadata.json").read_text())
    assert saved["file_name"] == "renamed"
    assert saved["file_path"].endswith("renamed.safetensors")
    assert saved["preview_url"].endswith("renamed.preview.webp")
    assert str(mirror).replace(os.sep, "/") in saved["preview_url"]


@pytest.mark.asyncio
async def test_move_model_centralized(
    library_root: Path, centralized: Path, monkeypatch: pytest.MonkeyPatch
):
    source_dir = library_root / "old"
    source_dir.mkdir()
    model = source_dir / "model.safetensors"
    model.write_bytes(b"weights")
    target_dir = library_root / "new"

    old_mirror = _mirror_dir(library_root, centralized, "old")
    _write_sidecar(
        old_mirror, "model", file_path=model, preview_name="model.preview.webp"
    )

    scanner = CheckpointScanner()
    monkeypatch.setattr(
        scanner, "update_single_model_cache", AsyncMock(return_value=True)
    )

    result = await scanner.move_model(_normalize(model), _normalize(target_dir))

    assert result is not None
    moved_model = target_dir / "model.safetensors"
    assert moved_model.exists()
    assert not model.exists()

    new_mirror = _mirror_dir(library_root, centralized, "new")
    assert (new_mirror / "model.metadata.json").exists()
    assert (new_mirror / "model.preview.webp").exists()
    assert not (old_mirror / "model.metadata.json").exists()
    assert not (old_mirror / "model.preview.webp").exists()

    saved = json.loads((new_mirror / "model.metadata.json").read_text())
    assert saved["file_path"].endswith("new/model.safetensors")
    assert saved["preview_url"].endswith("model.preview.webp")
    assert str(new_mirror).replace(os.sep, "/") in saved["preview_url"]


class _FakeCache:
    def __init__(self, raw_data: List[Dict[str, Any]]):
        self.raw_data = raw_data
        self.all_folders: List[str] = []
        self.folders: List[str] = []

    def remove_from_version_index(self, _item) -> None:
        pass

    def rebuild_version_index(self) -> None:
        pass

    async def resort(self) -> None:
        pass


@pytest.mark.asyncio
async def test_rename_known_folder_centralized(
    library_root: Path, centralized: Path, monkeypatch: pytest.MonkeyPatch
):
    # The caller (ModelFileService.rename_folder) has already renamed the
    # model directory on disk when the scanner is asked to re-key records.
    old_dir = library_root / "oldfolder"
    new_dir = library_root / "newfolder"
    new_dir.mkdir()
    model = new_dir / "model.safetensors"
    model.write_bytes(b"weights")

    old_model_path = old_dir / "model.safetensors"
    old_mirror = _mirror_dir(library_root, centralized, "oldfolder")
    _write_sidecar(
        old_mirror, "model", file_path=old_model_path, preview_name="model.preview.webp"
    )

    cache_entry: Dict[str, Any] = {
        "file_path": _normalize(old_model_path),
        "folder": "oldfolder",
        "preview_url": _normalize(old_mirror / "model.preview.webp"),
        "sha256": "",
    }
    scanner = CheckpointScanner()
    scanner._cache = _FakeCache([cache_entry])
    monkeypatch.setattr(scanner, "_persist_current_cache", AsyncMock())

    changed = await scanner.rename_known_folder(
        "oldfolder",
        "newfolder",
        previous_path=str(old_dir),
        new_path=str(new_dir),
    )

    assert changed is True

    new_mirror = _mirror_dir(library_root, centralized, "newfolder")
    assert (new_mirror / "model.metadata.json").exists()
    assert (new_mirror / "model.preview.webp").exists()
    assert not old_mirror.exists()

    saved = json.loads((new_mirror / "model.metadata.json").read_text())
    assert saved["file_path"] == _normalize(model)
    assert saved["preview_url"] == _normalize(new_mirror / "model.preview.webp")

    assert cache_entry["file_path"] == _normalize(model)
    assert cache_entry["folder"] == "newfolder"
    assert cache_entry["preview_url"] == _normalize(
        new_mirror / "model.preview.webp"
    )


@pytest.mark.asyncio
async def test_pending_models_mirror_walk(library_root: Path, centralized: Path):
    model = library_root / "model.safetensors"
    model.write_bytes(b"weights")
    mirror = _mirror_dir(library_root, centralized)
    _write_sidecar(
        mirror,
        "model",
        file_path=model,
        extra={"hash_status": "pending", "sha256": ""},
    )
    # Orphan sidecar: recorded model path is gone and no stem match exists.
    _write_sidecar(
        mirror,
        "ghost",
        file_path=library_root / "ghost.safetensors",
        extra={"hash_status": "pending", "sha256": ""},
    )

    scanner = CheckpointScanner()
    pending = await scanner._find_pending_models_from_filesystem()

    assert len(pending) == 1
    assert pending[0]["file_path"] == _normalize(model)
    assert pending[0]["hash_status"] == "pending"


@pytest.mark.asyncio
async def test_pending_models_mirror_walk_uses_stem_fallback(
    library_root: Path, centralized: Path
):
    """A stale recorded file_path falls back to probing by stem + extension."""

    model = library_root / "model.safetensors"
    model.write_bytes(b"weights")
    mirror = _mirror_dir(library_root, centralized)
    _write_sidecar(
        mirror,
        "model",
        file_path=library_root / "renamed-away.safetensors",
        extra={"hash_status": "pending", "sha256": ""},
    )

    scanner = CheckpointScanner()
    pending = await scanner._find_pending_models_from_filesystem()

    assert len(pending) == 1
    assert pending[0]["file_path"] == _normalize(model)
