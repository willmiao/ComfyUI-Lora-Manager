from typing import Dict, Any
from .model_file_service import ProgressCallback
from .websocket_manager import ws_manager


class WebSocketProgressCallback(ProgressCallback):
    """WebSocket implementation of progress callback"""
    
    async def on_progress(self, progress_data: Dict[str, Any]) -> None:
        """Send progress data via WebSocket"""
        await ws_manager.broadcast_auto_organize_progress(progress_data)