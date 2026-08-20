"""Unit tests for DownloadQueueService history operations.

Covers the new ``download_id``-based code paths in
``delete_history_item`` and ``retry_from_history``, plus backward
compatibility with ``id``.
"""

import json
import sqlite3
import time
from pathlib import Path

import pytest

from py.services.download_queue_service import DownloadQueueService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(tmp_path: Path) -> DownloadQueueService:
    """Create a DownloadQueueService backed by a temporary database."""
    return DownloadQueueService(db_path=str(tmp_path / "queue.sqlite"))


async def _seed(
    svc: DownloadQueueService,
    download_id: str,
    status: str = "failed",
) -> tuple[int, str]:
    """Insert a history row and return (autoincrement id, download_id)."""
    row_id = await svc.add_to_history(
        download_id=download_id,
        model_id=1,
        model_version_id=100,
        model_name="TestModel",
        version_name="v1",
        status=status,
    )
    return row_id, download_id


# ---------------------------------------------------------------------------
# delete_history_item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_by_download_id(tmp_path: Path) -> None:
    """delete_history_item(download_id=...) removes the correct row."""
    svc = _make_service(tmp_path)
    rid, did = await _seed(svc, "dl-aaa")

    deleted = await svc.delete_history_item(download_id=did)
    assert deleted is True

    # Verify gone from history
    history = await svc.get_history()
    assert len(history["items"]) == 0


@pytest.mark.asyncio
async def test_delete_by_id_legacy(tmp_path: Path) -> None:
    """delete_history_item(id=...) still works (backward compat)."""
    svc = _make_service(tmp_path)
    rid, _did = await _seed(svc, "dl-bbb")

    deleted = await svc.delete_history_item(id=rid)
    assert deleted is True

    history = await svc.get_history()
    assert len(history["items"]) == 0


@pytest.mark.asyncio
async def test_delete_no_params_returns_false(tmp_path: Path) -> None:
    """Calling delete_history_item with no params returns False."""
    svc = _make_service(tmp_path)
    await _seed(svc, "dl-ccc")

    deleted = await svc.delete_history_item()
    assert deleted is False

    # Row is still there
    history = await svc.get_history()
    assert len(history["items"]) == 1


@pytest.mark.asyncio
async def test_delete_download_id_precedence(tmp_path: Path) -> None:
    """When both id and download_id are given, download_id is used."""
    svc = _make_service(tmp_path)
    # Insert two rows
    rid_a, did_a = await _seed(svc, "dl-aaa")
    rid_b, did_b = await _seed(svc, "dl-bbb")

    # Delete by download_id while also passing the *wrong* id
    deleted = await svc.delete_history_item(id=rid_b, download_id=did_a)
    assert deleted is True

    history = await svc.get_history()
    ids_left = [it["id"] for it in history["items"]]
    assert rid_a not in ids_left  # dl-aaa was deleted
    assert rid_b in ids_left     # dl-bbb (wrong id) was ignored


# ---------------------------------------------------------------------------
# retry_from_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_by_download_id(tmp_path: Path) -> None:
    """retry_from_history(download_id=...) re-queues and deletes history."""
    svc = _make_service(tmp_path)
    rid, did = await _seed(svc, "dl-fail", status="failed")

    item = await svc.retry_from_history(download_id=did)
    assert item is not None
    assert item["status"] == "queued"

    # History row must be deleted (the bug fix)
    history = await svc.get_history()
    ids_in_history = [it["id"] for it in history["items"]]
    assert rid not in ids_in_history

    # Queue must contain the new item
    queue = await svc.get_queue()
    assert len(queue) == 1


@pytest.mark.asyncio
async def test_retry_by_download_id_canceled(tmp_path: Path) -> None:
    """retry_from_history works for 'canceled' status too."""
    svc = _make_service(tmp_path)
    rid, did = await _seed(svc, "dl-cancel", status="canceled")

    item = await svc.retry_from_history(download_id=did)
    assert item is not None
    assert item["status"] == "queued"

    history = await svc.get_history()
    assert len(history["items"]) == 0


@pytest.mark.asyncio
async def test_retry_by_id_legacy(tmp_path: Path) -> None:
    """retry_from_history(item_id=...) still works (backward compat)."""
    svc = _make_service(tmp_path)
    rid, _did = await _seed(svc, "dl-legacy", status="failed")

    item = await svc.retry_from_history(item_id=rid)
    assert item is not None
    assert item["status"] == "queued"

    history = await svc.get_history()
    assert len(history["items"]) == 0


@pytest.mark.asyncio
async def test_retry_no_params_returns_none(tmp_path: Path) -> None:
    """Calling retry_from_history with no params returns None."""
    svc = _make_service(tmp_path)
    await _seed(svc, "dl-none", status="failed")

    item = await svc.retry_from_history()
    assert item is None

    # History untouched
    history = await svc.get_history()
    assert len(history["items"]) == 1


