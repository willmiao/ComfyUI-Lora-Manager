from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from py.services.aria2_downloader import (
    Aria2Downloader,
    Aria2Error,
    Aria2Transfer,
    MAX_TRANSFER_RECOVERY_ATTEMPTS,
)
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

    async def fake_rpc_call(method, params, **_kwargs):
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

    async def fake_rpc_call(method, params, **_kwargs):
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
    downloader._transfers["download-1"] = Aria2Transfer(
        gid="gid-1", save_path="/tmp/model.safetensors"
    )

    calls = []

    async def fake_rpc_call(method, params, **_kwargs):
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
    downloader._transfers["download-1"] = Aria2Transfer(
        gid="gid-1", save_path=str(save_path)
    )

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

    async def fake_rpc_call(method, params, **_kwargs):
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


@pytest.mark.asyncio
async def test_download_file_recovers_when_transfer_lost_mid_poll(
    tmp_path, monkeypatch
):
    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1/jsonrpc"
    downloader._rpc_secret = "secret"

    save_path = tmp_path / "downloads" / "model.safetensors"
    add_uri_count = {"n": 0}
    poll_count = {"n": 0}

    async def fake_rpc_call(method, params, **_kwargs):
        if method == "aria2.addUri":
            add_uri_count["n"] += 1
            return "gid-1" if add_uri_count["n"] == 1 else "gid-2"
        if method == "aria2.tellStatus":
            poll_count["n"] += 1
            if poll_count["n"] == 1:
                # Simulate a concurrent close() wiping the transfer mid-poll.
                downloader._transfers.pop("download-1", None)
                return {
                    "gid": "gid-1",
                    "status": "active",
                    "completedLength": "5",
                    "totalLength": "10",
                    "downloadSpeed": "25",
                }
            return {
                "gid": "gid-2",
                "status": "complete",
                "completedLength": "10",
                "totalLength": "10",
                "downloadSpeed": "0",
                "files": [{"path": str(save_path)}],
            }
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
    assert add_uri_count["n"] == 2
    assert downloader._transfers == {}


@pytest.mark.asyncio
async def test_download_file_recovers_when_rpc_fails_mid_poll(tmp_path, monkeypatch):
    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1/jsonrpc"
    downloader._rpc_secret = "secret"

    save_path = tmp_path / "downloads" / "model.safetensors"
    add_uri_count = {"n": 0}
    poll_count = {"n": 0}

    async def fake_rpc_call(method, params, **_kwargs):
        if method == "aria2.addUri":
            add_uri_count["n"] += 1
            return "gid-1" if add_uri_count["n"] == 1 else "gid-2"
        raise AssertionError(f"Unexpected RPC method: {method}")

    async def fake_get_status_with_retry(download_id):
        poll_count["n"] += 1
        if poll_count["n"] == 1:
            raise Aria2Error(
                "Failed to query aria2 download status after 4 attempts: boom"
            )
        return {
            "gid": "gid-2",
            "status": "complete",
            "completedLength": "10",
            "totalLength": "10",
            "downloadSpeed": "0",
            "files": [{"path": str(save_path)}],
        }

    monkeypatch.setattr(downloader, "_ensure_process", AsyncMock())
    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)
    monkeypatch.setattr(downloader, "_get_status_with_retry", fake_get_status_with_retry)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    success, result = await downloader.download_file(
        "https://example.com/model.safetensors",
        str(save_path),
        download_id="download-1",
    )

    assert success is True
    assert result == str(save_path)
    assert add_uri_count["n"] == 2
    assert downloader._transfers == {}


@pytest.mark.asyncio
async def test_download_file_fails_after_recovery_attempts_exhausted(
    tmp_path, monkeypatch
):
    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1/jsonrpc"
    downloader._rpc_secret = "secret"

    save_path = tmp_path / "downloads" / "model.safetensors"
    add_uri_count = {"n": 0}

    async def fake_rpc_call(method, params, **_kwargs):
        if method == "aria2.addUri":
            add_uri_count["n"] += 1
            return f"gid-{add_uri_count['n']}"
        raise AssertionError(f"Unexpected RPC method: {method}")

    async def fake_get_status(download_id):
        return None  # transfer never tracked / always lost

    monkeypatch.setattr(downloader, "_ensure_process", AsyncMock())
    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)
    monkeypatch.setattr(downloader, "get_status", fake_get_status)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    success, result = await downloader.download_file(
        "https://example.com/model.safetensors",
        str(save_path),
        download_id="download-1",
    )

    assert success is False
    assert result == "aria2 download not found"
    assert add_uri_count["n"] == 1 + MAX_TRANSFER_RECOVERY_ATTEMPTS
    assert downloader._transfers == {}


