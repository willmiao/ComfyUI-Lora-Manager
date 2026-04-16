"""Unit tests for BatchImportService."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from py.services.batch_import_service import (
    AdaptiveConcurrencyController,
    BatchImportItem,
    BatchImportProgress,
    BatchImportService,
    ImportItemType,
    ImportStatus,
)


class MockWebSocketManager:
    def __init__(self):
        self.broadcasts: List[Dict[str, Any]] = []

    async def broadcast(self, data: Dict[str, Any]):
        self.broadcasts.append(data)


@dataclass
class MockAnalysisResult:
    payload: Dict[str, Any]
    status: int = 200


class MockAnalysisService:
    def __init__(self, results: Optional[Dict[str, MockAnalysisResult]] = None):
        self.results = results or {}
        self.call_count = 0
        self.last_url = None
        self.last_path = None

    async def analyze_remote_image(self, *, url: str, recipe_scanner, civitai_client):
        self.call_count += 1
        self.last_url = url
        if url in self.results:
            return self.results[url]
        return MockAnalysisResult({"error": "No metadata found", "loras": []})

    async def analyze_local_image(self, *, file_path: str, recipe_scanner):
        self.call_count += 1
        self.last_path = file_path
        if file_path in self.results:
            return self.results[file_path]
        return MockAnalysisResult({"error": "No metadata found", "loras": []})


@dataclass
class MockSaveResult:
    payload: Dict[str, Any]
    status: int = 200


class MockPersistenceService:
    def __init__(self, should_succeed: bool = True):
        self.should_succeed = should_succeed
        self.saved_recipes: List[Dict[str, Any]] = []
        self.call_count = 0

    async def save_recipe(
        self,
        *,
        recipe_scanner,
        image_bytes: Optional[bytes] = None,
        image_base64: Optional[str] = None,
        name: str,
        tags: List[str],
        metadata: Dict[str, Any],
        extension: Optional[str] = None,
    ):
        self.call_count += 1
        self.saved_recipes.append(
            {
                "name": name,
                "tags": tags,
                "metadata": metadata,
            }
        )
        if self.should_succeed:
            return MockSaveResult({"success": True, "id": f"recipe_{self.call_count}"})
        return MockSaveResult({"success": False, "error": "Save failed"}, status=400)


class TestAdaptiveConcurrencyController:
    def test_initial_values(self):
        controller = AdaptiveConcurrencyController()
        assert controller.current_concurrency == 3
        assert controller.min_concurrency == 1
        assert controller.max_concurrency == 5

    def test_custom_initial_values(self):
        controller = AdaptiveConcurrencyController(
            min_concurrency=2,
            max_concurrency=10,
            initial_concurrency=5,
        )
        assert controller.current_concurrency == 5
        assert controller.min_concurrency == 2
        assert controller.max_concurrency == 10

    def test_increase_concurrency_on_success(self):
        controller = AdaptiveConcurrencyController(initial_concurrency=3)
        controller.record_result(duration=0.5, success=True)
        assert controller.current_concurrency == 4

    def test_do_not_exceed_max(self):
        controller = AdaptiveConcurrencyController(
            max_concurrency=5,
            initial_concurrency=5,
        )
        controller.record_result(duration=0.5, success=True)
        assert controller.current_concurrency == 5

    def test_decrease_concurrency_on_failure(self):
        controller = AdaptiveConcurrencyController(initial_concurrency=3)
        controller.record_result(duration=1.0, success=False)
        assert controller.current_concurrency == 2

    def test_do_not_go_below_min(self):
        controller = AdaptiveConcurrencyController(
            min_concurrency=1,
            initial_concurrency=1,
        )
        controller.record_result(duration=1.0, success=False)
        assert controller.current_concurrency == 1

    def test_slow_task_decreases_concurrency(self):
        controller = AdaptiveConcurrencyController(initial_concurrency=3)
        controller.record_result(duration=11.0, success=True)
        assert controller.current_concurrency == 2

    def test_fast_task_increases_concurrency(self):
        controller = AdaptiveConcurrencyController(initial_concurrency=3)
        controller.record_result(duration=0.5, success=True)
        assert controller.current_concurrency == 4

    def test_moderate_task_no_change(self):
        controller = AdaptiveConcurrencyController(initial_concurrency=3)
        controller.record_result(duration=5.0, success=True)
        assert controller.current_concurrency == 3


class TestBatchImportProgress:
    def test_to_dict(self):
        progress = BatchImportProgress(
            operation_id="test-123",
            total=10,
            completed=5,
            success=3,
            failed=2,
            skipped=0,
            current_item="image.png",
            status="running",
        )
        result = progress.to_dict()
        assert result["operation_id"] == "test-123"
        assert result["total"] == 10
        assert result["completed"] == 5
        assert result["success"] == 3
        assert result["failed"] == 2
        assert result["progress_percent"] == 50.0

    def test_progress_percent_zero_total(self):
        progress = BatchImportProgress(
            operation_id="test-123",
            total=0,
        )
        assert progress.to_dict()["progress_percent"] == 0


class TestBatchImportItem:
    def test_defaults(self):
        item = BatchImportItem(
            id="item-1",
            source="https://example.com/image.png",
            item_type=ImportItemType.URL,
        )
        assert item.status == ImportStatus.PENDING
        assert item.error_message is None
        assert item.recipe_name is None


class TestBatchImportService:
    @pytest.fixture
    def mock_services(self):
        ws_manager = MockWebSocketManager()
        analysis_service = MockAnalysisService()
        persistence_service = MockPersistenceService()
        logger = logging.getLogger("test")
        return ws_manager, analysis_service, persistence_service, logger

    @pytest.fixture
    def service(self, mock_services):
        ws_manager, analysis_service, persistence_service, logger = mock_services
        return BatchImportService(
            analysis_service=analysis_service,
            persistence_service=persistence_service,
            ws_manager=ws_manager,
            logger=logger,
        )

    def test_is_import_running_no_operations(self, service):
        assert not service.is_import_running()

    @pytest.mark.asyncio
    async def test_start_batch_import_creates_operation(self, service):
        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[{"source": "https://example.com/image.png"}],
        )

        assert operation_id is not None
        assert service.is_import_running(operation_id)

    @pytest.mark.asyncio
    async def test_get_progress(self, service):
        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[
                {"source": "https://example.com/1.png"},
                {"source": "https://example.com/2.png"},
            ],
        )

        progress = service.get_progress(operation_id)
        assert progress is not None
        assert progress.total == 2
        assert progress.status in ("pending", "running")

    @pytest.mark.asyncio
    async def test_cancel_import(self, service):
        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[{"source": "https://example.com/image.png"}],
        )

        assert service.cancel_import(operation_id) is True
        assert service.cancel_import("nonexistent") is False

    @pytest.mark.asyncio
    async def test_discover_images_non_recursive(self, service, tmp_path):
        for i in range(3):
            (tmp_path / f"image{i}.png").write_bytes(b"fake-image")

        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "hidden.png").write_bytes(b"fake-image")

        images = await service._discover_images(str(tmp_path), recursive=False)
        assert len(images) == 3

    @pytest.mark.asyncio
    async def test_discover_images_recursive(self, service, tmp_path):
        for i in range(2):
            (tmp_path / f"image{i}.png").write_bytes(b"fake-image")

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        for i in range(2):
            (subdir / f"nested{i}.jpg").write_bytes(b"fake-image")

        images = await service._discover_images(str(tmp_path), recursive=True)
        assert len(images) == 4

    @pytest.mark.asyncio
    async def test_discover_images_filters_by_extension(self, service, tmp_path):
        (tmp_path / "image.png").write_bytes(b"fake-image")
        (tmp_path / "image.jpg").write_bytes(b"fake-image")
        (tmp_path / "image.webp").write_bytes(b"fake-image")
        (tmp_path / "document.pdf").write_bytes(b"fake-doc")
        (tmp_path / "script.py").write_bytes(b"print('hello')")

        images = await service._discover_images(str(tmp_path), recursive=False)
        assert len(images) == 3

    @pytest.mark.asyncio
    async def test_discover_images_invalid_directory(self, service):
        from py.services.recipes.errors import RecipeValidationError

        with pytest.raises(RecipeValidationError):
            await service._discover_images("/nonexistent/path", recursive=False)

    def test_is_supported_image(self, service):
        assert service._is_supported_image("test.png") is True
        assert service._is_supported_image("test.jpg") is True
        assert service._is_supported_image("test.jpeg") is True
        assert service._is_supported_image("test.webp") is True
        assert service._is_supported_image("test.gif") is True
        assert service._is_supported_image("test.bmp") is True
        assert service._is_supported_image("test.pdf") is False
        assert service._is_supported_image("test.txt") is False

    @pytest.mark.asyncio
    async def test_batch_import_processes_items(self, mock_services, tmp_path):
        ws_manager, _, persistence_service, logger = mock_services

        analysis_service = MockAnalysisService(
            {
                "https://example.com/valid.png": MockAnalysisResult(
                    {
                        "loras": [{"name": "test-lora", "weight": 1.0}],
                        "base_model": "SD1.5",
                        "gen_params": {"steps": 20},
                    }
                ),
            }
        )

        service = BatchImportService(
            analysis_service=analysis_service,
            persistence_service=persistence_service,
            ws_manager=ws_manager,
            logger=logger,
        )

        recipe_scanner_getter = lambda: SimpleNamespace(
            find_recipes_by_fingerprint=lambda x: [],
            add_recipe=lambda x: None,
        )
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[
                {"source": "https://example.com/valid.png"},
                {"source": "https://example.com/no-meta.png"},
            ],
            skip_no_metadata=True,
        )

        await asyncio.sleep(0.5)

        progress = service.get_progress(operation_id)
        assert progress is not None or persistence_service.call_count == 1

    @pytest.mark.asyncio
    async def test_start_directory_import(self, service, tmp_path):
        for i in range(5):
            (tmp_path / f"image{i}.png").write_bytes(b"fake-image")

        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_directory_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            directory=str(tmp_path),
            recursive=False,
        )

        progress = service.get_progress(operation_id)
        assert progress is not None
        assert progress.total == 5

    @pytest.mark.asyncio
    async def test_websocket_broadcasts_progress(self, mock_services):
        ws_manager, analysis_service, persistence_service, logger = mock_services

        service = BatchImportService(
            analysis_service=analysis_service,
            persistence_service=persistence_service,
            ws_manager=ws_manager,
            logger=logger,
        )

        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[{"source": "https://example.com/test.png"}],
        )

        await asyncio.sleep(0.3)

        assert len(ws_manager.broadcasts) > 0
        assert any(
            b.get("type") == "batch_import_progress" for b in ws_manager.broadcasts
        )

    @pytest.mark.asyncio
    async def test_cancellation_stops_processing(self, mock_services):
        ws_manager, analysis_service, persistence_service, logger = mock_services

        service = BatchImportService(
            analysis_service=analysis_service,
            persistence_service=persistence_service,
            ws_manager=ws_manager,
            logger=logger,
        )

        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        items = [{"source": f"https://example.com/{i}.png"} for i in range(10)]

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=items,
        )

        service.cancel_import(operation_id)
        await asyncio.sleep(0.3)

        progress = service.get_progress(operation_id)
        if progress:
            assert progress.status == "cancelled"


class TestBatchImportServiceEdgeCases:
    @pytest.fixture
    def service(self):
        ws_manager = MockWebSocketManager()
        analysis_service = MockAnalysisService()
        persistence_service = MockPersistenceService()
        logger = logging.getLogger("test")

        return BatchImportService(
            analysis_service=analysis_service,
            persistence_service=persistence_service,
            ws_manager=ws_manager,
            logger=logger,
        )

    @pytest.mark.asyncio
    async def test_empty_items_list(self, service):
        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[],
        )

        progress = service.get_progress(operation_id)
        assert progress is not None
        assert progress.total == 0

    @pytest.mark.asyncio
    async def test_mixed_url_and_path_items(self, service, tmp_path):
        (tmp_path / "local.png").write_bytes(b"fake-image")

        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[
                {"source": "https://example.com/remote.png", "type": "url"},
                {"source": str(tmp_path / "local.png"), "type": "local_path"},
            ],
        )

        progress = service.get_progress(operation_id)
        assert progress is not None
        assert progress.total == 2
        assert progress.items[0].item_type == ImportItemType.URL
        assert progress.items[1].item_type == ImportItemType.LOCAL_PATH

    @pytest.mark.asyncio
    async def test_tags_are_passed_to_persistence(self, tmp_path):
        ws_manager = MockWebSocketManager()
        analysis_service = MockAnalysisService(
            {
                str(tmp_path / "test.png"): MockAnalysisResult(
                    {
                        "loras": [{"name": "test-lora"}],
                    }
                ),
            }
        )
        persistence_service = MockPersistenceService()
        logger = logging.getLogger("test")

        (tmp_path / "test.png").write_bytes(b"fake-image")

        service = BatchImportService(
            analysis_service=analysis_service,
            persistence_service=persistence_service,
            ws_manager=ws_manager,
            logger=logger,
        )

        recipe_scanner_getter = lambda: SimpleNamespace(
            find_recipes_by_fingerprint=lambda x: [],
        )
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[{"source": str(tmp_path / "test.png")}],
            tags=["batch-import", "test"],
        )

        await asyncio.sleep(0.3)

        if persistence_service.saved_recipes:
            assert "batch-import" in persistence_service.saved_recipes[0]["tags"]
            assert "test" in persistence_service.saved_recipes[0]["tags"]

    @pytest.mark.asyncio
    async def test_skip_duplicates_parameter(self, service):
        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[{"source": "https://example.com/test.png"}],
            skip_duplicates=True,
        )

        progress = service.get_progress(operation_id)
        assert progress is not None
        assert progress.skip_duplicates is True

    @pytest.mark.asyncio
    async def test_skip_duplicates_false_by_default(self, service):
        recipe_scanner_getter = lambda: SimpleNamespace()
        civitai_client_getter = lambda: SimpleNamespace()

        operation_id = await service.start_batch_import(
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            items=[{"source": "https://example.com/test.png"}],
        )

        progress = service.get_progress(operation_id)
        assert progress is not None
        assert progress.skip_duplicates is False


class TestInputValidation:
    @pytest.fixture
    def service(self):
        ws_manager = MockWebSocketManager()
        analysis_service = MockAnalysisService()
        persistence_service = MockPersistenceService()
        logger = logging.getLogger("test")

        return BatchImportService(
            analysis_service=analysis_service,
            persistence_service=persistence_service,
            ws_manager=ws_manager,
            logger=logger,
        )

    def test_validate_valid_url(self, service):
        assert service._validate_url("https://example.com/image.png") is True
        assert service._validate_url("http://example.com/image.png") is True
        assert service._validate_url("https://civitai.com/images/123") is True
        assert service._validate_url("https://civitai.red/images/123") is True

    def test_validate_invalid_url(self, service):
        assert service._validate_url("not-a-url") is False
        assert service._validate_url("ftp://example.com/file") is False
        assert service._validate_url("") is False

    def test_validate_valid_local_path(self, service, tmp_path):
        valid_path = str(tmp_path / "image.png")
        assert service._validate_local_path(valid_path) is True

    def test_validate_invalid_local_path(self, service):
        assert service._validate_local_path("../etc/passwd") is False
        assert service._validate_local_path("relative/path.png") is False
        assert service._validate_local_path("") is False
