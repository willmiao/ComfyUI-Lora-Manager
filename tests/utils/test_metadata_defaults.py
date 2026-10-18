import json
import struct
import pytest

from py.utils.metadata_manager import MetadataManager
from py.utils.models import BaseModelMetadata


def _write_safetensors(path, metadata, payload=b"payload-bytes"):
    """Write a minimal real safetensors file: 8-byte little-endian header
    length, a JSON header containing ``__metadata__``, then arbitrary payload."""
    header = json.dumps({"__metadata__": metadata}).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)


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


@pytest.mark.asyncio
async def test_create_default_metadata_writes_autov3_from_safetensors(tmp_path):
    model_path = tmp_path / "example.safetensors"
    _write_safetensors(model_path, {"sshs_model_hash": "abcdef1234567890abcdef"})

    metadata = await MetadataManager.create_default_metadata(str(model_path))

    assert metadata is not None
    assert metadata.autov3 == "abcdef123456"

    metadata_path = model_path.with_suffix(".metadata.json")
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert payload.get("autov3") == "abcdef123456"


@pytest.mark.asyncio
async def test_create_default_metadata_writes_autov3_null_for_non_safetensors(tmp_path):
    model_path = tmp_path / "example.safetensors"
    model_path.write_bytes(b"stub")

    metadata = await MetadataManager.create_default_metadata(str(model_path))

    assert metadata is not None
    assert metadata.autov3 == ""

    metadata_path = model_path.with_suffix(".metadata.json")
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert payload.get("autov3") is None
