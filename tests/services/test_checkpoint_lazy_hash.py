"""Tests for checkpoint lazy hash calculation feature."""

import json
import os
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from py.services import model_scanner
from py.services.checkpoint_scanner import CheckpointScanner
from py.services.model_scanner import ModelScanner
from py.utils.models import CheckpointMetadata


class RecordingWebSocketManager:
    def __init__(self) -> None:
        self.payloads: List[dict] = []

    async def broadcast_init_progress(self, payload: dict) -> None:
        self.payloads.append(payload)


def _normalize(path: Path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


@pytest.mark.asyncio
async def test_checkpoint_default_metadata_has_pending_hash(tmp_path: Path, monkeypatch):
    """Test that checkpoint metadata is created with hash_status='pending' and empty sha256."""
    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()

    # Create a fake checkpoint file (small for testing)
    checkpoint_file = checkpoints_root / "test_model.safetensors"
    checkpoint_file.write_text("fake checkpoint content", encoding="utf-8")

    normalized_root = _normalize(checkpoints_root)
    normalized_file = _normalize(checkpoint_file)

    monkeypatch.setattr(
        model_scanner.config,
        "base_models_roots",
        [normalized_root],
        raising=False,
    )
    monkeypatch.setattr(
        model_scanner.config,
        "checkpoints_roots",
        [normalized_root],
        raising=False,
    )

    scanner = CheckpointScanner()
    
    # Create default metadata
    metadata = await scanner._create_default_metadata(normalized_file)
    
    assert metadata is not None
    assert metadata.sha256 == "", "sha256 should be empty for lazy hash"
    assert metadata.hash_status == "pending", "hash_status should be 'pending'"
    assert metadata.from_civitai is False, "from_civitai should be False for local models"
    assert metadata.file_name == "test_model"


@pytest.mark.asyncio
async def test_checkpoint_metadata_saved_to_disk_with_pending_status(tmp_path: Path, monkeypatch):
    """Test that pending metadata is saved to .metadata.json file."""
    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()

    checkpoint_file = checkpoints_root / "test_model.safetensors"
    checkpoint_file.write_text("fake content", encoding="utf-8")

    normalized_root = _normalize(checkpoints_root)
    normalized_file = _normalize(checkpoint_file)

    monkeypatch.setattr(
        model_scanner.config,
        "base_models_roots",
        [normalized_root],
        raising=False,
    )

    scanner = CheckpointScanner()
    
    # Create metadata
    metadata = await scanner._create_default_metadata(normalized_file)
    assert metadata is not None
    
    # Verify the metadata file was created
    metadata_file = checkpoints_root / "test_model.metadata.json"
    assert metadata_file.exists(), "Metadata file should be created"
    
    # Load and verify content
    with open(metadata_file, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    
    assert saved_data.get("sha256") == "", "Saved sha256 should be empty"
    assert saved_data.get("hash_status") == "pending", "Saved hash_status should be 'pending'"


@pytest.mark.asyncio
async def test_calculate_hash_for_model_completes_pending(tmp_path: Path, monkeypatch):
    """Test that calculate_hash_for_model updates status to 'completed'."""
    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()

    checkpoint_file = checkpoints_root / "test_model.safetensors"
    checkpoint_file.write_text("fake content for hashing", encoding="utf-8")

    normalized_root = _normalize(checkpoints_root)
    normalized_file = _normalize(checkpoint_file)

    monkeypatch.setattr(
        model_scanner.config,
        "base_models_roots",
        [normalized_root],
        raising=False,
    )

    scanner = CheckpointScanner()
    
    # Create pending metadata
    metadata = await scanner._create_default_metadata(normalized_file)
    assert metadata is not None
    assert metadata.hash_status == "pending"
    
    # Calculate hash
    hash_result = await scanner.calculate_hash_for_model(normalized_file)
    
    assert hash_result is not None, "Hash calculation should succeed"
    assert len(hash_result) == 64, "SHA256 should be 64 hex characters"
    
    # Verify metadata was updated
    metadata_file = checkpoints_root / "test_model.metadata.json"
    with open(metadata_file, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    
    assert saved_data.get("sha256") == hash_result, "sha256 should be updated"
    assert saved_data.get("hash_status") == "completed", "hash_status should be 'completed'"


@pytest.mark.asyncio
async def test_calculate_hash_skips_if_already_completed(tmp_path: Path, monkeypatch):
    """Test that calculate_hash_for_model skips calculation if already completed."""
    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()

    checkpoint_file = checkpoints_root / "test_model.safetensors"
    checkpoint_file.write_text("fake content", encoding="utf-8")

    normalized_root = _normalize(checkpoints_root)
    normalized_file = _normalize(checkpoint_file)

    monkeypatch.setattr(
        model_scanner.config,
        "base_models_roots",
        [normalized_root],
        raising=False,
    )

    scanner = CheckpointScanner()
    
    # Create metadata with completed hash
    metadata = CheckpointMetadata(
        file_name="test_model",
        model_name="test_model",
        file_path=normalized_file,
        size=100,
        modified=1234567890.0,
        sha256="existing_hash_value",
        base_model="Unknown",
        preview_url="",
        hash_status="completed",
        from_civitai=False,
    )
    
    # Save metadata first
    from py.utils.metadata_manager import MetadataManager
    await MetadataManager.save_metadata(normalized_file, metadata)
    
    # Calculate hash should return existing value
    with patch("py.utils.file_utils.calculate_sha256") as mock_calc:
        mock_calc.return_value = "new_calculated_hash"
        hash_result = await scanner.calculate_hash_for_model(normalized_file)
    
    assert hash_result == "existing_hash_value", "Should return existing hash"
    mock_calc.assert_not_called(), "Should not recalculate if already completed"


@pytest.mark.asyncio
async def test_calculate_all_pending_hashes(tmp_path: Path, monkeypatch):
    """Test bulk hash calculation for all pending checkpoints."""
    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()

    # Create multiple checkpoint files
    for i in range(3):
        checkpoint_file = checkpoints_root / f"model_{i}.safetensors"
        checkpoint_file.write_text(f"content {i}", encoding="utf-8")

    normalized_root = _normalize(checkpoints_root)

    monkeypatch.setattr(
        model_scanner.config,
        "base_models_roots",
        [normalized_root],
        raising=False,
    )

    scanner = CheckpointScanner()
    
    # Create pending metadata for all models
    for i in range(3):
        checkpoint_file = checkpoints_root / f"model_{i}.safetensors"
        await scanner._create_default_metadata(_normalize(checkpoint_file))
    
    # Mock progress callback
    progress_calls = []
    async def progress_callback(current, total, file_path):
        progress_calls.append((current, total, file_path))
    
    # Calculate all pending hashes
    result = await scanner.calculate_all_pending_hashes(progress_callback)
    
    assert result["total"] == 3, "Should find 3 pending models"
    assert result["completed"] == 3, "Should complete all 3"
    assert result["failed"] == 0, "Should not fail any"
    assert len(progress_calls) == 3, "Progress callback should be called 3 times"


@pytest.mark.asyncio
async def test_lora_scanner_not_affected(tmp_path: Path, monkeypatch):
    """Test that LoraScanner still calculates hash during initial scan."""
    from py.services.lora_scanner import LoraScanner
    
    loras_root = tmp_path / "loras"
    loras_root.mkdir()

    lora_file = loras_root / "test_lora.safetensors"
    lora_file.write_text("fake lora content", encoding="utf-8")

    normalized_root = _normalize(loras_root)

    monkeypatch.setattr(
        model_scanner.config,
        "loras_roots",
        [normalized_root],
        raising=False,
    )

    # Reset singleton for LoraScanner
    if LoraScanner in ModelScanner._instances:
        del ModelScanner._instances[LoraScanner]

    scanner = LoraScanner()
    
    # LoraScanner should use parent's _create_default_metadata which calculates hash
    # We verify this by checking that it doesn't override the method
    assert scanner._create_default_metadata.__qualname__ == "ModelScanner._create_default_metadata"
