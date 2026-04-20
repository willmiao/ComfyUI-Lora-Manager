from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from py.services.aria2_downloader import Aria2Downloader, Aria2Error
from py.services.aria2_transfer_state import Aria2TransferStateStore
from py.services import aria2_transfer_state


@pytest.fixture(autouse=True)
def isolate_aria2_state(monkeypatch, tmp_path):
    state_path = tmp_path / "cache" / "aria2" / "downloads.json"
    monkeypatch.setattr(
        aria2_transfer_state,
        "get_aria2_state_path",
        lambda: str(state_path),
    )


@pytest.mark.asyncio
async def test_download_file_polls_until_complete(tmp_path, monkeypatch):
    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1/jsonrpc"
    downloader._rpc_secret = "secret"

    save_path = tmp_path / "downloads" / "model.safetensors"
    progress_events = []
    rpc_calls = []
    statuses = iter(
        [
            {
                "gid": "gid-1",
                "status": "active",
                "completedLength": "5",
                "totalLength": "10",
                "downloadSpeed": "25",
            },
            {
                "gid": "gid-1",
                "status": "complete",
                "completedLength": "10",
                "totalLength": "10",
                "downloadSpeed": "0",
                "files": [{"path": str(save_path)}],
            },
        ]
    )

    async def fake_rpc_call(method, params):
        rpc_calls.append((method, params))
        if method == "aria2.addUri":
            return "gid-1"
        if method == "aria2.tellStatus":
            return next(statuses)
        raise AssertionError(f"Unexpected RPC method: {method}")

    monkeypatch.setattr(downloader, "_ensure_process", AsyncMock())
    monkeypatch.setattr(
        downloader,
        "_resolve_authenticated_redirect_url",
        AsyncMock(
            return_value="https://signed.example.com/model.safetensors?token=abc"
        ),
    )
    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    async def progress_callback(progress, snapshot=None):
        progress_events.append(snapshot.percent_complete if snapshot else progress)

    success, result = await downloader.download_file(
        "https://civitai.com/api/download/models/123",
        str(save_path),
        download_id="download-1",
        progress_callback=progress_callback,
        headers={"Authorization": "Bearer token"},
    )

    assert success is True
    assert result == str(save_path)
    assert progress_events == [50.0, 100.0]
    assert downloader._transfers == {}
    assert rpc_calls[0][0] == "aria2.addUri"
    assert rpc_calls[0][1][0] == [
        "https://signed.example.com/model.safetensors?token=abc"
    ]
    assert rpc_calls[0][1][1]["out"] == "model.safetensors"
    assert "header" not in rpc_calls[0][1][1]


@pytest.mark.asyncio
async def test_transfer_state_store_shares_lock_and_preserves_concurrent_updates(tmp_path):
    state_path = tmp_path / "cache" / "aria2" / "downloads.json"
    store_a = Aria2TransferStateStore(str(state_path))
    store_b = Aria2TransferStateStore(str(state_path))

    assert store_a._lock is store_b._lock

    await asyncio.gather(
        store_a.upsert("download-1", {"status": "downloading", "gid": "gid-1"}),
        store_b.upsert("download-2", {"status": "paused", "gid": "gid-2"}),
    )

    assert await store_a.get("download-1") == {"status": "downloading", "gid": "gid-1"}
    assert await store_b.get("download-2") == {"status": "paused", "gid": "gid-2"}


@pytest.mark.asyncio
async def test_download_file_keeps_auth_headers_when_civitai_does_not_redirect(
    tmp_path, monkeypatch
):
    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1/jsonrpc"
    downloader._rpc_secret = "secret"

    save_path = tmp_path / "downloads" / "model.safetensors"
    rpc_calls = []
    statuses = iter(
        [
            {
                "gid": "gid-1",
                "status": "complete",
                "completedLength": "10",
                "totalLength": "10",
                "downloadSpeed": "0",
                "files": [{"path": str(save_path)}],
            },
        ]
    )

    async def fake_rpc_call(method, params):
        rpc_calls.append((method, params))
        if method == "aria2.addUri":
            return "gid-1"
        if method == "aria2.tellStatus":
            return next(statuses)
        raise AssertionError(f"Unexpected RPC method: {method}")

    monkeypatch.setattr(downloader, "_ensure_process", AsyncMock())
    monkeypatch.setattr(
        downloader,
        "_resolve_authenticated_redirect_url",
        AsyncMock(return_value="https://civitai.com/api/download/models/123"),
    )
    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    success, result = await downloader.download_file(
        "https://civitai.com/api/download/models/123",
        str(save_path),
        download_id="download-1",
        headers={"Authorization": "Bearer token"},
    )

    assert success is True
    assert result == str(save_path)
    assert rpc_calls[0][1][0] == ["https://civitai.com/api/download/models/123"]
    assert rpc_calls[0][1][1]["header"] == ["Authorization: Bearer token"]


