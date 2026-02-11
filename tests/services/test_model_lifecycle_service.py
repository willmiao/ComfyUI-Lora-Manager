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
async def test_rename_model_preserves_extension(tmp_path: Path):
    old_name = "model"
    old_extension = ".gguf"
    new_name = "model-renamed"

    model_path = tmp_path / f"{old_name}{old_extension}"
    model_path.write_bytes(b"model")

    preview_path = tmp_path / f"{old_name}.preview.png"
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

    expected_main = tmp_path / f"{new_name}{old_extension}"
    expected_metadata = tmp_path / f"{new_name}.metadata.json"
    expected_preview = tmp_path / f"{new_name}.preview.png"

    assert expected_main.exists()
    assert not model_path.exists()
    assert result["new_file_path"].endswith(f"{new_name}{old_extension}")
    assert expected_preview.exists()
    assert not preview_path.exists()

    saved_metadata = json.loads(expected_metadata.read_text())
    assert saved_metadata["file_name"] == new_name
    assert saved_metadata["file_path"].endswith(f"{new_name}{old_extension}")
    assert saved_metadata["preview_url"].endswith(f"{new_name}.preview.png")

    assert scanner.calls
    old_call_path, new_call_path, payload = scanner.calls[0]
    assert old_call_path.endswith(f"{old_name}{old_extension}")
    assert new_call_path.endswith(f"{new_name}{old_extension}")
    assert payload["file_name"] == new_name


@pytest.mark.asyncio
async def test_rename_model_with_dotted_basename(tmp_path: Path):
    old_name = "model.v1"
    old_extension = ".gguf"
    new_name = "renamed-model"

    model_path = tmp_path / f"{old_name}{old_extension}"
    model_path.write_bytes(b"content")

    metadata_path = tmp_path / f"{old_name}.metadata.json"
    metadata_payload = {
        "file_name": old_name,
        "file_path": model_path.as_posix(),
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

    expected_main = tmp_path / f"{new_name}{old_extension}"
    assert expected_main.exists()
    assert result["new_file_path"] == expected_main.as_posix()
    assert any(p.endswith(f"{new_name}{old_extension}") for p in result["renamed_files"])

    saved_metadata = json.loads((tmp_path / f"{new_name}.metadata.json").read_text())
    assert saved_metadata["file_name"] == new_name
    assert saved_metadata["file_path"].endswith(f"{new_name}{old_extension}")

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


# =============================================================================
# Tests for exclude_model functionality
# =============================================================================


@pytest.mark.asyncio
async def test_exclude_model_marks_as_excluded(tmp_path: Path):
    """Verify exclude_model marks model as excluded and updates metadata."""
    model_path = tmp_path / "test_model.safetensors"
    model_path.write_bytes(b"content")

    metadata_path = tmp_path / "test_model.metadata.json"
    metadata_payload = {"file_name": "test_model", "file_path": str(model_path)}
    metadata_path.write_text(json.dumps(metadata_payload))

    raw_data = [
        {
            "file_path": str(model_path),
            "tags": ["tag1", "tag2"],
        }
    ]

    class ExcludeTestScanner:
        def __init__(self, raw_data):
            self.cache = DummyCache(raw_data)
            self.model_type = "lora"
            self._tags_count = {"tag1": 1, "tag2": 1}
            self._hash_index = DummyHashIndex()
            self._excluded_models = []

        async def get_cached_data(self):
            return self.cache

    scanner = ExcludeTestScanner(raw_data)

    saved_metadata = []

    class SavingMetadataManager:
        async def save_metadata(self, path: str, metadata: dict):
            saved_metadata.append((path, metadata.copy()))

    async def metadata_loader(path: str):
        return metadata_payload.copy()

    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=SavingMetadataManager(),
        metadata_loader=metadata_loader,
    )

    result = await service.exclude_model(str(model_path))

    assert result["success"] is True
    assert "excluded" in result["message"].lower()
    assert saved_metadata[0][1]["exclude"] is True
    assert str(model_path) in scanner._excluded_models


@pytest.mark.asyncio
async def test_exclude_model_updates_tag_counts(tmp_path: Path):
    """Verify exclude_model decrements tag counts correctly."""
    model_path = tmp_path / "test_model.safetensors"
    model_path.write_bytes(b"content")

    metadata_path = tmp_path / "test_model.metadata.json"
    metadata_path.write_text(json.dumps({}))

    raw_data = [
        {
            "file_path": str(model_path),
            "tags": ["tag1", "tag2"],
        }
    ]

    class TagCountScanner:
        def __init__(self, raw_data):
            self.cache = DummyCache(raw_data)
            self.model_type = "lora"
            self._tags_count = {"tag1": 2, "tag2": 1}
            self._hash_index = DummyHashIndex()
            self._excluded_models = []

        async def get_cached_data(self):
            return self.cache

    scanner = TagCountScanner(raw_data)

    class DummyMetadataManagerLocal:
        async def save_metadata(self, path: str, metadata: dict):
            pass

    async def metadata_loader(path: str):
        return {}

    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=DummyMetadataManagerLocal(),
        metadata_loader=metadata_loader,
    )

    await service.exclude_model(str(model_path))

    # tag2 count should become 0 and be removed
    assert "tag2" not in scanner._tags_count
    # tag1 count should decrement to 1
    assert scanner._tags_count["tag1"] == 1


