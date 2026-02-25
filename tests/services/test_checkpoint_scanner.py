import os
from pathlib import Path
from typing import List

import pytest

from py.services import model_scanner
from py.services.checkpoint_scanner import CheckpointScanner
from py.services.model_scanner import ModelScanner
from py.services.persistent_model_cache import PersistedCacheData


class RecordingWebSocketManager:
    def __init__(self) -> None:
        self.payloads: List[dict] = []

    async def broadcast_init_progress(self, payload: dict) -> None:
        self.payloads.append(payload)


def _normalize(path: Path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


@pytest.mark.asyncio
async def test_persisted_cache_restores_model_type(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LORA_MANAGER_DISABLE_PERSISTENT_CACHE", "0")

    checkpoints_root = tmp_path / "checkpoints"
    unet_root = tmp_path / "unet"
    checkpoints_root.mkdir()
    unet_root.mkdir()

    checkpoint_file = checkpoints_root / "alpha.safetensors"
    unet_file = unet_root / "beta.safetensors"
    checkpoint_file.write_text("alpha", encoding="utf-8")
    unet_file.write_text("beta", encoding="utf-8")

    normalized_checkpoint_root = _normalize(checkpoints_root)
    normalized_unet_root = _normalize(unet_root)
    normalized_checkpoint_file = _normalize(checkpoint_file)
    normalized_unet_file = _normalize(unet_file)

    monkeypatch.setattr(
        model_scanner.config,
        "base_models_roots",
        [normalized_checkpoint_root, normalized_unet_root],
        raising=False,
    )
    monkeypatch.setattr(
        model_scanner.config,
        "checkpoints_roots",
        [normalized_checkpoint_root],
        raising=False,
    )
    monkeypatch.setattr(
        model_scanner.config,
        "unet_roots",
        [normalized_unet_root],
        raising=False,
    )

    raw_checkpoint = {
        "file_path": normalized_checkpoint_file,
        "file_name": "alpha",
        "model_name": "alpha",
        "folder": "",
        "size": 1,
        "modified": 1.0,
        "sha256": "hash-alpha",
        "base_model": "",
        "preview_url": "",
        "preview_nsfw_level": 0,
        "from_civitai": False,
        "favorite": False,
        "notes": "",
        "usage_tips": "",
        "metadata_source": None,
        "exclude": False,
        "db_checked": False,
        "last_checked_at": 0.0,
        "tags": [],
        "civitai": None,
        "civitai_deleted": False,
    }

    raw_unet = dict(raw_checkpoint)
    raw_unet.update(
        {
            "file_path": normalized_unet_file,
            "file_name": "beta",
            "model_name": "beta",
            "sha256": "hash-beta",
        }
    )

    persisted = PersistedCacheData(
        raw_data=[raw_checkpoint, raw_unet],
        hash_rows=[],
        excluded_models=[],
    )

    class FakePersistentCache:
        def load_cache(self, model_type: str):
            assert model_type == "checkpoint"
            return persisted

    fake_cache = FakePersistentCache()
    monkeypatch.setattr(model_scanner, "get_persistent_cache", lambda: fake_cache)

    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, "ws_manager", ws_stub)

    scanner = CheckpointScanner()

    loaded = await scanner._load_persisted_cache("checkpoints")
    assert loaded is True

    cache = await scanner.get_cached_data()
    types_by_path = {item["file_path"]: item.get("sub_type") for item in cache.raw_data}

    assert types_by_path[normalized_checkpoint_file] == "checkpoint"
    assert types_by_path[normalized_unet_file] == "diffusion_model"

    assert ws_stub.payloads


@pytest.mark.asyncio
async def test_checkpoint_scanner_get_model_roots_includes_extra_paths(monkeypatch, tmp_path):
    """Test that get_model_roots includes both main and extra paths."""
    checkpoints_root = tmp_path / "checkpoints"
    extra_checkpoints_root = tmp_path / "extra_checkpoints"
    unet_root = tmp_path / "unet"
    extra_unet_root = tmp_path / "extra_unet"

    for directory in (checkpoints_root, extra_checkpoints_root, unet_root, extra_unet_root):
        directory.mkdir()

    normalized_checkpoints = _normalize(checkpoints_root)
    normalized_extra_checkpoints = _normalize(extra_checkpoints_root)
    normalized_unet = _normalize(unet_root)
    normalized_extra_unet = _normalize(extra_unet_root)

    monkeypatch.setattr(
        model_scanner.config,
        "base_models_roots",
        [normalized_checkpoints, normalized_unet],
        raising=False,
    )
    monkeypatch.setattr(
        model_scanner.config,
        "checkpoints_roots",
        [normalized_checkpoints],
        raising=False,
    )
    monkeypatch.setattr(
        model_scanner.config,
        "unet_roots",
        [normalized_unet],
        raising=False,
    )
    monkeypatch.setattr(
        model_scanner.config,
        "extra_checkpoints_roots",
        [normalized_extra_checkpoints],
        raising=False,
    )
    monkeypatch.setattr(
        model_scanner.config,
        "extra_unet_roots",
        [normalized_extra_unet],
        raising=False,
    )

    scanner = CheckpointScanner()
    roots = scanner.get_model_roots()

    assert normalized_checkpoints in roots
    assert normalized_unet in roots
    assert normalized_extra_checkpoints in roots
    assert normalized_extra_unet in roots
