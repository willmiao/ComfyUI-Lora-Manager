"""Handler-level tests for download queue terminal/status transitions.

Regression test: a "not found in queue" outcome must be returned as HTTP 200
with ``success: false``, not 404. The browser extension's apiFetch treats any
404 as a missing endpoint and retries a legacy URL, producing spurious
``/api/downloads/queue/complete ... 404`` warnings on every completion.
"""

import json
import logging
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from py.routes.handlers.model_handlers import ModelDownloadHandler
from py.services.download_queue_service import DownloadQueueService


def _make_handler() -> ModelDownloadHandler:
    return ModelDownloadHandler(
        ws_manager=None,  # pyright: ignore[reportArgumentType] - unused by queue endpoints
        logger=logging.getLogger("test-download-queue"),
        download_use_case=None,  # pyright: ignore[reportArgumentType] - unused by queue endpoints
        download_coordinator=None,  # pyright: ignore[reportArgumentType] - unused by queue endpoints
    )


def _queue_request(path: str, query: dict[str, str]) -> web.Request:
    query_string = "&".join(f"{key}={value}" for key, value in query.items())
    return make_mocked_request("GET", f"{path}?{query_string}")


@pytest.fixture
def queue_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> DownloadQueueService:
    """Return a tmp-backed DownloadQueueService and stub the singleton."""
    service = DownloadQueueService(db_path=str(tmp_path / "queue.sqlite"))

    async def fake_get_instance(_cls: object = None) -> DownloadQueueService:
        return service

    monkeypatch.setattr(DownloadQueueService, "get_instance", fake_get_instance)
    return service


@pytest.mark.asyncio
async def test_complete_missing_download_returns_200_not_404(
    queue_service: DownloadQueueService,
) -> None:
    """Completing a download that is not queued is a business outcome."""
    handler = _make_handler()
    response = await handler.complete_download_in_queue(
        _queue_request(
            "/api/lm/downloads/queue/complete",
            {"download_id": "dl-nope", "status": "completed"},
        )
    )
    assert response.status == 200
    text = response.text
    assert text is not None
    assert json.loads(text) == {
        "success": False,
        "error": "Download not found in queue",
    }
    # The failed completion must not have side effects on the queue.
    assert await queue_service.get_queue() == []


@pytest.mark.asyncio
async def test_complete_queued_download_returns_success(
    queue_service: DownloadQueueService,
) -> None:
    """The happy path still moves the item to history with HTTP 200."""
    await queue_service.add_to_queue(download_id="dl-1", model_id=1)
    handler = _make_handler()
    response = await handler.complete_download_in_queue(
        _queue_request(
            "/api/lm/downloads/queue/complete",
            {"download_id": "dl-1", "status": "completed"},
        )
    )
    assert response.status == 200
    text = response.text
    assert text is not None
    payload = json.loads(text)
    assert payload["success"] is True
    # The returned item reflects the pre-transition queue record; the
    # terminal status lands in history.
    history = await queue_service.get_history()
    assert len(history["items"]) == 1
    assert history["items"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_status_missing_download_returns_200_not_404(
    queue_service: DownloadQueueService,
) -> None:
    """Status updates for unknown items also return 200 with success: false."""
    handler = _make_handler()
    response = await handler.update_download_queue_status(
        _queue_request(
            "/api/lm/downloads/queue/status",
            {"download_id": "dl-nope", "status": "downloading"},
        )
    )
    assert response.status == 200
    text = response.text
    assert text is not None
    assert json.loads(text) == {
        "success": False,
        "error": "Download not found in queue",
    }
    assert await queue_service.get_queue() == []


@pytest.mark.asyncio
async def test_status_queued_download_returns_success(
    queue_service: DownloadQueueService,
) -> None:
    """The happy path still updates the queue item with HTTP 200."""
    await queue_service.add_to_queue(download_id="dl-2", model_id=2)
    handler = _make_handler()
    response = await handler.update_download_queue_status(
        _queue_request(
            "/api/lm/downloads/queue/status",
            {"download_id": "dl-2", "status": "downloading"},
        )
    )
    assert response.status == 200
    text = response.text
    assert text is not None
    assert json.loads(text) == {"success": True}


@pytest.mark.asyncio
async def test_retry_missing_history_returns_200_not_404(
    queue_service: DownloadQueueService,
) -> None:
    """Retrying a history entry that no longer exists is a business outcome."""
    handler = _make_handler()
    response = await handler.retry_download_from_history(
        _queue_request(
            "/api/lm/downloads/history/retry",
            {"download_id": "dl-nope"},
        )
    )
    assert response.status == 200
    text = response.text
    assert text is not None
    assert json.loads(text) == {
        "success": False,
        "error": "History item not found or not retryable",
    }
    # No side effects: history and queue stay empty.
    history = await queue_service.get_history()
    assert history["items"] == []
    assert await queue_service.get_queue() == []


@pytest.mark.asyncio
async def test_retry_failed_history_returns_success(
    queue_service: DownloadQueueService,
) -> None:
    """The happy path still re-queues a retryable history entry with HTTP 200."""
    await queue_service.add_to_history(
        download_id="dl-fail", model_id=1, status="failed"
    )
    handler = _make_handler()
    response = await handler.retry_download_from_history(
        _queue_request(
            "/api/lm/downloads/history/retry",
            {"download_id": "dl-fail"},
        )
    )
    assert response.status == 200
    text = response.text
    assert text is not None
    payload = json.loads(text)
    assert payload["success"] is True
    # The retried item is re-queued under a fresh download_id.
    queue = await queue_service.get_queue()
    assert len(queue) == 1
    assert queue[0]["status"] == "queued"
