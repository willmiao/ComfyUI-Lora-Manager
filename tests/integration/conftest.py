"""Shared fixtures for integration tests."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Generator, List
from unittest.mock import AsyncMock, MagicMock

import pytest
import aiohttp
from aiohttp import web


@pytest.fixture
def temp_download_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for download tests."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    return download_dir


@pytest.fixture
def sample_model_file() -> bytes:
    """Create sample model file content for testing."""
    return b"fake model data for testing purposes"


@pytest.fixture
def sample_recipe_data() -> Dict[str, Any]:
    """Create sample recipe data for testing."""
    return {
        "id": "test-recipe-001",
        "title": "Test Recipe",
        "file_path": "/path/to/recipe.png",
        "folder": "test-folder",
        "base_model": "SD1.5",
        "fingerprint": "abc123def456",
        "created_date": 1700000000.0,
        "modified": 1700000100.0,
        "favorite": False,
        "repair_version": 1,
        "preview_nsfw_level": 0,
        "loras": [
            {"hash": "lora1hash", "file_name": "test_lora1", "strength": 0.8},
            {"hash": "lora2hash", "file_name": "test_lora2", "strength": 1.0},
        ],
        "checkpoint": {"name": "model.safetensors", "hash": "cphash123"},
        "gen_params": {
            "prompt": "masterpiece, best quality, test subject",
            "negative_prompt": "low quality, blurry",
            "steps": 20,
            "cfg": 7.0,
            "sampler": "DPM++ 2M Karras",
        },
        "tags": ["test", "integration", "recipe"],
    }


@pytest.fixture
def mock_websocket_manager():
    """Provide a recording WebSocket manager for integration tests."""
    class RecordingWebSocketManager:
        def __init__(self):
            self.payloads: List[Dict[str, Any]] = []
            self.download_progress: Dict[str, List[Dict[str, Any]]] = {}

        async def broadcast(self, payload: Dict[str, Any]) -> None:
            self.payloads.append(payload)

        async def broadcast_download_progress(
            self, download_id: str, data: Dict[str, Any]
        ) -> None:
            if download_id not in self.download_progress:
                self.download_progress[download_id] = []
            self.download_progress[download_id].append(data)

        def get_download_progress(self, download_id: str) -> Dict[str, Any] | None:
            progress_list = self.download_progress.get(download_id, [])
            if not progress_list:
                return None
            # Return the latest progress
            latest = progress_list[-1]
            return {"download_id": download_id, **latest}

    return RecordingWebSocketManager()


@pytest.fixture
def mock_scanner():
    """Provide a mock model scanner with configurable behavior."""
    class MockScanner:
        def __init__(self):
            self._cache = MagicMock()
            self._cache.raw_data = []
            self._hash_index = MagicMock()
            self.model_type = "lora"
            self._tags_count: Dict[str, int] = {}
            self._excluded_models: List[str] = []

        async def get_cached_data(self, force_refresh: bool = False):
            return self._cache

        async def update_single_model_cache(
            self, original_path: str, new_path: str, metadata: Dict[str, Any]
        ) -> bool:
            for item in self._cache.raw_data:
                if item.get("file_path") == original_path:
                    item.update(metadata)
                    return True
            return False

        def remove_by_path(self, path: str) -> None:
            pass

    return MockScanner


@pytest.fixture
def mock_metadata_manager():
    """Provide a mock metadata manager."""
    class MockMetadataManager:
        def __init__(self):
            self.saved_metadata: List[tuple] = []
            self.loaded_payloads: Dict[str, Dict[str, Any]] = {}

        async def save_metadata(self, file_path: str, metadata: Dict[str, Any]) -> None:
            self.saved_metadata.append((file_path, metadata.copy()))

        async def load_metadata_payload(self, file_path: str) -> Dict[str, Any]:
            return self.loaded_payloads.get(file_path, {})

        def set_payload(self, file_path: str, payload: Dict[str, Any]) -> None:
            self.loaded_payloads[file_path] = payload

    return MockMetadataManager


@pytest.fixture
def mock_download_coordinator():
    """Provide a mock download coordinator."""
    class MockDownloadCoordinator:
        def __init__(self):
            self.active_downloads: Dict[str, Any] = {}
            self.cancelled_downloads: List[str] = []
            self.paused_downloads: List[str] = []
            self.resumed_downloads: List[str] = []

        async def cancel_download(self, download_id: str) -> Dict[str, Any]:
            self.cancelled_downloads.append(download_id)
            return {"success": True, "message": f"Download {download_id} cancelled"}

        async def pause_download(self, download_id: str) -> Dict[str, Any]:
            self.paused_downloads.append(download_id)
            return {"success": True, "message": f"Download {download_id} paused"}

        async def resume_download(self, download_id: str) -> Dict[str, Any]:
            self.resumed_downloads.append(download_id)
            return {"success": True, "message": f"Download {download_id} resumed"}

    return MockDownloadCoordinator


@pytest.fixture
async def test_http_server(
    tmp_path: Path,
) -> AsyncGenerator[tuple[str, int], None]:
    """Create a test HTTP server that serves files from a temporary directory."""
    from aiohttp import web

    async def handle_download(request):
        """Handle file download requests."""
        filename = request.match_info.get("filename", "test_model.safetensors")
        file_path = tmp_path / filename
        if file_path.exists():
            return web.FileResponse(path=file_path)
        return web.Response(status=404, text="File not found")

    async def handle_status(request):
        """Return server status."""
        return web.json_response({"status": "ok", "server": "test"})

    app = web.Application()
    app.router.add_get("/download/{filename}", handle_download)
    app.router.add_get("/status", handle_status)

    runner = web.AppRunner(app)
    await runner.setup()

    # Use port 0 to get an available port
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = site._server.sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"

    yield base_url, port

    await runner.cleanup()


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
