from datetime import datetime, timedelta

import pytest

from py.services.websocket_manager import WebSocketManager


class DummyWebSocket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send_json(self, data):
        if self.closed:
            raise RuntimeError("WebSocket closed")
        self.messages.append(data)


@pytest.fixture
def manager():
    return WebSocketManager()


async def test_broadcast_init_progress_replays_cached_payloads(manager):
    first_payload = {"pageType": "loras", "progress": 15}
    second_payload = {"scanner_type": "loras", "progress": 45}

    await manager.broadcast_init_progress(first_payload)
    await manager.broadcast_init_progress(second_payload)

    replay_socket = DummyWebSocket()
    await manager._send_cached_init_progress(replay_socket)

    assert replay_socket.messages == [
        {
            "pageType": "loras",
            "progress": 15,
            "stage": "processing",
            "details": "Processing...",
        },
        {
            "scanner_type": "loras",
            "progress": 45,
            "stage": "processing",
            "details": "Processing...",
        },
    ]


async def test_broadcast_init_progress_adds_defaults(manager):
    ws = DummyWebSocket()
    manager._init_websockets.add(ws)

    await manager.broadcast_init_progress({})

    assert ws.messages == [
        {
            "stage": "processing",
            "progress": 0,
            "details": "Processing...",
        }
    ]


async def test_broadcast_init_progress_caches_payload(manager):
    await manager.broadcast_init_progress({'pageType': 'loras', 'progress': 42})

    cached = manager._last_init_progress.get('page:loras')
    assert cached is not None
    assert cached['progress'] == 42
    assert cached['stage'] == 'processing'
    assert cached['details'] == 'Processing...'


async def test_send_cached_progress_to_new_client(manager):
    await manager.broadcast_init_progress({'pageType': 'loras', 'progress': 87})

    ws = DummyWebSocket()
    await manager._send_cached_init_progress(ws)

    assert ws.messages[-1]['progress'] == 87
    assert ws.messages[-1]['pageType'] == 'loras'

async def test_broadcast_download_progress_tracks_state(manager):
    ws = DummyWebSocket()
    download_id = "abc"
    manager._download_websockets[download_id] = ws

    await manager.broadcast_download_progress(
        download_id,
        {
            "progress": 55,
            "bytes_downloaded": 512,
            "total_bytes": 1024,
            "bytes_per_second": 128.0,
        },
    )

    assert ws.messages == [
        {
            "progress": 55,
            "bytes_downloaded": 512,
            "total_bytes": 1024,
            "bytes_per_second": 128.0,
        }
    ]
    stored = manager.get_download_progress(download_id)
    assert stored["progress"] == 55
    assert stored["bytes_downloaded"] == 512
    assert stored["total_bytes"] == 1024
    assert stored["bytes_per_second"] == 128.0


async def test_broadcast_download_progress_to_multiple_updates(manager):
    ws = DummyWebSocket()
    download_id = "batch"
    manager._download_websockets[download_id] = ws

    await manager.broadcast_download_progress(download_id, {"progress": 10})
    await manager.broadcast_download_progress(download_id, {"progress": 75})

    assert ws.messages == [{"progress": 10}, {"progress": 75}]
    assert manager.get_download_progress(download_id)["progress"] == 75


async def test_broadcast_download_progress_missing_socket(manager):
    await manager.broadcast_download_progress("missing", {"progress": 30})
    # Progress should be stored even without a live websocket
    missing = manager.get_download_progress("missing")
    assert missing["progress"] == 30
    assert "bytes_downloaded" not in missing


async def test_auto_organize_progress_helpers(manager):
    payload = {"status": "processing", "progress": 10}
    await manager.broadcast_auto_organize_progress(payload)

    assert manager.get_auto_organize_progress() == payload
    assert manager.is_auto_organize_running() is True

    manager.cleanup_auto_organize_progress()
    assert manager.get_auto_organize_progress() is None
    assert manager.is_auto_organize_running() is False


async def test_broadcast_auto_organize_progress_notifies_all_clients(manager):
    ws_primary = DummyWebSocket()
    ws_secondary = DummyWebSocket()
    manager._websockets.update({ws_primary, ws_secondary})

    payload = {"status": "started", "progress": 5}
    await manager.broadcast_auto_organize_progress(payload)

    assert ws_primary.messages == [payload]
    assert ws_secondary.messages == [payload]


def test_cleanup_old_downloads(manager):
    now = datetime.now()
    manager._download_progress = {
        "recent": {"progress": 10, "timestamp": now},
        "stale": {"progress": 100, "timestamp": now - timedelta(hours=48)},
    }

    manager.cleanup_old_downloads(max_age_hours=24)

    assert "stale" not in manager._download_progress
    assert "recent" in manager._download_progress


def test_generate_download_id(manager):
    download_id = manager.generate_download_id()
    assert isinstance(download_id, str)
    assert download_id
