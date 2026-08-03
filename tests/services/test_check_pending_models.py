"""Tests for the check_pending_models lightweight pre-check functionality."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils import example_images_download_manager as download_module


class StubScanner:
    """Scanner double returning predetermined cache contents."""

    def __init__(self, models: list[dict]) -> None:
        self._cache = SimpleNamespace(raw_data=models)

    async def get_cached_data(self):
        return self._cache


def _patch_scanners(
    monkeypatch: pytest.MonkeyPatch,
    lora_scanner: StubScanner | None = None,
    checkpoint_scanner: StubScanner | None = None,
    embedding_scanner: StubScanner | None = None,
) -> None:
    """Patch ServiceRegistry to return stub scanners."""

    async def _get_lora_scanner(cls):
        return lora_scanner or StubScanner([])

    async def _get_checkpoint_scanner(cls):
        return checkpoint_scanner or StubScanner([])

    async def _get_embedding_scanner(cls):
        return embedding_scanner or StubScanner([])

    monkeypatch.setattr(
        download_module.ServiceRegistry,
        "get_lora_scanner",
        classmethod(_get_lora_scanner),
    )
    monkeypatch.setattr(
        download_module.ServiceRegistry,
        "get_checkpoint_scanner",
        classmethod(_get_checkpoint_scanner),
    )
    monkeypatch.setattr(
        download_module.ServiceRegistry,
        "get_embedding_scanner",
        classmethod(_get_embedding_scanner),
    )


class RecordingWebSocketManager:
    """Collects broadcast payloads for assertions."""

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def broadcast(self, payload: dict) -> None:
        self.payloads.append(payload)


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_returns_zero_when_all_processed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Test that check_pending_models returns 0 pending when all models are processed."""
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    # Create processed models
    processed_hashes = ["a" * 64, "b" * 64, "c" * 64]
    models = [
        {"sha256": h, "model_name": f"Model {i}"}
        for i, h in enumerate(processed_hashes)
    ]

    # Create progress file with all models processed
    progress_file = tmp_path / ".download_progress.json"
    progress_file.write_text(
        json.dumps({"processed_models": processed_hashes, "failed_models": []}),
        encoding="utf-8",
    )

    # Create model directories with files (simulating completed downloads)
    for h in processed_hashes:
        model_dir = tmp_path / h
        model_dir.mkdir()
        (model_dir / "image_0.png").write_text("data")

    _patch_scanners(monkeypatch, lora_scanner=StubScanner(models))

    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["is_downloading"] is False
    assert result["total_models"] == 3
    assert result["pending_count"] == 0
    assert result["processed_count"] == 3
    assert result["needs_download"] is False


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_finds_unprocessed_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Test that check_pending_models correctly identifies unprocessed models."""
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    # Create models - some processed, some not
    processed_hash = "a" * 64
    unprocessed_hash = "b" * 64
    models = [
        {"sha256": processed_hash, "model_name": "Processed Model"},
        {"sha256": unprocessed_hash, "model_name": "Unprocessed Model"},
    ]

    # Create progress file with only one model processed
    progress_file = tmp_path / ".download_progress.json"
    progress_file.write_text(
        json.dumps({"processed_models": [processed_hash], "failed_models": []}),
        encoding="utf-8",
    )

    # Create directory only for processed model
    processed_dir = tmp_path / processed_hash
    processed_dir.mkdir()
    (processed_dir / "image_0.png").write_text("data")

    _patch_scanners(monkeypatch, lora_scanner=StubScanner(models))

    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["total_models"] == 2
    assert result["pending_count"] == 1
    assert result["processed_count"] == 1
    assert result["needs_download"] is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_skips_models_without_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Test that models without sha256 are not counted as pending."""
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    # Models - one with hash, one without
    models = [
        {"sha256": "a" * 64, "model_name": "Hashed Model"},
        {"sha256": None, "model_name": "No Hash Model"},
        {"model_name": "Missing Hash Model"},  # No sha256 key at all
    ]

    _patch_scanners(monkeypatch, lora_scanner=StubScanner(models))

    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["total_models"] == 3
    assert result["pending_count"] == 1  # Only the one with hash
    assert result["needs_download"] is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_handles_multiple_model_types(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Test that check_pending_models aggregates counts across multiple model types."""
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    lora_models = [
        {"sha256": "a" * 64, "model_name": "Lora 1"},
        {"sha256": "b" * 64, "model_name": "Lora 2"},
    ]
    checkpoint_models = [
        {"sha256": "c" * 64, "model_name": "Checkpoint 1"},
    ]
    embedding_models = [
        {"sha256": "d" * 64, "model_name": "Embedding 1"},
        {"sha256": "e" * 64, "model_name": "Embedding 2"},
        {"sha256": "f" * 64, "model_name": "Embedding 3"},
    ]

    _patch_scanners(
        monkeypatch,
        lora_scanner=StubScanner(lora_models),
        checkpoint_scanner=StubScanner(checkpoint_models),
        embedding_scanner=StubScanner(embedding_models),
    )

    result = await manager.check_pending_models(["lora", "checkpoint", "embedding"])

    assert result["success"] is True
    assert result["total_models"] == 6  # 2 + 1 + 3
    assert result["pending_count"] == 6  # All unprocessed
    assert result["needs_download"] is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_returns_error_when_download_in_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Test that check_pending_models returns special response when download is running."""
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    # Simulate download in progress
    manager._is_downloading = True

    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["is_downloading"] is True
    assert result["needs_download"] is False
    assert result["pending_count"] == 0
    assert "already in progress" in result["message"].lower()


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_handles_empty_library(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Test that check_pending_models handles empty model library."""
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    _patch_scanners(monkeypatch, lora_scanner=StubScanner([]))

    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["total_models"] == 0
    assert result["pending_count"] == 0
    assert result["processed_count"] == 0
    assert result["needs_download"] is False


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_reads_failed_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Test that check_pending_models correctly reports failed model count."""
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    models = [{"sha256": "a" * 64, "model_name": "Model"}]

    # Create progress file with failed models
    progress_file = tmp_path / ".download_progress.json"
    progress_file.write_text(
        json.dumps({"processed_models": [], "failed_models": ["a" * 64, "b" * 64]}),
        encoding="utf-8",
    )

    _patch_scanners(monkeypatch, lora_scanner=StubScanner(models))

    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["failed_count"] == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_handles_missing_progress_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Test that check_pending_models works correctly when no progress file exists."""
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    models = [
        {"sha256": "a" * 64, "model_name": "Model 1"},
        {"sha256": "b" * 64, "model_name": "Model 2"},
    ]

    _patch_scanners(monkeypatch, lora_scanner=StubScanner(models))

    # No progress file created
    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["total_models"] == 2
    assert result["pending_count"] == 2  # All pending since no progress
    assert result["processed_count"] == 0
    assert result["failed_count"] == 0
    assert result["needs_download"] is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_handles_corrupted_progress_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """Test that check_pending_models handles corrupted progress file gracefully."""
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    models = [{"sha256": "a" * 64, "model_name": "Model"}]

    # Create corrupted progress file
    progress_file = tmp_path / ".download_progress.json"
    progress_file.write_text("not valid json", encoding="utf-8")

    _patch_scanners(monkeypatch, lora_scanner=StubScanner(models))

    result = await manager.check_pending_models(["lora"])

    # Should still succeed, treating all as unprocessed
    assert result["success"] is True
    assert result["total_models"] == 1
    assert result["pending_count"] == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_uses_bulk_folder_index_for_large_libraries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """For >1000 candidates the pre-check scans the library root once instead of
    probing every folder individually."""

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    # 1500 unprocessed models triggers the bulk lookup path
    models = [
        {"sha256": f"{i:064x}", "model_name": f"Model {i}"}
        for i in range(1500)
    ]

    # Create folders with files for the first 500 models
    for i in range(500):
        model_dir = tmp_path / f"{i:064x}"
        model_dir.mkdir()
        (model_dir / "image_0.png").write_text("data")

    _patch_scanners(monkeypatch, lora_scanner=StubScanner(models))

    per_model_checks = 0

    def counting_model_directory_has_files(path: str) -> bool:
        nonlocal per_model_checks
        per_model_checks += 1
        return False

    monkeypatch.setattr(
        download_module,
        "_model_directory_has_files",
        counting_model_directory_has_files,
    )

    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["total_models"] == 1500
    assert result["pending_count"] == 1000
    assert result["needs_download"] is True
    # The per-folder check should not be used once we cross the threshold.
    assert per_model_checks == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_uses_per_folder_check_for_small_candidate_sets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """For <=1000 candidates the pre-check keeps the accurate per-folder path."""

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    models = [
        {"sha256": f"{i:064x}", "model_name": f"Model {i}"}
        for i in range(500)
    ]

    # Create folders with files for the first 200 models
    for i in range(200):
        model_dir = tmp_path / f"{i:064x}"
        model_dir.mkdir()
        (model_dir / "image_0.png").write_text("data")

    _patch_scanners(monkeypatch, lora_scanner=StubScanner(models))

    per_model_checks = 0
    original_has_files = download_module._model_directory_has_files

    def counting_model_directory_has_files(path: str) -> bool:
        nonlocal per_model_checks
        per_model_checks += 1
        return original_has_files(path)

    monkeypatch.setattr(
        download_module,
        "_model_directory_has_files",
        counting_model_directory_has_files,
    )

    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["total_models"] == 500
    assert result["pending_count"] == 300
    assert result["needs_download"] is True
    # Per-folder path should run once per candidate.
    assert per_model_checks == 500


@pytest.mark.asyncio
@pytest.mark.usefixtures("tmp_path")
async def test_check_pending_models_bulk_index_includes_legacy_folders(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    """In multi-library mode the bulk index also scans the legacy root so models
    whose folders have not been consolidated yet are not reported pending."""

    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"default": {}, "extra": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "extra")

    # 1500 unprocessed models triggers the bulk lookup path
    models = [
        {"sha256": f"{i:064x}", "model_name": f"Model {i}"}
        for i in range(1500)
    ]

    # Folders live at the LEGACY root/<hash> path (not yet consolidated)
    for i in range(500):
        model_dir = tmp_path / f"{i:064x}"
        model_dir.mkdir()
        (model_dir / "image_0.png").write_text("data")

    _patch_scanners(monkeypatch, lora_scanner=StubScanner(models))

    result = await manager.check_pending_models(["lora"])

    assert result["success"] is True
    assert result["total_models"] == 1500
    assert result["pending_count"] == 1000
    assert result["needs_download"] is True


@pytest.fixture
def settings_manager():
    return get_settings_manager()