@pytest.mark.asyncio
async def test_download_file_concurrent_same_id_schedules_once(tmp_path, monkeypatch):
    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1/jsonrpc"
    downloader._rpc_secret = "secret"

    save_path = tmp_path / "downloads" / "model.safetensors"
    add_uri_count = {"n": 0}
    poll_count = {"n": 0}

    async def fake_rpc_call(method, params, **_kwargs):
        if method == "aria2.addUri":
            add_uri_count["n"] += 1
            return "gid-1"
        if method == "aria2.tellStatus":
            poll_count["n"] += 1
            if poll_count["n"] < 4:
                return {
                    "gid": "gid-1",
                    "status": "active",
                    "completedLength": "5",
                    "totalLength": "10",
                    "downloadSpeed": "25",
                }
            return {
                "gid": "gid-1",
                "status": "complete",
                "completedLength": "10",
                "totalLength": "10",
                "downloadSpeed": "0",
                "files": [{"path": str(save_path)}],
            }
        raise AssertionError(f"Unexpected RPC method: {method}")

    monkeypatch.setattr(downloader, "_ensure_process", AsyncMock())
    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    results = await asyncio.gather(
        downloader.download_file(
            "https://example.com/model.safetensors",
            str(save_path),
            download_id="download-1",
        ),
        downloader.download_file(
            "https://example.com/model.safetensors",
            str(save_path),
            download_id="download-1",
        ),
    )

    assert all(success for success, _ in results)
    assert all(result == str(save_path) for _, result in results)
    assert add_uri_count["n"] <= 2
    assert downloader._transfers == {}


@pytest.mark.asyncio
async def test_download_file_cleanup_preserves_newer_registration(tmp_path, monkeypatch):
    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1/jsonrpc"
    downloader._rpc_secret = "secret"

    save_path = tmp_path / "downloads" / "model.safetensors"
    poll_count = {"n": 0}

    async def fake_rpc_call(method, params, **_kwargs):
        if method == "aria2.addUri":
            return "gid-1"
        if method == "aria2.tellStatus":
            poll_count["n"] += 1
            if poll_count["n"] == 1:
                # Simulate another invocation registering its own transfer.
                downloader._transfers["download-1"] = Aria2Transfer(
                    gid="gid-new", save_path=str(save_path)
                )
                return {
                    "gid": "gid-1",
                    "status": "active",
                    "completedLength": "5",
                    "totalLength": "10",
                    "downloadSpeed": "25",
                }
            return {
                "gid": "gid-new",
                "status": "complete",
                "completedLength": "10",
                "totalLength": "10",
                "downloadSpeed": "0",
                "files": [{"path": str(save_path)}],
            }
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
    assert downloader._transfers["download-1"].gid == "gid-new"


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


@pytest.mark.asyncio
async def test_get_status_with_retry_passes_through_success(monkeypatch):
    """A successful first call returns immediately, no retries."""
    downloader = Aria2Downloader()
    call_count = 0

    async def fake_get_status(_id):
        nonlocal call_count
        call_count += 1
        return {"status": "active", "completedLength": "50", "totalLength": "100"}

    monkeypatch.setattr(downloader, "get_status", fake_get_status)

    result = await downloader._get_status_with_retry("dummy")
    assert result is not None
    assert result["status"] == "active"
    assert call_count == 1


