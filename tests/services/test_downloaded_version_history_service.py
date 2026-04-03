from pathlib import Path

import pytest

from py.services.downloaded_version_history_service import (
    DownloadedVersionHistoryService,
)


class DummySettings:
    def get_active_library_name(self) -> str:
        return "alpha"


@pytest.mark.asyncio
async def test_download_history_roundtrip_and_manual_override(tmp_path: Path) -> None:
    db_path = tmp_path / "download-history.sqlite"
    service = DownloadedVersionHistoryService(
        str(db_path),
        settings_manager=DummySettings(),
    )

    await service.mark_downloaded(
        "lora",
        101,
        model_id=11,
        source="scan",
        file_path="/models/a.safetensors",
    )
    assert await service.has_been_downloaded("lora", 101) is True
    assert await service.get_downloaded_version_ids("lora", 11) == [101]

    await service.mark_not_downloaded("lora", 101)
    assert await service.has_been_downloaded("lora", 101) is False
    assert await service.get_downloaded_version_ids("lora", 11) == []

    await service.mark_downloaded(
        "lora",
        101,
        model_id=11,
        source="download",
        file_path="/models/a.safetensors",
    )
    assert await service.has_been_downloaded("lora", 101) is True
    assert await service.get_downloaded_version_ids("lora", 11) == [101]


@pytest.mark.asyncio
async def test_download_history_bulk_lookup(tmp_path: Path) -> None:
    db_path = tmp_path / "download-history.sqlite"
    service = DownloadedVersionHistoryService(
        str(db_path),
        settings_manager=DummySettings(),
    )

    await service.mark_downloaded_bulk(
        "checkpoint",
        [
            {"model_id": 5, "version_id": 501, "file_path": "/m/one.safetensors"},
            {"model_id": 5, "version_id": 502, "file_path": "/m/two.safetensors"},
            {"model_id": 6, "version_id": 601, "file_path": "/m/three.safetensors"},
        ],
        source="scan",
    )

    assert await service.get_downloaded_version_ids("checkpoint", 5) == [501, 502]
    assert await service.get_downloaded_version_ids_bulk("checkpoint", [5, 6, 7]) == {
        5: {501, 502},
        6: {601},
    }
