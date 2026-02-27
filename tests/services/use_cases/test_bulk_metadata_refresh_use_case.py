"""Tests for BulkMetadataRefreshUseCase."""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

from py.services.use_cases.bulk_metadata_refresh_use_case import (
    BulkMetadataRefreshUseCase,
    MetadataRefreshProgressReporter,
)
from py.utils import metadata_manager


class MockProgressReporter:
    """Mock progress reporter for testing."""

    def __init__(self):
        self.progress_calls = []

    async def on_progress(self, payload: Dict[str, Any]) -> None:
        self.progress_calls.append(payload)


@pytest.fixture
def mock_service():
    """Create a mock service with scanner."""
    scanner = MagicMock()
    scanner.get_cached_data = AsyncMock()
    scanner.reset_cancellation = MagicMock()
    scanner.is_cancelled = MagicMock(return_value=False)
    scanner.update_single_model_cache = AsyncMock(return_value=True)
    scanner.calculate_hash_for_model = AsyncMock(return_value="calculated_hash_123")

    service = MagicMock()
    service.scanner = scanner
    service.model_type = "checkpoint"

    return service


@pytest.fixture
def mock_metadata_sync():
    """Create a mock metadata sync service."""
    sync = MagicMock()
    sync.fetch_and_update_model = AsyncMock(return_value=(True, None))
    return sync


@pytest.fixture
def mock_settings():
    """Create mock settings service."""
    settings = MagicMock()
    settings.get = MagicMock(return_value=False)
    return settings


