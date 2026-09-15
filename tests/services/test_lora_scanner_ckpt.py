"""Tests for LoRA scanner discovery of Draw Things converted .ckpt LoRA files."""

import os
from pathlib import Path

import pytest

from py.services import model_scanner
from py.services.lora_scanner import LoraScanner
from py.services.model_scanner import ModelScanner


def _normalize(path: Path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


def _make_loras_root(tmp_path: Path):
    """Create a loras root containing a .safetensors and a Draw Things style .ckpt file."""
    loras_root = tmp_path / "loras"
    loras_root.mkdir()

    safetensors_file = loras_root / "test_lora.safetensors"
    safetensors_file.write_bytes(b"\x00" * 64)

    # Draw Things names converted LoRAs like `<name>_lora_f16.ckpt`
    ckpt_file = loras_root / "draw_things_lora_f16.ckpt"
    ckpt_file.write_bytes(b"\x00" * 64)

    ignored_file = loras_root / "notes.txt"
    ignored_file.write_text("not a model", encoding="utf-8")

    return loras_root, safetensors_file, ckpt_file, ignored_file


@pytest.mark.asyncio
async def test_lora_scanner_supports_ckpt_extension(tmp_path: Path, monkeypatch):
    """The LoRA scanner must accept .ckpt alongside .safetensors."""
    loras_root, _, _, _ = _make_loras_root(tmp_path)

    monkeypatch.setattr(
        model_scanner.config,
        "loras_roots",
        [_normalize(loras_root)],
        raising=False,
    )

    scanner = LoraScanner()

    assert scanner.file_extensions == {".safetensors", ".ckpt"}


@pytest.mark.asyncio
async def test_lora_scanner_discovers_ckpt_files(tmp_path: Path, monkeypatch):
    """Draw Things converted .ckpt LoRAs must be discovered during the scan."""
    loras_root, safetensors_file, ckpt_file, ignored_file = _make_loras_root(tmp_path)

    monkeypatch.setattr(
        model_scanner.config,
        "loras_roots",
        [_normalize(loras_root)],
        raising=False,
    )

    scanner = LoraScanner()

    result = await scanner._gather_model_data()

    discovered = {entry["file_path"] for entry in result.raw_data}
    assert _normalize(safetensors_file) in discovered, "safetensors file should still be discovered"
    assert _normalize(ckpt_file) in discovered, "Draw Things .ckpt LoRA should be discovered"
    assert len(result.raw_data) == 2, "unsupported extensions (.txt) must stay ignored"
    assert all(not path.endswith(ignored_file.suffix) for path in discovered)
