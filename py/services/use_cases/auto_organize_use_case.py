"""Auto-organize use case orchestrating concurrency and progress handling."""

from __future__ import annotations

import asyncio
from typing import Optional, Protocol, Sequence

from ..model_file_service import AutoOrganizeResult, ModelFileService, ProgressCallback


class AutoOrganizeLockProvider(Protocol):
    """Minimal protocol for objects exposing auto-organize locking primitives."""

    def is_auto_organize_running(self) -> bool:
        """Return ``True`` when an auto-organize operation is in-flight."""

    async def get_auto_organize_lock(self) -> asyncio.Lock:
        """Return the asyncio lock guarding auto-organize operations."""


class AutoOrganizeInProgressError(RuntimeError):
    """Raised when an auto-organize run is already active."""


class AutoOrganizeUseCase:
    """Coordinate auto-organize execution behind a shared lock."""

    def __init__(
        self,
        *,
        file_service: ModelFileService,
        lock_provider: AutoOrganizeLockProvider,
    ) -> None:
        self._file_service = file_service
        self._lock_provider = lock_provider

    async def execute(
        self,
        *,
        file_paths: Optional[Sequence[str]] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AutoOrganizeResult:
        """Run the auto-organize routine guarded by a shared lock."""

        if self._lock_provider.is_auto_organize_running():
            raise AutoOrganizeInProgressError("Auto-organize is already running")

        lock = await self._lock_provider.get_auto_organize_lock()
        if lock.locked():
            raise AutoOrganizeInProgressError("Auto-organize is already running")

        async with lock:
            return await self._file_service.auto_organize_models(
                file_paths=list(file_paths) if file_paths is not None else None,
                progress_callback=progress_callback,
            )
