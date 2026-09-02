import json
import logging
from types import SimpleNamespace

import pytest
from multidict import MultiDict

from py.routes.handlers.model_handlers import ModelQueryHandler
from py.services.active_filters_store import ActiveFiltersStore


class DummyService:
    model_type = "loras"

    def __init__(self):
        self.calls = []

    async def search_relative_paths(self, search, limit, offset, **kwargs):
        self.calls.append((search, limit, offset, kwargs))
        return []


def make_handler(service=None):
    return ModelQueryHandler(
        service=service or DummyService(), logger=logging.getLogger(__name__)
    )


def make_request(query=None, body=None, raise_on_json=False):
    async def json_body():
        if raise_on_json:
            raise ValueError("bad json")
        return body

    return SimpleNamespace(
        query=MultiDict(query or {}),
        json=json_body,
    )


@pytest.fixture(autouse=True)
def reset_store():
    ActiveFiltersStore.reset_instance()
    yield
    ActiveFiltersStore.reset_instance()


@pytest.mark.asyncio
async def test_update_active_filters_stores_sanitized_payload():
    handler = make_handler()
    response = await handler.update_active_filters(
        make_request(
            body={
                "activeFolder": "SD_XL",
                "recursiveSearch": False,
                "filters": {"baseModel": ["SDXL 1.0"], "rogue": "dropped"},
                "rogue": "dropped",
            }
        )
    )

    assert response.status == 200
    stored = ActiveFiltersStore.get_instance().get_filters("loras")
    assert stored == {
        "activeFolder": "SD_XL",
        "recursiveSearch": False,
        "filters": {"baseModel": ["SDXL 1.0"]},
    }


@pytest.mark.asyncio
async def test_update_active_filters_rejects_invalid_json():
    handler = make_handler()
    response = await handler.update_active_filters(
        make_request(raise_on_json=True)
    )
    assert response.status == 400


@pytest.mark.asyncio
async def test_update_active_filters_rejects_non_object_body():
    handler = make_handler()
    response = await handler.update_active_filters(make_request(body=["not", "dict"]))
    assert response.status == 400


@pytest.mark.asyncio
async def test_get_active_filters_returns_stored_payload():
    ActiveFiltersStore.get_instance().set_filters(
        "loras", {"activeFolder": "anime", "recursiveSearch": True, "filters": None}
    )
    handler = make_handler()
    response = await handler.get_active_filters(make_request())

    payload = json.loads(response.text)
    assert payload["success"] is True
    assert payload["filters"]["activeFolder"] == "anime"


@pytest.mark.asyncio
async def test_get_active_filters_returns_null_when_unset():
    handler = make_handler()
    response = await handler.get_active_filters(make_request())

    payload = json.loads(response.text)
    assert payload["success"] is True
    assert payload["filters"] is None


@pytest.mark.asyncio
async def test_relative_paths_injects_stored_active_filters():
    ActiveFiltersStore.get_instance().set_filters(
        "loras",
        {
            "activeFolder": "SD_XL",
            "recursiveSearch": False,
            "filters": {
                "baseModel": ["SDXL 1.0"],
                "tags": {"anime": "include"},
                "tagLogic": "all",
            },
        },
    )
    service = DummyService()
    handler = make_handler(service)

    response = await handler.get_relative_paths(
        make_request({"search": "cartoon", "use_active_filters": "true"})
    )

    assert response.status == 200
    _, _, _, kwargs = service.calls[0]
    assert kwargs["folder"] == "SD_XL"
    assert kwargs["recursive"] is False
    assert kwargs["base_models"] == ["SDXL 1.0"]
    assert kwargs["tags"] == {"anime": "include"}
    assert kwargs["tag_logic"] == "all"
    assert kwargs["apply_filters"] is True


@pytest.mark.asyncio
async def test_relative_paths_explicit_params_take_precedence():
    ActiveFiltersStore.get_instance().set_filters(
        "loras",
        {
            "activeFolder": "SD_XL",
            "recursiveSearch": True,
            "filters": {"baseModel": ["SDXL 1.0"]},
        },
    )
    service = DummyService()
    handler = make_handler(service)

    await handler.get_relative_paths(
        make_request(
            {
                "search": "cartoon",
                "use_active_filters": "true",
                "folder": "pony",
                "base_model": "Pony",
            }
        )
    )

    _, _, _, kwargs = service.calls[0]
    assert kwargs["folder"] == "pony"
    assert kwargs["base_models"] == ["Pony"]


@pytest.mark.asyncio
async def test_relative_paths_empty_store_still_runs_filter_pipeline():
    service = DummyService()
    handler = make_handler(service)

    await handler.get_relative_paths(
        make_request({"search": "cartoon", "use_active_filters": "true"})
    )

    _, _, _, kwargs = service.calls[0]
    assert kwargs["apply_filters"] is True
    assert kwargs["folder"] is None
    assert kwargs["base_models"] == []


@pytest.mark.asyncio
async def test_relative_paths_without_flag_ignores_store():
    ActiveFiltersStore.get_instance().set_filters(
        "loras", {"activeFolder": "SD_XL", "recursiveSearch": True, "filters": None}
    )
    service = DummyService()
    handler = make_handler(service)

    await handler.get_relative_paths(make_request({"search": "cartoon"}))

    _, _, _, kwargs = service.calls[0]
    assert kwargs["folder"] is None
    assert kwargs["apply_filters"] is False