@pytest.mark.asyncio
async def test_get_status_with_retry_succeeds_after_transient_failure(monkeypatch):
    """A transient Aria2Error on the first call is retried and succeeds."""
    downloader = Aria2Downloader()
    call_count = 0

    async def fake_get_status(_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Aria2Error("timeout")
        return {"status": "complete", "completedLength": "100", "totalLength": "100"}

    monkeypatch.setattr(downloader, "get_status", fake_get_status)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    result = await downloader._get_status_with_retry("dummy")
    assert result is not None
    assert result["status"] == "complete"
    assert call_count == 2


@pytest.mark.asyncio
async def test_get_status_with_retry_raises_after_all_retries_exhausted(monkeypatch):
    """All retry attempts fail → Aria2Error with a descriptive message."""
    downloader = Aria2Downloader()

    async def fake_get_status(_id):
        raise Aria2Error("connection reset")

    monkeypatch.setattr(downloader, "get_status", fake_get_status)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    with pytest.raises(Aria2Error) as exc_info:
        await downloader._get_status_with_retry("dummy")

    msg = str(exc_info.value)
    assert "after 4 attempts" in msg
    assert "connection reset" in msg


@pytest.mark.asyncio
async def test_get_status_with_retry_returns_none_when_not_tracked(monkeypatch):
    """No transfer in _transfers → get_status returns None → no retry needed."""
    downloader = Aria2Downloader()

    # get_status returns None when the download_id has no transfer;
    # _get_status_with_retry should propagate that without raising.
    result = await downloader._get_status_with_retry("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_wait_until_ready_includes_stderr_in_error():
    """When the subprocess exits early, its stderr output must be in Aria2Error."""
    import sys

    downloader = Aria2Downloader()

    # Start a subprocess that writes a message to stderr and exits with code 28.
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c",
        "import sys; print('ERROR: unknown option --fsync', file=sys.stderr); sys.exit(28)",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    # Let the process exit
    await asyncio.sleep(0.2)

    # Point the downloader at this dead process and let _wait_until_ready
    # discover the exit and read stderr.
    downloader._process = proc

    with pytest.raises(Aria2Error) as exc_info:
        await downloader._wait_until_ready()

    msg = str(exc_info.value)
    assert "code 28" in msg
    assert "ERROR: unknown option --fsync" in msg


def test_is_disk_write_error_matches_wrapper_and_cause_lines():
    downloader = Aria2Downloader()

    assert downloader._is_disk_write_error(
        "[ERROR] [DownloadCommand.cc:127] errorCode=9 Write disk cache flush failure index=18798"
    )
    assert downloader._is_disk_write_error(
        "Exception: [AbstractDiskWriter.cc:454] errNum=28 errorCode=9 "
        "Failed to write into the file D:\\models\\model.safetensors, "
        "cause: No space left on device"
    )
    # Windows: "used by another process" = the file is locked by antivirus etc.
    assert downloader._is_disk_write_error(
        "Exception: ... The process cannot access the file because it is "
        "being used by another process."
    )
    assert not downloader._is_disk_write_error(
        "Download aborted. URI=https://example.com/model.safetensors"
    )
    assert not downloader._is_disk_write_error("")
    assert not downloader._is_disk_write_error("bad option: --fsync")


@pytest.mark.asyncio
async def test_drain_stderr_promotes_disk_write_failure_to_info(caplog):
    downloader = Aria2Downloader()

    class FakeStderr:
        def __init__(self, lines):
            self._lines = list(lines)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._lines:
                raise StopAsyncIteration
            return self._lines.pop(0)

    proc = type(
        "Proc",
        (),
        {
            "stderr": FakeStderr(
                [
                    b"",
                    b"[ERROR] [WrDiskCacheEntry.cc:83] Error when trying to flush write cache",
                    b"Exception: [AbstractDiskWriter.cc:454] errNum=28 errorCode=9 "
                    b"Failed to write into the file D:\\models\\model.safetensors, "
                    b"cause: No space left on device",
                    b"Download aborted. URI=https://example.com/model.safetensors",
                ]
            )
        },
    )()
    downloader._process = proc

    with caplog.at_level(logging.DEBUG, logger="py.services.aria2_downloader"):
        await downloader._drain_stderr()

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]

    assert any(
        "Error when trying to flush write cache" in r.message for r in info_records
    )
    assert any("No space left on device" in r.message for r in info_records)
    assert any("Download aborted" in r.message for r in debug_records)
    assert not any("Download aborted" in r.message for r in info_records)


def test_stderr_error_rate_limited_to_one_info_per_window(caplog, monkeypatch):
    downloader = Aria2Downloader()
    line = "Exception: ... cause: No space left on device"

    with caplog.at_level(logging.DEBUG, logger="py.services.aria2_downloader"):
        downloader._report_stderr_error(line)
        downloader._report_stderr_error(line)
        monkeypatch.setattr(downloader, "_stderr_error_report", {})
        downloader._report_stderr_error(line)

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]

    assert len(info_records) == 2
    assert len(debug_records) == 1
    assert "repeated disk write error" in debug_records[0].message


