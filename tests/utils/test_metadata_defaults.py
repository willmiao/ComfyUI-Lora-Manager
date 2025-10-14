import json
import pytest

from py.utils.metadata_manager import MetadataManager
from py.utils.models import BaseModelMetadata


@pytest.mark.asyncio
async def test_base_model_metadata_sets_empty_civitai_dict():
    metadata = BaseModelMetadata(
        file_name="model",
        model_name="Model",
        file_path="/tmp/model.safetensors",
        size=0,
        modified=0.0,
        sha256="deadbeef",
        base_model="Unknown",
        preview_url="",
    )

    assert metadata.civitai == {}


@pytest.mark.asyncio
async def test_create_default_metadata_uses_empty_civitai(tmp_path):
    model_path = tmp_path / "example.safetensors"
    model_path.write_bytes(b"stub")

    metadata = await MetadataManager.create_default_metadata(str(model_path))

    assert metadata is not None
    assert metadata.civitai == {}

    metadata_path = model_path.with_suffix(".metadata.json")
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert payload.get("civitai") == {}
