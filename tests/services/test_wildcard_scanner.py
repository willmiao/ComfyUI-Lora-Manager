from __future__ import annotations

import pytest

from py.services.model_cache import ModelCache
from py.services.wildcard_scanner import WildcardScanner
from py.utils.models import WildcardMetadata


@pytest.mark.asyncio
async def test_default_metadata_contains_parsed_index(tmp_path):
    artifact = tmp_path / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    scanner = WildcardScanner()

    metadata = await scanner._create_default_metadata(str(artifact))

    assert isinstance(metadata, WildcardMetadata)
    assert metadata.wildcard_format == "txt"
    assert metadata.entry_count == 1
    assert metadata.value_count == 2
    assert metadata.entries[0]["key"] == "colors"
    assert metadata.sha256


@pytest.mark.asyncio
async def test_cache_entry_keeps_parsed_index(tmp_path):
    artifact = tmp_path / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    scanner = WildcardScanner()

    metadata = await scanner._create_default_metadata(str(artifact))
    entry = scanner._build_cache_entry(metadata)

    assert entry["wildcard_format"] == "txt"
    assert entry["files"] == ["colors.txt"]
    assert entry["entries"][0]["key"] == "colors"
    assert entry["entry_count"] == 1
    assert entry["value_count"] == 2


@pytest.mark.asyncio
async def test_backfill_restores_index_for_hydrated_entries(tmp_path, monkeypatch):
    artifact = tmp_path / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    scanner = WildcardScanner()
    metadata = await scanner._create_default_metadata(str(artifact))

    hydrated = {
        "file_path": metadata.file_path,
        "file_name": metadata.file_name,
        "model_name": metadata.model_name,
        "sha256": metadata.sha256,
    }
    scanner._cache = ModelCache(raw_data=[hydrated], folders=[])

    persisted = []

    async def fake_persist():
        persisted.append(True)

    monkeypatch.setattr(scanner, "_persist_current_cache", fake_persist)

    await scanner._backfill_parsed_index()

    assert hydrated["wildcard_format"] == "txt"
    assert hydrated["files"] == ["colors.txt"]
    assert hydrated["entries"][0]["key"] == "colors"
    assert hydrated["entry_count"] == 1
    assert hydrated["value_count"] == 2
    assert persisted == [True]


def test_civitai_metadata_uses_model_and_version_identity():
    version = {
        "id": 20,
        "modelId": 10,
        "name": "v1",
        "baseModel": "Other",
        "model": {"name": "Pack", "type": "Wildcards", "tags": ["style"]},
    }
    file_info = {"name": "pack.zip", "sizeKB": 2, "hashes": {"SHA256": "abc"}}

    metadata = WildcardMetadata.from_civitai_info(version, file_info, "/library/pack.zip")

    assert metadata.model_name == "Pack"
    assert metadata.civitai["id"] == 20
    assert metadata.sub_type == "wildcard"
    assert metadata.wildcard_format == "zip"
