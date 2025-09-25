"""Use case for scheduling model downloads with consistent error handling."""

from __future__ import annotations

from typing import Any, Dict

from ..download_coordinator import DownloadCoordinator


class DownloadModelValidationError(ValueError):
    """Raised when incoming payload validation fails."""


class DownloadModelEarlyAccessError(RuntimeError):
    """Raised when the download is gated behind Civitai early access."""


class DownloadModelUseCase:
    """Coordinate download scheduling through the coordinator service."""

    def __init__(self, *, download_coordinator: DownloadCoordinator) -> None:
        self._download_coordinator = download_coordinator

    async def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Schedule a download and normalize error conditions."""

        try:
            return await self._download_coordinator.schedule_download(payload)
        except ValueError as exc:
            raise DownloadModelValidationError(str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive logging path
            message = str(exc)
            if "401" in message:
                raise DownloadModelEarlyAccessError(
                    "Early Access Restriction: This model requires purchase. Please buy early access on Civitai.com."
                ) from exc
            raise
