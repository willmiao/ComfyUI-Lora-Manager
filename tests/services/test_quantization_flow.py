"""Scanner -> format_response flow tests for the quantization field."""

from __future__ import annotations

import hashlib
import io
import json
import os
import struct
from pathlib import Path
from typing import List

import pytest

from py.services import model_scanner
from py.services.checkpoint_scanner import CheckpointScanner
from py.services.checkpoint_service import CheckpointService
from py.services.model_scanner import ModelScanner


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


def _normalize(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _write_gguf(path: Path, file_type: int) -> None:
    """Write a minimal GGUF file whose general.file_type is ``file_type``."""
    blob = io.BytesIO()
    blob.write(b"GGUF")
    blob.write(struct.pack("<I", 3))  # version
    blob.write(struct.pack("<Q", 0))  # tensor_count
    blob.write(struct.pack("<Q", 1))  # metadata_kv_count
    key = b"general.file_type"
    blob.write(struct.pack("<Q", len(key)))
    blob.write(key)
    blob.write(struct.pack("<I", 4))  # UINT32
    blob.write(struct.pack("<I", file_type))
    path.write_bytes(blob.getvalue())


@pytest.mark.asyncio
async def test_gguf_checkpoint_quantization_flows_to_format_response(tmp_path: Path, monkeypatch):
    """A Q4_K_M GGUF checkpoint keeps its quantization from scan to API response."""
    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()
    checkpoint_file = checkpoints_root / "quantized_model.gguf"
    _write_gguf(checkpoint_file, 15)  # MOSTLY_Q4_K_M

    normalized_root = _normalize(checkpoints_root)
    normalized_file = _normalize(checkpoint_file)

    monkeypatch.setattr(model_scanner.config, "base_models_roots", [normalized_root], raising=False)
    monkeypatch.setattr(model_scanner.config, "checkpoints_roots", [normalized_root], raising=False)

    scanner = CheckpointScanner()
    model_data = await scanner._process_model_file(normalized_file, normalized_root)

    assert model_data is not None
    assert model_data["quantization"] == "Q4_K_M"

    # The checked value is persisted to the sidecar, so future scans never
    # re-read the header.
    sidecar = checkpoints_root / "quantized_model.metadata.json"
    assert sidecar.exists()
    saved = json.loads(sidecar.read_text(encoding="utf-8"))
    assert saved.get("quantization") == "Q4_K_M"

    service = CheckpointService(scanner)
    response = await service.format_response(model_data)
    assert response is not None
    assert response["quantization"] == "Q4_K_M"


@pytest.mark.asyncio
async def test_fp8_safetensors_checkpoint_quantization_flows_to_format_response(
    tmp_path: Path, monkeypatch
):
    """A safetensors checkpoint with a dominant F8 dtype reports FP8 end to end."""
    torch = pytest.importorskip("torch")
    from safetensors.torch import save_file

    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()
    checkpoint_file = checkpoints_root / "fp8_model.safetensors"
    save_file(
        {"weight": torch.zeros(32, 32, dtype=torch.float8_e4m3fn)},
        str(checkpoint_file),
    )

    normalized_root = _normalize(checkpoints_root)
    normalized_file = _normalize(checkpoint_file)

    monkeypatch.setattr(model_scanner.config, "base_models_roots", [normalized_root], raising=False)
    monkeypatch.setattr(model_scanner.config, "checkpoints_roots", [normalized_root], raising=False)

    scanner = CheckpointScanner()
    model_data = await scanner._process_model_file(normalized_file, normalized_root)

    assert model_data is not None
    assert model_data["quantization"] == "FP8"

    service = CheckpointService(scanner)
    response = await service.format_response(model_data)
    assert response is not None
    assert response["quantization"] == "FP8"


@pytest.mark.asyncio
async def test_fp16_safetensors_checkpoint_reports_checked_unavailable(
    tmp_path: Path, monkeypatch
):
    """An unquantized safetensors checkpoint stores '' (checked, no value)."""
    torch = pytest.importorskip("torch")
    from safetensors.torch import save_file

    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()
    checkpoint_file = checkpoints_root / "plain_model.safetensors"
    save_file({"weight": torch.zeros(32, 32, dtype=torch.float16)}, str(checkpoint_file))

    normalized_root = _normalize(checkpoints_root)
    normalized_file = _normalize(checkpoint_file)

    monkeypatch.setattr(model_scanner.config, "base_models_roots", [normalized_root], raising=False)
    monkeypatch.setattr(model_scanner.config, "checkpoints_roots", [normalized_root], raising=False)

    scanner = CheckpointScanner()
    model_data = await scanner._process_model_file(normalized_file, normalized_root)

    assert model_data is not None
    assert model_data["quantization"] == ""

    # JSON null encodes the checked-unavailable state in the sidecar.
    sidecar = checkpoints_root / "plain_model.metadata.json"
    saved = json.loads(sidecar.read_text(encoding="utf-8"))
    assert "quantization" in saved
    assert saved["quantization"] is None

    service = CheckpointService(scanner)
    response = await service.format_response(model_data)
    assert response is not None
    assert response["quantization"] == ""


@pytest.mark.asyncio
async def test_civitai_fp8_fallback_fills_unchecked_lora(tmp_path: Path, monkeypatch):
    """When content detection is inconclusive and the sidecar carries Civitai
    metadata whose SHA256-matching file is fp8, the scan resolves 'FP8'."""
    from py.services.lora_scanner import LoraScanner

    loras_root = tmp_path / "loras"
    loras_root.mkdir()
    lora_file = loras_root / "fp8_lora.safetensors"
    content = b"fake lora content - not a real safetensors header"
    lora_file.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()

    normalized_root = _normalize(loras_root)
    normalized_file = _normalize(lora_file)

    # Pre-existing sidecar with Civitai data but no quantization key yet.
    sidecar = loras_root / "fp8_lora.metadata.json"
    sidecar.write_text(
        json.dumps({
            "file_name": "fp8_lora",
            "model_name": "fp8_lora",
            "file_path": normalized_file,
            "size": len(content),
            "modified": 1.0,
            "sha256": sha256,
            "base_model": "Unknown",
            "preview_url": "",
            "civitai": {
                "files": [
                    {
                        "name": "fp8_lora.safetensors",
                        "hashes": {"SHA256": sha256.upper()},
                        "metadata": {"fp": "fp8"},
                    }
                ]
            },
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(model_scanner.config, "loras_roots", [normalized_root], raising=False)

    scanner = LoraScanner()
    model_data = await scanner._process_model_file(normalized_file, normalized_root)

    assert model_data is not None
    assert model_data["quantization"] == "FP8"

    saved = json.loads(sidecar.read_text(encoding="utf-8"))
    assert saved.get("quantization") == "FP8"