@pytest.mark.asyncio
async def test_retry_non_retryable_status(tmp_path: Path) -> None:
    """retry_from_history returns None for 'completed' status."""
    svc = _make_service(tmp_path)
    _rid, did = await _seed(svc, "dl-ok", status="completed")

    item = await svc.retry_from_history(download_id=did)
    assert item is None

    # History untouched
    history = await svc.get_history()
    assert len(history["items"]) == 1


@pytest.mark.asyncio
async def test_retry_unknown_download_id(tmp_path: Path) -> None:
    """retry_from_history returns None for a non-existent download_id."""
    svc = _make_service(tmp_path)
    await _seed(svc, "dl-real", status="failed")

    item = await svc.retry_from_history(download_id="dl-nope")
    assert item is None


# ---------------------------------------------------------------------------
# file_params persistence across queue -> history -> retry (#1058)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_params_survive_queue_to_history(tmp_path: Path) -> None:
    """complete_download copies the queue row's file_params into history."""
    svc = _make_service(tmp_path)
    await svc.add_to_queue(
        download_id="dl-fp",
        model_id=1,
        model_version_id=100,
        file_params={"id": 1002, "type": "Model"},
    )

    await svc.complete_download("dl-fp", status="failed", error="boom")

    history = await svc.get_history()
    assert len(history["items"]) == 1
    assert json.loads(history["items"][0]["file_params"]) == {
        "id": 1002,
        "type": "Model",
    }


@pytest.mark.asyncio
async def test_retry_restores_file_params(tmp_path: Path) -> None:
    """retry_from_history re-queues with the originally selected file."""
    svc = _make_service(tmp_path)
    await svc.add_to_history(
        download_id="dl-fail-fp",
        model_id=1,
        model_version_id=100,
        status="failed",
        file_params={"id": 1002, "type": "Model"},
    )

    item = await svc.retry_from_history(download_id="dl-fail-fp")

    assert item is not None
    assert item["status"] == "queued"
    assert json.loads(item["file_params"]) == {"id": 1002, "type": "Model"}


@pytest.mark.asyncio
async def test_retry_all_restores_file_params(tmp_path: Path) -> None:
    """retry_all_failed preserves file_params for every re-queued item."""
    svc = _make_service(tmp_path)
    await svc.add_to_history(
        download_id="dl-f1", status="failed", file_params={"id": 1001}
    )
    await svc.add_to_history(download_id="dl-f2", status="canceled")

    count = await svc.retry_all_failed()
    assert count == 2

    queue = await svc.get_queue()
    restored = sorted(
        (q["file_params"] or "") for q in queue
    )
    assert restored[0] == ""  # dl-f2 never had file_params
    assert json.loads(restored[1]) == {"id": 1001}


