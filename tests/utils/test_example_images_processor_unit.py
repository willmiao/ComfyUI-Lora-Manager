from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Tuple

import pytest

from py.services.settings_manager import settings
from py.utils import example_images_processor as processor_module


@pytest.fixture(autouse=True)
def restore_settings() -> None:
    original = settings.settings.copy()
    try:
        yield
    finally:
        settings.settings.clear()
        settings.settings.update(original)


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
    settings.settings["example_images_path"] = str(tmp_path / "examples")
    settings.settings["libraries"] = {"default": {}}
    settings.settings["active_library"] = "default"

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

    model_folder = Path(settings.settings["example_images_path"]) / ("a" * 64)
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
    settings.settings["example_images_path"] = str(tmp_path)

    async def _empty_scanner(cls=None):
        return StubScanner([])

    monkeypatch.setattr(processor_module.ServiceRegistry, "get_lora_scanner", classmethod(_empty_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_checkpoint_scanner", classmethod(_empty_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_embedding_scanner", classmethod(_empty_scanner))

    with pytest.raises(processor_module.ExampleImagesImportError):
        await processor_module.ExampleImagesProcessor.import_images("a" * 64, [str(tmp_path / "missing.png")])
