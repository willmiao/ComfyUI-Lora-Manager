"""Cached-metadata fallback for the model modal.

When the model's disk is offline the authoritative ``.metadata.json`` cannot be
read, but the scanner still holds the cache entry. The modal must keep showing
what the cache retains (creator, version name, trigger words, license
permissions) instead of falling back to the stripped list payload.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from py.services.lora_service import LoraService
from py.utils.civitai_utils import build_license_flags
from py.utils.models import LoraMetadata


def make_service(entries, *, path_available=True):
    scanner = Mock()
    scanner.get_cached_data = AsyncMock(
        return_value=SimpleNamespace(raw_data=list(entries))
    )
    scanner.is_file_path_available = Mock(return_value=path_available)
    return LoraService(scanner)


def make_entry(file_path):
    return {
        "file_path": file_path,
        "file_name": "artist_style",
        "model_name": "Artist Style",
        "base_model": "Illustrious",
        "license_flags": build_license_flags(
            {
                "allowNoCredit": False,
                "allowCommercialUse": ["Image", "Rent"],
                "allowDerivatives": False,
                "allowDifferentLicense": True,
            }
        ),
        "civitai": {
            "id": 42,
            "modelId": 7,
            "name": "v2.0",
            "creator": {"username": "artist"},
            "trainedWords": ["artist style"],
            "model": {"type": "LORA"},
        },
    }


@pytest.fixture
def offline_model(tmp_path):
    """A cache entry whose model file and sidecar are on an unreachable root."""
    file_path = str(tmp_path / "removable" / "artist_style.safetensors")
    return file_path, make_entry(file_path)


async def test_metadata_falls_back_to_cache_entry(offline_model):
    file_path, entry = offline_model
    service = make_service([entry], path_available=False)

    metadata, partial, offline = await service.get_model_metadata_with_fallback(file_path)

    assert partial is True
    assert offline is True
    assert metadata["creator"] == {"username": "artist"}
    assert metadata["name"] == "v2.0"
    assert metadata["id"] == 42
    assert metadata["modelId"] == 7
    assert metadata["trainedWords"] == ["artist style"]
    assert metadata["baseModel"] == "Illustrious"


async def test_fallback_decodes_license_permissions(offline_model):
    file_path, entry = offline_model
    service = make_service([entry], path_available=False)

    metadata, _partial, _offline = await service.get_model_metadata_with_fallback(file_path)

    assert metadata["model"] == {
        "type": "LORA",
        "allowNoCredit": False,
        "allowCommercialUse": ["Image", "Rent"],
        "allowDerivatives": False,
        "allowDifferentLicense": True,
    }


async def test_fallback_does_not_invent_license_data_without_civitai_model(tmp_path):
    file_path = str(tmp_path / "huggingface" / "flux.safetensors")
    entry = {
        "file_path": file_path,
        "file_name": "flux",
        "model_name": "Flux",
        "base_model": "Flux",
        "license_flags": 127,
        "civitai": {
            "trainedWords": ["trigger"],
            "creator": {"username": "someone"},
        },
    }
    service = make_service([entry], path_available=False)

    metadata, partial, _offline = await service.get_model_metadata_with_fallback(file_path)

    assert partial is True
    assert "model" not in metadata
    assert metadata["creator"] == {"username": "someone"}


async def test_fallback_matches_forward_slashed_cache_path(offline_model):
    file_path, entry = offline_model
    service = make_service([entry], path_available=False)

    # The API echoes the path as the card sent it (host separators on Windows).
    windows_style = file_path.replace("/", "\\")

    metadata, partial, _offline = await service.get_model_metadata_with_fallback(
        windows_style
    )

    assert partial is True
    assert metadata["name"] == "v2.0"


async def test_unknown_path_still_reports_missing_metadata(tmp_path):
    service = make_service([], path_available=True)

    metadata, partial, offline = await service.get_model_metadata_with_fallback(
        str(tmp_path / "elsewhere" / "nope.safetensors")
    )

    assert metadata is None
    assert partial is False
    assert offline is False


async def test_entry_without_civitai_data_reports_missing_metadata(tmp_path):
    file_path = str(tmp_path / "plain" / "hf-model.safetensors")
    entry = {
        "file_path": file_path,
        "file_name": "hf-model",
        "model_name": "HF Model",
        "base_model": "Flux",
        "civitai": None,
    }
    service = make_service([entry], path_available=False)

    metadata, partial, offline = await service.get_model_metadata_with_fallback(file_path)

    assert metadata is None
    assert partial is False
    assert offline is True


async def test_sidecar_payload_wins_when_readable(tmp_path, offline_model):
    file_path, entry = offline_model
    sidecar = tmp_path / "removable" / "artist_style.metadata.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps(
            {
                "file_name": "artist_style",
                "model_name": "Artist Style",
                "file_path": file_path,
                "size": 1234,
                "modified": 111.0,
                "sha256": "a" * 64,
                "base_model": "Illustrious",
                "preview_url": "",
                "civitai": {"name": "v3.0", "creator": {"username": "artist"}},
            }
        ),
        encoding="utf-8",
    )

    scanner_service = make_service([entry], path_available=True)
    scanner_service.scanner.sync_cache_from_metadata = AsyncMock(return_value=False)

    metadata, partial, offline = await scanner_service.get_model_metadata_with_fallback(
        file_path
    )

    assert partial is False
    assert offline is False
    assert metadata["name"] == "v3.0"


async def test_offline_path_skips_the_disk_read_in_alongside_mode(
    offline_model, monkeypatch
):
    """A dead share must not be stat()ed just to open the modal."""
    file_path, entry = offline_model
    load_metadata = AsyncMock(return_value=(None, False))
    monkeypatch.setattr(
        "py.services.base_model_service.MetadataManager.load_metadata", load_metadata
    )
    monkeypatch.setattr(
        "py.services.base_model_service.is_centralized", lambda: False
    )

    service = make_service([entry], path_available=False)
    metadata, partial, _offline = await service.get_model_metadata_with_fallback(file_path)

    load_metadata.assert_not_awaited()
    assert partial is True
    assert metadata["creator"] == {"username": "artist"}


async def test_centralized_storage_still_reads_the_sidecar_when_drive_is_offline(
    offline_model, monkeypatch
):
    """Centralized sidecars sit on the app disk, so the real payload survives."""
    file_path, entry = offline_model
    sidecar_payload = LoraMetadata(
        file_name="artist_style",
        model_name="Artist Style",
        file_path=file_path,
        size=1234,
        modified=111.0,
        sha256="a" * 64,
        base_model="Illustrious",
        preview_url="",
        civitai={"name": "v3.0", "creator": {"username": "artist"}},
    )
    monkeypatch.setattr(
        "py.services.base_model_service.MetadataManager.load_metadata",
        AsyncMock(return_value=(sidecar_payload, False)),
    )
    monkeypatch.setattr(
        "py.services.base_model_service.is_centralized", lambda: True
    )
    service = make_service([entry], path_available=False)
    service.scanner.sync_cache_from_metadata = AsyncMock(return_value=False)

    metadata, partial, offline = await service.get_model_metadata_with_fallback(file_path)

    assert partial is False
    assert offline is True
    assert metadata["name"] == "v3.0"
