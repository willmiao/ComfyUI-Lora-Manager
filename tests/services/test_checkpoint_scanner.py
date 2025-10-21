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
    types_by_path = {item["file_path"]: item.get("model_type") for item in cache.raw_data}

    assert types_by_path[normalized_checkpoint_file] == "checkpoint"
    assert types_by_path[normalized_unet_file] == "diffusion_model"

    assert ws_stub.payloads
    assert ws_stub.payloads[-1]["stage"] == "loading_cache"
