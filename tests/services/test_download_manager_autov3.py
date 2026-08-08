"""AutoV3 resolution in the download completion path (``_build_metadata_entries``).

Covers the Civitai-first / local-header fallback contract: a downloaded file
whose Civitai file_info reports no AutoV3 gets the embedded safetensors header
hash resolved right away (instead of waiting for the next startup's backfill),
and a file with no usable header is marked ``''`` (checked but unavailable).
"""

import json
import struct

import pytest

from py.services.download_manager import DownloadManager
from py.utils.models import LoraMetadata


def _write_safetensors(path, metadata, payload=b"payload-bytes"):
    """Write a minimal real safetensors file: 8-byte little-endian header
    length, a JSON header containing ``__metadata__``, then arbitrary payload."""
    header = json.dumps({"__metadata__": metadata}).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)


@pytest.fixture
def manager():
    # _build_metadata_entries touches no instance state, so a bare instance is
    # enough and avoids the DownloadManager singleton's heavy dependencies.
    return DownloadManager.__new__(DownloadManager)


def _lora_metadata(file_path: str, autov3=None):
    return LoraMetadata(
        file_name="model",
        model_name="Model",
        file_path=str(file_path),
        size=0,
        modified=0.0,
        sha256="abc123",
        base_model="SDXL",
        preview_url="",
        autov3=autov3,
    )


@pytest.mark.asyncio
async def test_keeps_civitai_reported_autov3(manager, tmp_path):
    file_path = tmp_path / "model.safetensors"
    _write_safetensors(file_path, {"sshs_model_hash": "ffffffffffffffffffff"})
    metadata = _lora_metadata(file_path, autov3="abcdef123456")

    entries = await manager._build_metadata_entries(metadata, [str(file_path)])

    assert entries[0].autov3 == "abcdef123456"


@pytest.mark.asyncio
async def test_resolves_header_autov3_when_civitai_missing(manager, tmp_path):
    file_path = tmp_path / "model.safetensors"
    _write_safetensors(file_path, {"sshs_model_hash": "ABCDEF1234567890ABCDEF"})
    metadata = _lora_metadata(file_path, autov3=None)

    entries = await manager._build_metadata_entries(metadata, [str(file_path)])

    assert entries[0].autov3 == "abcdef123456"


@pytest.mark.asyncio
async def test_marks_checked_unavailable_when_no_header_hash(manager, tmp_path):
    file_path = tmp_path / "model.ckpt"
    file_path.write_bytes(b"just some plain bytes, not a safetensors file")
    metadata = _lora_metadata(file_path, autov3=None)

    entries = await manager._build_metadata_entries(metadata, [str(file_path)])

    assert entries[0].autov3 == ""


@pytest.mark.asyncio
async def test_does_not_retry_checked_unavailable(manager, tmp_path, monkeypatch):
    # '' (checked but unavailable) must never trigger a header re-read: the
    # backfill query (autov3 IS NULL) already excludes such rows, and the
    # download-time guard must honor the same contract.
    file_path = tmp_path / "model.ckpt"
    file_path.write_bytes(b"bytes")
    metadata = _lora_metadata(file_path, autov3="")
    called = {"count": 0}

    def _spy_calculate_autov3(_path):
        called["count"] += 1
        return None

    monkeypatch.setattr(
        "py.services.download_manager.calculate_autov3", _spy_calculate_autov3
    )

    entries = await manager._build_metadata_entries(metadata, [str(file_path)])

    assert entries[0].autov3 == ""
    assert called["count"] == 0
