from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from py.routes.example_images_route_registrar import ExampleImagesRouteRegistrar
from py.routes.handlers.example_images_handlers import (
    ExampleImagesDownloadHandler,
    ExampleImagesFileHandler,
    ExampleImagesHandlerSet,
    ExampleImagesManagementHandler,
)
from py.services.use_cases.example_images import (
    DownloadExampleImagesInProgressError,
    ImportExampleImagesValidationError,
)
from py.utils.example_images_download_manager import (
    DownloadInProgressError,
    DownloadNotRunningError,
)


class StubDownloadUseCase:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.error: Exception | None = None

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return {"success": True, "payload": payload}


class StubDownloadManager:
    def __init__(self) -> None:
        self.pause_calls = 0
        self.resume_calls = 0
        self.stop_calls = 0
        self.force_payloads: list[dict[str, Any]] = []
        self.pause_error: Exception | None = None
        self.resume_error: Exception | None = None
        self.stop_error: Exception | None = None
        self.force_error: Exception | None = None
        self.check_pending_result: dict[str, Any] | None = None
        self.check_pending_calls: list[list[str]] = []

    async def get_status(self, request: web.Request) -> dict[str, Any]:
        return {"success": True, "status": "idle"}

    async def pause_download(self, request: web.Request) -> dict[str, Any]:
        self.pause_calls += 1
        if self.pause_error:
            raise self.pause_error
        return {"success": True, "message": "paused"}

    async def resume_download(self, request: web.Request) -> dict[str, Any]:
        self.resume_calls += 1
        if self.resume_error:
            raise self.resume_error
        return {"success": True, "message": "resumed"}

    async def stop_download(self, request: web.Request) -> dict[str, Any]:
        self.stop_calls += 1
        if self.stop_error:
            raise self.stop_error
        return {"success": True, "message": "stopping"}

    async def start_force_download(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.force_payloads.append(payload)
        if self.force_error:
            raise self.force_error
        return {"success": True, "payload": payload}

    async def check_pending_models(self, model_types: list[str]) -> dict[str, Any]:
        self.check_pending_calls.append(model_types)
        if self.check_pending_result is not None:
            return self.check_pending_result
        return {
            "success": True,
            "is_downloading": False,
            "total_models": 100,
            "pending_count": 10,
            "processed_count": 90,
            "failed_count": 0,
            "needs_download": True,
        }


class StubImportUseCase:
    def __init__(self) -> None:
        self.requests: list[web.Request] = []
        self.error: Exception | None = None

    async def execute(self, request: web.Request) -> dict[str, Any]:
        self.requests.append(request)
        if self.error:
            raise self.error
        return {"success": True}


class StubProcessor:
    def __init__(self) -> None:
        self.delete_calls: list[web.Request] = []
        self.nsfw_calls: list[web.Request] = []

    async def delete_custom_image(self, request: web.Request) -> web.Response:
        self.delete_calls.append(request)
        return web.json_response({"deleted": True})

    async def set_example_image_nsfw_level(self, request: web.Request) -> web.Response:
        self.nsfw_calls.append(request)
        return web.json_response({"updated": True})


class StubCleanupService:
    def __init__(self) -> None:
        self.calls = 0

    async def cleanup_example_image_folders(self) -> dict[str, Any]:
        self.calls += 1
        return {"success": True}


class StubFileManager:
    async def open_folder(self, request: web.Request) -> web.Response:
        return web.json_response({"opened": True})

    async def get_files(self, request: web.Request) -> web.Response:
        return web.json_response({"files": []})

    async def has_images(self, request: web.Request) -> web.Response:
        return web.json_response({"has": False})


@dataclass
class RegistrarHarness:
    client: TestClient
    download_use_case: StubDownloadUseCase
    download_manager: StubDownloadManager
    import_use_case: StubImportUseCase


@asynccontextmanager
async def registrar_app() -> RegistrarHarness:
    app = web.Application()

    download_use_case = StubDownloadUseCase()
    download_manager = StubDownloadManager()
    import_use_case = StubImportUseCase()
    processor = StubProcessor()
    cleanup_service = StubCleanupService()
    file_manager = StubFileManager()

    handler_set = ExampleImagesHandlerSet(
        download=ExampleImagesDownloadHandler(download_use_case, download_manager),
        management=ExampleImagesManagementHandler(import_use_case, processor, cleanup_service),
        files=ExampleImagesFileHandler(file_manager),
    )

    registrar = ExampleImagesRouteRegistrar(app)
    registrar.register_routes(handler_set.to_route_mapping())

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        yield RegistrarHarness(
            client=client,
            download_use_case=download_use_case,
            download_manager=download_manager,
            import_use_case=import_use_case,
        )
    finally:
        await client.close()


async def _json(response: web.StreamResponse) -> Dict[str, Any]:
    text = await response.text()
    return json.loads(text) if text else {}


async def test_download_route_surfaces_in_progress_error():
    async with registrar_app() as harness:
        progress = {"status": "running"}
        harness.download_use_case.error = DownloadExampleImagesInProgressError(progress)

        response = await harness.client.post(
            "/api/lm/download-example-images",
            json={"model_types": ["lora"]},
        )

        assert response.status == 400
        body = await _json(response)
        assert body["status"] == progress
        assert body["error"] == "Download already in progress"


async def test_force_download_translates_manager_errors():
    async with registrar_app() as harness:
        snapshot = {"status": "running"}
        harness.download_manager.force_error = DownloadInProgressError(snapshot)

        response = await harness.client.post(
            "/api/lm/force-download-example-images",
            json={"model_hashes": ["abc"]},
        )

        assert response.status == 400
        body = await _json(response)
        assert body["status"] == snapshot
        assert body["error"] == "Download already in progress"


async def test_pause_and_resume_return_client_errors_when_not_running():
    async with registrar_app() as harness:
        harness.download_manager.pause_error = DownloadNotRunningError()
        harness.download_manager.resume_error = DownloadNotRunningError("Stopped")
        harness.download_manager.stop_error = DownloadNotRunningError("Not running")

        pause_response = await harness.client.post("/api/lm/pause-example-images")
        resume_response = await harness.client.post("/api/lm/resume-example-images")
        stop_response = await harness.client.post("/api/lm/stop-example-images")

        assert pause_response.status == 400
        assert resume_response.status == 400
        assert stop_response.status == 400

        pause_body = await _json(pause_response)
        resume_body = await _json(resume_response)
        stop_body = await _json(stop_response)
        assert pause_body == {"success": False, "error": "No download in progress"}
        assert resume_body == {"success": False, "error": "Stopped"}
        assert stop_body == {"success": False, "error": "Not running"}


async def test_import_route_returns_validation_errors():
    async with registrar_app() as harness:
        harness.import_use_case.error = ImportExampleImagesValidationError("bad payload")

        response = await harness.client.post(
            "/api/lm/import-example-images",
            json={"model_hash": "missing"},
        )

        assert response.status == 400
        body = await _json(response)
        assert body == {"success": False, "error": "bad payload"}


async def test_check_example_images_needed_returns_pending_counts():
    """Test that check_example_images_needed endpoint returns pending model counts."""
    async with registrar_app() as harness:
        harness.download_manager.check_pending_result = {
            "success": True,
            "is_downloading": False,
            "total_models": 5500,
            "pending_count": 12,
            "processed_count": 5488,
            "failed_count": 45,
            "needs_download": True,
        }

        response = await harness.client.post(
            "/api/lm/check-example-images-needed",
            json={"model_types": ["lora", "checkpoint"]},
        )

        assert response.status == 200
        body = await _json(response)
        assert body["success"] is True
        assert body["total_models"] == 5500
        assert body["pending_count"] == 12
        assert body["processed_count"] == 5488
        assert body["failed_count"] == 45
        assert body["needs_download"] is True
        assert body["is_downloading"] is False

        # Verify the manager was called with correct model types
        assert harness.download_manager.check_pending_calls == [["lora", "checkpoint"]]


async def test_check_example_images_needed_handles_download_in_progress():
    """Test that check_example_images_needed returns correct status when download is running."""
    async with registrar_app() as harness:
        harness.download_manager.check_pending_result = {
            "success": True,
            "is_downloading": True,
            "total_models": 0,
            "pending_count": 0,
            "processed_count": 0,
            "failed_count": 0,
            "needs_download": False,
            "message": "Download already in progress",
        }

        response = await harness.client.post(
            "/api/lm/check-example-images-needed",
            json={"model_types": ["lora"]},
        )

        assert response.status == 200
        body = await _json(response)
        assert body["success"] is True
        assert body["is_downloading"] is True
        assert body["needs_download"] is False


async def test_check_example_images_needed_handles_no_pending_models():
    """Test that check_example_images_needed returns correct status when no work is needed."""
    async with registrar_app() as harness:
        harness.download_manager.check_pending_result = {
            "success": True,
            "is_downloading": False,
            "total_models": 5500,
            "pending_count": 0,
            "processed_count": 5500,
            "failed_count": 0,
            "needs_download": False,
        }

        response = await harness.client.post(
            "/api/lm/check-example-images-needed",
            json={"model_types": ["lora", "checkpoint", "embedding"]},
        )

        assert response.status == 200
        body = await _json(response)
        assert body["success"] is True
        assert body["pending_count"] == 0
        assert body["needs_download"] is False
        assert body["processed_count"] == 5500


async def test_check_example_images_needed_uses_default_model_types():
    """Test that check_example_images_needed uses default model types when not specified."""
    async with registrar_app() as harness:
        response = await harness.client.post(
            "/api/lm/check-example-images-needed",
            json={},  # No model_types specified
        )

        assert response.status == 200
        # Should use default model types
        assert harness.download_manager.check_pending_calls == [["lora", "checkpoint", "embedding"]]


async def test_check_example_images_needed_returns_error_on_exception():
    """Test that check_example_images_needed returns 500 on internal error."""
    async with registrar_app() as harness:
        # Simulate an error by setting result to an error state
        # Actually, we need to make the method raise an exception
        original_method = harness.download_manager.check_pending_models

        async def failing_check(_model_types):
            raise RuntimeError("Database connection failed")

        harness.download_manager.check_pending_models = failing_check

        response = await harness.client.post(
            "/api/lm/check-example-images-needed",
            json={"model_types": ["lora"]},
        )

        assert response.status == 500
        body = await _json(response)
        assert body["success"] is False
        assert "Database connection failed" in body["error"]
