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
async def test_missing_metadata_sidecar_is_refetched_from_cached_hash(
    mock_hydrate,
    use_case,
    mock_service,
    mock_metadata_sync,
    tmp_path,
):
    """A deleted sidecar must override stale cached CivitAI metadata."""
    mock_hydrate.return_value = None

    missing_sidecar_model = tmp_path / "missing.safetensors"
    missing_sidecar_model.write_bytes(b"model")

    intact_model = tmp_path / "intact.safetensors"
    intact_model.write_bytes(b"model")
    intact_model.with_suffix(".metadata.json").write_text("{}", encoding="utf-8")

    models = [
        {
            "file_path": str(missing_sidecar_model),
            "sha256": "cached_hash_missing",
            "hash_status": "completed",
            "model_name": "Missing Sidecar",
            "civitai": {"id": 101},
            "from_civitai": True,
        },
        {
            "file_path": str(intact_model),
            "sha256": "cached_hash_intact",
            "hash_status": "completed",
            "model_name": "Intact Sidecar",
            "civitai": {"id": 202},
            "from_civitai": True,
        },
    ]
    cache = SimpleNamespace(raw_data=models, resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    result = await use_case.execute()

    mock_metadata_sync.fetch_and_update_model.assert_called_once()
    call_args = mock_metadata_sync.fetch_and_update_model.call_args.kwargs
    assert call_args["file_path"] == str(missing_sidecar_model)
    assert call_args["sha256"] == "cached_hash_missing"
    assert not mock_service.scanner.calculate_hash_for_model.called
    assert result["processed"] == 1
    assert result["updated"] == 1


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_huggingface_model_with_missing_sidecar_can_query_civitai(
    mock_hydrate,
    use_case,
    mock_service,
    mock_metadata_sync,
    tmp_path,
):
    """HF provenance must not block repair after its sidecar is deleted."""
    mock_hydrate.return_value = None

    missing_sidecar_model = tmp_path / "hf_missing.safetensors"
    missing_sidecar_model.write_bytes(b"model")

    intact_model = tmp_path / "hf_intact.safetensors"
    intact_model.write_bytes(b"model")
    intact_model.with_suffix(".metadata.json").write_text("{}", encoding="utf-8")

    models = [
        {
            "file_path": str(missing_sidecar_model),
            "sha256": "cached_hf_hash_missing",
            "hash_status": "completed",
            "model_name": "HF Missing Sidecar",
            "hf_url": "https://huggingface.co/example/missing",
            "civitai": {},
        },
        {
            "file_path": str(intact_model),
            "sha256": "cached_hf_hash_intact",
            "hash_status": "completed",
            "model_name": "HF Intact Sidecar",
            "hf_url": "https://huggingface.co/example/intact",
            "civitai": {},
        },
    ]
    cache = SimpleNamespace(raw_data=models, resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    result = await use_case.execute()

    mock_metadata_sync.fetch_and_update_model.assert_called_once()
    call_args = mock_metadata_sync.fetch_and_update_model.call_args.kwargs
    assert call_args["file_path"] == str(missing_sidecar_model)
    assert call_args["sha256"] == "cached_hf_hash_missing"
    assert not mock_service.scanner.calculate_hash_for_model.called
    assert result["processed"] == 1
    assert result["updated"] == 1


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_missing_sidecar_hydration_preserves_cached_model_identity(
    mock_hydrate,
    use_case,
    mock_service,
    mock_metadata_sync,
    tmp_path,
):
    """Hydrating a missing sidecar must not erase the cached hash or path."""
    model_file = tmp_path / "anima.safetensors"
    model_file.write_bytes(b"model")
    model = {
        "file_path": str(model_file),
        "file_name": "anima",
        "model_name": "Anima",
        "size": 5,
        "sha256": "cached_anima_hash",
        "hash_status": "completed",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": True,
        "db_checked": True,
    }

    async def clear_like_missing_sidecar(model_data):
        file_path = model_data["file_path"]
        model_data.clear()
        model_data["file_path"] = file_path
        return model_data

    mock_hydrate.side_effect = clear_like_missing_sidecar
    cache = SimpleNamespace(raw_data=[model], resort=AsyncMock())
    mock_service.scanner.get_cached_data.return_value = cache

    result = await use_case.execute()

    mock_metadata_sync.fetch_and_update_model.assert_called_once()
    call_args = mock_metadata_sync.fetch_and_update_model.call_args.kwargs
    assert call_args["sha256"] == "cached_anima_hash"
    assert call_args["file_path"] == str(model_file)
    assert model["sha256"] == "cached_anima_hash"
    assert model["file_name"] == "anima"
    assert not mock_service.scanner.calculate_hash_for_model.called
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
async def test_model_without_hash_is_recalculated(use_case, mock_service, mock_metadata_sync):
    """A missing hash is recovered even when stale status says completed."""
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

    mock_service.scanner.calculate_hash_for_model.assert_called_once_with(
        "/models/no_hash_model.safetensors"
    )
    mock_metadata_sync.fetch_and_update_model.assert_called_once()
    call_args = mock_metadata_sync.fetch_and_update_model.call_args.kwargs
    assert call_args["sha256"] == "calculated_hash_123"

    assert result["processed"] == 1
    assert result["updated"] == 1


@pytest.mark.asyncio
@patch.object(metadata_manager.MetadataManager, "hydrate_model_data")
async def test_retry_not_found_mode_processes_only_negative_cache(
    mock_hydrate,
    use_case,
    mock_service,
    mock_metadata_sync,
):
    """The explicit retry mode must not mix in normal fetch candidates."""
    mock_hydrate.return_value = None
    confirmed_not_found = {
        "file_path": "/models/not_found.safetensors",
        "sha256": "not_found_hash",
        "model_name": "Not Found",
        "civitai": {},
        "from_civitai": False,
        "civitai_deleted": True,
        "db_checked": True,
    }
    normal_candidate = {
        "file_path": "/models/new.safetensors",
        "sha256": "new_hash",
        "model_name": "New",
        "civitai": {},
        "from_civitai": None,
        "civitai_deleted": False,
    }
    complete_model = {
        "file_path": "/models/complete.safetensors",
        "sha256": "complete_hash",
        "model_name": "Complete",
        "civitai": {"id": 123},
        "from_civitai": True,
    }
    cache = SimpleNamespace(
        raw_data=[confirmed_not_found, normal_candidate, complete_model],
        resort=AsyncMock(),
    )
    mock_service.scanner.get_cached_data.return_value = cache
    reporter = MockProgressReporter()

    result = await use_case.execute(
        progress_callback=reporter,
        retry_not_found_only=True,
    )

    mock_metadata_sync.fetch_and_update_model.assert_called_once()
    call_args = mock_metadata_sync.fetch_and_update_model.call_args.kwargs
    assert call_args["file_path"] == "/models/not_found.safetensors"
    assert call_args["force_civitai_retry"] is True
    assert result["processed"] == 1
    assert result["updated"] == 1
    assert reporter.progress_calls[0]["candidate_total"] == 1
    assert reporter.progress_calls[0]["retry_not_found_only"] is True