@pytest.fixture
def use_case(mock_service, mock_metadata_sync, mock_settings):
    """Create a BulkMetadataRefreshUseCase instance."""
    return BulkMetadataRefreshUseCase(
        service=mock_service,
        metadata_sync=mock_metadata_sync,
        settings_service=mock_settings,
    )


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_pending_hash_calculated_on_demand(mock_hydrate, use_case, mock_service, mock_metadata_sync):
    """Test that models with pending hash status get their hash calculated on demand."""
    mock_hydrate.return_value = None
    
    # Setup cache with a model that has pending hash
    pending_model = {
        "file_path": "/extra_ckpt/model.safetensors",
        "sha256": "",  # Empty hash
        "hash_status": "pending",
        "model_name": "Test Model",
        "folder": "extra_ckpt",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    cache = SimpleNamespace(raw_data=[pending_model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    # Execute
    result = await use_case.execute()

    # Verify hash was calculated
    mock_service.scanner.calculate_hash_for_model.assert_called_once_with(
        "/extra_ckpt/model.safetensors"
    )

    # Verify model hash was updated
    assert pending_model["sha256"] == "calculated_hash_123"
    assert pending_model["hash_status"] == "completed"

    # Verify metadata sync was called with the calculated hash
    mock_metadata_sync.fetch_and_update_model.assert_called_once()
    call_args = mock_metadata_sync.fetch_and_update_model.call_args[1]
    assert call_args["sha256"] == "calculated_hash_123"

    assert result["success"] is True


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_skip_model_when_hash_calculation_fails(mock_hydrate, use_case, mock_service, mock_metadata_sync):
    """Test that models are skipped when hash calculation fails."""
    mock_hydrate.return_value = None
    
    # Setup model with pending hash
    pending_model = {
        "file_path": "/extra_ckpt/model.safetensors",
        "sha256": "",
        "hash_status": "pending",
        "model_name": "Test Model",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    # Make hash calculation fail
    mock_service.scanner.calculate_hash_for_model.return_value = None

    cache = SimpleNamespace(raw_data=[pending_model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    # Execute
    result = await use_case.execute()

    # Verify hash was attempted
    mock_service.scanner.calculate_hash_for_model.assert_called_once()

    # Verify metadata sync was NOT called (model skipped)
    mock_metadata_sync.fetch_and_update_model.assert_not_called()

    # Verify result shows processed but no success
    assert result["success"] is True
    assert result["processed"] == 1
    assert result["updated"] == 0


@pytest.mark.asyncio
async def test_skip_model_when_scanner_does_not_support_lazy_hash(
    use_case, mock_service, mock_metadata_sync
):
    """Test that models are skipped when scanner doesn't support lazy hash calculation."""
    # Setup model with pending hash
    pending_model = {
        "file_path": "/models/model.safetensors",
        "sha256": "",
        "hash_status": "pending",
        "model_name": "Test Model",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    # Remove calculate_hash_for_model method (simulating LoRA scanner)
    del mock_service.scanner.calculate_hash_for_model

    cache = SimpleNamespace(raw_data=[pending_model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    # Execute
    result = await use_case.execute()

    # Verify metadata sync was NOT called
    mock_metadata_sync.fetch_and_update_model.assert_not_called()

    assert result["success"] is True
    assert result["processed"] == 1
    assert result["updated"] == 0


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_normal_model_with_existing_hash_not_affected(mock_hydrate, use_case, mock_service, mock_metadata_sync):
    """Test that models with existing hash work normally."""
    mock_hydrate.return_value = None
    
    # Setup model with existing hash
    existing_model = {
        "file_path": "/models/model.safetensors",
        "sha256": "existing_hash_abc",
        "hash_status": "completed",
        "model_name": "Test Model",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    cache = SimpleNamespace(raw_data=[existing_model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    # Execute
    result = await use_case.execute()

    # Verify hash calculation was NOT called
    assert not mock_service.scanner.calculate_hash_for_model.called

    # Verify metadata sync was called with existing hash
    mock_metadata_sync.fetch_and_update_model.assert_called_once()
    call_args = mock_metadata_sync.fetch_and_update_model.call_args[1]
    assert call_args["sha256"] == "existing_hash_abc"

    assert result["success"] is True
    assert result["updated"] == 1


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_mixed_models_some_pending_some_existing(mock_hydrate, use_case, mock_service, mock_metadata_sync):
    """Test handling of mixed models: some with pending hash, some with existing hash."""
    mock_hydrate.return_value = None
    
    pending_model = {
        "file_path": "/extra_ckpt/pending_model.safetensors",
        "sha256": "",
        "hash_status": "pending",
        "model_name": "Pending Model",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    existing_model = {
        "file_path": "/models/existing_model.safetensors",
        "sha256": "existing_hash_xyz",
        "hash_status": "completed",
        "model_name": "Existing Model",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    cache = SimpleNamespace(raw_data=[pending_model, existing_model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    # Execute
    result = await use_case.execute()

    # Verify hash was calculated only for pending model
    mock_service.scanner.calculate_hash_for_model.assert_called_once_with(
        "/extra_ckpt/pending_model.safetensors"
    )

    # Verify metadata sync was called for both
    assert mock_metadata_sync.fetch_and_update_model.call_count == 2

    assert result["success"] is True
    assert result["processed"] == 2


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_progress_callback_receives_updates(mock_hydrate, use_case, mock_service):
    """Test that progress callback receives correct updates."""
    mock_hydrate.return_value = None
    
    model = {
        "file_path": "/models/model.safetensors",
        "sha256": "hash123",
        "model_name": "Test Model",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    cache = SimpleNamespace(raw_data=[model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    reporter = MockProgressReporter()

    # Execute
    await use_case.execute(progress_callback=reporter)

    # Verify progress was reported
    assert len(reporter.progress_calls) >= 2

    # Check started status
    started_calls = [c for c in reporter.progress_calls if c["status"] == "started"]
    assert len(started_calls) == 1

    # Check completed status
    completed_calls = [c for c in reporter.progress_calls if c["status"] == "completed"]
    assert len(completed_calls) == 1
    assert completed_calls[0]["processed"] == 1
    assert completed_calls[0]["success"] == 1


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_respects_skip_metadata_refresh_flag(mock_hydrate, use_case, mock_service, mock_metadata_sync):
    """Test that models with skip_metadata_refresh=True are skipped."""
    mock_hydrate.return_value = None
    
    skip_model = {
        "file_path": "/models/skip_model.safetensors",
        "sha256": "hash123",
        "model_name": "Skip Model",
        "skip_metadata_refresh": True,
        "civitai": {},
    }

    normal_model = {
        "file_path": "/models/normal_model.safetensors",
        "sha256": "hash456",
        "model_name": "Normal Model",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    cache = SimpleNamespace(raw_data=[skip_model, normal_model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    # Execute
    result = await use_case.execute()

    # Verify only normal model was processed
    assert mock_metadata_sync.fetch_and_update_model.call_count == 1
    call_args = mock_metadata_sync.fetch_and_update_model.call_args[1]
    assert call_args["file_path"] == "/models/normal_model.safetensors"

    assert result["processed"] == 1


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_respects_skip_paths(mock_hydrate, use_case, mock_service, mock_metadata_sync):
    """Test that models in skip paths are excluded."""
    mock_hydrate.return_value = None
    
    # Setup settings to skip certain paths
    use_case._settings.get = MagicMock(side_effect=lambda key, default=None: {
        "enable_metadata_archive_db": False,
        "metadata_refresh_skip_paths": ["skip_folder"],
    }.get(key, default))

    skip_path_model = {
        "file_path": "/models/skip_folder/model.safetensors",
        "sha256": "hash123",
        "model_name": "Skip Path Model",
        "folder": "skip_folder",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    normal_model = {
        "file_path": "/models/normal/model.safetensors",
        "sha256": "hash456",
        "model_name": "Normal Model",
        "folder": "normal",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    cache = SimpleNamespace(raw_data=[skip_path_model, normal_model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    # Execute
    result = await use_case.execute()

    # Verify only normal model was processed
    assert mock_metadata_sync.fetch_and_update_model.call_count == 1
    call_args = mock_metadata_sync.fetch_and_update_model.call_args[1]
    assert "normal" in call_args["file_path"]

    assert result["processed"] == 1


@pytest.mark.asyncio
async def test_model_without_hash_skipped(use_case, mock_service, mock_metadata_sync):
    """Test that models without hash (and not pending) are skipped."""
    no_hash_model = {
        "file_path": "/models/no_hash_model.safetensors",
        "sha256": "",  # Empty but NOT pending
        "hash_status": "completed",  # Not pending
        "model_name": "No Hash Model",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": False,
    }

    cache = SimpleNamespace(raw_data=[no_hash_model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    # Execute
    result = await use_case.execute()

    # Verify metadata sync was NOT called
    mock_metadata_sync.fetch_and_update_model.assert_not_called()

    assert result["processed"] == 1
    assert result["updated"] == 0
