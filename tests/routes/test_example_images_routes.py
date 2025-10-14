from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from py.routes.example_images_route_registrar import ROUTE_DEFINITIONS
from py.routes.example_images_routes import ExampleImagesRoutes
from py.routes.handlers.example_images_handlers import (
    ExampleImagesDownloadHandler,
    ExampleImagesFileHandler,
    ExampleImagesHandlerSet,
    ExampleImagesManagementHandler,
)


@dataclass
class ExampleImagesHarness:
    """Container exposing the aiohttp client and stubbed collaborators."""

    client: TestClient
    download_manager: "StubDownloadManager"
    processor: "StubExampleImagesProcessor"
    file_manager: "StubExampleImagesFileManager"
    cleanup_service: "StubExampleImagesCleanupService"
    controller: ExampleImagesRoutes


class StubDownloadManager:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Any]] = []

    async def start_download(self, payload: Any) -> dict:
        self.calls.append(("start_download", payload))
        return {"operation": "start_download", "payload": payload}

    async def get_status(self, request: web.Request) -> dict:
        self.calls.append(("get_status", dict(request.query)))
        return {"operation": "get_status"}

    async def pause_download(self, request: web.Request) -> dict:
        self.calls.append(("pause_download", None))
        return {"operation": "pause_download"}

    async def resume_download(self, request: web.Request) -> dict:
        self.calls.append(("resume_download", None))
        return {"operation": "resume_download"}

    async def stop_download(self, request: web.Request) -> dict:
        self.calls.append(("stop_download", None))
        return {"operation": "stop_download"}

    async def start_force_download(self, payload: Any) -> dict:
        self.calls.append(("start_force_download", payload))
        return {"operation": "start_force_download", "payload": payload}


