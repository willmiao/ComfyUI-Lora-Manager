from pathlib import Path

import threading

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

    await service.mark_as_deleted("lora", 101)
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


@pytest.mark.asyncio
async def test_mark_downloaded_bulk_writes_off_event_loop(
    tmp_path: Path, monkeypatch
) -> None:
    """The executemany upsert + commit must not run on the event loop thread."""
    db_path = tmp_path / "download-history.sqlite"
    service = DownloadedVersionHistoryService(
        str(db_path),
        settings_manager=DummySettings(),
    )

    loop_thread = threading.get_ident()
    write_threads: list[int] = []
    original_write = service._mark_downloaded_bulk_sync

    def tracking_write(payload):
        write_threads.append(threading.get_ident())
        return original_write(payload)

    monkeypatch.setattr(service, "_mark_downloaded_bulk_sync", tracking_write)

    await service.mark_downloaded_bulk(
        "lora",
        [{"model_id": 7, "version_id": 701, "file_path": "/m/x.safetensors"}],
        source="scan",
    )

    assert write_threads and write_threads[0] != loop_thread
    assert await service.has_been_downloaded("lora", 701) is True


@pytest.mark.asyncio
async def test_per_file_history_tracking(tmp_path: Path) -> None:
    """Per-file records coexist with the version-level row (#1058)."""
    db_path = tmp_path / "download-history.sqlite"
    service = DownloadedVersionHistoryService(
        str(db_path),
        settings_manager=DummySettings(),
    )

    await service.mark_downloaded(
        "lora", 101, model_id=11, source="download",
        file_path="/models/a.safetensors", file_id=1001, file_name="a.safetensors",
    )
    await service.mark_downloaded(
        "lora", 101, model_id=11, source="download",
        file_path="/models/b.safetensors", file_id=1002, file_name="b.safetensors",
    )

    assert await service.get_downloaded_file_ids("lora", 101) == [1001, 1002]
    # Version-level tracking remains single-row per version
    assert await service.get_downloaded_version_ids("lora", 11) == [101]

    # Re-downloading the same file updates in place, no duplicate
    await service.mark_downloaded(
        "lora", 101, source="download", file_id=1001, file_name="a.safetensors",
    )
    assert await service.get_downloaded_file_ids("lora", 101) == [1001, 1002]

    # Single-file deletion keeps the sibling record
    await service.mark_file_deleted("lora", 101, 1001)
    assert await service.get_downloaded_file_ids("lora", 101) == [1002]

    # Whole-version deletion clears per-file records
    await service.mark_as_deleted("lora", 101)
    assert await service.get_downloaded_file_ids("lora", 101) == []
    assert await service.has_been_downloaded("lora", 101) is False


@pytest.mark.asyncio
async def test_per_file_history_ignores_invalid_ids(tmp_path: Path) -> None:
    service = DownloadedVersionHistoryService(
        str(tmp_path / "download-history.sqlite"),
        settings_manager=DummySettings(),
    )

    # mark_downloaded without a file id only touches the version-level table
    await service.mark_downloaded("lora", 201, model_id=21, source="scan")
    assert await service.get_downloaded_file_ids("lora", 201) == []

    # Invalid inputs are no-ops
    await service.mark_file_deleted("lora", 201, None)  # type: ignore[arg-type]
    assert await service.get_downloaded_file_ids("unknown-type", 201) == []


@pytest.mark.asyncio
async def test_file_history_table_created_for_legacy_db(tmp_path: Path) -> None:
    """Existing databases gain the per-file table via CREATE IF NOT EXISTS."""
    import sqlite3

    db_path = tmp_path / "download-history.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE downloaded_model_versions (
            model_type TEXT NOT NULL,
            version_id INTEGER NOT NULL,
            model_id INTEGER,
            first_seen_at REAL NOT NULL,
            last_seen_at REAL NOT NULL,
            source TEXT NOT NULL,
            last_file_path TEXT,
            last_library_name TEXT,
            is_deleted_override INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (model_type, version_id)
        );
        """
    )
    conn.close()

    service = DownloadedVersionHistoryService(
        str(db_path),
        settings_manager=DummySettings(),
    )
    await service.mark_downloaded(
        "lora", 301, model_id=31, source="download",
        file_id=9001, file_name="file.safetensors",
    )
    assert await service.get_downloaded_file_ids("lora", 301) == [9001]
    assert await service.has_been_downloaded("lora", 301) is True
