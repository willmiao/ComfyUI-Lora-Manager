"""Use case coordinating example image downloads."""

from __future__ import annotations

from typing import Any, Dict

from ....utils.example_images_download_manager import (
    DownloadConfigurationError,
    DownloadInProgressError,
    ExampleImagesDownloadError,
)


class DownloadExampleImagesInProgressError(RuntimeError):
    """Raised when a download is already running."""

    def __init__(self, progress: Dict[str, Any]) -> None:
        super().__init__("Download already in progress")
        self.progress = progress


class DownloadExampleImagesConfigurationError(ValueError):
    """Raised when settings prevent downloads from starting."""


class DownloadExampleImagesUseCase:
    """Validate payloads and trigger the download manager."""

    def __init__(self, *, download_manager) -> None:
        self._download_manager = download_manager

    async def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Start a download and translate manager errors."""

        try:
            return await self._download_manager.start_download(payload)
        except DownloadInProgressError as exc:
            raise DownloadExampleImagesInProgressError(exc.progress_snapshot) from exc
        except DownloadConfigurationError as exc:
            raise DownloadExampleImagesConfigurationError(str(exc)) from exc
        except ExampleImagesDownloadError:
            raise
