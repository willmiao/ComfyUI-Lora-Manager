import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from py.routes.lora_routes import LoraRoutes
from server import PromptServer


class DummyRequest:
    def __init__(self, *, query=None, match_info=None, json_data=None):
        self.query = query or {}
        self.match_info = match_info or {}
        self._json_data = json_data or {}

    async def json(self):
        return self._json_data


class StubLoraService:
    def __init__(self):
        self.notes = {}
        self.trigger_words = {}
        self.usage_tips = {}
        self.previews = {}
        self.civitai = {}

    async def get_lora_notes(self, name):
        return self.notes.get(name)

    async def get_lora_trigger_words(self, name):
        return self.trigger_words.get(name, [])

    async def get_lora_usage_tips_by_relative_path(self, path):
        return self.usage_tips.get(path)

    async def get_lora_preview_url(self, name):
        return self.previews.get(name)

    async def get_lora_civitai_url(self, name):
        return self.civitai.get(name, {"civitai_url": ""})


@pytest.fixture
def routes():
    handler = LoraRoutes()
    handler.service = StubLoraService()
    return handler


async def test_get_lora_notes_success(routes):
    routes.service.notes["demo"] = "Great notes"
    request = DummyRequest(query={"name": "demo"})

    response = await routes.get_lora_notes(request)
    payload = json.loads(response.text)

    assert payload == {"success": True, "notes": "Great notes"}


async def test_get_lora_notes_missing_name(routes):
    response = await routes.get_lora_notes(DummyRequest())
    assert response.status == 400
    assert response.text == "Lora file name is required"


async def test_get_lora_notes_not_found(routes):
    response = await routes.get_lora_notes(DummyRequest(query={"name": "missing"}))
    payload = json.loads(response.text)
    assert response.status == 404
    assert payload == {"success": False, "error": "LoRA not found in cache"}


async def test_get_lora_notes_error(routes, monkeypatch):
    async def failing(*_args, **_kwargs):
        raise RuntimeError("boom")

    routes.service.get_lora_notes = failing

    response = await routes.get_lora_notes(DummyRequest(query={"name": "demo"}))
    payload = json.loads(response.text)

    assert response.status == 500
    assert payload["success"] is False
    assert payload["error"] == "boom"


async def test_get_lora_trigger_words_success(routes):
    routes.service.trigger_words["demo"] = ["trigger"]
    response = await routes.get_lora_trigger_words(DummyRequest(query={"name": "demo"}))
    payload = json.loads(response.text)
    assert payload == {"success": True, "trigger_words": ["trigger"]}


async def test_get_lora_trigger_words_missing_name(routes):
    response = await routes.get_lora_trigger_words(DummyRequest())
    assert response.status == 400


async def test_get_lora_trigger_words_error(routes):
    async def failing(*_args, **_kwargs):
        raise RuntimeError("fail")

    routes.service.get_lora_trigger_words = failing

    response = await routes.get_lora_trigger_words(DummyRequest(query={"name": "demo"}))
    payload = json.loads(response.text)
    assert response.status == 500
    assert payload["success"] is False


async def test_get_usage_tips_success(routes):
    routes.service.usage_tips["path"] = "tips"
    response = await routes.get_lora_usage_tips_by_path(DummyRequest(query={"relative_path": "path"}))
    payload = json.loads(response.text)
    assert payload == {"success": True, "usage_tips": "tips"}


async def test_get_usage_tips_missing_param(routes):
    response = await routes.get_lora_usage_tips_by_path(DummyRequest())
    assert response.status == 400


async def test_get_usage_tips_error(routes):
    async def failing(*_args, **_kwargs):
        raise RuntimeError("bad")

    routes.service.get_lora_usage_tips_by_relative_path = failing
    response = await routes.get_lora_usage_tips_by_path(DummyRequest(query={"relative_path": "path"}))
    payload = json.loads(response.text)
    assert response.status == 500
    assert payload["success"] is False


async def test_get_preview_url_success(routes):
    routes.service.previews["demo"] = "http://preview"
    response = await routes.get_lora_preview_url(DummyRequest(query={"name": "demo"}))
    payload = json.loads(response.text)
    assert payload == {"success": True, "preview_url": "http://preview"}


async def test_get_preview_url_missing(routes):
    response = await routes.get_lora_preview_url(DummyRequest())
    assert response.status == 400


async def test_get_preview_url_not_found(routes):
    response = await routes.get_lora_preview_url(DummyRequest(query={"name": "missing"}))
    payload = json.loads(response.text)
    assert response.status == 404
    assert payload["success"] is False


async def test_get_civitai_url_success(routes):
    routes.service.civitai["demo"] = {"civitai_url": "https://civitai.com"}
    response = await routes.get_lora_civitai_url(DummyRequest(query={"name": "demo"}))
    payload = json.loads(response.text)
    assert payload == {"success": True, "civitai_url": "https://civitai.com"}


async def test_get_civitai_url_missing(routes):
    response = await routes.get_lora_civitai_url(DummyRequest())
    assert response.status == 400


async def test_get_civitai_url_not_found(routes):
    response = await routes.get_lora_civitai_url(DummyRequest(query={"name": "missing"}))
    payload = json.loads(response.text)
    assert response.status == 404
    assert payload["success"] is False


async def test_get_civitai_url_error(routes):
    async def failing(*_args, **_kwargs):
        raise RuntimeError("oops")

    routes.service.get_lora_civitai_url = failing
    response = await routes.get_lora_civitai_url(DummyRequest(query={"name": "demo"}))
    payload = json.loads(response.text)
    assert response.status == 500
    assert payload["success"] is False


async def test_get_trigger_words_broadcasts(monkeypatch, routes):
    send_mock = MagicMock()
    PromptServer.instance = SimpleNamespace(send_sync=send_mock)

    monkeypatch.setattr("py.routes.lora_routes.get_lora_info", lambda name: (f"path/{name}", [f"trigger-{name}"]))

    request = DummyRequest(json_data={"lora_names": ["one"], "node_ids": [{"node_id": "node", "graph_id": "graph-1"}]})

    response = await routes.get_trigger_words(request)
    payload = json.loads(response.text)

    assert payload == {"success": True}
    send_mock.assert_called_once_with(
        "trigger_word_update",
        {"id": "node", "graph_id": "graph-1", "message": "trigger-one"},
    )


async def test_get_trigger_words_error(monkeypatch, routes):
    async def failing_json():
        raise RuntimeError("bad json")

    request = DummyRequest(json_data=None)
    request.json = failing_json

    response = await routes.get_trigger_words(request)
    payload = json.loads(response.text)
    assert response.status == 500
    assert payload["success"] is False
