import asyncio
import json
import os
import sys
from pathlib import Path

import types
from dataclasses import dataclass, field
from typing import Optional

folder_paths_stub = types.SimpleNamespace(get_folder_paths=lambda *_: [])
sys.modules.setdefault("folder_paths", folder_paths_stub)

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

from py.config import config
from py.routes.base_model_routes import BaseModelRoutes
from py.services import model_file_service
from py.services.downloader import DownloadProgress
from py.services.metadata_sync_service import MetadataSyncService
from py.services.model_file_service import AutoOrganizeResult
from py.services.model_update_service import ModelVersionRecord
from py.services.service_registry import ServiceRegistry
from py.services.websocket_manager import ws_manager
from py.utils.exif_utils import ExifUtils
from py.utils.metadata_manager import MetadataManager


class DummyRoutes(BaseModelRoutes):
    template_name = "dummy.html"

    def setup_specific_routes(self, registrar, prefix: str) -> None:  # pragma: no cover - no extra routes in smoke tests
        return None

    def __init__(self, service=None):
        super().__init__(service)
        self.set_model_update_service(NullModelUpdateService())


@dataclass
class NullUpdateRecord:
    model_type: str
    model_id: int
    versions: list[ModelVersionRecord] = field(default_factory=list)
    last_checked_at: float | None = None
    should_ignore_model: bool = False

    @property
    def largest_version_id(self) -> int | None:
        if not self.versions:
            return None
        return max(version.version_id for version in self.versions)

    @property
    def version_ids(self) -> list[int]:
        return [version.version_id for version in self.versions]

    @property
    def in_library_version_ids(self) -> list[int]:
        return [version.version_id for version in self.versions if version.is_in_library]

    def has_update(self) -> bool:
        return False


class NullModelUpdateService:
    async def refresh_for_model_type(self, *args, **kwargs):
        return {}

    async def refresh_single_model(self, *args, **kwargs):
        return None

    async def update_in_library_versions(self, model_type, model_id, version_ids):
        versions = [
            ModelVersionRecord(
                version_id=version_id,
                name=None,
                base_model=None,
                released_at=None,
                size_bytes=None,
                preview_url=None,
                is_in_library=True,
                should_ignore=False,
            )
            for version_id in version_ids
        ]
        return NullUpdateRecord(model_type=model_type, model_id=model_id, versions=versions)

    async def set_should_ignore(self, model_type, model_id, should_ignore):
        return NullUpdateRecord(
            model_type=model_type,
            model_id=model_id,
            should_ignore_model=should_ignore,
        )

    async def set_version_should_ignore(self, model_type, model_id, version_id, should_ignore):
        return await self.set_should_ignore(model_type, model_id, should_ignore)

    async def get_record(self, *args, **kwargs):
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
            self.error = None
            self.cancelled = []
            self.active_downloads = {}
            self.last_progress_snapshot: Optional[DownloadProgress] = None

        async def download_from_civitai(self, **kwargs):
            self.calls.append(kwargs)
            if self.error is not None:
                raise self.error
            snapshot = DownloadProgress(
                percent_complete=50.0,
                bytes_downloaded=5120,
                total_bytes=10240,
                bytes_per_second=2048.0,
                timestamp=0.0,
            )
            self.last_progress_snapshot = snapshot
            await kwargs["progress_callback"](snapshot)
            return {"success": True, "path": "/tmp/model.safetensors"}

        async def cancel_download(self, download_id):
            self.cancelled.append(download_id)
            return {"success": True, "download_id": download_id}

        async def get_active_downloads(self):
            return self.active_downloads

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


def test_routes_return_service_not_ready_when_unattached():
    async def scenario():
        client = await create_test_client(None)
        try:
            response = await client.get("/api/lm/test-models/list")
            payload = await response.json()

            assert response.status == 503
            assert payload == {"success": False, "error": "Service not ready"}
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
            assert mock_scanner._cache.raw_data[0]["preview_url"] == expected_preview
            assert mock_scanner._cache.raw_data[0]["preview_nsfw_level"] == 2

            updated_metadata = json.loads(metadata_path.read_text())
            assert updated_metadata["preview_url"] == expected_preview
            assert updated_metadata["preview_nsfw_level"] == 2
        finally:
            await client.close()

    asyncio.run(scenario())


