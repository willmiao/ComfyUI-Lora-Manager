from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Tuple

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils import example_images_metadata as metadata_module
from py.utils import example_images_processor as processor_module
from py.utils.example_images_paths import get_model_folder


@pytest.fixture(autouse=True)
def restore_settings() -> None:
    manager = get_settings_manager()
    original = manager.settings.copy()
    try:
        yield
    finally:
        manager.settings.clear()
        manager.settings.update(original)


@pytest.fixture(autouse=True)
def patch_metadata_loader(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr(processor_module.MetadataManager, "load_metadata", staticmethod(fake_load))
    monkeypatch.setattr(metadata_module.MetadataManager, "load_metadata", staticmethod(fake_load))


def test_get_file_extension_from_magic_bytes() -> None:
    jpg_bytes = b"\xff\xd8\xff" + b"rest"
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        jpg_bytes, {}, None
    )
    assert ext == ".jpg"


def test_get_file_extension_from_headers() -> None:
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        b"", {"content-type": "image/png"}, None
    )
    assert ext == ".png"


def test_get_file_extension_from_url_fallback() -> None:
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        b"", {}, "https://example.com/file.webm?query=1"
    )
    assert ext == ".webm"


def test_get_file_extension_defaults_to_jpg() -> None:
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        b"", {}, None
    )
    assert ext == ".jpg"


class StubScanner:
    def __init__(self, models: list[Dict[str, Any]]) -> None:
        self._cache = SimpleNamespace(raw_data=models)
        self.updated: list[Tuple[str, str, Dict[str, Any]]] = []

    async def get_cached_data(self):
        return self._cache

    async def update_single_model_cache(self, old_path: str, new_path: str, metadata: Dict[str, Any]) -> bool:
        self.updated.append((old_path, new_path, metadata))
        return True

    def has_hash(self, _hash: str) -> bool:
        return True


@pytest.fixture
def stub_scanners(monkeypatch: pytest.MonkeyPatch, tmp_path) -> StubScanner:
    model_hash = "a" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("content", encoding="utf-8")
    model_data = {
        "sha256": model_hash,
        "model_name": "Example",
        "file_path": str(model_path),
        "civitai": {},
    }
    scanner = StubScanner([model_data])

    async def _return_scanner(cls=None):
        return scanner

    monkeypatch.setattr(processor_module.ServiceRegistry, "get_lora_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_checkpoint_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_embedding_scanner", classmethod(_return_scanner))

    return scanner


async def test_import_images_creates_hash_directory(monkeypatch: pytest.MonkeyPatch, tmp_path, stub_scanners: StubScanner) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path / "examples")
    settings_manager.settings["libraries"] = {"default": {}}
    settings_manager.settings["active_library"] = "default"

    source_file = tmp_path / "upload.png"
    source_file.write_bytes(b"PNG data")

    monkeypatch.setattr(processor_module.ExampleImagesProcessor, "generate_short_id", staticmethod(lambda: "short"))

    recorded: Dict[str, Any] = {}

    async def fake_update_metadata(model_hash, model_data, scanner, paths):
        recorded["args"] = (model_hash, list(paths))
        return ["regular"], ["custom"]

    monkeypatch.setattr(processor_module.MetadataUpdater, "update_metadata_after_import", staticmethod(fake_update_metadata))

    result = await processor_module.ExampleImagesProcessor.import_images("a" * 64, [str(source_file)])

    assert result["success"] is True
    assert result["files"][0]["name"].startswith("custom_short")

    model_folder = Path(settings_manager.settings["example_images_path"]) / ("a" * 64)
    assert model_folder.exists()
    created_files = list(model_folder.glob("custom_short*.png"))
    assert len(created_files) == 1
    assert created_files[0].read_bytes() == source_file.read_bytes()

    model_hash, paths = recorded["args"]
    assert model_hash == "a" * 64
    assert paths[0][0].startswith(str(model_folder))


async def test_import_images_rejects_missing_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(processor_module.ExampleImagesValidationError):
        await processor_module.ExampleImagesProcessor.import_images("", [])

    with pytest.raises(processor_module.ExampleImagesValidationError):
        await processor_module.ExampleImagesProcessor.import_images("abc", [])


async def test_import_images_raises_when_model_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)

    async def _empty_scanner(cls=None):
        return StubScanner([])

    monkeypatch.setattr(processor_module.ServiceRegistry, "get_lora_scanner", classmethod(_empty_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_checkpoint_scanner", classmethod(_empty_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_embedding_scanner", classmethod(_empty_scanner))

    with pytest.raises(processor_module.ExampleImagesImportError):
        await processor_module.ExampleImagesProcessor.import_images("a" * 64, [str(tmp_path / "missing.png")])


@pytest.mark.asyncio
async def test_delete_custom_image_preserves_existing_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path / "examples")

    model_hash = "c" * 64
    model_file = tmp_path / "keep.safetensors"
    model_file.write_text("content", encoding="utf-8")
    metadata_path = tmp_path / "keep.metadata.json"

    existing_metadata = {
        "model_name": "Keep",
        "file_path": str(model_file),
        "civitai": {
            "images": [{"url": "https://example.com/default.png", "type": "image"}],
            "customImages": [{"id": "existing-id", "url": "", "type": "image"}],
            "trainedWords": ["foo"],
        },
    }
    metadata_path.write_text(json.dumps(existing_metadata), encoding="utf-8")

    model_data = {
        "sha256": model_hash,
        "model_name": "Keep",
        "file_path": str(model_file),
        "civitai": {
            "customImages": [{"id": "existing-id", "url": "", "type": "image"}],
            "trainedWords": ["foo"],
        },
    }

    class Scanner(StubScanner):
        def has_hash(self, hash_value: str) -> bool:
            return hash_value == model_hash

    scanner = Scanner([model_data])

    async def _return_scanner(cls=None):
        return scanner

    monkeypatch.setattr(processor_module.ServiceRegistry, "get_lora_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_checkpoint_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_embedding_scanner", classmethod(_return_scanner))

    model_folder = get_model_folder(model_hash)
    os.makedirs(model_folder, exist_ok=True)
    (Path(model_folder) / "custom_existing-id.png").write_bytes(b"data")

    saved: list[tuple[str, Dict[str, Any]]] = []

    async def fake_save(path: str, payload: Dict[str, Any]) -> bool:
        saved.append((path, payload.copy()))
        return True

    monkeypatch.setattr(processor_module.MetadataManager, "save_metadata", staticmethod(fake_save))

    class StubRequest:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload

        async def json(self) -> Dict[str, Any]:
            return self._payload

    response = await processor_module.ExampleImagesProcessor.delete_custom_image(
        StubRequest({"model_hash": model_hash, "short_id": "existing-id"})
    )

    assert response.status == 200
    body = json.loads(response.text)
    assert body["success"] is True
    assert body["custom_images"] == []
    assert not (Path(model_folder) / "custom_existing-id.png").exists()

    saved_path, saved_payload = saved[-1]
    assert saved_path == str(model_file)
    assert saved_payload["civitai"]["images"] == existing_metadata["civitai"]["images"]
    assert saved_payload["civitai"]["trainedWords"] == ["foo"]
    assert saved_payload["civitai"]["customImages"] == []

    assert scanner.updated
    _, _, updated_metadata = scanner.updated[-1]
    assert updated_metadata["civitai"]["images"] == existing_metadata["civitai"]["images"]
    assert updated_metadata["civitai"]["customImages"] == []
