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

    async def delete_custom_image(self, request: web.Request) -> web.Response:
        self.delete_calls.append(request)
        return web.json_response({"deleted": True})


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
