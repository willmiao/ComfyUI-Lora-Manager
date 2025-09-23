from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, List, Tuple

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
    controller: ExampleImagesRoutes


class StubDownloadManager:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Any]] = []

    async def start_download(self, request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        self.calls.append(("start_download", payload))
        return web.json_response({"operation": "start_download", "payload": payload})

    async def get_status(self, request: web.Request) -> web.StreamResponse:
        self.calls.append(("get_status", dict(request.query)))
        return web.json_response({"operation": "get_status"})

    async def pause_download(self, request: web.Request) -> web.StreamResponse:
        self.calls.append(("pause_download", None))
        return web.json_response({"operation": "pause_download"})

    async def resume_download(self, request: web.Request) -> web.StreamResponse:
        self.calls.append(("resume_download", None))
        return web.json_response({"operation": "resume_download"})

    async def start_force_download(self, request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        self.calls.append(("start_force_download", payload))
        return web.json_response({"operation": "start_force_download", "payload": payload})


class StubExampleImagesProcessor:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Any]] = []

    async def import_images(self, request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        self.calls.append(("import_images", payload))
        return web.json_response({"operation": "import_images", "payload": payload})

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


@asynccontextmanager
async def example_images_app() -> ExampleImagesHarness:
    """Yield an ExampleImagesRoutes app wired with stubbed collaborators."""

    download_manager = StubDownloadManager()
    processor = StubExampleImagesProcessor()
    file_manager = StubExampleImagesFileManager()

    controller = ExampleImagesRoutes(
        download_manager=download_manager,
        processor=processor,
        file_manager=file_manager,
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


async def test_pause_and_resume_routes_delegate():
    async with example_images_app() as harness:
        pause_response = await harness.client.post("/api/lm/pause-example-images")
        resume_response = await harness.client.post("/api/lm/resume-example-images")

        assert pause_response.status == 200
        assert await pause_response.json() == {"operation": "pause_download"}
        assert resume_response.status == 200
        assert await resume_response.json() == {"operation": "resume_download"}

        assert harness.download_manager.calls[-2:] == [
            ("pause_download", None),
            ("resume_download", None),
        ]


async def test_import_route_delegates_to_processor():
    payload = {"model_hash": "abc123", "files": ["/path/image.png"]}
    async with example_images_app() as harness:
        response = await harness.client.post(
            "/api/lm/import-example-images", json=payload
        )
        body = await response.json()

        assert response.status == 200
        assert body == {"operation": "import_images", "payload": payload}
        assert harness.processor.calls == [("import_images", payload)]


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


@pytest.mark.asyncio
async def test_download_handler_methods_delegate() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.calls: List[Tuple[str, Any]] = []

        async def start_download(self, request) -> str:
            self.calls.append(("start_download", request))
            return "download"

        async def get_status(self, request) -> str:
            self.calls.append(("get_status", request))
            return "status"

        async def pause_download(self, request) -> str:
            self.calls.append(("pause_download", request))
            return "pause"

        async def resume_download(self, request) -> str:
            self.calls.append(("resume_download", request))
            return "resume"

        async def start_force_download(self, request) -> str:
            self.calls.append(("start_force_download", request))
            return "force"

    recorder = Recorder()
    handler = ExampleImagesDownloadHandler(recorder)
    request = object()

    assert await handler.download_example_images(request) == "download"
    assert await handler.get_example_images_status(request) == "status"
    assert await handler.pause_example_images(request) == "pause"
    assert await handler.resume_example_images(request) == "resume"
    assert await handler.force_download_example_images(request) == "force"

    expected = [
        ("start_download", request),
        ("get_status", request),
        ("pause_download", request),
        ("resume_download", request),
        ("start_force_download", request),
    ]
    assert recorder.calls == expected


@pytest.mark.asyncio
async def test_management_handler_methods_delegate() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.calls: List[Tuple[str, Any]] = []

        async def import_images(self, request) -> str:
            self.calls.append(("import_images", request))
            return "import"

        async def delete_custom_image(self, request) -> str:
            self.calls.append(("delete_custom_image", request))
            return "delete"

    recorder = Recorder()
    handler = ExampleImagesManagementHandler(recorder)
    request = object()

    assert await handler.import_example_images(request) == "import"
    assert await handler.delete_example_image(request) == "delete"
    assert recorder.calls == [
        ("import_images", request),
        ("delete_custom_image", request),
    ]


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
    download = ExampleImagesDownloadHandler(object())
    management = ExampleImagesManagementHandler(object())
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
        "force_download_example_images",
        "import_example_images",
        "delete_example_image",
        "open_example_images_folder",
        "get_example_image_files",
        "has_example_images",
    }

    assert mapping.keys() == expected_keys
    for key in expected_keys:
        assert callable(mapping[key])
