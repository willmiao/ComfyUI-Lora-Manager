import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from py.routes.lora_routes import LoraRoutes, _build_lora_folder_index
from server import PromptServer  # pyright: ignore[reportMissingImports]


class DummyRequest:
    def __init__(self, *, query=None, match_info=None, json_data=None):
        self.query = query or {}
        self.match_info = match_info or {}
        self._json_data = json_data or {}

    async def json(self):
        return self._json_data


class StubLoraService:
    def __init__(self):
        self.trigger_words = {}
        self.usage_tips = {}
        self.details = {}
        self.full_metadata = {}
        self.model_descriptions = {}

    async def get_model_info_by_name(self, name):
        return self.details.get(name)

    async def get_model_metadata(self, file_path):
        return self.full_metadata.get(file_path)

    async def get_model_description(self, file_path):
        return self.model_descriptions.get(file_path)

    async def get_lora_trigger_words(self, name):
        return self.trigger_words.get(name, [])

    async def get_lora_usage_tips_by_relative_path(self, path):
        return self.usage_tips.get(path)


@pytest.fixture
def routes():
    handler = LoraRoutes()
    handler.service = StubLoraService()  # pyright: ignore[reportAttributeAccessIssue]
    return handler


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


async def test_get_lora_details_uses_cached_metadata(routes):
    routes.service.details["folder/demo"] = {
        "model_name": "Demo",
        "base_model": "Flux",
        "preview_url": "",
    }
    response = await routes.get_lora_details(DummyRequest(query={"name": "folder/demo"}))
    payload = json.loads(response.text)
    assert payload["success"] is True
    assert payload["metadata"]["model_name"] == "Demo"
    assert payload["metadata"]["base_model"] == "Flux"


async def test_get_lora_details_requires_name(routes):
    response = await routes.get_lora_details(DummyRequest())
    assert response.status == 400


async def test_get_lora_details_not_found(routes):
    response = await routes.get_lora_details(DummyRequest(query={"name": "missing"}))
    payload = json.loads(response.text)
    assert response.status == 404
    assert payload["success"] is False


def test_build_lora_folder_index_counts_nested_items():
    root = _build_lora_folder_index([
        {"file_name": "root.safetensors", "folder": "", "model_name": "Root"},
        {"file_name": "one.safetensors", "folder": "characters/portraits", "model_name": "One"},
        {"file_name": "two.safetensors", "folder": "characters", "model_name": "Two"},
        {"file_name": "excluded.safetensors", "folder": "characters", "exclude": True},
    ])

    assert root["count"] == 3
    assert root["folders"]["characters"]["count"] == 2
    assert root["folders"]["characters"]["folders"]["portraits"]["count"] == 1
    assert root["folders"]["characters"]["items"][0]["relative_path"] == "characters/two.safetensors"
    assert root["items"][0]["relative_path"] == "root.safetensors"


async def test_get_lora_details_merges_full_sidecar_descriptions(routes):
    file_path = "/models/demo.safetensors"
    routes.service.details["demo"] = {
        "file_path": file_path,
        "model_name": "Demo",
        "preview_url": "",
    }
    routes.service.full_metadata[file_path] = {
        "description": "Version description",
        "model": {"description": "Model description"},
    }
    routes.service.model_descriptions[file_path] = "Model description"

    response = await routes.get_lora_details(DummyRequest(query={"name": "demo"}))
    payload = json.loads(response.text)

    assert payload["metadata"]["description"] == "Version description"
    assert payload["metadata"]["modelDescription"] == "Model description"
    assert payload["metadata"]["civitai"]["model"]["description"] == "Model description"