@pytest.mark.asyncio
async def test_legacy_history_db_gains_file_params_column(tmp_path: Path) -> None:
    """Databases created before the file_params column get migrated (#1058)."""
    db_path = tmp_path / "queue.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE download_queue (
            download_id TEXT PRIMARY KEY,
            model_id INTEGER,
            model_version_id INTEGER,
            model_name TEXT NOT NULL DEFAULT '',
            version_name TEXT DEFAULT '',
            thumbnail_url TEXT DEFAULT '',
            source TEXT,
            file_params TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            priority INTEGER DEFAULT 0,
            progress INTEGER DEFAULT 0,
            bytes_downloaded INTEGER DEFAULT 0,
            total_bytes INTEGER,
            bytes_per_second REAL DEFAULT 0.0,
            error TEXT,
            file_path TEXT,
            added_at REAL NOT NULL,
            started_at REAL,
            completed_at REAL
        );
        CREATE TABLE download_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            download_id TEXT,
            model_id INTEGER,
            model_version_id INTEGER,
            model_name TEXT NOT NULL DEFAULT '',
            version_name TEXT DEFAULT '',
            thumbnail_url TEXT DEFAULT '',
            status TEXT NOT NULL,
            error TEXT,
            file_path TEXT,
            bytes_downloaded INTEGER DEFAULT 0,
            total_bytes INTEGER,
            completed_at REAL NOT NULL,
            is_already_exists INTEGER DEFAULT 0
        );
        """
    )
    conn.close()

    svc = DownloadQueueService(db_path=str(db_path))

    # The migrated table accepts file_params writes
    await svc.add_to_history(
        download_id="dl-legacy-fp", status="failed", file_params={"id": 5}
    )
    history = await svc.get_history()
    assert json.loads(history["items"][0]["file_params"]) == {"id": 5}

    # And retry restores them
    item = await svc.retry_from_history(download_id="dl-legacy-fp")
    assert item is not None
    assert json.loads(item["file_params"]) == {"id": 5}


# ---------------------------------------------------------------------------
# deduplicate() — file identity in the dedup key (#1058)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_queue_keeps_distinct_files_of_same_version(tmp_path: Path) -> None:
    """Two queued downloads of different files of one version both survive."""
    svc = _make_service(tmp_path)
    await svc.add_to_queue(
        download_id="dl-a",
        model_id=1,
        model_version_id=100,
        file_params={"id": 1001, "type": "Model"},
    )
    await svc.add_to_queue(
        download_id="dl-b",
        model_id=1,
        model_version_id=100,
        file_params={"id": 1002, "type": "Model"},
    )

    result = await svc.deduplicate()

    assert result["removed_queue"] == 0
    queue = await svc.get_queue()
    assert sorted(item["download_id"] for item in queue) == ["dl-a", "dl-b"]


@pytest.mark.asyncio
async def test_dedup_queue_collapses_same_file_and_legacy_rows(tmp_path: Path) -> None:
    """Same version + same/absent file id still collapses to the latest row."""
    svc = _make_service(tmp_path)
    # Same file id -> only the most recently enqueued row survives
    await svc.add_to_queue(
        download_id="dl-old",
        model_id=1,
        model_version_id=100,
        file_params={"id": 1001},
    )
    await svc.add_to_queue(
        download_id="dl-new",
        model_id=1,
        model_version_id=100,
        file_params={"id": 1001},
    )
    # Rows without file identity keep the old per-version behavior
    await svc.add_to_queue(
        download_id="dl-legacy-old", model_id=2, model_version_id=200
    )
    await svc.add_to_queue(
        download_id="dl-legacy-new", model_id=2, model_version_id=200
    )

    result = await svc.deduplicate()

    assert result["removed_queue"] == 2
    remaining = {item["download_id"] for item in await svc.get_queue()}
    assert remaining == {"dl-new", "dl-legacy-new"}


@pytest.mark.asyncio
async def test_dedup_queue_does_not_mix_null_and_file_id(tmp_path: Path) -> None:
    """A row with a file id never dedups against a row without one."""
    svc = _make_service(tmp_path)
    await svc.add_to_queue(
        download_id="dl-file",
        model_id=1,
        model_version_id=100,
        file_params={"id": 1001},
    )
    await svc.add_to_queue(
        download_id="dl-nofile", model_id=1, model_version_id=100
    )

    result = await svc.deduplicate()

    assert result["removed_queue"] == 0
    assert len(await svc.get_queue()) == 2


@pytest.mark.asyncio
async def test_dedup_queue_unparseable_file_params_treated_as_none(tmp_path: Path) -> None:
    """Corrupt file_params JSON falls back to the NULL file identity."""
    svc = _make_service(tmp_path)
    await svc.add_to_queue(
        download_id="dl-plain", model_id=1, model_version_id=100
    )
    conn = sqlite3.connect(str(tmp_path / "queue.sqlite"))
    conn.execute(
        "INSERT INTO download_queue (download_id, model_id, model_version_id, "
        "file_params, status, added_at) VALUES (?, ?, ?, ?, 'queued', ?)",
        ("dl-corrupt", 1, 100, "{not json", time.time()),
    )
    conn.commit()
    conn.close()

    result = await svc.deduplicate()

    assert result["removed_queue"] == 1
    assert len(await svc.get_queue()) == 1


@pytest.mark.asyncio
async def test_dedup_history_keeps_distinct_files_of_same_version(tmp_path: Path) -> None:
    """History rows of different files never collapse, even across statuses."""
    svc = _make_service(tmp_path)
    await svc.add_to_history(
        download_id="dl-h1",
        model_id=1,
        model_version_id=100,
        status="completed",
        file_params={"id": 1001},
    )
    await svc.add_to_history(
        download_id="dl-h2",
        model_id=1,
        model_version_id=100,
        status="completed",
        file_params={"id": 1002},
    )
    # A failed entry for file 1002 must not remove file 1001's completed row
    await svc.add_to_history(
        download_id="dl-h3",
        model_id=1,
        model_version_id=100,
        status="failed",
        file_params={"id": 1002},
    )

    result = await svc.deduplicate()

    assert result["removed_history"] == 1  # only dl-h3 collapses (same file)
    history = await svc.get_history()
    remaining = {item["download_id"] for item in history["items"]}
    assert remaining == {"dl-h1", "dl-h2"}


@pytest.mark.asyncio
async def test_dedup_history_collapses_same_file_and_legacy_rows(tmp_path: Path) -> None:
    """Same file id / absent file id history rows still dedup as before."""
    svc = _make_service(tmp_path)
    # Same file id + same status -> keep the most recent row
    await svc.add_to_history(
        download_id="dl-x1",
        model_id=1,
        model_version_id=100,
        status="completed",
        file_params={"id": 1001},
    )
    await svc.add_to_history(
        download_id="dl-x2",
        model_id=1,
        model_version_id=100,
        status="completed",
        file_params={"id": 1001},
    )
    # Legacy rows without file identity: cross-status dedup still applies
    await svc.add_to_history(
        download_id="dl-y1", model_id=2, model_version_id=200, status="failed"
    )
    await svc.add_to_history(
        download_id="dl-y2", model_id=2, model_version_id=200, status="completed"
    )

    result = await svc.deduplicate()

    assert result["removed_history"] == 2
    history = await svc.get_history()
    remaining = {item["download_id"] for item in history["items"]}
    assert remaining == {"dl-x2", "dl-y2"}
