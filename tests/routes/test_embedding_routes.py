import json

import pytest

from py.routes.embedding_routes import EmbeddingRoutes


class DummyRequest:
    def __init__(self, *, match_info=None):
        self.match_info = match_info or {}


class StubEmbeddingService:
    def __init__(self):
        self.info = {}

    async def get_model_info_by_name(self, name):
        value = self.info.get(name)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def routes():
    handler = EmbeddingRoutes()
    handler.service = StubEmbeddingService()
    return handler


async def test_get_embedding_info_success(routes):
    routes.service.info["demo"] = {"name": "demo"}
    response = await routes.get_embedding_info(DummyRequest(match_info={"name": "demo"}))
    payload = json.loads(response.text)
    assert payload == {"name": "demo"}


async def test_get_embedding_info_missing(routes):
    response = await routes.get_embedding_info(DummyRequest(match_info={"name": "missing"}))
    payload = json.loads(response.text)
    assert response.status == 404
    assert payload == {"error": "Embedding not found"}


async def test_get_embedding_info_error(routes):
    routes.service.info["demo"] = RuntimeError("boom")
    response = await routes.get_embedding_info(DummyRequest(match_info={"name": "demo"}))
    payload = json.loads(response.text)
    assert response.status == 500
    assert payload == {"error": "boom"}
