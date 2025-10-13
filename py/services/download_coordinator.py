"""Service wrapper for coordinating download lifecycle events."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from .downloader import DownloadProgress


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

        async def progress_callback(progress: Any, snapshot: Optional[DownloadProgress] = None) -> None:
            percent = 0.0
            metrics: Optional[DownloadProgress] = None

            if isinstance(progress, DownloadProgress):
                metrics = progress
                percent = progress.percent_complete
            elif isinstance(snapshot, DownloadProgress):
                metrics = snapshot
                percent = snapshot.percent_complete
            else:
                try:
                    percent = float(progress)
                except (TypeError, ValueError):
                    percent = 0.0

            payload: Dict[str, Any] = {
                "status": "progress",
                "progress": round(percent),
                "download_id": download_id,
            }

            if metrics is not None:
                payload.update(
                    {
                        "bytes_downloaded": metrics.bytes_downloaded,
                        "total_bytes": metrics.total_bytes,
                        "bytes_per_second": metrics.bytes_per_second,
                    }
                )

            await self._ws_manager.broadcast_download_progress(
                download_id,
                payload,
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

    async def pause_download(self, download_id: str) -> Dict[str, Any]:
        """Pause an active download and notify listeners."""

        download_manager = await self._download_manager_factory()
        result = await download_manager.pause_download(download_id)

        if result.get("success"):
            cached_progress = self._ws_manager.get_download_progress(download_id) or {}
            payload: Dict[str, Any] = {
                "status": "paused",
                "progress": cached_progress.get("progress", 0),
                "download_id": download_id,
                "message": "Download paused by user",
            }

            for field in ("bytes_downloaded", "total_bytes", "bytes_per_second"):
                if field in cached_progress:
                    payload[field] = cached_progress[field]

            payload["bytes_per_second"] = 0.0

            await self._ws_manager.broadcast_download_progress(download_id, payload)

        return result

    async def resume_download(self, download_id: str) -> Dict[str, Any]:
        """Resume a paused download and notify listeners."""

        download_manager = await self._download_manager_factory()
        result = await download_manager.resume_download(download_id)

        if result.get("success"):
            cached_progress = self._ws_manager.get_download_progress(download_id) or {}
            payload: Dict[str, Any] = {
                "status": "downloading",
                "progress": cached_progress.get("progress", 0),
                "download_id": download_id,
                "message": "Download resumed by user",
            }

            for field in ("bytes_downloaded", "total_bytes"):
                if field in cached_progress:
                    payload[field] = cached_progress[field]

            payload["bytes_per_second"] = cached_progress.get("bytes_per_second", 0.0)

            await self._ws_manager.broadcast_download_progress(download_id, payload)

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

