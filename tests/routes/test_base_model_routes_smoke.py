import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

import types

folder_paths_stub = types.SimpleNamespace(get_folder_paths=lambda *_: [])
sys.modules.setdefault("folder_paths", folder_paths_stub)

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

REPO_ROOT = Path(__file__).resolve().parents[2]
PY_PACKAGE_PATH = REPO_ROOT / "py"

spec = importlib.util.spec_from_file_location(
    "py_local",
    PY_PACKAGE_PATH / "__init__.py",
    submodule_search_locations=[str(PY_PACKAGE_PATH)],
)
py_local = importlib.util.module_from_spec(spec)
assert spec.loader is not None  # for mypy/static analyzers
spec.loader.exec_module(py_local)
sys.modules.setdefault("py_local", py_local)

from py_local.routes.base_model_routes import BaseModelRoutes
from py_local.services.service_registry import ServiceRegistry
from py_local.services.websocket_manager import ws_manager
from py_local.utils.routes_common import ExifUtils
from py_local.config import config


class DummyRoutes(BaseModelRoutes):
    template_name = "dummy.html"

    def setup_specific_routes(self, app: web.Application, prefix: str) -> None:  # pragma: no cover - no extra routes in smoke tests
        return None


async def create_test_client(service) -> TestClient:
    routes = DummyRoutes(service)
    app = web.Application()
    routes.setup_routes(app, "test-models")

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client


@pytest.fixture(autouse=True)
def reset_ws_manager_state():
    ws_manager.cleanup_auto_organize_progress()
    ws_manager._download_progress.clear()
    yield
    ws_manager.cleanup_auto_organize_progress()
    ws_manager._download_progress.clear()


@pytest.fixture
def download_manager_stub():
    class FakeDownloadManager:
        def __init__(self):
            self.calls = []

        async def download_from_civitai(self, **kwargs):
            self.calls.append(kwargs)
            await kwargs["progress_callback"](42)
            return {"success": True, "path": "/tmp/model.safetensors"}

    stub = FakeDownloadManager()
    previous = ServiceRegistry._services.get("download_manager")
    asyncio.run(ServiceRegistry.register_service("download_manager", stub))
    try:
        yield stub
    finally:
        if previous is not None:
            ServiceRegistry._services["download_manager"] = previous
        else:
            ServiceRegistry._services.pop("download_manager", None)


def test_list_models_returns_formatted_items(mock_service, mock_scanner):
    mock_service.paginated_items = [{"file_path": "/tmp/demo.safetensors", "name": "Demo"}]

    async def scenario():
        client = await create_test_client(mock_service)
        try:
            response = await client.get("/api/lm/test-models/list")
            payload = await response.json()

            assert response.status == 200
            assert payload["items"] == [{"file_path": "/tmp/demo.safetensors", "name": "Demo", "formatted": True}]
            assert payload["total"] == 1
            assert mock_service.formatted == payload["items"]
        finally:
            await client.close()

    asyncio.run(scenario())


def test_delete_model_updates_cache_and_hash_index(mock_service, mock_scanner, tmp_path: Path):
    model_path = tmp_path / "sample.safetensors"
    model_path.write_bytes(b"model")
    mock_scanner._cache.raw_data = [{"file_path": str(model_path)}]

    async def scenario():
        client = await create_test_client(mock_service)
        try:
            response = await client.post(
                "/api/lm/test-models/delete",
                json={"file_path": str(model_path)},
            )
            payload = await response.json()

            assert response.status == 200
            assert payload["success"] is True
            assert mock_scanner._cache.raw_data == []
            assert mock_scanner._cache.resort_calls == 1
            assert mock_scanner._hash_index.removed_paths == [str(model_path)]
        finally:
            await client.close()

    asyncio.run(scenario())
    assert not model_path.exists()


def test_replace_preview_writes_file_and_updates_cache(
    mock_service,
    mock_scanner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    model_path = tmp_path / "preview-model.safetensors"
    model_path.write_bytes(b"model")
    metadata_path = tmp_path / "preview-model.metadata.json"
    metadata_path.write_text(json.dumps({"file_path": str(model_path)}))

    mock_scanner._cache.raw_data = [{"file_path": str(model_path)}]

    monkeypatch.setattr(
        ExifUtils,
        "optimize_image",
        staticmethod(lambda image_data, **_: (image_data, ".webp")),
    )
    monkeypatch.setattr(
        config,
        "get_preview_static_url",
        lambda preview_path: f"/static/{Path(preview_path).name}",
    )

    form = FormData()
    form.add_field("preview_file", b"binary-data", filename="preview.png", content_type="image/png")
    form.add_field("model_path", str(model_path))
    form.add_field("nsfw_level", "2")

    async def scenario():
        client = await create_test_client(mock_service)
        try:
            response = await client.post("/api/lm/test-models/replace-preview", data=form)
            payload = await response.json()

            expected_preview = str((tmp_path / "preview-model.webp")).replace(os.sep, "/")
            assert response.status == 200
            assert payload["success"] is True
            assert payload["preview_url"] == "/static/preview-model.webp"
            assert Path(expected_preview).exists()
            assert mock_scanner.preview_updates[-1]["preview_path"] == expected_preview

            updated_metadata = json.loads(metadata_path.read_text())
            assert updated_metadata["preview_url"] == expected_preview
            assert updated_metadata["preview_nsfw_level"] == 2
        finally:
            await client.close()

    asyncio.run(scenario())


def test_download_model_invokes_download_manager(
    mock_service,
    download_manager_stub,
    tmp_path: Path,
):
    async def scenario():
        client = await create_test_client(mock_service)
        try:
            response = await client.post(
                "/api/lm/download-model",
                json={"model_id": 1, "model_root": str(tmp_path)},
            )
            payload = await response.json()

            assert response.status == 200
            assert payload["success"] is True
            assert download_manager_stub.calls

            call_args = download_manager_stub.calls[0]
            assert call_args["model_id"] == 1
            assert call_args["download_id"] == payload["download_id"]
            progress = ws_manager.get_download_progress(payload["download_id"])
            assert progress is not None
            assert progress["progress"] == 42
            ws_manager.cleanup_download_progress(payload["download_id"])
        finally:
            await client.close()

    asyncio.run(scenario())


def test_auto_organize_progress_returns_latest_snapshot(mock_service):
    async def scenario():
        client = await create_test_client(mock_service)
        try:
            await ws_manager.broadcast_auto_organize_progress({"status": "processing", "percent": 50})

            response = await client.get("/api/lm/test-models/auto-organize-progress")
            payload = await response.json()

            assert response.status == 200
            assert payload == {"success": True, "progress": {"status": "processing", "percent": 50}}
        finally:
            await client.close()

    asyncio.run(scenario())