@pytest.mark.asyncio
async def test_pause_resume_cancel_forward_to_rpc(monkeypatch):
    downloader = Aria2Downloader()
    downloader._transfers["download-1"] = type(
        "Transfer", (), {"gid": "gid-1", "save_path": "/tmp/model.safetensors"}
    )()

    calls = []

    async def fake_rpc_call(method, params):
        calls.append((method, params))
        return "gid-1"

    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)

    pause_result = await downloader.pause_download("download-1")
    resume_result = await downloader.resume_download("download-1")
    cancel_result = await downloader.cancel_download("download-1")

    assert pause_result["success"] is True
    assert resume_result["success"] is True
    assert cancel_result["success"] is True
    assert calls == [
        ("aria2.forcePause", ["gid-1"]),
        ("aria2.unpause", ["gid-1"]),
        ("aria2.forceRemove", ["gid-1"]),
    ]


@pytest.mark.asyncio
async def test_download_file_reuses_existing_transfer_without_add_uri(
    tmp_path, monkeypatch
):
    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1/jsonrpc"
    downloader._rpc_secret = "secret"

    save_path = tmp_path / "downloads" / "model.safetensors"
    downloader._transfers["download-1"] = type(
        "Transfer", (), {"gid": "gid-1", "save_path": str(save_path)}
    )()

    rpc_calls = []
    statuses = iter(
        [
            {
                "gid": "gid-1",
                "status": "active",
                "completedLength": "5",
                "totalLength": "10",
                "downloadSpeed": "25",
            },
            {
                "gid": "gid-1",
                "status": "complete",
                "completedLength": "10",
                "totalLength": "10",
                "downloadSpeed": "0",
                "files": [{"path": str(save_path)}],
            },
        ]
    )

    async def fake_rpc_call(method, params):
        rpc_calls.append((method, params))
        if method == "aria2.tellStatus":
            return next(statuses)
        raise AssertionError(f"Unexpected RPC method: {method}")

    monkeypatch.setattr(downloader, "_ensure_process", AsyncMock())
    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    success, result = await downloader.download_file(
        "https://example.com/model.safetensors",
        str(save_path),
        download_id="download-1",
    )

    assert success is True
    assert result == str(save_path)
    assert [call[0] for call in rpc_calls] == ["aria2.tellStatus", "aria2.tellStatus"]


def test_build_progress_snapshot_normalizes_numeric_fields():
    downloader = Aria2Downloader()

    snapshot = downloader._build_progress_snapshot(
        {
            "completedLength": "75",
            "totalLength": "100",
            "downloadSpeed": "512",
        }
    )

    assert snapshot.percent_complete == 75.0
    assert snapshot.bytes_downloaded == 75
    assert snapshot.total_bytes == 100
    assert snapshot.bytes_per_second == 512.0


def test_resolve_executable_raises_when_binary_missing(monkeypatch):
    downloader = Aria2Downloader()
    settings = type("Settings", (), {"get": lambda self, key, default=None: ""})()

    monkeypatch.setattr("py.services.aria2_downloader.get_settings_manager", lambda: settings)
    monkeypatch.setattr("py.services.aria2_downloader.shutil.which", lambda _: None)

    with pytest.raises(Aria2Error):
        downloader._resolve_executable()


@pytest.mark.asyncio
async def test_rpc_call_surfaces_json_error_on_non_200(monkeypatch):
    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1:6800/jsonrpc"
    downloader._rpc_secret = "secret"

    class FakeResponse:
        status = 400

        async def text(self):
            return (
                '{"jsonrpc":"2.0","id":"x","error":{"code":1,"message":"Unauthorized"}}'
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def post(self, _url, json=None):
            return FakeResponse()

    monkeypatch.setattr(downloader, "_get_rpc_session", AsyncMock(return_value=FakeSession()))

    with pytest.raises(Aria2Error) as exc_info:
        await downloader._rpc_call("aria2.addUri", [["https://example.com/file"]])

    assert "Unauthorized" in str(exc_info.value)
    assert "aria2.addUri" in str(exc_info.value)


@pytest.mark.asyncio
async def test_resolve_authenticated_redirect_url_returns_location(monkeypatch):
    downloader = Aria2Downloader()

    class FakeResponse:
        status = 307
        headers = {"Location": "https://signed.example.com/file.safetensors"}

        async def text(self):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def get(self, _url, headers=None, allow_redirects=False, proxy=None):
            return FakeResponse()

    class FakeDownloader:
        default_headers = {"User-Agent": "ComfyUI-LoRA-Manager/1.0"}
        proxy_url = None

        @property
        def session(self):
            async def _session():
                return FakeSession()

            return _session()

    fake_downloader = FakeDownloader()

    monkeypatch.setattr(
        "py.services.aria2_downloader.get_downloader",
        AsyncMock(return_value=fake_downloader),
    )

    result = await downloader._resolve_authenticated_redirect_url(
        "https://civitai.com/api/download/models/123",
        {"Authorization": "Bearer token"},
    )

    assert result == "https://signed.example.com/file.safetensors"