@pytest.mark.asyncio
async def test_exclude_model_empty_path_raises_error():
    """Verify exclude_model raises ValueError for empty path."""
    service = ModelLifecycleService(
        scanner=VersionAwareScanner([]),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="Model path is required"):
        await service.exclude_model("")


# =============================================================================
# Tests for bulk_delete_models functionality
# =============================================================================


@pytest.mark.asyncio
async def test_bulk_delete_models_deletes_multiple_files(tmp_path: Path):
    """Verify bulk_delete_models deletes multiple models via scanner."""
    model1_path = tmp_path / "model1.safetensors"
    model1_path.write_bytes(b"content1")
    model2_path = tmp_path / "model2.safetensors"
    model2_path.write_bytes(b"content2")

    file_paths = [str(model1_path), str(model2_path)]

    class BulkDeleteScanner:
        def __init__(self):
            self.model_type = "lora"
            self.bulk_delete_calls = []

        async def bulk_delete_models(self, paths):
            self.bulk_delete_calls.append(paths)
            return {"success": True, "deleted": paths}

    scanner = BulkDeleteScanner()

    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    result = await service.bulk_delete_models(file_paths)

    assert result["success"] is True
    assert len(scanner.bulk_delete_calls) == 1
    assert scanner.bulk_delete_calls[0] == file_paths


@pytest.mark.asyncio
async def test_bulk_delete_models_empty_list_raises_error():
    """Verify bulk_delete_models raises ValueError for empty list."""
    service = ModelLifecycleService(
        scanner=VersionAwareScanner([]),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="No file paths provided"):
        await service.bulk_delete_models([])


# =============================================================================
# Tests for error paths and edge cases
# =============================================================================


@pytest.mark.asyncio
async def test_delete_model_empty_path_raises_error():
    """Verify delete_model raises ValueError for empty path."""
    service = ModelLifecycleService(
        scanner=VersionAwareScanner([]),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="Model path is required"):
        await service.delete_model("")


@pytest.mark.asyncio
async def test_rename_model_empty_path_raises_error():
    """Verify rename_model raises ValueError for empty path."""
    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="required"):
        await service.rename_model(file_path="", new_file_name="new_name")


@pytest.mark.asyncio
async def test_rename_model_empty_name_raises_error(tmp_path: Path):
    """Verify rename_model raises ValueError for empty new name."""
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(b"content")

    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="required"):
        await service.rename_model(file_path=str(model_path), new_file_name="")


@pytest.mark.asyncio
async def test_rename_model_invalid_characters_raises_error(tmp_path: Path):
    """Verify rename_model raises ValueError for invalid characters."""
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(b"content")

    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    invalid_names = [
        "model/name",
        "model\\\\name",
        "model:name",
        "model*name",
        "model?name",
        'model"name',
        "model<name>",
        "model|name",
    ]

    for invalid_name in invalid_names:
        with pytest.raises(ValueError, match="Invalid characters"):
            await service.rename_model(
                file_path=str(model_path), new_file_name=invalid_name
            )


@pytest.mark.asyncio
async def test_rename_model_existing_file_raises_error(tmp_path: Path):
    """Verify rename_model raises ValueError if target exists."""
    old_name = "model"
    new_name = "existing"
    extension = ".safetensors"

    old_path = tmp_path / f"{old_name}{extension}"
    old_path.write_bytes(b"content")

    # Create existing file with target name
    existing_path = tmp_path / f"{new_name}{extension}"
    existing_path.write_bytes(b"existing content")

    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="already exists"):
        await service.rename_model(
            file_path=str(old_path), new_file_name=new_name
        )


# =============================================================================
# Tests for _extract_model_id_from_payload utility
# =============================================================================


@pytest.mark.asyncio
async def test_extract_model_id_from_civitai_payload():
    """Verify model ID extraction from civitai-formatted payload."""
    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    # Test civitai.modelId
    payload1 = {"civitai": {"modelId": 12345}}
    assert service._extract_model_id_from_payload(payload1) == 12345

    # Test civitai.model.id nested
    payload2 = {"civitai": {"model": {"id": 67890}}}
    assert service._extract_model_id_from_payload(payload2) == 67890

    # Test model_id fallback
    payload3 = {"model_id": 11111}
    assert service._extract_model_id_from_payload(payload3) == 11111

    # Test civitai_model_id fallback
    payload4 = {"civitai_model_id": 22222}
    assert service._extract_model_id_from_payload(payload4) == 22222


@pytest.mark.asyncio
async def test_extract_model_id_returns_none_for_invalid_payload():
    """Verify model ID extraction returns None for invalid payloads."""
    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    assert service._extract_model_id_from_payload({}) is None
    assert service._extract_model_id_from_payload(None) is None
    assert service._extract_model_id_from_payload("string") is None
    assert service._extract_model_id_from_payload({"civitai": None}) is None
    assert service._extract_model_id_from_payload({"civitai": {}}) is None


@pytest.mark.asyncio
async def test_extract_model_id_handles_string_values():
    """Verify model ID extraction handles string values."""
    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    payload = {"civitai": {"modelId": "54321"}}
    assert service._extract_model_id_from_payload(payload) == 54321
