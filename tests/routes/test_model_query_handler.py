import json
import logging
from types import SimpleNamespace

import pytest

from py.routes.handlers.model_handlers import ModelQueryHandler


class DummyService:
    def __init__(self):
        self.received_limit = None

    async def get_base_models(self, limit):
        self.received_limit = limit
        return [{"name": "SDXL", "count": 2}]


@pytest.mark.asyncio
async def test_model_query_handler_accepts_limit_zero_for_base_models():
    service = DummyService()
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.get_base_models(SimpleNamespace(query={"limit": "0"}))
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert service.received_limit == 0


@pytest.mark.asyncio
async def test_model_query_handler_rejects_negative_limit_for_base_models():
    service = DummyService()
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    await handler.get_base_models(SimpleNamespace(query={"limit": "-1"}))

    assert service.received_limit == 20


class DummySearchTagsService:
    """Minimal service stub recording search_tags arguments."""

    def __init__(self, result=None):
        self.received_query = None
        self.received_limit = None
        self._result = result or []

    async def search_tags(self, query, limit):
        self.received_query = query
        self.received_limit = limit
        return self._result


@pytest.mark.asyncio
async def test_model_query_handler_search_tags_passes_query_and_limit():
    service = DummySearchTagsService(result=[{"tag": "anime", "count": 3}])
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.search_tags(
        SimpleNamespace(query={"q": "ani", "limit": "50"})
    )
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert payload["tags"] == [{"tag": "anime", "count": 3}]
    assert service.received_query == "ani"
    assert service.received_limit == 50


@pytest.mark.asyncio
async def test_model_query_handler_search_tags_defaults_limit_to_20():
    service = DummySearchTagsService()
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    await handler.search_tags(SimpleNamespace(query={}))

    assert service.received_limit == 20


@pytest.mark.asyncio
async def test_model_query_handler_search_tags_clamps_negative_limit():
    service = DummySearchTagsService()
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    await handler.search_tags(SimpleNamespace(query={"limit": "-5"}))

    assert service.received_limit == 20
