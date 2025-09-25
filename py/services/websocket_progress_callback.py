"""Progress callback implementations backed by the shared WebSocket manager."""

from typing import Any, Dict, Protocol

from .model_file_service import ProgressCallback
from .websocket_manager import ws_manager


class ProgressReporter(Protocol):
    """Protocol representing an async progress callback."""

    async def on_progress(self, progress_data: Dict[str, Any]) -> None:
        """Handle a progress update payload."""


class WebSocketProgressCallback(ProgressCallback):
    """WebSocket implementation of progress callback."""

    async def on_progress(self, progress_data: Dict[str, Any]) -> None:
        """Send progress data via WebSocket."""
        await ws_manager.broadcast_auto_organize_progress(progress_data)


class WebSocketBroadcastCallback:
    """Generic WebSocket progress callback broadcasting to all clients."""

    async def on_progress(self, progress_data: Dict[str, Any]) -> None:
        """Send the provided payload to all connected clients."""
        await ws_manager.broadcast(progress_data)
