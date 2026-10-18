"""Tests for the OpenModelDB model source (URL parsing, downloads, card context)."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

from py.services.model_sources import (
    ModelSourceError,
    detect_source,
    get_download_source,
    source_group_key,
)
from py.services.model_sources.openmodeldb import OpenModelDBSource
from py.services.openmodeldb_client import OpenModelDBClient

MODEL_SHA = "a" * 64
ALT_SHA = "b" * 64


def _dumps() -> Dict[str, Dict[str, Any]]:
    return {
        "models": {
            "4x-UltraSharp": {
                "name": "4x UltraSharp",
                "author": "kim",
                "license": "MIT",
                "tags": ["general"],
                "description": "Sharp general-purpose upscaler",
                "date": "2023-01-02",
                "architecture": "esrgan",
                "scale": 4,
                "resources": [
                    {
                        "platform": "pytorch",
                        "type": "pth",
                        "size": 67_000_000,
                        "sha256": MODEL_SHA,
                        "urls": [
                            "https://files.example.com/4x-UltraSharp.pth",
                            "https://mega.nz/file/mirror",
                        ],
                    },
                    {
                        "platform": "pytorch",
                        "type": "safetensors",
                        "size": 67_100_000,
                        "sha256": ALT_SHA,
                        "urls": ["https://files.example.com/4x-UltraSharp.safetensors"],
                    },
                ],
                "images": [
                    {
                        "type": "paired",
                        "LR": "https://img.example.com/lr.jpg",
                        "SR": "https://img.example.com/sr.jpg",
                    }
                ],
            },
            "onnx-only": {
                "name": "ONNX Only",
                "author": "kim",
                "architecture": "esrgan",
                "scale": 2,
                "resources": [
                    {
                        "platform": "onnx",
                        "type": "onnx",
                        "size": 10_000,
                        "sha256": "c" * 64,
                        "urls": ["https://files.example.com/onnx-only.onnx"],
                    }
                ],
            },
            "2x-90s-Sonic-LG": {
                "name": "90s Sonic 2x (Large)",
                "author": "kim",
                "architecture": "esrgan",
                "scale": 2,
                "resources": [
                    {
                        "platform": "pytorch",
                        "type": "pth",
                        "size": 9_443_322,
                        "sha256": "d" * 64,
                        "urls": [
                            "https://www.mediafire.com/file/e57pd40qph8nak2/90s_Sonic_2x.pth/file"
                        ],
                    }
                ],
            },
            "mixed-mirror": {
                "name": "Mixed Mirror",
                "author": "kim",
                "architecture": "esrgan",
                "scale": 4,
                "resources": [
                    {
                        "platform": "pytorch",
                        "type": "pth",
                        "size": 60_000_000,
                        "sha256": "e" * 64,
                        # Gateway host first, direct mirror second.
                        "urls": [
                            "https://mega.nz/folder/qZRBmaIY#nIG8KyWFcGNTuMX_XNbJ_g",
                            "https://files.example.com/Mixed-Mirror.pth",
                        ],
                    }
                ],
            },
        },
        "users": {"kim": {"name": "Kim"}},
        "tags": {"general": {"name": "General Purpose"}},
        "architectures": {"esrgan": {"name": "ESRGAN"}},
    }


@pytest.fixture
def client(tmp_path, monkeypatch) -> OpenModelDBClient:
    """A catalogue-loaded client, installed as the singleton for the source."""
    seeded = OpenModelDBClient(cache_dir=str(tmp_path / "omdb"))
    seeded._install_payloads(_dumps())
    monkeypatch.setattr(
        OpenModelDBClient, "get_instance", AsyncMock(return_value=seeded)
    )
    return seeded


# ---------------------------------------------------------------------------
# Identity and URL parsing
# ---------------------------------------------------------------------------


def test_url_parsing_lenient_and_strict():
    source = OpenModelDBSource()
    assert source.parse("https://openmodeldb.info/models/4x-UltraSharp") == "4x-UltraSharp"
    assert (
        source.parse("https://openmodeldb.info/models/4x-UltraSharp", strict=True)
        == "4x-UltraSharp"
    )
    assert (
        source.parse("https://openmodeldb.info/models/4x-UltraSharp/", strict=True)
        == "4x-UltraSharp"
    )
    # Query strings are tolerated only in lenient mode.
    assert source.parse("https://openmodeldb.info/models/4x-UltraSharp?x=1") == "4x-UltraSharp"
    assert source.parse("https://openmodeldb.info/models/4x-UltraSharp?x=1", strict=True) is None
    assert source.parse("https://openmodeldb.info/") is None


def test_detect_source_and_group_key():
    ref = detect_source("https://openmodeldb.info/models/4x-UltraSharp")
    assert ref is not None
    assert ref.platform == "openmodeldb"
    assert ref.source_id == "4x-UltraSharp"
    assert ref.url == "https://openmodeldb.info/models/4x-UltraSharp"

    # The model id IS the published-model identity, so downloads group by it.
    assert (
        source_group_key(
            {"source_url": ref.url, "source_platform": "openmodeldb"}
        )
        == "omdb:4x-UltraSharp"
    )


def test_flat_source_id_validation_and_default_paths():
    source = get_download_source("openmodeldb")
    assert source is not None
    assert source.is_valid_source_id("4x-UltraSharp") is True
    assert source.is_valid_source_id("owner/name") is False
    assert source.is_valid_source_id("../escape") is False
    assert source.is_valid_source_id("") is False
    # Flat catalogue: no owner/repo namespace under the default directory.
    assert source.default_subdir_parts("4x-UltraSharp") == ("openmodeldb",)


def test_capabilities():
    source = OpenModelDBSource()
    assert source.supports_download is True
    assert source.supports_enrichment is True
    assert source.example_source_id
    assert source.canonical_url(source.example_source_id).startswith(
        "https://openmodeldb.info/models/"
    )


# ---------------------------------------------------------------------------
# File listing and download URL resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_files_returns_pytorch_resources_largest_first(client):
    files = await OpenModelDBSource().list_files("4x-UltraSharp")
    assert [f["filename"] for f in files] == [
        "4x-UltraSharp.safetensors",
        "4x-UltraSharp.pth",
    ]
    assert files[0]["size"] == 67_100_000


@pytest.mark.asyncio
async def test_list_files_skips_non_pytorch_resources(client):
    # `.onnx` is not a loadable weight format, so an onnx-only model has an
    # empty download list rather than offering an unusable file.
    assert await OpenModelDBSource().list_files("onnx-only") == []


@pytest.mark.asyncio
async def test_list_files_raises_manual_download_hint_when_mirror_only(client):
    # Every mirror is an HTML gateway: an empty list would surface in the UI
    # as "no model files found", so the source reports the actionable cause.
    with pytest.raises(ModelSourceError) as excinfo:
        await OpenModelDBSource().list_files("2x-90s-Sonic-LG")
    assert excinfo.value.status == 400
    assert "manual" in str(excinfo.value).lower()
    assert "openmodeldb.info/models/2x-90s-Sonic-LG" in str(excinfo.value)


@pytest.mark.asyncio
async def test_list_files_prefers_direct_mirror_over_gateway(client):
    files = await OpenModelDBSource().list_files("mixed-mirror")
    assert files == [{"filename": "Mixed-Mirror.pth", "size": 60_000_000}]


@pytest.mark.asyncio
async def test_resolve_download_url_rejects_html_gateway_mirror(client):
    with pytest.raises(ModelSourceError) as excinfo:
        await OpenModelDBSource().resolve_download_url(
            "2x-90s-Sonic-LG", "90s_Sonic_2x.pth"
        )
    assert excinfo.value.status == 400
    message = str(excinfo.value)
    assert "mediafire.com" in message
    assert "openmodeldb.info/models/2x-90s-Sonic-LG" in message


@pytest.mark.asyncio
async def test_resolve_download_url_uses_direct_mirror(client):
    url = await OpenModelDBSource().resolve_download_url(
        "mixed-mirror", "Mixed-Mirror.pth"
    )
    assert url == "https://files.example.com/Mixed-Mirror.pth"


@pytest.mark.asyncio
async def test_list_files_unknown_model_raises_404(client):
    with pytest.raises(ModelSourceError) as excinfo:
        await OpenModelDBSource().list_files("nope")
    assert excinfo.value.status == 404


@pytest.mark.asyncio
async def test_resolve_download_url_uses_primary_url_only(client):
    source = OpenModelDBSource()
    url = await source.resolve_download_url("4x-UltraSharp", "4x-UltraSharp.pth")
    # Mirrors (mega.nz & co.) need site-specific handling and are never used.
    assert url == "https://files.example.com/4x-UltraSharp.pth"
    assert (
        await source.resolve_download_url("4x-UltraSharp", "4x-UltraSharp.safetensors")
        == "https://files.example.com/4x-UltraSharp.safetensors"
    )


@pytest.mark.asyncio
async def test_resolve_download_url_unknown_file_raises_404(client):
    with pytest.raises(ModelSourceError) as excinfo:
        await OpenModelDBSource().resolve_download_url("4x-UltraSharp", "nope.pth")
    assert excinfo.value.status == 404


@pytest.mark.asyncio
async def test_unavailable_catalogue_raises_502(tmp_path, monkeypatch):
    broken = OpenModelDBClient(cache_dir=str(tmp_path / "omdb"))
    monkeypatch.setattr(broken, "_ensure_loaded", AsyncMock(return_value=False))
    monkeypatch.setattr(
        OpenModelDBClient, "get_instance", AsyncMock(return_value=broken)
    )

    with pytest.raises(ModelSourceError) as excinfo:
        await OpenModelDBSource().list_files("4x-UltraSharp")
    assert excinfo.value.status == 502

    with pytest.raises(ModelSourceError) as excinfo:
        await OpenModelDBSource().resolve_download_url("4x-UltraSharp", "x.pth")
    assert excinfo.value.status == 502


# ---------------------------------------------------------------------------
# Card context (download-time hydration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_model_card_context(client):
    context = await OpenModelDBSource().fetch_model_card_context(
        "4x-UltraSharp", "4x-UltraSharp.pth", sha256=MODEL_SHA
    )
    assert context.description == "Sharp general-purpose upscaler"
    assert context.model_name == "4x UltraSharp"
    assert context.license == "MIT"
    assert context.model_type == "Upscaler"
    assert context.official_tags == ["General Purpose"]
    # Paired previews show the upscaled (SR) result.
    assert context.example_images == ["https://img.example.com/sr.jpg"]
    assert context.source_model_id == "4x-UltraSharp"
    assert context.is_empty() is False


@pytest.mark.asyncio
async def test_fetch_model_card_context_unknown_model_is_empty(client):
    context = await OpenModelDBSource().fetch_model_card_context("nope")
    assert context.is_empty() is True


@pytest.mark.asyncio
async def test_fetch_model_card_context_survives_catalogue_failure(
    tmp_path, monkeypatch
):
    broken = OpenModelDBClient(cache_dir=str(tmp_path / "omdb"))
    monkeypatch.setattr(
        broken, "_ensure_loaded", AsyncMock(side_effect=RuntimeError("boom"))
    )
    monkeypatch.setattr(
        OpenModelDBClient, "get_instance", AsyncMock(return_value=broken)
    )
    # Never raises: a lookup fault reads as "the site had nothing extra".
    context = await OpenModelDBSource().fetch_model_card_context("4x-UltraSharp")
    assert context.is_empty() is True
