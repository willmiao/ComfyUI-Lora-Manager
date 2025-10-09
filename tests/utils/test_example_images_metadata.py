from __future__ import annotations

import json
import os
from pathlib import Path
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

    class SimpleMetadata:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload
            self._unknown_fields: Dict[str, Any] = {}

        def to_dict(self) -> Dict[str, Any]:
            return self._payload.copy()

    async def fake_load(path: str, *_args: Any, **_kwargs: Any):
        metadata_path = path if path.endswith(".metadata.json") else f"{os.path.splitext(path)[0]}.metadata.json"
        if os.path.exists(metadata_path):
            data = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
            return SimpleMetadata(data), False
        return None, False

    monkeypatch.setattr(metadata_module.MetadataManager, "save_metadata", staticmethod(fake_save))
    monkeypatch.setattr(metadata_module.MetadataManager, "load_metadata", staticmethod(fake_load))
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

    assert Path(patch_metadata_manager[0][0]) == model_file
    assert scanner.updates


@pytest.mark.asyncio
async def test_update_metadata_after_import_preserves_existing_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    patch_metadata_manager,
):
    model_hash = "b" * 64
    model_file = tmp_path / "preserve.safetensors"
    model_file.write_text("content", encoding="utf-8")
    metadata_path = tmp_path / "preserve.metadata.json"

    existing_payload = {
        "model_name": "Example",
        "file_path": str(model_file),
        "civitai": {
            "id": 42,
            "modelId": 88,
            "name": "Example",
            "trainedWords": ["foo"],
            "images": [{"url": "https://example.com/default.png", "type": "image"}],
            "customImages": [
                {"id": "existing-id", "type": "image", "url": "", "nsfwLevel": 0}
            ],
        },
        "extraField": "keep-me",
    }
    metadata_path.write_text(json.dumps(existing_payload), encoding="utf-8")

    model_data = {
        "sha256": model_hash,
        "model_name": "Example",
        "file_path": str(model_file),
        "civitai": {
            "id": 42,
            "modelId": 88,
            "name": "Example",
            "trainedWords": ["foo"],
            "customImages": [],
        },
    }
    scanner = StubScanner([model_data])

    image_path = tmp_path / "new.png"
    image_path.write_bytes(b"fakepng")

    monkeypatch.setattr(metadata_module.ExifUtils, "extract_image_metadata", staticmethod(lambda _path: None))
    monkeypatch.setattr(metadata_module.MetadataUpdater, "_parse_image_metadata", staticmethod(lambda payload: None))

    regular, custom = await metadata_module.MetadataUpdater.update_metadata_after_import(
        model_hash,
        model_data,
        scanner,
        [(str(image_path), "new-id")],
    )

    assert regular == existing_payload["civitai"]["images"]
    assert any(entry["id"] == "new-id" for entry in custom)

    saved_path, saved_payload = patch_metadata_manager[-1]
    assert Path(saved_path) == model_file
    assert saved_payload["extraField"] == "keep-me"
    assert saved_payload["civitai"]["images"] == existing_payload["civitai"]["images"]
    assert saved_payload["civitai"]["trainedWords"] == ["foo"]
    assert {entry["id"] for entry in saved_payload["civitai"]["customImages"]} == {"existing-id", "new-id"}

    assert scanner.updates
    updated_metadata = scanner.updates[-1][2]
    assert updated_metadata["civitai"]["images"] == existing_payload["civitai"]["images"]
    assert {entry["id"] for entry in updated_metadata["civitai"]["customImages"]} == {"existing-id", "new-id"}

async def test_refresh_model_metadata_records_failures(monkeypatch: pytest.MonkeyPatch, tmp_path):
    model_hash = "b" * 64
    model_file = tmp_path / "model.safetensors"
    model_file.write_text("content", encoding="utf-8")
    cache_item = {"sha256": model_hash, "file_path": str(model_file)}
    scanner = StubScanner([cache_item])

    class StubMetadataSync:
        async def fetch_and_update_model(self, **_kwargs):
            return True, None

    async def fake_hydrate(model_data: Dict[str, Any]) -> Dict[str, Any]:
        model_data["hydrated"] = True
        return model_data

    monkeypatch.setattr(
        metadata_module.MetadataManager,
        "hydrate_model_data",
        staticmethod(fake_hydrate),
    )

    monkeypatch.setattr(metadata_module, "_metadata_sync_service", StubMetadataSync())

    result = await metadata_module.MetadataUpdater.refresh_model_metadata(
        model_hash,
        "Example",
        "lora",
        scanner,
        {"refreshed_models": set(), "errors": [], "last_error": None},
    )
    assert result is True
    assert cache_item["hydrated"] is True


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