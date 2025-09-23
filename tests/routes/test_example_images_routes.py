from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, List, Set, Tuple

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from py.routes import example_images_routes
from py.routes.example_images_routes import ExampleImagesRoutes
from py.routes.example_images_route_registrar import ROUTE_DEFINITIONS


@dataclass
class ExampleImagesHarness:
    """Container exposing the aiohttp client and stubbed collaborators."""

    client: TestClient
    download_manager: Any
    processor: Any
    file_manager: Any


@asynccontextmanager
async def example_images_app(monkeypatch: pytest.MonkeyPatch) -> ExampleImagesHarness:
    """Yield an ExampleImagesRoutes app wired with stubbed collaborators."""

    class StubDownloadManager:
        calls: List[Tuple[str, Any]] = []

        @staticmethod
        async def start_download(request):
            payload = await request.json()
            StubDownloadManager.calls.append(("start_download", payload))
            return web.json_response({"operation": "start_download", "payload": payload})

        @staticmethod
        async def get_status(request):
            StubDownloadManager.calls.append(("get_status", dict(request.query)))
            return web.json_response({"operation": "get_status"})

        @staticmethod
        async def pause_download(request):
            StubDownloadManager.calls.append(("pause_download", None))
            return web.json_response({"operation": "pause_download"})

        @staticmethod
        async def resume_download(request):
            StubDownloadManager.calls.append(("resume_download", None))
            return web.json_response({"operation": "resume_download"})

        @staticmethod
        async def start_force_download(request):
            payload = await request.json()
            StubDownloadManager.calls.append(("start_force_download", payload))
            return web.json_response({"operation": "start_force_download", "payload": payload})

    class StubExampleImagesProcessor:
        calls: List[Tuple[str, Any]] = []

        @staticmethod
        async def import_images(request):
            payload = await request.json()
            StubExampleImagesProcessor.calls.append(("import_images", payload))
            return web.json_response({"operation": "import_images", "payload": payload})

        @staticmethod
        async def delete_custom_image(request):
            payload = await request.json()
            StubExampleImagesProcessor.calls.append(("delete_custom_image", payload))
            return web.json_response({"operation": "delete_custom_image", "payload": payload})

    class StubExampleImagesFileManager:
        calls: List[Tuple[str, Any]] = []

        @staticmethod
        async def open_folder(request):
            payload = await request.json()
            StubExampleImagesFileManager.calls.append(("open_folder", payload))
            return web.json_response({"operation": "open_folder", "payload": payload})

        @staticmethod
        async def get_files(request):
            StubExampleImagesFileManager.calls.append(("get_files", dict(request.query)))
            return web.json_response({"operation": "get_files", "query": dict(request.query)})

        @staticmethod
        async def has_images(request):
            StubExampleImagesFileManager.calls.append(("has_images", dict(request.query)))
            return web.json_response({"operation": "has_images", "query": dict(request.query)})

    monkeypatch.setattr(example_images_routes, "DownloadManager", StubDownloadManager)
    monkeypatch.setattr(example_images_routes, "ExampleImagesProcessor", StubExampleImagesProcessor)
    monkeypatch.setattr(example_images_routes, "ExampleImagesFileManager", StubExampleImagesFileManager)

    app = web.Application()
    ExampleImagesRoutes.setup_routes(app)

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        yield ExampleImagesHarness(
            client=client,
            download_manager=StubDownloadManager,
            processor=StubExampleImagesProcessor,
            file_manager=StubExampleImagesFileManager,
        )
    finally:
        await client.close()


async def test_setup_routes_registers_all_definitions(monkeypatch: pytest.MonkeyPatch):
    async with example_images_app(monkeypatch) as harness:
        registered: Set[tuple[str, str]] = {
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
async def test_download_routes_delegate_to_manager(endpoint, payload, monkeypatch: pytest.MonkeyPatch):
    async with example_images_app(monkeypatch) as harness:
        response = await harness.client.post(endpoint, json=payload)
        body = await response.json()

        assert response.status == 200
        assert body["payload"] == payload
        assert body["operation"].startswith("start")

        expected_call = body["operation"], payload
        assert expected_call in harness.download_manager.calls


async def test_status_route_returns_manager_payload(monkeypatch: pytest.MonkeyPatch):
    async with example_images_app(monkeypatch) as harness:
        response = await harness.client.get(
            "/api/lm/example-images-status", params={"detail": "true"}
        )
        body = await response.json()

        assert response.status == 200
        assert body == {"operation": "get_status"}
        assert harness.download_manager.calls == [("get_status", {"detail": "true"})]


async def test_pause_and_resume_routes_delegate(monkeypatch: pytest.MonkeyPatch):
    async with example_images_app(monkeypatch) as harness:
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


async def test_import_route_delegates_to_processor(monkeypatch: pytest.MonkeyPatch):
    payload = {"model_hash": "abc123", "files": ["/path/image.png"]}
    async with example_images_app(monkeypatch) as harness:
        response = await harness.client.post(
            "/api/lm/import-example-images", json=payload
        )
        body = await response.json()

        assert response.status == 200
        assert body == {"operation": "import_images", "payload": payload}
        assert harness.processor.calls == [("import_images", payload)]


async def test_delete_route_delegates_to_processor(monkeypatch: pytest.MonkeyPatch):
    payload = {"model_hash": "abc123", "short_id": "xyz"}
    async with example_images_app(monkeypatch) as harness:
        response = await harness.client.post(
            "/api/lm/delete-example-image", json=payload
        )
        body = await response.json()

        assert response.status == 200
        assert body == {"operation": "delete_custom_image", "payload": payload}
        assert harness.processor.calls == [("delete_custom_image", payload)]


async def test_file_routes_delegate_to_file_manager(monkeypatch: pytest.MonkeyPatch):
    open_payload = {"model_hash": "abc123"}
    files_params = {"model_hash": "def456"}

    async with example_images_app(monkeypatch) as harness:
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
