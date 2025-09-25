"""Service wrapper for coordinating download lifecycle events."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional


logger = logging.getLogger(__name__)


class DownloadCoordinator:
    """Manage download scheduling, cancellation and introspection."""

    def __init__(
        self,
        *,
        ws_manager,
        download_manager_factory: Callable[[], Awaitable],
    ) -> None:
        self._ws_manager = ws_manager
        self._download_manager_factory = download_manager_factory

    async def schedule_download(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Schedule a download using the provided payload."""

        download_manager = await self._download_manager_factory()

        download_id = payload.get("download_id") or self._ws_manager.generate_download_id()
        payload.setdefault("download_id", download_id)

        async def progress_callback(progress: Any) -> None:
            await self._ws_manager.broadcast_download_progress(
                download_id,
                {
                    "status": "progress",
                    "progress": progress,
                    "download_id": download_id,
                },
            )

        model_id = self._parse_optional_int(payload.get("model_id"), "model_id")
        model_version_id = self._parse_optional_int(
            payload.get("model_version_id"), "model_version_id"
        )

        if model_id is None and model_version_id is None:
            raise ValueError(
                "Missing required parameter: Please provide either 'model_id' or 'model_version_id'"
            )

        result = await download_manager.download_from_civitai(
            model_id=model_id,
            model_version_id=model_version_id,
            save_dir=payload.get("model_root"),
            relative_path=payload.get("relative_path", ""),
            use_default_paths=payload.get("use_default_paths", False),
            progress_callback=progress_callback,
            download_id=download_id,
            source=payload.get("source"),
        )

        result["download_id"] = download_id
        return result

    async def cancel_download(self, download_id: str) -> Dict[str, Any]:
        """Cancel an active download and emit a broadcast event."""

        download_manager = await self._download_manager_factory()
        result = await download_manager.cancel_download(download_id)

        await self._ws_manager.broadcast_download_progress(
            download_id,
            {
                "status": "cancelled",
                "progress": 0,
                "download_id": download_id,
                "message": "Download cancelled by user",
            },
        )

        return result

    async def list_active_downloads(self) -> Dict[str, Any]:
        """Return the active download map from the underlying manager."""

        download_manager = await self._download_manager_factory()
        return await download_manager.get_active_downloads()

    def _parse_optional_int(self, value: Any, field: str) -> Optional[int]:
        """Parse an optional integer from user input."""

        if value is None or value == "":
            return None

        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {field}: Must be an integer") from exc

