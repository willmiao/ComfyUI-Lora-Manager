import json
import logging

import pytest

from py.routes.handlers.model_handlers import ModelMoveHandler


class FakeMoveService:
    def __init__(self, result):
        self._result = result
        self.received_path = None

    async def create_folder(self, folder_path):
        self.received_path = folder_path
        return self._result


class FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def _make_handler(result):
    service = FakeMoveService(result)
    handler = ModelMoveHandler(
        move_service=service, logger=logging.getLogger(__name__)
    )
    return handler, service


@pytest.mark.asyncio
async def test_create_folder_success():
    handler, service = _make_handler(
        {"success": True, "folder": "characters/anime", "created": True}
    )

    response = await handler.create_folder(
        FakeRequest({"folder_path": "/library/characters/anime"})
    )

    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["success"] is True
    assert payload["folder"] == "characters/anime"
    assert service.received_path == "/library/characters/anime"


@pytest.mark.asyncio
async def test_create_folder_missing_path():
    handler, service = _make_handler({"success": True})

    response = await handler.create_folder(FakeRequest({}))

    assert response.status == 400
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert service.received_path is None


@pytest.mark.asyncio
async def test_create_folder_service_failure_maps_to_400():
    handler, _service = _make_handler(
        {
            "success": False,
            "error": "Folder path '/etc/evil' is outside configured library directories",
        }
    )

    response = await handler.create_folder(FakeRequest({"folder_path": "/etc/evil"}))

    assert response.status == 400
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert "outside configured library" in payload["error"]


@pytest.mark.asyncio
async def test_create_folder_invalid_json_body():
    class BadJsonRequest:
        async def json(self):
            raise ValueError("bad json")

    handler, _service = _make_handler({"success": True})

    response = await handler.create_folder(BadJsonRequest())

    assert response.status == 400
    payload = json.loads(response.text)
    assert payload["success"] is False
