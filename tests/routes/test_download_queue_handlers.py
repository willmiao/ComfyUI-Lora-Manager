"""Handler-level tests for download queue terminal/status transitions.

Regression test: a "not found in queue" outcome must be returned as HTTP 200
with ``success: false``, not 404. The browser extension's apiFetch treats any
404 as a missing endpoint and retries a legacy URL, producing spurious
``/api/downloads/queue/complete ... 404`` warnings on every completion.
"""

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from py.routes.handlers.model_handlers import ModelDownloadHandler
from py.services.download_queue_service import DownloadQueueService
from py.services.use_cases import DownloadModelValidationError


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


# ----------------------------------------------------------------------
# Structured 429 rate-limit responses (download queue contract)
# ----------------------------------------------------------------------

_RATE_LIMITED_RESULT = {
    "success": False,
    "reason": "rate_limited",
    "retry_after": 120,
    "error": "Download rate limited (429), retry after 120s",
    "download_id": "dl-1",
}


def _make_download_handler(result: dict) -> ModelDownloadHandler:
    return ModelDownloadHandler(
        ws_manager=None,  # pyright: ignore[reportArgumentType] - unused by download endpoints
        logger=logging.getLogger("test-download-rate-limit"),
        download_use_case=SimpleNamespace(execute=AsyncMock(return_value=result)),  # pyright: ignore[reportArgumentType]
        download_coordinator=None,  # pyright: ignore[reportArgumentType] - unused by download endpoints
    )


@pytest.mark.asyncio
async def test_download_model_post_returns_429_when_rate_limited() -> None:
    """POST /download-model maps reason="rate_limited" to HTTP 429."""
    handler = _make_download_handler(dict(_RATE_LIMITED_RESULT))
    request = SimpleNamespace(json=AsyncMock(return_value={"model_id": 1}))

    response = await handler.download_model(request)

    assert response.status == 429
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert payload["reason"] == "rate_limited"
    assert payload["retry_after"] == 120
    assert payload["error"]


@pytest.mark.asyncio
async def test_download_model_post_keeps_500_for_other_failures() -> None:
    handler = _make_download_handler({"success": False, "error": "boom"})
    request = SimpleNamespace(json=AsyncMock(return_value={"model_id": 1}))

    response = await handler.download_model(request)

    assert response.status == 500
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert "reason" not in payload


@pytest.mark.asyncio
async def test_download_model_get_returns_429_when_rate_limited() -> None:
    """GET /download-model-get (extension queue driver) gets the same 429."""
    handler = _make_download_handler(dict(_RATE_LIMITED_RESULT))
    request = _queue_request("/api/lm/download-model-get", {"model_id": "1"})

    response = await handler.download_model_get(request)

    assert response.status == 429
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert payload["reason"] == "rate_limited"
    assert payload["retry_after"] == 120
    assert payload["error"]


@pytest.mark.asyncio
async def test_download_model_get_keeps_500_for_other_failures() -> None:
    handler = _make_download_handler({"success": False, "error": "boom"})
    request = _queue_request("/api/lm/download-model-get", {"model_id": "1"})

    response = await handler.download_model_get(request)

    assert response.status == 500
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert "reason" not in payload


# ----------------------------------------------------------------------
# retry with start=true: backend executor for clients that do not run the
# companion browser extension (#1196)
# ----------------------------------------------------------------------


def _make_retry_start_handler(result: dict) -> tuple[ModelDownloadHandler, AsyncMock]:
    execute = AsyncMock(return_value=result)
    handler = ModelDownloadHandler(
        ws_manager=None,  # pyright: ignore[reportArgumentType] - unused here
        logger=logging.getLogger("test-retry-start"),
        download_use_case=SimpleNamespace(execute=execute),  # pyright: ignore[reportArgumentType]
        download_coordinator=None,  # pyright: ignore[reportArgumentType] - unused here
    )
    return handler, execute


@pytest.mark.asyncio
async def test_retry_with_start_runs_download_server_side(
    queue_service: DownloadQueueService,
) -> None:
    """start=true executes the re-queued item instead of parking it."""
    await queue_service.add_to_history(
        download_id="dl-fail",
        model_id=7,
        model_version_id=70,
        status="failed",
        file_params={"id": 7001, "type": "Model"},
    )
    handler, execute = _make_retry_start_handler(
        {"success": True, "download_id": "ignored-by-handler"}
    )

    response = await handler.retry_download_from_history(
        _queue_request(
            "/api/lm/downloads/history/retry",
            {"download_id": "dl-fail", "start": "true"},
        )
    )

    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["success"] is True
    assert payload["started"] is True
    queued = (await queue_service.get_queue())[0]
    execute.assert_awaited_once()
    sent = execute.await_args.args[0]
    assert sent["model_id"] == 7
    assert sent["model_version_id"] == 70
    assert sent["download_id"] == queued["download_id"]
    assert sent["use_default_paths"] is True
    assert sent["source"] == "retry"
    assert sent["file_params"] == {"id": 7001, "type": "Model"}


@pytest.mark.asyncio
async def test_retry_without_start_keeps_client_side_drain(
    queue_service: DownloadQueueService,
) -> None:
    """The extension's call (no start flag) must not trigger a download."""
    await queue_service.add_to_history(
        download_id="dl-fail", model_id=1, status="failed"
    )
    handler, execute = _make_retry_start_handler({"success": True})

    response = await handler.retry_download_from_history(
        _queue_request(
            "/api/lm/downloads/history/retry", {"download_id": "dl-fail"}
        )
    )

    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["success"] is True
    assert "started" not in payload
    execute.assert_not_awaited()
    assert (await queue_service.get_queue())[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_retry_with_start_maps_rate_limit_to_429(
    queue_service: DownloadQueueService,
) -> None:
    await queue_service.add_to_history(
        download_id="dl-fail", model_id=1, status="failed"
    )
    handler, _execute = _make_retry_start_handler(dict(_RATE_LIMITED_RESULT))

    response = await handler.retry_download_from_history(
        _queue_request(
            "/api/lm/downloads/history/retry",
            {"download_id": "dl-fail", "start": "1"},
        )
    )

    assert response.status == 429
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert payload["reason"] == "rate_limited"
    assert payload["started"] is True


@pytest.mark.asyncio
async def test_retry_with_start_maps_validation_error_to_400(
    queue_service: DownloadQueueService,
) -> None:
    await queue_service.add_to_history(
        download_id="dl-fail", model_id=1, status="failed"
    )
    handler, execute = _make_retry_start_handler({})
    execute.side_effect = DownloadModelValidationError("bad payload")

    response = await handler.retry_download_from_history(
        _queue_request(
            "/api/lm/downloads/history/retry",
            {"download_id": "dl-fail", "start": "true"},
        )
    )

    assert response.status == 400
    assert json.loads(response.text)["success"] is False
