"""Route-layer tests for the first-run endpoints and init-status gating."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from py.routes.handlers.misc_handlers import FirstRunHandler, HealthCheckHandler
from py.routes.misc_route_registrar import MISC_ROUTE_DEFINITIONS


class FakeRequest:
    def __init__(self, *, json_data=None, query=None, method="POST"):
        self._json_data = json_data or {}
        self.query = query or {}
        self.method = method

    async def json(self):
        return self._json_data


def _json_payload(response) -> dict[str, Any]:
    text = response.text
    assert text is not None
    return json.loads(text)


def _make_manager(*, awaiting: bool = True, info=None) -> SimpleNamespace:
    return SimpleNamespace(
        is_awaiting_first_scan=lambda: awaiting,
        collect_first_run_info=AsyncMock(return_value=info or {}),
        start_initial_scan=AsyncMock(return_value={"status": "scanning"}),
    )


async def test_first_run_info_reports_awaiting_status():
    manager = _make_manager(
        info={"loras": {"roots": [], "file_count": 0, "total_bytes": 0}}
    )
    handler = FirstRunHandler(first_run_manager=manager)

    response = await handler.get_first_run_info(FakeRequest(method="GET"))  # pyright: ignore[reportArgumentType]
    payload = _json_payload(response)

    assert response.status == 200
    assert payload["status"] == "awaiting_first_scan"
    assert payload["loras"]["file_count"] == 0
    manager.collect_first_run_info.assert_awaited_once()


async def test_first_run_info_reports_completed_when_gate_closed():
    manager = _make_manager(awaiting=False)
    handler = FirstRunHandler(first_run_manager=manager)

    response = await handler.get_first_run_info(FakeRequest(method="GET"))  # pyright: ignore[reportArgumentType]
    payload = _json_payload(response)

    assert payload == {"status": "completed"}
    manager.collect_first_run_info.assert_not_awaited()


async def test_start_first_scan_post_happy_path():
    manager = _make_manager()
    handler = FirstRunHandler(first_run_manager=manager)

    response = await handler.start_first_scan(
        FakeRequest(
            json_data={
                "sidecar_storage_mode": "alongside",
                "defer": True,
            }
        )  # pyright: ignore[reportArgumentType]
    )
    payload = _json_payload(response)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["status"] == "scanning"
    manager.start_initial_scan.assert_awaited_once_with(
        sidecar_storage_mode="alongside",
        sidecar_storage_path=None,
        defer=True,
    )


async def test_start_first_scan_get_query_params():
    manager = _make_manager()
    handler = FirstRunHandler(first_run_manager=manager)

    response = await handler.start_first_scan(
        FakeRequest(
            method="GET",
            query={
                "sidecar_storage_mode": "centralized",
                "sidecar_storage_path": "/tmp/sidecars",
                "defer": "true",
            },
        )  # pyright: ignore[reportArgumentType]
    )
    payload = _json_payload(response)

    assert response.status == 200
    assert payload["success"] is True
    manager.start_initial_scan.assert_awaited_once_with(
        sidecar_storage_mode="centralized",
        sidecar_storage_path="/tmp/sidecars",
        defer=True,
    )


async def test_start_first_scan_returns_400_on_invalid_params():
    manager = _make_manager()
    manager.start_initial_scan = AsyncMock(
        side_effect=ValueError("sidecar_storage_path is required")
    )
    handler = FirstRunHandler(first_run_manager=manager)

    response = await handler.start_first_scan(
        FakeRequest(json_data={"sidecar_storage_mode": "centralized"})  # pyright: ignore[reportArgumentType]
    )
    payload = _json_payload(response)

    assert response.status == 400
    assert payload["success"] is False
    assert "sidecar_storage_path" in payload["error"]


async def test_init_status_reports_awaiting_first_scan():
    async def ready_scanner():
        return SimpleNamespace(_cache=object(), is_initializing=lambda: False)

    handler = HealthCheckHandler(
        scanner_getters={"lora": ready_scanner},
        first_run_manager=SimpleNamespace(
            is_awaiting_first_scan=lambda: True
        ),
    )

    response = await handler.get_init_status(FakeRequest(method="GET"))  # pyright: ignore[reportArgumentType]
    payload = _json_payload(response)

    assert payload["status"] == "awaiting_first_scan"


async def test_init_status_unaffected_when_gate_completed():
    async def ready_scanner():
        return SimpleNamespace(_cache=object(), is_initializing=lambda: False)

    handler = HealthCheckHandler(
        scanner_getters={"lora": ready_scanner},
        first_run_manager=SimpleNamespace(
            is_awaiting_first_scan=lambda: False
        ),
    )

    response = await handler.get_init_status(FakeRequest(method="GET"))  # pyright: ignore[reportArgumentType]
    payload = _json_payload(response)

    assert payload["status"] == "complete"


def test_first_run_route_definitions_registered():
    routes = {(d.method, d.path) for d in MISC_ROUTE_DEFINITIONS}

    assert ("GET", "/api/lm/first-run-info") in routes
    assert ("POST", "/api/lm/first-scan/start") in routes
    assert ("GET", "/api/lm/first-scan/start") in routes
