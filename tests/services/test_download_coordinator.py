from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock

from py.services.download_coordinator import DownloadCoordinator


@dataclass
class StubWebSocketManager:
    progress: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    broadcasts: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)

    def generate_download_id(self) -> str:
        return "generated"

    def get_download_progress(self, download_id: str) -> Dict[str, Any] | None:
        return self.progress.get(download_id)

    async def broadcast_download_progress(self, download_id: str, payload: Dict[str, Any]) -> None:
        self.broadcasts.append((download_id, payload))


async def test_pause_download_broadcasts_cached_state():
    ws_manager = StubWebSocketManager(
        progress={
            "dl": {
                "progress": 45,
                "bytes_downloaded": 1024,
                "total_bytes": 2048,
                "bytes_per_second": 256.0,
            }
        }
    )

    download_manager = AsyncMock()
    download_manager.pause_download = AsyncMock(return_value={"success": True})

    async def factory():
        return download_manager

    coordinator = DownloadCoordinator(ws_manager=ws_manager, download_manager_factory=factory)

    result = await coordinator.pause_download("dl")

    assert result == {"success": True}
    assert ws_manager.broadcasts == [
        (
            "dl",
            {
                "status": "paused",
                "progress": 45,
                "download_id": "dl",
                "message": "Download paused by user",
                "bytes_downloaded": 1024,
                "total_bytes": 2048,
                "bytes_per_second": 0.0,
            },
        )
    ]


async def test_resume_download_broadcasts_cached_state():
    ws_manager = StubWebSocketManager(
        progress={
            "dl": {
                "progress": 75,
                "bytes_downloaded": 2048,
                "total_bytes": 4096,
                "bytes_per_second": 512.0,
            }
        }
    )

    download_manager = AsyncMock()
    download_manager.resume_download = AsyncMock(return_value={"success": True})

    async def factory():
        return download_manager

    coordinator = DownloadCoordinator(ws_manager=ws_manager, download_manager_factory=factory)

    result = await coordinator.resume_download("dl")

    assert result == {"success": True}
    assert ws_manager.broadcasts == [
        (
            "dl",
            {
                "status": "downloading",
                "progress": 75,
                "download_id": "dl",
                "message": "Download resumed by user",
                "bytes_downloaded": 2048,
                "total_bytes": 4096,
                "bytes_per_second": 512.0,
            },
        )
    ]


async def test_pause_download_does_not_broadcast_on_failure():
    ws_manager = StubWebSocketManager()

    download_manager = AsyncMock()
    download_manager.pause_download = AsyncMock(return_value={"success": False, "error": "nope"})

    async def factory():
        return download_manager

    coordinator = DownloadCoordinator(ws_manager=ws_manager, download_manager_factory=factory)

    result = await coordinator.pause_download("dl")

    assert result == {"success": False, "error": "nope"}
    assert ws_manager.broadcasts == []