class StubExampleImagesProcessor:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Any]] = []

    async def import_images(self, model_hash: str, files: List[str]) -> dict:
        payload = {"model_hash": model_hash, "file_paths": files}
        self.calls.append(("import_images", payload))
        return {"operation": "import_images", "payload": payload}

    async def delete_custom_image(self, request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        self.calls.append(("delete_custom_image", payload))
        return web.json_response({"operation": "delete_custom_image", "payload": payload})


class StubExampleImagesFileManager:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Any]] = []

    async def open_folder(self, request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        self.calls.append(("open_folder", payload))
        return web.json_response({"operation": "open_folder", "payload": payload})

    async def get_files(self, request: web.Request) -> web.StreamResponse:
        self.calls.append(("get_files", dict(request.query)))
        return web.json_response({"operation": "get_files", "query": dict(request.query)})

    async def has_images(self, request: web.Request) -> web.StreamResponse:
        self.calls.append(("has_images", dict(request.query)))
        return web.json_response({"operation": "has_images", "query": dict(request.query)})


class StubExampleImagesCleanupService:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.result: Dict[str, Any] = {
            "success": True,
            "moved_total": 0,
            "moved_empty_folders": 0,
            "moved_orphaned_folders": 0,
        }

    async def cleanup_example_image_folders(self) -> Dict[str, Any]:
        self.calls.append({})
        return self.result


class StubWebSocketManager:
    def __init__(self) -> None:
        self.broadcast_calls: List[Dict[str, Any]] = []

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        self.broadcast_calls.append(payload)


@asynccontextmanager
async def example_images_app() -> ExampleImagesHarness:
    """Yield an ExampleImagesRoutes app wired with stubbed collaborators."""

    download_manager = StubDownloadManager()
    processor = StubExampleImagesProcessor()
    file_manager = StubExampleImagesFileManager()
    cleanup_service = StubExampleImagesCleanupService()
    ws_manager = StubWebSocketManager()

    controller = ExampleImagesRoutes(
        ws_manager=ws_manager,
        download_manager=download_manager,
        processor=processor,
        file_manager=file_manager,
        cleanup_service=cleanup_service,
    )

    app = web.Application()
    controller.register(app)

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        yield ExampleImagesHarness(
            client=client,
            download_manager=download_manager,
            processor=processor,
            file_manager=file_manager,
            cleanup_service=cleanup_service,
            controller=controller,
        )
    finally:
        await client.close()


async def test_setup_routes_registers_all_definitions():
    async with example_images_app() as harness:
        registered = {
            (route.method, route.resource.canonical)
            for route in harness.client.app.router.routes()
            if route.resource.canonical
        }

        expected = {(definition.method, definition.path) for definition in ROUTE_DEFINITIONS}

        assert expected <= registered


@pytest.mark.parametrize(
    "endpoint, payload",
    [
        ("/api/lm/download-example-images", {"model_types": ["lora"], "optimize": False}),
        ("/api/lm/force-download-example-images", {"model_hashes": ["abc123"]}),
    ],
)
async def test_download_routes_delegate_to_manager(endpoint, payload):
    async with example_images_app() as harness:
        response = await harness.client.post(endpoint, json=payload)
        body = await response.json()

        assert response.status == 200
        assert body["payload"] == payload
        assert body["operation"].startswith("start")

        expected_call = body["operation"], payload
        assert expected_call in harness.download_manager.calls


async def test_status_route_returns_manager_payload():
    async with example_images_app() as harness:
        response = await harness.client.get(
            "/api/lm/example-images-status", params={"detail": "true"}
        )
        body = await response.json()

        assert response.status == 200
        assert body == {"operation": "get_status"}
        assert harness.download_manager.calls == [("get_status", {"detail": "true"})]


async def test_pause_resume_and_stop_routes_delegate():
    async with example_images_app() as harness:
        pause_response = await harness.client.post("/api/lm/pause-example-images")
        resume_response = await harness.client.post("/api/lm/resume-example-images")
        stop_response = await harness.client.post("/api/lm/stop-example-images")

        assert pause_response.status == 200
        assert await pause_response.json() == {"operation": "pause_download"}
        assert resume_response.status == 200
        assert await resume_response.json() == {"operation": "resume_download"}
        assert stop_response.status == 200
        assert await stop_response.json() == {"operation": "stop_download"}

        assert harness.download_manager.calls[-3:] == [
            ("pause_download", None),
            ("resume_download", None),
            ("stop_download", None),
        ]


async def test_import_route_delegates_to_processor():
    payload = {"model_hash": "abc123", "file_paths": ["/path/image.png"]}
    async with example_images_app() as harness:
        response = await harness.client.post(
            "/api/lm/import-example-images", json=payload
        )
        body = await response.json()

        assert response.status == 200
        assert body == {"operation": "import_images", "payload": payload}
        expected_call = ("import_images", payload)
        assert expected_call in harness.processor.calls


async def test_delete_route_delegates_to_processor():
    payload = {"model_hash": "abc123", "short_id": "xyz"}
    async with example_images_app() as harness:
        response = await harness.client.post(
            "/api/lm/delete-example-image", json=payload
        )
        body = await response.json()

        assert response.status == 200
        assert body == {"operation": "delete_custom_image", "payload": payload}
        assert harness.processor.calls == [("delete_custom_image", payload)]


async def test_file_routes_delegate_to_file_manager():
    open_payload = {"model_hash": "abc123"}
    files_params = {"model_hash": "def456"}

    async with example_images_app() as harness:
        open_response = await harness.client.post(
            "/api/lm/open-example-images-folder", json=open_payload
        )
        files_response = await harness.client.get(
            "/api/lm/example-image-files", params=files_params
        )
        has_response = await harness.client.get(
            "/api/lm/has-example-images", params=files_params
        )

        assert open_response.status == 200
        assert files_response.status == 200
        assert has_response.status == 200

        assert await open_response.json() == {"operation": "open_folder", "payload": open_payload}
        assert await files_response.json() == {
            "operation": "get_files",
            "query": files_params,
        }
        assert await has_response.json() == {
            "operation": "has_images",
            "query": files_params,
        }

        assert harness.file_manager.calls == [
            ("open_folder", open_payload),
            ("get_files", files_params),
            ("has_images", files_params),
        ]


async def test_cleanup_route_delegates_to_service():
    async with example_images_app() as harness:
        harness.cleanup_service.result = {
            "success": True,
            "moved_total": 2,
            "moved_empty_folders": 1,
            "moved_orphaned_folders": 1,
        }

        response = await harness.client.post("/api/lm/cleanup-example-image-folders")
        body = await response.json()

        assert response.status == 200
        assert body == harness.cleanup_service.result
        assert len(harness.cleanup_service.calls) == 1


@pytest.mark.asyncio
async def test_download_handler_methods_delegate() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.calls: List[Tuple[str, Any]] = []

        async def get_status(self, request) -> dict:
            self.calls.append(("get_status", request))
            return {"status": "ok"}

        async def pause_download(self, request) -> dict:
            self.calls.append(("pause_download", request))
            return {"status": "paused"}

        async def resume_download(self, request) -> dict:
            self.calls.append(("resume_download", request))
            return {"status": "running"}

        async def stop_download(self, request) -> dict:
            self.calls.append(("stop_download", request))
            return {"status": "stopping"}

        async def start_force_download(self, payload) -> dict:
            self.calls.append(("start_force_download", payload))
            return {"status": "force", "payload": payload}

    class StubDownloadUseCase:
        def __init__(self) -> None:
            self.payloads: List[Any] = []

        async def execute(self, payload: dict) -> dict:
            self.payloads.append(payload)
            return {"status": "started", "payload": payload}

    class DummyRequest:
        def __init__(self, payload: dict) -> None:
            self._payload = payload
            self.query = {}

        async def json(self) -> dict:
            return self._payload

    recorder = Recorder()
    use_case = StubDownloadUseCase()
    handler = ExampleImagesDownloadHandler(use_case, recorder)
    request = DummyRequest({"foo": "bar"})

    download_response = await handler.download_example_images(request)
    assert json.loads(download_response.text) == {"status": "started", "payload": {"foo": "bar"}}
    status_response = await handler.get_example_images_status(request)
    assert json.loads(status_response.text) == {"status": "ok"}
    pause_response = await handler.pause_example_images(request)
    assert json.loads(pause_response.text) == {"status": "paused"}
    resume_response = await handler.resume_example_images(request)
    assert json.loads(resume_response.text) == {"status": "running"}
    stop_response = await handler.stop_example_images(request)
    assert json.loads(stop_response.text) == {"status": "stopping"}
    force_response = await handler.force_download_example_images(request)
    assert json.loads(force_response.text) == {"status": "force", "payload": {"foo": "bar"}}

    assert use_case.payloads == [{"foo": "bar"}]
    assert recorder.calls == [
        ("get_status", request),
        ("pause_download", request),
        ("resume_download", request),
        ("stop_download", request),
        ("start_force_download", {"foo": "bar"}),
    ]


@pytest.mark.asyncio
async def test_management_handler_methods_delegate() -> None:
    class StubImportUseCase:
        def __init__(self) -> None:
            self.requests: List[Any] = []

        async def execute(self, request: Any) -> dict:
            self.requests.append(request)
            return {"status": "imported"}

    class Recorder:
        def __init__(self) -> None:
            self.calls: List[Tuple[str, Any]] = []

        async def delete_custom_image(self, request) -> str:
            self.calls.append(("delete_custom_image", request))
            return "delete"

    recorder = Recorder()
    cleanup_service = StubExampleImagesCleanupService()
    use_case = StubImportUseCase()
    handler = ExampleImagesManagementHandler(use_case, recorder, cleanup_service)
    request = object()

    import_response = await handler.import_example_images(request)
    assert json.loads(import_response.text) == {"status": "imported"}
    assert await handler.delete_example_image(request) == "delete"
    cleanup_service.result = {"success": True}
    cleanup_response = await handler.cleanup_example_image_folders(request)
    assert json.loads(cleanup_response.text) == {"success": True}
    assert use_case.requests == [request]
    assert recorder.calls == [("delete_custom_image", request)]
    assert len(cleanup_service.calls) == 1


@pytest.mark.asyncio
async def test_file_handler_methods_delegate() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.calls: List[Tuple[str, Any]] = []

        async def open_folder(self, request) -> str:
            self.calls.append(("open_folder", request))
            return "open"

        async def get_files(self, request) -> str:
            self.calls.append(("get_files", request))
            return "files"

        async def has_images(self, request) -> str:
            self.calls.append(("has_images", request))
            return "has"

    recorder = Recorder()
    handler = ExampleImagesFileHandler(recorder)
    request = object()

    assert await handler.open_example_images_folder(request) == "open"
    assert await handler.get_example_image_files(request) == "files"
    assert await handler.has_example_images(request) == "has"
    assert recorder.calls == [
        ("open_folder", request),
        ("get_files", request),
        ("has_images", request),
    ]


def test_handler_set_route_mapping_includes_all_handlers() -> None:
    class DummyUseCase:
        async def execute(self, payload):
            return payload

    class DummyManager:
        async def get_status(self, request):
            return {}

        async def pause_download(self, request):
            return {}

        async def resume_download(self, request):
            return {}

        async def start_force_download(self, payload):
            return payload

    class DummyProcessor:
        async def delete_custom_image(self, request):
            return {}

    download = ExampleImagesDownloadHandler(DummyUseCase(), DummyManager())
    cleanup_service = StubExampleImagesCleanupService()
    management = ExampleImagesManagementHandler(DummyUseCase(), DummyProcessor(), cleanup_service)
    files = ExampleImagesFileHandler(object())
    handler_set = ExampleImagesHandlerSet(
        download=download,
        management=management,
        files=files,
    )

    mapping = handler_set.to_route_mapping()

    expected_keys = {
        "download_example_images",
        "get_example_images_status",
        "pause_example_images",
        "resume_example_images",
        "stop_example_images",
        "force_download_example_images",
        "import_example_images",
        "delete_example_image",
        "cleanup_example_image_folders",
        "open_example_images_folder",
        "get_example_image_files",
        "has_example_images",
    }

    assert mapping.keys() == expected_keys
    for key in expected_keys:
        assert callable(mapping[key])
