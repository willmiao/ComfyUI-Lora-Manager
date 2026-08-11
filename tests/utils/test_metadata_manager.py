from __future__ import annotations

import json

import pytest

from py.utils.metadata_manager import MetadataManager
from py.utils.models import LoraMetadata


@pytest.mark.asyncio
async def test_save_metadata_fills_missing_file_facts(tmp_path) -> None:
    """A payload missing file_name/size/modified is healed on write."""
    model_path = tmp_path / "MyModel.safetensors"
    model_path.write_bytes(b"fake model data")
    payload = {"file_path": str(model_path), "model_name": "My Model"}

    result = await MetadataManager.save_metadata(str(model_path), payload)
    assert result is True

    metadata_path = tmp_path / "MyModel.metadata.json"
    saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    stat_result = model_path.stat()
    assert saved["file_name"] == "MyModel"
    assert saved["size"] == stat_result.st_size
    assert saved["modified"] == stat_result.st_mtime


@pytest.mark.asyncio
async def test_save_metadata_keeps_existing_file_facts(tmp_path) -> None:
    """Existing file facts are never overwritten on write."""
    model_path = tmp_path / "MyModel.safetensors"
    model_path.write_bytes(b"fake model data")
    payload = {
        "file_path": str(model_path),
        "file_name": "CustomName",
        "size": 123,
        "modified": 456.0,
    }

    result = await MetadataManager.save_metadata(str(model_path), payload)
    assert result is True

    metadata_path = tmp_path / "MyModel.metadata.json"
    saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert saved["file_name"] == "CustomName"
    assert saved["size"] == 123
    assert saved["modified"] == 456.0


@pytest.mark.asyncio
async def test_load_metadata_payload_restores_file_facts_when_sidecar_missing(
    tmp_path,
) -> None:
    """Missing sidecar: the payload is rebuilt with local file facts."""
    model_path = tmp_path / "MyModel.safetensors"
    model_path.write_bytes(b"fake model data")

    payload = await MetadataManager.load_metadata_payload(str(model_path))

    stat_result = model_path.stat()
    assert payload["file_path"] == str(model_path)
    assert payload["file_name"] == "MyModel"
    assert payload["size"] == stat_result.st_size
    assert payload["modified"] == stat_result.st_mtime


@pytest.mark.asyncio
async def test_hydrate_model_data_restores_required_fields_when_sidecar_missing(
    tmp_path,
) -> None:
    """Self-heal repro: sidecar deleted, cache entry hydrated, base fields kept."""
    model_path = tmp_path / "MyModel.safetensors"
    model_path.write_bytes(b"fake model data")
    model_data = {
        "file_path": str(model_path),
        "folder": "extra_loras",
        "file_name": "MyModel",
        "model_name": "My Model",
        "size": 10,
        "modified": 100.0,
        "sha256": "abc123",
        "base_model": "Illustrious",
        "preview_url": "",
        "civitai": {"id": 123},
    }

    await MetadataManager.hydrate_model_data(model_data)

    stat_result = model_path.stat()
    assert model_data["file_name"] == "MyModel"
    assert model_data["model_name"] == "My Model"
    assert model_data["size"] == stat_result.st_size
    # `modified` is the import timestamp per schema; the cache value wins.
    assert model_data["modified"] == 100.0
    assert model_data["sha256"] == "abc123"
    assert model_data["base_model"] == "Illustrious"
    assert model_data["folder"] == "extra_loras"
    assert model_data["civitai"] == {"id": 123}


@pytest.mark.asyncio
async def test_hydrate_model_data_disk_wins_when_sidecar_exists(tmp_path) -> None:
    """Existing sidecar stays authoritative; no cache key is resurrected."""
    model_path = tmp_path / "MyModel.safetensors"
    model_path.write_bytes(b"fake model data")
    stat_result = model_path.stat()
    sidecar = {
        "file_path": str(model_path),
        "file_name": "MyModel",
        "model_name": "Disk Name",
        "size": stat_result.st_size,
        "modified": stat_result.st_mtime,
        "sha256": "diskhash",
        "base_model": "SDXL",
        "preview_url": "",
    }
    (tmp_path / "MyModel.metadata.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )
    model_data = {
        "file_path": str(model_path),
        "folder": "extra_loras",
        "model_name": "Cache Name",
        "sha256": "cachehash",
        "civitai": {"id": 999},
    }

    await MetadataManager.hydrate_model_data(model_data)

    assert model_data["model_name"] == "Disk Name"
    assert model_data["sha256"] == "diskhash"
    # civitai is present only as the dataclass default {}; the cache's value
    # ({"id": 999}) is not resurrected.
    assert model_data["civitai"] == {}
    assert model_data["folder"] == "extra_loras"


@pytest.mark.asyncio
async def test_hydrate_model_data_keeps_sha256_missing_for_caller_persist_fix(
    tmp_path,
) -> None:
    """Sidecar exists but lacks sha256: hydrate leaves it missing so the
    caller's self-heal persist block still has work to do."""
    model_path = tmp_path / "MyModel.safetensors"
    model_path.write_bytes(b"fake model data")
    stat_result = model_path.stat()
    sidecar = {
        "file_path": str(model_path),
        "file_name": "MyModel",
        "model_name": "My Model",
        "size": stat_result.st_size,
        "modified": stat_result.st_mtime,
        "base_model": "SDXL",
        "preview_url": "",
        # sha256 deliberately absent
    }
    (tmp_path / "MyModel.metadata.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )
    model_data = {
        "file_path": str(model_path),
        "sha256": "cachehash",
        "model_name": "Cache Name",
    }

    await MetadataManager.hydrate_model_data(model_data)

    assert "sha256" not in model_data


@pytest.mark.asyncio
async def test_load_metadata_payload_tolerates_missing_model_file(tmp_path) -> None:
    """A nonexistent model file must not crash payload loading."""
    missing_path = tmp_path / "Ghost.safetensors"
    payload = await MetadataManager.load_metadata_payload(str(missing_path))
    assert payload["file_path"] == str(missing_path)
    assert "file_name" not in payload
    assert "size" not in payload
    assert "modified" not in payload


@pytest.mark.asyncio
async def test_self_healed_sidecar_is_parseable(tmp_path) -> None:
    """End-to-end repro: deleted sidecar + refresh recreates a parseable file."""
    model_path = tmp_path / "MyModel.safetensors"
    model_path.write_bytes(b"fake model data")
    model_data = {
        "file_path": str(model_path),
        "folder": "extra_loras",
        "file_name": "MyModel",
        "model_name": "My Model",
        "size": 10,
        "modified": 100.0,
        "sha256": "abc123",
        "base_model": "Illustrious",
        "preview_url": "",
        "civitai": {"id": 123},
    }

    # Simulate the self-heal flow: hydrate from (missing) sidecar, then persist.
    await MetadataManager.hydrate_model_data(model_data)
    data_to_save = model_data.copy()
    data_to_save.pop("folder", None)
    await MetadataManager.save_metadata(str(model_path), data_to_save)

    metadata, should_skip = await MetadataManager.load_metadata(
        str(model_path), LoraMetadata
    )
    assert should_skip is False
    assert metadata is not None
    assert metadata.file_name == "MyModel"
    assert metadata.model_name == "My Model"
    assert metadata.sha256 == "abc123"
