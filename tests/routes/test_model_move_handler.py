import json
import logging

import pytest

from py.routes.handlers.model_handlers import ModelMoveHandler


class FakeMoveService:
    def __init__(self, result):
        self._result = result
        self.received_path = None
        self.received_dry_run = None
        self.received_new_name = None

    async def create_folder(self, folder_path):
        self.received_path = folder_path
        return self._result

    async def delete_folder(self, folder_path, dry_run=False):
        self.received_path = folder_path
        self.received_dry_run = dry_run
        return self._result

    async def rename_folder(self, folder_path, new_name):
        self.received_path = folder_path
        self.received_new_name = new_name
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


@pytest.mark.asyncio
async def test_delete_folder_success():
    handler, service = _make_handler(
        {
            "success": True,
            "folder": "characters/anime",
            "model_count": 0,
            "restorable": True,
        }
    )

    response = await handler.delete_folder(
        FakeRequest({"folder_path": "/library/characters/anime"})
    )

    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["success"] is True
    assert payload["restorable"] is True
    assert service.received_path == "/library/characters/anime"
    assert service.received_dry_run is False


@pytest.mark.asyncio
async def test_delete_folder_forwards_dry_run():
    handler, service = _make_handler({"success": True, "dry_run": True})

    response = await handler.delete_folder(
        FakeRequest({"folder_path": "/library/empty", "dry_run": True})
    )

    assert response.status == 200
    assert service.received_dry_run is True
    assert json.loads(response.text)["dry_run"] is True


@pytest.mark.asyncio
async def test_delete_folder_missing_path():
    handler, service = _make_handler({"success": True})

    response = await handler.delete_folder(FakeRequest({}))

    assert response.status == 400
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert service.received_path is None


@pytest.mark.asyncio
async def test_delete_folder_not_empty_maps_to_409():
    handler, _service = _make_handler(
        {
            "success": False,
            "code": "not_empty",
            "error": "Folder still contains 2 model file(s); delete or move them first",
            "manifest": {"model_count": 2},
        }
    )

    response = await handler.delete_folder(
        FakeRequest({"folder_path": "/library/full"})
    )

    assert response.status == 409
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert payload["code"] == "not_empty"
    assert payload["manifest"]["model_count"] == 2


@pytest.mark.asyncio
async def test_delete_folder_busy_maps_to_409():
    handler, _service = _make_handler(
        {"success": False, "code": "busy", "error": "staged delete pending"}
    )

    response = await handler.delete_folder(
        FakeRequest({"folder_path": "/library/full"})
    )

    assert response.status == 409
    assert json.loads(response.text)["code"] == "busy"


@pytest.mark.asyncio
async def test_delete_folder_containment_failure_maps_to_400():
    handler, _service = _make_handler(
        {
            "success": False,
            "error": "Folder path '/etc/evil' is outside configured library directories",
        }
    )

    response = await handler.delete_folder(FakeRequest({"folder_path": "/etc/evil"}))

    assert response.status == 400
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert "outside configured library" in payload["error"]


@pytest.mark.asyncio
async def test_delete_folder_invalid_json_body():
    class BadJsonRequest:
        async def json(self):
            raise ValueError("bad json")

    handler, _service = _make_handler({"success": True})

    response = await handler.delete_folder(BadJsonRequest())

    assert response.status == 400
    assert json.loads(response.text)["success"] is False


@pytest.mark.asyncio
async def test_rename_folder_success():
    handler, service = _make_handler(
        {
            "success": True,
            "renamed": True,
            "folder": "characters/animation",
            "previous_folder": "characters/anime",
        }
    )

    response = await handler.rename_folder(
        FakeRequest(
            {"folder_path": "/library/characters/anime", "new_name": "animation"}
        )
    )

    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["success"] is True
    assert payload["folder"] == "characters/animation"
    assert service.received_path == "/library/characters/anime"
    assert service.received_new_name == "animation"


@pytest.mark.asyncio
async def test_rename_folder_missing_path():
    handler, service = _make_handler({"success": True})

    response = await handler.rename_folder(FakeRequest({"new_name": "animation"}))

    assert response.status == 400
    assert json.loads(response.text)["success"] is False
    assert service.received_path is None


@pytest.mark.asyncio
async def test_rename_folder_missing_name():
    handler, service = _make_handler({"success": True})

    response = await handler.rename_folder(
        FakeRequest({"folder_path": "/library/characters/anime"})
    )

    assert response.status == 400
    payload = json.loads(response.text)
    assert payload["success"] is False
    assert service.received_new_name is None


@pytest.mark.asyncio
async def test_rename_folder_target_exists_maps_to_409():
    handler, _service = _make_handler(
        {
            "success": False,
            "code": "target_exists",
            "error": 'A folder named "animation" already exists here',
        }
    )

    response = await handler.rename_folder(
        FakeRequest(
            {"folder_path": "/library/characters/anime", "new_name": "animation"}
        )
    )

    assert response.status == 409
    payload = json.loads(response.text)
    assert payload["code"] == "target_exists"


@pytest.mark.asyncio
async def test_rename_folder_busy_maps_to_409():
    handler, _service = _make_handler(
        {"success": False, "code": "busy", "error": "staged delete pending"}
    )

    response = await handler.rename_folder(
        FakeRequest({"folder_path": "/library/full", "new_name": "renamed"})
    )

    assert response.status == 409
    assert json.loads(response.text)["code"] == "busy"


@pytest.mark.asyncio
async def test_rename_folder_invalid_name_maps_to_400():
    handler, _service = _make_handler(
        {"success": False, "error": "Invalid characters in folder name"}
    )

    response = await handler.rename_folder(
        FakeRequest({"folder_path": "/library/full", "new_name": "a/b"})
    )

    assert response.status == 400
    assert json.loads(response.text)["success"] is False


@pytest.mark.asyncio
async def test_rename_folder_invalid_json_body():
    class BadJsonRequest:
        async def json(self):
            raise ValueError("bad json")

    handler, _service = _make_handler({"success": True})

    response = await handler.rename_folder(BadJsonRequest())

    assert response.status == 400
    assert json.loads(response.text)["success"] is False
