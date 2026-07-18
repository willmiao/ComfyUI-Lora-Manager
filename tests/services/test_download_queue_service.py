"""Unit tests for DownloadQueueService history operations.

Covers the new ``download_id``-based code paths in
``delete_history_item`` and ``retry_from_history``, plus backward
compatibility with ``id``.
"""

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
