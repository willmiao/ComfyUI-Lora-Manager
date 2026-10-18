"""Example-images download dispatch accepts the "other" model type.

Covers the three scanner-dispatch sites from docs/plans/other-models-page.md
§9.1: check_pending_models, _download_all_example_images and
_download_specific_models_example_images_sync.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils import example_images_download_manager as download_module


class StubScanner:
    """Scanner double returning predetermined cache contents."""

    def __init__(self, models: list[dict[str, Any]]) -> None:
        self._cache = SimpleNamespace(raw_data=models)

    async def get_cached_data(self):
        return self._cache


class RecordingWebSocketManager:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def broadcast(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


def _patch_all_scanners(monkeypatch: pytest.MonkeyPatch, **scanners) -> None:
    for name, getter in (
        ("lora", "get_lora_scanner"),
        ("checkpoint", "get_checkpoint_scanner"),
        ("embedding", "get_embedding_scanner"),
        ("other", "get_other_scanner"),
    ):
        scanner = scanners.get(name) or StubScanner([])

        async def _get_scanner(cls, _scanner=scanner):
            return _scanner

        monkeypatch.setattr(
            download_module.ServiceRegistry,
            getter,
            classmethod(_get_scanner),
        )


@pytest.mark.asyncio
async def test_check_pending_models_includes_other_scanner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    other_models = [{"sha256": "d" * 64, "model_name": "VAE Model"}]
    _patch_all_scanners(monkeypatch, other=StubScanner(other_models))

    result = await manager.check_pending_models(["other"])

    assert result["success"] is True
    assert result["total_models"] == 1
    assert result["pending_count"] == 1


@pytest.mark.asyncio
async def test_download_all_example_images_processes_other_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    other_models = [{"sha256": "e" * 64, "model_name": "Upscaler Model"}]
    _patch_all_scanners(monkeypatch, other=StubScanner(other_models))

    async def fake_get_downloader():
        return object()

    processed: list[tuple[str, dict[str, Any]]] = []

    async def fake_process_model(self, scanner_type, model, scanner, *_args, **_kwargs):
        processed.append((scanner_type, model))
        return False

    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)
    monkeypatch.setattr(
        download_module.DownloadManager, "_process_model", fake_process_model
    )

    # Simulate the running state that start_download establishes.
    manager._progress["status"] = "running"

    await manager._download_all_example_images(
        str(tmp_path),
        optimize=False,
        model_types=["other"],
        delay=0,
        library_name="default",
    )

    assert processed == [("other", other_models[0])]


@pytest.mark.asyncio
async def test_download_specific_models_example_images_processes_other_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    settings_manager,
):
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)

    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(tmp_path))

    model_hash = "f" * 64
    other_models = [{"sha256": model_hash, "model_name": "Text Encoder Model"}]
    _patch_all_scanners(monkeypatch, other=StubScanner(other_models))

    async def fake_get_downloader():
        return object()

    processed: list[tuple[str, dict[str, Any]]] = []

    async def fake_process_specific_model(
        self, scanner_type, model, scanner, *_args, **_kwargs
    ):
        processed.append((scanner_type, model))
        return True

    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)
    monkeypatch.setattr(
        download_module.DownloadManager,
        "_process_specific_model",
        fake_process_specific_model,
    )

    # Simulate the running state that start_force_download establishes.
    manager._progress["status"] = "running"

    await manager._download_specific_models_example_images_sync(
        [model_hash],
        str(tmp_path),
        optimize=False,
        model_types=["other"],
        delay=0,
        library_name="default",
    )

    assert processed == [("other", other_models[0])]


@pytest.fixture
def settings_manager():
    return get_settings_manager()
