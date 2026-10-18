"""Handler tests for the recipe workflow send endpoint.

Covers ``RecipeWorkflowHandler.send_recipe_workflow`` and the wiring of the
``send_recipe_workflow`` key in ``RecipeHandlerSet.to_route_mapping``.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from py.routes.handlers.recipe_handlers import (
    RecipeHandlerSet,
    RecipeWorkflowHandler,
)
from py.routes.handlers import recipe_handlers


async def _noop_ensure() -> None:
    return None


@pytest.fixture(autouse=True)
def _clear_standalone_env(monkeypatch: pytest.MonkeyPatch):
    """Clear the standalone env flag leaked by other modules.

    ``standalone.py`` sets ``LORA_MANAGER_STANDALONE=1`` at import time, and
    unrelated tests import that module; without cleanup the flag bleeds into
    later tests and flips the handler's standalone branch.
    """
    monkeypatch.delenv("LORA_MANAGER_STANDALONE", raising=False)


class FakeRequest:
    """Minimal request double exposing ``match_info``."""

    def __init__(self, *, match_info: dict[str, Any] | None = None) -> None:
        self.match_info = match_info or {}


class StubRecipeScanner:
    """Scanner double returning a configurable recipe for an id."""

    def __init__(self, recipe: dict[str, Any] | None = None) -> None:
        self.recipe = recipe
        self.lookup_calls: list[str] = []

    async def get_recipe_by_id(self, recipe_id: str) -> dict[str, Any] | None:
        self.lookup_calls.append(recipe_id)
        return self.recipe


def _json_payload(response) -> dict[str, Any]:
    """Decode the JSON body of a web.Response, asserting it is not null."""
    text = response.text
    assert text is not None
    return json.loads(text)


def _make_prompt_server(send_calls: list[tuple[str, Any]], *, send_error: Exception | None = None):
    """Return a PromptServer-like class whose instance records send_sync calls."""

    class RecordingPromptServer:
        class Instance:
            def send_sync(self, event, payload, sid=None):
                if send_error is not None:
                    raise send_error
                send_calls.append((event, payload))

        instance = Instance()

    return RecordingPromptServer


def _make_handler(
    scanner: StubRecipeScanner,
    prompt_server,
    *,
    ensure=_noop_ensure,
) -> RecipeWorkflowHandler:
    return RecipeWorkflowHandler(
        ensure_dependencies_ready=ensure,
        recipe_scanner_getter=lambda: scanner,
        prompt_server=prompt_server,  # pyright: ignore[reportArgumentType]
        logger=logging.getLogger(__name__),
    )


async def test_send_recipe_workflow_broadcasts_embedded_workflow(monkeypatch: pytest.MonkeyPatch):
    recipe = {
        "file_path": "/models/recipes/sample.png",
        "title": "My Recipe",
    }
    scanner = StubRecipeScanner(recipe=recipe)
    send_calls: list[tuple[str, Any]] = []
    prompt_server = _make_prompt_server(send_calls)

    monkeypatch.setattr(
        recipe_handlers.ExifUtils,
        "_load_structured_metadata",
        lambda _image_path: {"workflow": '{"nodes":[]}'},
    )

    handler = _make_handler(scanner, prompt_server)
    response = await handler.send_recipe_workflow(
        FakeRequest(match_info={"recipe_id": "r1"})  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 200
    payload = _json_payload(response)
    assert payload == {"success": True, "sent": True}
    assert send_calls == [
        (
            "lm_load_workflow",
            {
                "workflow": {"nodes": []},
                "name": "My Recipe",
                "recipe_id": "r1",
            },
        )
    ]
    assert scanner.lookup_calls == ["r1"]


async def test_send_recipe_workflow_defaults_empty_title(monkeypatch: pytest.MonkeyPatch):
    recipe = {"file_path": "/models/recipes/sample.png"}
    scanner = StubRecipeScanner(recipe=recipe)
    send_calls: list[tuple[str, Any]] = []
    prompt_server = _make_prompt_server(send_calls)

    monkeypatch.setattr(
        recipe_handlers.ExifUtils,
        "_load_structured_metadata",
        lambda _image_path: {"workflow": "{}"},
    )

    handler = _make_handler(scanner, prompt_server)
    response = await handler.send_recipe_workflow(
        FakeRequest(match_info={"recipe_id": "r2"})  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 200
    assert send_calls[0][1]["workflow"] == {}
    assert send_calls[0][1]["name"] == ""
    assert send_calls[0][1]["recipe_id"] == "r2"


async def test_send_recipe_workflow_recipe_not_found():
    scanner = StubRecipeScanner(recipe=None)
    prompt_server = _make_prompt_server([])

    handler = _make_handler(scanner, prompt_server)
    response = await handler.send_recipe_workflow(
        FakeRequest(match_info={"recipe_id": "missing"})  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 404
    assert _json_payload(response) == {"error": "Recipe not found"}


async def test_send_recipe_workflow_missing_file_path():
    scanner = StubRecipeScanner(recipe={"title": "No File"})
    prompt_server = _make_prompt_server([])

    handler = _make_handler(scanner, prompt_server)
    response = await handler.send_recipe_workflow(
        FakeRequest(match_info={"recipe_id": "r1"})  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 404
    assert _json_payload(response) == {"error": "no_workflow"}


async def test_send_recipe_workflow_no_embedded_workflow(monkeypatch: pytest.MonkeyPatch):
    recipe = {"file_path": "/models/recipes/sample.png", "title": "No Wf"}
    scanner = StubRecipeScanner(recipe=recipe)
    prompt_server = _make_prompt_server([])

    monkeypatch.setattr(
        recipe_handlers.ExifUtils,
        "_load_structured_metadata",
        lambda _image_path: {"parameters": "some params"},
    )

    handler = _make_handler(scanner, prompt_server)
    response = await handler.send_recipe_workflow(
        FakeRequest(match_info={"recipe_id": "r1"})  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 404
    assert _json_payload(response) == {
        "error": "no_workflow",
        "message": "No embedded workflow found in recipe image",
    }


async def test_send_recipe_workflow_invalid_json_payload(monkeypatch: pytest.MonkeyPatch):
    recipe = {"file_path": "/models/recipes/sample.png", "title": "Bad Wf"}
    scanner = StubRecipeScanner(recipe=recipe)
    prompt_server = _make_prompt_server([])

    monkeypatch.setattr(
        recipe_handlers.ExifUtils,
        "_load_structured_metadata",
        lambda _image_path: {"workflow": "not-json{"},
    )

    handler = _make_handler(scanner, prompt_server)
    response = await handler.send_recipe_workflow(
        FakeRequest(match_info={"recipe_id": "r1"})  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 404
    assert _json_payload(response)["error"] == "no_workflow"


async def test_send_recipe_workflow_standalone_mode(monkeypatch: pytest.MonkeyPatch):
    recipe = {"file_path": "/models/recipes/sample.png", "title": "Recipe"}
    scanner = StubRecipeScanner(recipe=recipe)
    prompt_server = _make_prompt_server([])

    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")

    handler = _make_handler(scanner, prompt_server)
    response = await handler.send_recipe_workflow(
        FakeRequest(match_info={"recipe_id": "r1"})  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 400
    assert _json_payload(response) == {"error": "Standalone Mode Active"}


async def test_send_recipe_workflow_send_sync_error(monkeypatch: pytest.MonkeyPatch):
    recipe = {"file_path": "/models/recipes/sample.png", "title": "Recipe"}
    scanner = StubRecipeScanner(recipe=recipe)
    prompt_server = _make_prompt_server([], send_error=RuntimeError("boom"))

    monkeypatch.setattr(
        recipe_handlers.ExifUtils,
        "_load_structured_metadata",
        lambda _image_path: {"workflow": "{}"},
    )

    handler = _make_handler(scanner, prompt_server)
    response = await handler.send_recipe_workflow(
        FakeRequest(match_info={"recipe_id": "r1"})  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 500
    assert _json_payload(response) == {"error": "boom"}


async def test_send_recipe_workflow_scanner_unavailable():
    handler = RecipeWorkflowHandler(
        ensure_dependencies_ready=_noop_ensure,
        recipe_scanner_getter=lambda: None,
        prompt_server=_make_prompt_server([]),  # pyright: ignore[reportArgumentType]
        logger=logging.getLogger(__name__),
    )
    response = await handler.send_recipe_workflow(
        FakeRequest(match_info={"recipe_id": "r1"})  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 500
    assert _json_payload(response) == {"error": "Recipe scanner unavailable"}


def test_route_mapping_includes_send_recipe_workflow():
    workflow = RecipeWorkflowHandler(
        ensure_dependencies_ready=_noop_ensure,
        recipe_scanner_getter=lambda: None,
        prompt_server=_make_prompt_server([]),  # pyright: ignore[reportArgumentType]
        logger=logging.getLogger(__name__),
    )
    handler_set = RecipeHandlerSet(
        page_view=MagicMock(),
        listing=MagicMock(),
        query=MagicMock(),
        management=MagicMock(),
        analysis=MagicMock(),
        sharing=MagicMock(),
        batch_import=MagicMock(),
        workflow=workflow,
    )

    mapping = handler_set.to_route_mapping()

    assert "send_recipe_workflow" in mapping
    assert mapping["send_recipe_workflow"] == workflow.send_recipe_workflow
