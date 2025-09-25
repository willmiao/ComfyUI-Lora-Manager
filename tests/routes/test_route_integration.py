"""End-to-end integration tests for aiohttp route registrars."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import AsyncIterator, Dict, Iterable, List, Sequence

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from py.routes.lora_routes import LoraRoutes
from py.services.service_registry import ServiceRegistry
from py.services.websocket_manager import ws_manager as global_ws_manager


class IntegrationCache:
    """Minimal cache implementation satisfying the service contract."""

    def __init__(self, items: Sequence[Dict[str, object]]) -> None:
        self.raw_data: List[Dict[str, object]] = [dict(item) for item in items]
        self.folders: List[str] = ["/"]

    async def get_sorted_data(self, *_: object, **__: object) -> List[Dict[str, object]]:
        """Return cached data without additional sorting."""
        return [dict(item) for item in self.raw_data]

    async def resort(self) -> None:
        """Resort is a no-op for the static fixture data."""
        return None


class IntegrationScanner:
    """Scanner double that registers with ServiceRegistry expectations."""

    def __init__(self, items: Iterable[Dict[str, object]]) -> None:
        self.model_type = "lora"
        self._cache = IntegrationCache(list(items))
        self._hash_index = SimpleNamespace(
            removed_paths=[],
            remove_by_path=lambda path: self._hash_index.removed_paths.append(path),
            get_duplicate_hashes=lambda: {},
            get_duplicate_filenames=lambda: {},
        )
        self._tags_count: Dict[str, int] = {}
        self._excluded_models: List[str] = []

    async def get_cached_data(self, *_: object, **__: object) -> IntegrationCache:
        return self._cache

    def get_model_roots(self) -> List[str]:  # pragma: no cover - documented surface
        return ["/"]

    async def bulk_delete_models(self, file_paths: Iterable[str]) -> Dict[str, object]:
        existing_paths = {item["file_path"] for item in self._cache.raw_data}
        deleted = [path for path in file_paths if path in existing_paths]
        self._cache.raw_data = [
            item for item in self._cache.raw_data if item["file_path"] not in deleted
        ]
        await self._cache.resort()
        for path in deleted:
            self._hash_index.remove_by_path(path)
        return {"success": True, "deleted": deleted}

    async def check_model_version_exists(self, *_: object, **__: object) -> bool:
        return False


@asynccontextmanager
async def aiohttp_client(app: web.Application) -> AsyncIterator[TestClient]:
    """Spin up a TestClient with lifecycle management."""

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


def test_lora_route_stack_returns_real_data():
    """Spin up LoRA routes and ensure ServiceRegistry-powered wiring succeeds."""

    async def scenario() -> None:
        ServiceRegistry.clear_services()

        fixture_item = {
            "model_name": "Alpha",
            "file_name": "alpha.safetensors",
            "folder": "root",
            "file_path": "/tmp/alpha.safetensors",
            "size": 128,
            "modified": "2024-01-01T00:00:00Z",
            "tags": ["integration"],
            "civitai": {"trainedWords": ["alpha"]},
            "preview_url": "",
            "preview_nsfw_level": 0,
            "base_model": "SD1",
            "usage_tips": "Use gently",
            "notes": "Integration sample",
            "from_civitai": True,
        }
        scanner = IntegrationScanner([fixture_item])
        await ServiceRegistry.register_service("lora_scanner", scanner)

        app = web.Application()
        routes = LoraRoutes()
        routes.setup_routes(app)

        async with aiohttp_client(app) as client:
            response = await client.get("/api/lm/loras/list")
            payload = await response.json()

            assert response.status == 200
            assert payload["total"] == 1
            returned = payload["items"][0]
            assert returned["model_name"] == "Alpha"
            assert returned["file_name"] == "alpha.safetensors"
            assert returned["usage_tips"] == "Use gently"

    asyncio.run(scenario())
    ServiceRegistry.clear_services()


def test_websocket_routes_broadcast_through_registry():
    """Ensure websocket endpoints accept connections and relay broadcasts."""

    async def scenario() -> None:
        ServiceRegistry.clear_services()
        ws_manager = await ServiceRegistry.get_websocket_manager()

        app = web.Application()
        app.router.add_get("/ws/fetch-progress", ws_manager.handle_connection)
        app.router.add_get("/ws/download-progress", ws_manager.handle_download_connection)

        async with aiohttp_client(app) as client:
            fetch_ws = await client.ws_connect("/ws/fetch-progress")
            await ws_manager.broadcast({"kind": "ping"})
            message = await asyncio.wait_for(fetch_ws.receive_json(), timeout=1)
            assert message == {"kind": "ping"}

            download_ws = await client.ws_connect("/ws/download-progress?id=session-1")
            greeting = await asyncio.wait_for(download_ws.receive_json(), timeout=1)
            assert greeting["type"] == "download_id"
            assert greeting["download_id"] == "session-1"

            await ws_manager.broadcast_download_progress("session-1", {"progress": 55})
            progress = await asyncio.wait_for(download_ws.receive_json(), timeout=1)
            assert progress["progress"] == 55

            await fetch_ws.close()
            await download_ws.close()

        # Ensure the registry cached instance matches the module-level singleton.
        assert ws_manager is global_ws_manager

    asyncio.run(scenario())
    ServiceRegistry.clear_services()
