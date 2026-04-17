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