def test_fetch_civitai_hydrates_metadata_before_sync(
    mock_service,
    mock_scanner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    model_path = tmp_path / "hydrate.safetensors"
    model_path.write_bytes(b"model")
    metadata_path = tmp_path / "hydrate.metadata.json"

    existing_metadata = {
        "file_path": str(model_path),
        "sha256": "abc123",
        "model_name": "Hydrated",
        "preview_url": "keep/me.png",
        "civitai": {
            "id": 99,
            "modelId": 42,
            "images": [{"url": "https://example.com/existing.png", "type": "image"}],
            "customImages": [{"id": "old-id", "url": "", "type": "image"}],
            "trainedWords": ["keep"],
        },
        "custom_field": "preserve",
    }
    metadata_path.write_text(json.dumps(existing_metadata), encoding="utf-8")

    minimal_cache_entry = {
        "file_path": str(model_path),
        "sha256": "abc123",
        "folder": "some/folder",
        "civitai": {"id": 99, "modelId": 42},
    }
    mock_scanner._cache.raw_data = [minimal_cache_entry]

    class FakeMetadata:
        def __init__(self, payload: dict) -> None:
            self._payload = payload
            self._unknown_fields = {"legacy_field": "legacy"}

        def to_dict(self) -> dict:
            return self._payload.copy()

    async def fake_load_metadata(path: str, *_args, **_kwargs):
        assert path == str(model_path)
        return FakeMetadata(existing_metadata), False

    async def fake_save_metadata(path: str, metadata: dict) -> bool:
        save_calls.append((path, json.loads(json.dumps(metadata))))
        return True

    async def fake_fetch_and_update_model(
        self,
        *,
        sha256: str,
        file_path: str,
        model_data: dict,
        update_cache_func,
    ):
        captured["model_data"] = json.loads(json.dumps(model_data))
        to_save = model_data.copy()
        to_save.pop("folder", None)
        await MetadataManager.save_metadata(
            os.path.splitext(file_path)[0] + ".metadata.json",
            to_save,
        )
        await update_cache_func(file_path, file_path, model_data)
        return True, None

    save_calls: list[tuple[str, dict]] = []
    captured: dict[str, dict] = {}

    monkeypatch.setattr(MetadataManager, "load_metadata", staticmethod(fake_load_metadata))
    monkeypatch.setattr(MetadataManager, "save_metadata", staticmethod(fake_save_metadata))
    monkeypatch.setattr(MetadataSyncService, "fetch_and_update_model", fake_fetch_and_update_model)

    async def scenario():
        client = await create_test_client(mock_service)
        try:
            response = await client.post(
                "/api/lm/test-models/fetch-civitai",
                json={"file_path": str(model_path)},
            )
            payload = await response.json()

            assert response.status == 200
            assert payload["success"] is True
            assert captured["model_data"]["custom_field"] == "preserve"
            assert captured["model_data"]["civitai"]["images"][0]["url"] == "https://example.com/existing.png"
            assert captured["model_data"]["civitai"]["trainedWords"] == ["keep"]
            assert captured["model_data"]["civitai"]["id"] == 99
        finally:
            await client.close()

    asyncio.run(scenario())

    assert save_calls, "Metadata save should be invoked"
    saved_path, saved_payload = save_calls[0]
    assert saved_path == str(metadata_path)
    assert saved_payload["custom_field"] == "preserve"
    assert saved_payload["civitai"]["images"][0]["url"] == "https://example.com/existing.png"
    assert saved_payload["civitai"]["trainedWords"] == ["keep"]
    assert saved_payload["civitai"]["id"] == 99
    assert saved_payload["legacy_field"] == "legacy"

    assert mock_scanner.updated_models
    updated_metadata = mock_scanner.updated_models[-1]["metadata"]
    assert updated_metadata["custom_field"] == "preserve"
    assert updated_metadata["civitai"]["customImages"][0]["id"] == "old-id"


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
            expected_progress = round(download_manager_stub.last_progress_snapshot.percent_complete)
            assert progress["progress"] == expected_progress
            assert progress["bytes_downloaded"] == download_manager_stub.last_progress_snapshot.bytes_downloaded
            assert progress["total_bytes"] == download_manager_stub.last_progress_snapshot.total_bytes
            assert progress["bytes_per_second"] == download_manager_stub.last_progress_snapshot.bytes_per_second
            assert "timestamp" in progress

            progress_response = await client.get(
                f"/api/lm/download-progress/{payload['download_id']}"
            )
            progress_payload = await progress_response.json()

            assert progress_response.status == 200
            assert progress_payload == {
                "success": True,
                "progress": expected_progress,
                "bytes_downloaded": download_manager_stub.last_progress_snapshot.bytes_downloaded,
                "total_bytes": download_manager_stub.last_progress_snapshot.total_bytes,
                "bytes_per_second": download_manager_stub.last_progress_snapshot.bytes_per_second,
            }
            ws_manager.cleanup_download_progress(payload["download_id"])
        finally:
            await client.close()

    asyncio.run(scenario())


def test_download_model_requires_identifier(mock_service, download_manager_stub):
    async def scenario():
        client = await create_test_client(mock_service)
        try:
            response = await client.post(
                "/api/lm/download-model",
                json={"model_root": "/tmp"},
            )
            payload = await response.json()

            assert response.status == 400
            assert payload["success"] is False
            assert "Missing required" in payload["error"]
        finally:
            await client.close()

    asyncio.run(scenario())


def test_download_model_maps_validation_errors(mock_service, download_manager_stub):
    download_manager_stub.error = ValueError("Invalid relative path")

    async def scenario():
        client = await create_test_client(mock_service)
        try:
            response = await client.post(
                "/api/lm/download-model",
                json={"model_version_id": 123},
            )
            payload = await response.json()

            assert response.status == 400
            assert payload == {"success": False, "error": "Invalid relative path"}
            assert ws_manager._download_progress == {}
        finally:
            await client.close()

    asyncio.run(scenario())


def test_download_model_maps_early_access_errors(mock_service, download_manager_stub):
    download_manager_stub.error = RuntimeError("401 early access")

    async def scenario():
        client = await create_test_client(mock_service)
        try:
            response = await client.post(
                "/api/lm/download-model",
                json={"model_id": 4},
            )
            payload = await response.json()

            assert response.status == 401
            assert payload == {
                "success": False,
                "error": "Early Access Restriction: This model requires purchase. Please buy early access on Civitai.com.",
            }
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


def test_auto_organize_route_emits_progress(mock_service, monkeypatch: pytest.MonkeyPatch):
    async def fake_auto_organize(self, file_paths=None, progress_callback=None):
        result = AutoOrganizeResult()
        result.total = 1
        result.processed = 1
        result.success_count = 1
        result.skipped_count = 0
        result.failure_count = 0
        result.operation_type = "bulk"
        if progress_callback is not None:
            await progress_callback.on_progress({"type": "auto_organize_progress", "status": "started"})
            await progress_callback.on_progress({"type": "auto_organize_progress", "status": "completed"})
        return result

    monkeypatch.setattr(
        model_file_service.ModelFileService,
        "auto_organize_models",
        fake_auto_organize,
    )

    async def scenario():
        client = await create_test_client(mock_service)
        try:
            response = await client.post("/api/lm/test-models/auto-organize", json={"file_paths": []})
            payload = await response.json()

            assert response.status == 200
            assert payload["success"] is True

            progress = ws_manager.get_auto_organize_progress()
            assert progress is not None
            assert progress["status"] == "completed"
        finally:
            await client.close()

    asyncio.run(scenario())


def test_auto_organize_conflict_when_running(mock_service):
    async def scenario():
        client = await create_test_client(mock_service)
        try:
            await ws_manager.broadcast_auto_organize_progress(
                {"type": "auto_organize_progress", "status": "started"}
            )

            response = await client.post("/api/lm/test-models/auto-organize")
            payload = await response.json()

            assert response.status == 409
            assert payload == {
                "success": False,
                "error": "Auto-organize is already running. Please wait for it to complete.",
            }
        finally:
            await client.close()

    asyncio.run(scenario())
