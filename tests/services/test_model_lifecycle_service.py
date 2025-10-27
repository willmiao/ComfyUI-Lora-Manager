import json
from pathlib import Path

import pytest

from py.services.model_lifecycle_service import ModelLifecycleService
from py.utils.metadata_manager import MetadataManager


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