def test_stderr_error_report_prunes_expired_entries():
    downloader = Aria2Downloader()
    old_line = "Exception: ... cause: No space left on device"
    new_line = "Exception: ... cause: Input/output error"
    downloader._stderr_error_report[old_line] = time.monotonic() - 120.0

    downloader._report_stderr_error(new_line)

    assert old_line not in downloader._stderr_error_report
    assert new_line in downloader._stderr_error_report


@pytest.mark.asyncio
async def test_get_status_returns_none_without_retry_when_gid_not_found(monkeypatch):
    """A forgotten GID is permanent: no retry attempts on a dead GID."""
    downloader = Aria2Downloader()
    downloader._transfers["download-1"] = Aria2Transfer(
        gid="gone-gid", save_path="/tmp/model.safetensors"
    )

    calls = []

    async def fake_rpc_call(method, params, **_kwargs):
        calls.append(method)
        raise Aria2Error("GID gone-gid is not found")

    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    assert await downloader._get_status_with_retry("download-1") is None
    assert calls == ["aria2.tellStatus"]


@pytest.mark.asyncio
async def test_get_status_still_raises_on_transient_rpc_error(monkeypatch):
    downloader = Aria2Downloader()
    downloader._transfers["download-1"] = Aria2Transfer(
        gid="gid-1", save_path="/tmp/model.safetensors"
    )

    async def fake_rpc_call(method, params, **_kwargs):
        raise Aria2Error("connection reset")

    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)
    monkeypatch.setattr("py.services.aria2_downloader.asyncio.sleep", AsyncMock())

    with pytest.raises(Aria2Error, match="Failed to query aria2 download status"):
        await downloader._get_status_with_retry("download-1")


@pytest.mark.asyncio
async def test_cancel_download_pops_transfer_on_success(monkeypatch):
    downloader = Aria2Downloader()
    downloader._transfers["download-1"] = Aria2Transfer(
        gid="gid-1", save_path="/tmp/model.safetensors"
    )

    async def fake_rpc_call(method, params, **_kwargs):
        return "gid-1"

    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)

    result = await downloader.cancel_download("download-1")

    assert result["success"] is True
    assert "download-1" not in downloader._transfers


@pytest.mark.asyncio
async def test_cancel_download_tolerates_missing_gid(monkeypatch):
    """Cancelling a transfer the daemon already forgot still succeeds."""
    downloader = Aria2Downloader()
    downloader._transfers["download-1"] = Aria2Transfer(
        gid="gone-gid", save_path="/tmp/model.safetensors"
    )
    await downloader._state_store.upsert(
        "download-1", {"gid": "gone-gid", "status": "downloading"}
    )

    async def fake_rpc_call(method, params, **_kwargs):
        raise Aria2Error("GID gone-gid is not found")

    monkeypatch.setattr(downloader, "_rpc_call", fake_rpc_call)

    result = await downloader.cancel_download("download-1")

    assert result["success"] is True
    assert "download-1" not in downloader._transfers
    assert await downloader._state_store.get("download-1") is None


@pytest.mark.asyncio
async def test_rpc_call_suppresses_error_log_when_log_errors_false(
    monkeypatch, caplog
):
    """Probing calls must not spam ERROR for an expected failure."""

    class FakeResponse:
        status = 400

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def text(self):
            return '{"jsonrpc": "2.0", "error": {"code": 1, "message": "GID x is not found"}}'

    class FakeSession:
        closed = False

        def post(self, *args, **kwargs):
            return FakeResponse()

    downloader = Aria2Downloader()
    downloader._rpc_url = "http://127.0.0.1/jsonrpc"
    downloader._rpc_secret = "secret"
    monkeypatch.setattr(downloader, "_get_rpc_session", AsyncMock(return_value=FakeSession()))

    with caplog.at_level(logging.DEBUG, logger="py.services.aria2_downloader"):
        with pytest.raises(Aria2Error, match="not found"):
            await downloader._rpc_call("aria2.tellStatus", ["x"], log_errors=False)

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert error_records == []
    assert any("GID x is not found" in r.message for r in debug_records)
