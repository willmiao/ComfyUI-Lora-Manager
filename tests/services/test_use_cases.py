import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from py_local.services.model_file_service import AutoOrganizeResult
from py_local.services.use_cases import (
    AutoOrganizeInProgressError,
    AutoOrganizeUseCase,
    BulkMetadataRefreshUseCase,
    DownloadModelEarlyAccessError,
    DownloadModelUseCase,
    DownloadModelValidationError,
)
from tests.conftest import MockModelService, MockScanner


class StubLockProvider:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.running = False

    def is_auto_organize_running(self) -> bool:
        return self.running

    async def get_auto_organize_lock(self) -> asyncio.Lock:
        return self._lock


class StubFileService:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def auto_organize_models(
        self,
        *,
        file_paths: Optional[List[str]] = None,
        progress_callback=None,
    ) -> AutoOrganizeResult:
        result = AutoOrganizeResult()
        result.total = len(file_paths or [])
        self.calls.append({"file_paths": file_paths, "progress_callback": progress_callback})
        return result


class StubMetadataSync:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def fetch_and_update_model(self, **kwargs: Any):
        self.calls.append(kwargs)
        model_data = kwargs["model_data"]
        model_data["model_name"] = model_data.get("model_name", "model") + "-updated"
        return True, None


@dataclass
class StubSettings:
    enable_metadata_archive_db: bool = False

    def get(self, key: str, default: Any = None) -> Any:
        if key == "enable_metadata_archive_db":
            return self.enable_metadata_archive_db
        return default


class ProgressCollector:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    async def on_progress(self, payload: Dict[str, Any]) -> None:
        self.events.append(payload)


class StubDownloadCoordinator:
    def __init__(self, *, error: Optional[str] = None) -> None:
        self.error = error
        self.payloads: List[Dict[str, Any]] = []

    async def schedule_download(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.payloads.append(payload)
        if self.error == "validation":
            raise ValueError("Missing required parameter: Please provide either 'model_id' or 'model_version_id'")
        if self.error == "401":
            raise RuntimeError("401 Unauthorized")
        return {"success": True, "download_id": "abc123"}


async def test_auto_organize_use_case_executes_with_lock() -> None:
    file_service = StubFileService()
    lock_provider = StubLockProvider()
    use_case = AutoOrganizeUseCase(file_service=file_service, lock_provider=lock_provider)

    result = await use_case.execute(file_paths=["model1"], progress_callback=None)

    assert isinstance(result, AutoOrganizeResult)
    assert file_service.calls[0]["file_paths"] == ["model1"]


async def test_auto_organize_use_case_rejects_when_running() -> None:
    file_service = StubFileService()
    lock_provider = StubLockProvider()
    lock_provider.running = True
    use_case = AutoOrganizeUseCase(file_service=file_service, lock_provider=lock_provider)

    with pytest.raises(AutoOrganizeInProgressError):
        await use_case.execute(file_paths=None, progress_callback=None)


async def test_bulk_metadata_refresh_emits_progress_and_updates_cache() -> None:
    scanner = MockScanner()
    scanner._cache.raw_data = [
        {
            "file_path": "model1.safetensors",
            "sha256": "hash",
            "from_civitai": True,
            "model_name": "Demo",
        }
    ]
    service = MockModelService(scanner)
    metadata_sync = StubMetadataSync()
    settings = StubSettings()
    progress = ProgressCollector()

    use_case = BulkMetadataRefreshUseCase(
        service=service,
        metadata_sync=metadata_sync,
        settings_service=settings,
        logger=logging.getLogger("test"),
    )

    result = await use_case.execute_with_error_handling(progress_callback=progress)

    assert result["success"] is True
    assert progress.events[0]["status"] == "started"
    assert progress.events[-1]["status"] == "completed"
    assert metadata_sync.calls
    assert scanner._cache.resort_calls == 1


async def test_bulk_metadata_refresh_reports_errors() -> None:
    class FailingScanner(MockScanner):
        async def get_cached_data(self, force_refresh: bool = False):
            raise RuntimeError("boom")

    service = MockModelService(FailingScanner())
    metadata_sync = StubMetadataSync()
    settings = StubSettings()
    progress = ProgressCollector()

    use_case = BulkMetadataRefreshUseCase(
        service=service,
        metadata_sync=metadata_sync,
        settings_service=settings,
        logger=logging.getLogger("test"),
    )

    with pytest.raises(RuntimeError):
        await use_case.execute_with_error_handling(progress_callback=progress)

    assert progress.events
    assert progress.events[-1]["status"] == "error"
    assert progress.events[-1]["error"] == "boom"


async def test_download_model_use_case_raises_validation_error() -> None:
    coordinator = StubDownloadCoordinator(error="validation")
    use_case = DownloadModelUseCase(download_coordinator=coordinator)

    with pytest.raises(DownloadModelValidationError):
        await use_case.execute({})


async def test_download_model_use_case_raises_early_access() -> None:
    coordinator = StubDownloadCoordinator(error="401")
    use_case = DownloadModelUseCase(download_coordinator=coordinator)

    with pytest.raises(DownloadModelEarlyAccessError):
        await use_case.execute({"model_id": 1})


async def test_download_model_use_case_returns_result() -> None:
    coordinator = StubDownloadCoordinator()
    use_case = DownloadModelUseCase(download_coordinator=coordinator)

    result = await use_case.execute({"model_id": 1})

    assert result["success"] is True
    assert result["download_id"] == "abc123"
