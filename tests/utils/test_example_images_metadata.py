from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest

from py.utils import example_images_metadata as metadata_module


class StubScanner:
    def __init__(self, cache_items: List[Dict[str, Any]]) -> None:
        self.cache = SimpleNamespace(raw_data=cache_items)
        self.updates: List[Tuple[str, str, Dict[str, Any]]] = []

    async def get_cached_data(self):
        return self.cache

    async def update_single_model_cache(self, old_path: str, new_path: str, metadata: Dict[str, Any]) -> bool:
        self.updates.append((old_path, new_path, metadata))
        return True


@pytest.fixture(autouse=True)
def patch_metadata_manager(monkeypatch: pytest.MonkeyPatch):
    saved: List[Tuple[str, Dict[str, Any]]] = []

    async def fake_save(path: str, metadata: Dict[str, Any]) -> bool:
        saved.append((path, metadata.copy()))
        return True

    monkeypatch.setattr(metadata_module.MetadataManager, "save_metadata", staticmethod(fake_save))
    return saved


async def test_update_metadata_after_import_enriches_entries(monkeypatch: pytest.MonkeyPatch, tmp_path, patch_metadata_manager):
    model_hash = "a" * 64
    model_file = tmp_path / "model.safetensors"
    model_file.write_text("content", encoding="utf-8")
    model_data = {
        "model_name": "Example",
        "file_path": str(model_file),
        "civitai": {},
    }
    scanner = StubScanner([model_data])

    image_path = tmp_path / "custom.png"
    image_path.write_bytes(b"fakepng")

    monkeypatch.setattr(metadata_module.ExifUtils, "extract_image_metadata", staticmethod(lambda _path: "Prompt text Negative prompt: bad Steps: 20, Sampler: Euler"))
    monkeypatch.setattr(metadata_module.MetadataUpdater, "_parse_image_metadata", staticmethod(lambda payload: {"prompt": "Prompt text", "negativePrompt": "bad", "parameters": {"Steps": "20"}}))

    regular, custom = await metadata_module.MetadataUpdater.update_metadata_after_import(
        model_hash,
        model_data,
        scanner,
        [(str(image_path), "short-id")],
    )

    assert isinstance(custom, list)
    assert custom[0]["id"] == "short-id"
    assert custom[0]["meta"]["prompt"] == "Prompt text"
    assert custom[0]["hasMeta"] is True
    assert custom[0]["type"] == "image"

    assert patch_metadata_manager[0][0] == str(model_file)
    assert scanner.updates


async def test_refresh_model_metadata_records_failures(monkeypatch: pytest.MonkeyPatch, tmp_path):
    model_hash = "b" * 64
    model_file = tmp_path / "model.safetensors"
    model_file.write_text("content", encoding="utf-8")
    cache_item = {"sha256": model_hash, "file_path": str(model_file)}
    scanner = StubScanner([cache_item])

    class StubMetadataSync:
        async def fetch_and_update_model(self, **_kwargs):
            return True, None

    monkeypatch.setattr(metadata_module, "_metadata_sync_service", StubMetadataSync())

    result = await metadata_module.MetadataUpdater.refresh_model_metadata(
        model_hash,
        "Example",
        "lora",
        scanner,
        {"refreshed_models": set(), "errors": [], "last_error": None},
    )
    assert result is True


async def test_update_metadata_from_local_examples_generates_entries(monkeypatch: pytest.MonkeyPatch, tmp_path):
    model_hash = "c" * 64
    model_dir = tmp_path / model_hash
    model_dir.mkdir()
    (model_dir / "image.png").write_text("data", encoding="utf-8")
    model_data = {"model_name": "Local", "civitai": {}, "file_path": str(tmp_path / "model.safetensors")}

    async def fake_save(path, metadata):
        return True

    monkeypatch.setattr(metadata_module.MetadataManager, "save_metadata", staticmethod(fake_save))
    monkeypatch.setattr(metadata_module.ExifUtils, "extract_image_metadata", staticmethod(lambda _path: None))

    success = await metadata_module.MetadataUpdater.update_metadata_from_local_examples(
        model_hash,
        model_data,
        "lora",
        StubScanner([model_data]),
        str(model_dir),
    )
    assert success is True
    assert model_data["civitai"]["images"]
