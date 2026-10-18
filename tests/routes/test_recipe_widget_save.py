"""Handler tests for the widget "Save Recipe" endpoint.

Covers the opt-in workflow body: the endpoint historically received no body at
all, so a missing, empty or malformed body must degrade to "no workflow"
rather than failing the save.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest

from py.routes.handlers.recipe_handlers import RecipeManagementHandler


async def _noop_ensure() -> None:
    return None


class FakeRequest:
    """Minimal request double exposing the optional-body contract."""

    def __init__(
        self,
        *,
        body: Any = None,
        can_read_body: bool = True,
        json_raises: bool = False,
    ) -> None:
        self._body = body
        self.can_read_body = can_read_body
        self._json_raises = json_raises

    async def json(self) -> Any:
        if self._json_raises or self._body is None:
            raise ValueError("no JSON body")
        return self._body


class CapturingPersistence:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def save_recipe_from_widget(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            payload={"success": True, "has_workflow": bool(kwargs.get("workflow"))},
            status=200,
        )


def _make_handler(persistence: CapturingPersistence) -> RecipeManagementHandler:
    analysis_service = SimpleNamespace(
        analyze_widget_metadata=lambda **kwargs: _analysis_result()
    )

    return RecipeManagementHandler(
        ensure_dependencies_ready=_noop_ensure,
        recipe_scanner_getter=lambda: object(),
        logger=logging.getLogger(__name__),
        persistence_service=persistence,  # pyright: ignore[reportArgumentType]
        analysis_service=analysis_service,  # pyright: ignore[reportArgumentType]
        downloader_factory=lambda: None,
        civitai_client_getter=lambda: None,
    )


async def _analysis_result() -> SimpleNamespace:
    return SimpleNamespace(
        payload={"metadata": {"loras": ""}, "image_bytes": b"image"}
    )


@pytest.mark.asyncio
async def test_widget_save_forwards_workflow_from_json_body():
    persistence = CapturingPersistence()
    handler = _make_handler(persistence)
    workflow = {"nodes": [{"id": 1}]}

    response = await handler.save_recipe_from_widget(
        FakeRequest(body={"workflow": workflow})  # type: ignore[arg-type]
    )

    assert response.status == 200
    assert persistence.calls[0]["workflow"] == workflow


@pytest.mark.asyncio
async def test_widget_save_without_body_passes_no_workflow():
    persistence = CapturingPersistence()
    handler = _make_handler(persistence)

    response = await handler.save_recipe_from_widget(
        FakeRequest(can_read_body=False)  # type: ignore[arg-type]
    )

    assert response.status == 200
    assert persistence.calls[0]["workflow"] is None


@pytest.mark.asyncio
async def test_widget_save_tolerates_malformed_body():
    persistence = CapturingPersistence()
    handler = _make_handler(persistence)

    await handler.save_recipe_from_widget(
        FakeRequest(json_raises=True)  # type: ignore[arg-type]
    )
    await handler.save_recipe_from_widget(
        FakeRequest(body=["not", "an", "object"])  # type: ignore[arg-type]
    )

    assert [call["workflow"] for call in persistence.calls] == [None, None]


@pytest.mark.asyncio
async def test_widget_save_reports_embedded_workflow_in_response():
    persistence = CapturingPersistence()
    handler = _make_handler(persistence)

    response = await handler.save_recipe_from_widget(
        FakeRequest(body={"workflow": {"nodes": []}})  # type: ignore[arg-type]
    )

    assert json.loads(response.text)["has_workflow"] is True
