from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from py.routes.handlers.misc_handlers import WildcardsHandler


class FakeRequest:
    def __init__(self, query=None):
        self.query = query or {}


@pytest.mark.asyncio
async def test_search_wildcards_returns_results():
    class StubService:
        def get_metadata(self, create_dir=False):
            assert create_dir is True
            return SimpleNamespace(
                has_wildcards=True,
                wildcards_dir="/tmp/settings/wildcards",
                supported_formats=(".txt", ".yaml", ".yml", ".json"),
            )

        def search_keys(self, search_term, limit, offset):
            assert search_term == "cat"
            assert limit == 25
            assert offset == 2
            return ["animals/cat"]

    handler = WildcardsHandler(service=StubService())
    response = await handler.search_wildcards(
        FakeRequest(query={"search": "cat", "limit": "25", "offset": "2"})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload == {
        "success": True,
        "words": ["animals/cat"],
        "meta": {
            "has_wildcards": True,
            "wildcards_dir": "/tmp/settings/wildcards",
            "supported_formats": [".txt", ".yaml", ".yml", ".json"],
        },
    }


@pytest.mark.asyncio
async def test_search_wildcards_handles_errors():
    class StubService:
        def get_metadata(self, create_dir=False):
            return SimpleNamespace(
                has_wildcards=False,
                wildcards_dir="/tmp/settings/wildcards",
                supported_formats=(".txt",),
            )

        def search_keys(self, search_term, limit, offset):
            raise RuntimeError("boom")

    handler = WildcardsHandler(service=StubService())
    response = await handler.search_wildcards(FakeRequest(query={"search": "cat"}))
    payload = json.loads(response.text)

    assert response.status == 500
    assert payload["error"] == "boom"
