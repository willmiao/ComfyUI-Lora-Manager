import json
from pathlib import Path

import pytest

from py.services.model_lifecycle_service import ModelLifecycleService
from py.utils.metadata_manager import MetadataManager


class DummyCache:
    def __init__(self, raw_data):
        self.raw_data = raw_data

    async def resort(self):
        return


class DummyHashIndex:
    def __init__(self):
        self.removed = []

    def remove_by_path(self, path, *args):
        self.removed.append(path)


class VersionAwareScanner:
    def __init__(self, raw_data, model_type="lora"):
        self.model_type = model_type
        self.cache = DummyCache(raw_data)
        self._hash_index = DummyHashIndex()

    async def get_cached_data(self):
        return self.cache

    async def get_model_versions_by_id(self, model_id):
        collected = []
        for item in self.cache.raw_data:
            civitai = item.get("civitai")
            if not isinstance(civitai, dict):
                continue
            candidate = civitai.get("modelId")
            try:
                normalized = int(candidate)
            except (TypeError, ValueError):
                continue
            if normalized != model_id:
                continue
            version_id = civitai.get("id")
            if version_id is None:
                continue
            collected.append({"versionId": version_id})
        return collected


class DummyMetadataManager:
    def __init__(self, payload):
        self._payload = dict(payload)

    async def load_metadata_payload(self, file_path: str):
        return dict(self._payload)


class DummyUpdateService:
    def __init__(self):
        self.calls = []

    async def update_in_library_versions(self, model_type, model_id, version_ids):
        self.calls.append((model_type, model_id, version_ids))


class DummyScanner:
    def __init__(self):
        self.calls = []
        self.model_type = "checkpoint"

    async def update_single_model_cache(self, old_path, new_path, metadata):
        self.calls.append((old_path, new_path, metadata))


class PassthroughMetadataManager:
    def __init__(self):
        self.saved_payloads = []

    async def save_metadata(self, path: str, metadata):
        self.saved_payloads.append((path, metadata.copy()))
        await MetadataManager.save_metadata(path, metadata)


@pytest.mark.asyncio
async def test_rename_model_preserves_compound_extensions(tmp_path: Path):
    old_name = "Qwen-Image-Edit-2509-Lightning-8steps-V1.0-bf16.0-bf16"
    new_name = f"{old_name}-testing"

    model_path = tmp_path / f"{old_name}.safetensors"
    model_path.write_bytes(b"lora")

    preview_path = tmp_path / f"{old_name}.preview.webp"
    preview_path.write_bytes(b"preview")

    metadata_path = tmp_path / f"{old_name}.metadata.json"
    metadata_payload = {
        "file_name": old_name,
        "file_path": model_path.as_posix(),
        "preview_url": preview_path.as_posix(),
    }
    metadata_path.write_text(json.dumps(metadata_payload))

    async def metadata_loader(path: str):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    scanner = DummyScanner()
    metadata_manager = PassthroughMetadataManager()
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=metadata_manager,
        metadata_loader=metadata_loader,
    )

    result = await service.rename_model(
        file_path=model_path.as_posix(),
        new_file_name=new_name,
    )

    expected_main = tmp_path / f"{new_name}.safetensors"
    expected_metadata = tmp_path / f"{new_name}.metadata.json"
    expected_preview = tmp_path / f"{new_name}.preview.webp"

    assert expected_main.exists()
    assert not model_path.exists()
    assert result["new_file_path"].endswith(f"{new_name}.safetensors")
    assert expected_preview.exists()
    assert not preview_path.exists()

    saved_metadata = json.loads(expected_metadata.read_text())
    assert saved_metadata["file_name"] == new_name
    assert saved_metadata["file_path"].endswith(f"{new_name}.safetensors")
    assert saved_metadata["preview_url"].endswith(f"{new_name}.preview.webp")

    assert scanner.calls
    old_call_path, new_call_path, payload = scanner.calls[0]
    assert old_call_path.endswith(f"{old_name}.safetensors")
    assert new_call_path.endswith(f"{new_name}.safetensors")
    assert payload["file_name"] == new_name


@pytest.mark.asyncio
async def test_delete_model_updates_update_service(tmp_path: Path):
    model_path = tmp_path / "sample.safetensors"
    model_path.write_bytes(b"content")

    other_path = tmp_path / "another.safetensors"
    other_path.write_bytes(b"other")

    raw_data = [
        {
            "file_path": model_path.as_posix(),
            "civitai": {"modelId": 42, "id": 1001},
        },
        {
            "file_path": other_path.as_posix(),
            "civitai": {"modelId": 42, "id": 1002},
        },
    ]

    scanner = VersionAwareScanner(raw_data)
    metadata_manager = DummyMetadataManager({"civitai": {"modelId": 42, "id": 1001}})

    async def metadata_loader(path: str):
        return {}

    update_service = DummyUpdateService()
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=metadata_manager,
        metadata_loader=metadata_loader,
        update_service=update_service,
    )

    result = await service.delete_model(model_path.as_posix())

    assert result["success"] is True
    assert not model_path.exists()
    assert update_service.calls == [("lora", 42, [1002])]


@pytest.mark.asyncio
async def test_delete_model_removes_gguf_file(tmp_path: Path):
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"content")

    metadata_path = tmp_path / "model.metadata.json"
    metadata_path.write_text(json.dumps({}))

    preview_path = tmp_path / "model.preview.png"
    preview_path.write_bytes(b"preview")

    raw_data = [
        {
            "file_path": model_path.as_posix(),
            "civitai": {"modelId": 1, "id": 10},
        }
    ]

    scanner = VersionAwareScanner(raw_data)
    metadata_manager = DummyMetadataManager({"civitai": {"modelId": 1, "id": 10}})

    async def metadata_loader(path: str):
        return {}

    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=metadata_manager,
        metadata_loader=metadata_loader,
    )

    result = await service.delete_model(model_path.as_posix())

    assert result["success"] is True
    assert not model_path.exists()
    assert not metadata_path.exists()
    assert not preview_path.exists()
    assert any(item.endswith("model.gguf") for item in result["deleted_files"])
