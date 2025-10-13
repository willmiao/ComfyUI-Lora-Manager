import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

from py.services.download_coordinator import DownloadCoordinator
from py.services.downloader import DownloadProgress
from py.services.metadata_sync_service import MetadataSyncService
from py.services.preview_asset_service import PreviewAssetService
from py.services.tag_update_service import TagUpdateService


class DummySettings:
    def __init__(self, values: Dict[str, Any] | None = None) -> None:
        self._values = values or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)


class RecordingMetadataManager:
    def __init__(self) -> None:
        self.saved: List[tuple[str, Dict[str, Any]]] = []

    async def save_metadata(self, path: str, metadata: Dict[str, Any]) -> bool:
        self.saved.append((path, json.loads(json.dumps(metadata))))
        metadata_path = path if path.endswith(".metadata.json") else f"{os.path.splitext(path)[0]}.metadata.json"
        Path(metadata_path).write_text(json.dumps(metadata))
        return True

    async def hydrate_model_data(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        return model_data


class RecordingPreviewService:
    def __init__(self) -> None:
        self.calls: List[tuple[str, List[Dict[str, Any]]]] = []

    async def ensure_preview_for_metadata(
        self, metadata_path: str, local_metadata: Dict[str, Any], images
    ) -> None:
        self.calls.append((metadata_path, list(images or [])))
        local_metadata["preview_url"] = "preview.webp"
        local_metadata["preview_nsfw_level"] = 1


class DummyProvider:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload

    async def get_model_by_hash(self, sha256: str):
        return self.payload, None

    async def get_model_version(self, model_id: int, model_version_id: int | None):
        return self.payload


class FakeExifUtils:
    @staticmethod
    def optimize_image(**kwargs):
        return kwargs["image_data"], {}


def test_metadata_sync_merges_remote_fields(tmp_path: Path) -> None:
    manager = RecordingMetadataManager()
    preview = RecordingPreviewService()
    provider = DummyProvider({
        "baseModel": "SD15",
        "model": {"name": "Merged", "description": "desc", "tags": ["tag"], "creator": {"username": "user"}},
        "trainedWords": ["word"],
        "images": [{"url": "http://example", "nsfwLevel": 2, "type": "image"}],
    })

    service = MetadataSyncService(
        metadata_manager=manager,
        preview_service=preview,
        settings=DummySettings(),
        default_metadata_provider_factory=lambda: asyncio.sleep(0, result=provider),
        metadata_provider_selector=lambda _name=None: asyncio.sleep(0, result=provider),
    )

    metadata_path = str(tmp_path / "model.metadata.json")
    local_metadata = {"civitai": {"trainedWords": ["existing"]}}

    updated = asyncio.run(service.update_model_metadata(metadata_path, local_metadata, provider.payload))

    assert updated["model_name"] == "Merged"
    assert updated["modelDescription"] == "desc"
    assert set(updated["civitai"]["trainedWords"]) == {"existing", "word"}
    assert manager.saved
    assert preview.calls


def test_metadata_sync_fetch_and_update_updates_cache(tmp_path: Path) -> None:
    manager = RecordingMetadataManager()
    preview = RecordingPreviewService()
    provider = DummyProvider({
        "baseModel": "SDXL",
        "model": {"name": "Updated"},
        "images": [],
    })

    update_cache_calls: List[Dict[str, Any]] = []

    async def update_cache(original: str, new: str, metadata: Dict[str, Any]) -> bool:
        update_cache_calls.append({"original": original, "metadata": metadata})
        return True

    service = MetadataSyncService(
        metadata_manager=manager,
        preview_service=preview,
        settings=DummySettings(),
        default_metadata_provider_factory=lambda: asyncio.sleep(0, result=provider),
        metadata_provider_selector=lambda _name=None: asyncio.sleep(0, result=provider),
    )

    model_data = {"sha256": "abc", "file_path": str(tmp_path / "model.safetensors")}
    asyncio.run(manager.hydrate_model_data(model_data))
    success, error = asyncio.run(
        service.fetch_and_update_model(
            sha256="abc",
            file_path=str(tmp_path / "model.safetensors"),
            model_data=model_data,
            update_cache_func=update_cache,
        )
    )

    assert success is True
    assert error is None
    assert update_cache_calls
    assert manager.saved


def test_preview_asset_service_replace_preview(tmp_path: Path) -> None:
    metadata_path = tmp_path / "sample.metadata.json"
    metadata_path.write_text(json.dumps({}))

    async def metadata_loader(path: str) -> Dict[str, Any]:
        return json.loads(Path(path).read_text())

    manager = RecordingMetadataManager()

    service = PreviewAssetService(
        metadata_manager=manager,
        downloader_factory=lambda: asyncio.sleep(0, result=None),
        exif_utils=FakeExifUtils(),
    )

    preview_calls: List[Dict[str, Any]] = []

    async def update_preview(model_path: str, preview_path: str, nsfw: int) -> bool:
        preview_calls.append({"model_path": model_path, "preview_path": preview_path, "nsfw": nsfw})
        return True

    model_path = str(tmp_path / "sample.safetensors")
    Path(model_path).write_bytes(b"model")

    result = asyncio.run(
        service.replace_preview(
            model_path=model_path,
            preview_data=b"image-bytes",
            content_type="image/png",
            original_filename="preview.png",
            nsfw_level=2,
            update_preview_in_cache=update_preview,
            metadata_loader=metadata_loader,
        )
    )

    assert result["preview_nsfw_level"] == 2
    assert preview_calls
    saved_metadata = json.loads(metadata_path.read_text())
    assert saved_metadata["preview_nsfw_level"] == 2


def test_download_coordinator_emits_progress() -> None:
    class WSStub:
        def __init__(self) -> None:
            self.progress_events: List[Dict[str, Any]] = []
            self.counter = 0

        def generate_download_id(self) -> str:
            self.counter += 1
            return f"dl-{self.counter}"

        async def broadcast_download_progress(self, download_id: str, payload: Dict[str, Any]) -> None:
            self.progress_events.append({"id": download_id, **payload})

    class DownloadManagerStub:
        def __init__(self) -> None:
            self.calls: List[Dict[str, Any]] = []
            self.snapshot = DownloadProgress(
                percent_complete=25.0,
                bytes_downloaded=256,
                total_bytes=1024,
                bytes_per_second=128.0,
                timestamp=0.0,
            )

        async def download_from_civitai(self, **kwargs) -> Dict[str, Any]:
            self.calls.append(kwargs)
            await kwargs["progress_callback"](self.snapshot)
            return {"success": True}

        async def cancel_download(self, download_id: str) -> Dict[str, Any]:
            return {"success": True, "download_id": download_id}

        async def get_active_downloads(self) -> Dict[str, Any]:
            return {"active": []}

    ws_stub = WSStub()
    manager_stub = DownloadManagerStub()

    coordinator = DownloadCoordinator(
        ws_manager=ws_stub,
        download_manager_factory=lambda: asyncio.sleep(0, result=manager_stub),
    )

    result = asyncio.run(coordinator.schedule_download({"model_id": 1}))

    assert result["success"] is True
    assert manager_stub.calls
    assert ws_stub.progress_events
    expected_progress = round(manager_stub.snapshot.percent_complete)
    first_event = ws_stub.progress_events[0]
    assert first_event["progress"] == expected_progress
    assert first_event["bytes_downloaded"] == manager_stub.snapshot.bytes_downloaded
    assert first_event["total_bytes"] == manager_stub.snapshot.total_bytes
    assert first_event["bytes_per_second"] == manager_stub.snapshot.bytes_per_second

    cancel_result = asyncio.run(coordinator.cancel_download(result["download_id"]))
    assert cancel_result["success"] is True

    active = asyncio.run(coordinator.list_active_downloads())
    assert active == {"active": []}


def test_tag_update_service_adds_unique_tags(tmp_path: Path) -> None:
    metadata_path = tmp_path / "model.metadata.json"
    metadata_path.write_text(json.dumps({"tags": ["Existing"]}))

    async def loader(path: str) -> Dict[str, Any]:
        return json.loads(Path(path).read_text())

    manager = RecordingMetadataManager()

    service = TagUpdateService(metadata_manager=manager)

    cache_updates: List[Dict[str, Any]] = []

    async def update_cache(original: str, new: str, metadata: Dict[str, Any]) -> bool:
        cache_updates.append(metadata)
        return True

    tags = asyncio.run(
        service.add_tags(
            file_path=str(tmp_path / "model.safetensors"),
            new_tags=["New", "existing"],
            metadata_loader=loader,
            update_cache=update_cache,
        )
    )

    assert tags == ["Existing", "New"]
    assert manager.saved
    assert cache_updates
