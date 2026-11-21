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
        FakeRequest(query={"search": "cat", "limit": "25", "offset": "2"})  # pyright: ignore[reportArgumentType]
    )
    text = response.text
    assert text is not None
    payload = json.loads(text)

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
    response = await handler.search_wildcards(
        FakeRequest(query={"search": "cat"})  # pyright: ignore[reportArgumentType]
    )
    text = response.text
    assert text is not None
    payload = json.loads(text)

    assert response.status == 500
    assert payload["error"] == "boom"


@pytest.mark.asyncio
async def test_search_wildcards_empty_state_includes_library_activation_counts():
    resources = [
        {"file_path": "/library/active.zip"},
        {"file_path": "/library/inactive.zip"},
        {"file_path": "/library/excluded.zip", "exclude": True},
    ]

    class StubService:
        def get_metadata(self, create_dir=False):
            return SimpleNamespace(
                has_wildcards=False,
                wildcards_dir="/tmp/settings/wildcards",
                supported_formats=(".txt",),
            )

        def search_keys(self, search_term, limit, offset):
            return []

    class StubSettings:
        def is_wildcards_enabled(self):
            return True

        def get_wildcard_path(self):
            return "/library"

    class StubScanner:
        async def get_cached_data(self):
            return SimpleNamespace(raw_data=resources)

    async def scanner_provider():
        return StubScanner()

    class StubActivationService:
        def count_active_resources(self, candidates):
            assert candidates == resources[:2]
            return 1

    handler = WildcardsHandler(
        service=StubService(),
        settings=StubSettings(),
        scanner_provider=scanner_provider,
        activation_service=StubActivationService(),
    )
    response = await handler.search_wildcards(FakeRequest())
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["meta"] == {
        "has_wildcards": False,
        "wildcards_dir": "/tmp/settings/wildcards",
        "supported_formats": [".txt"],
        "management_enabled": True,
        "library_configured": True,
        "library_resource_count": 2,
        "active_resource_count": 1,
    }


@pytest.mark.asyncio
async def test_search_wildcards_empty_state_does_not_scan_disabled_library():
    class StubService:
        def get_metadata(self, create_dir=False):
            return SimpleNamespace(
                has_wildcards=False,
                wildcards_dir="/tmp/settings/wildcards",
                supported_formats=(".txt",),
            )

        def search_keys(self, search_term, limit, offset):
            return []

    class StubSettings:
        def is_wildcards_enabled(self):
            return False

        def get_wildcard_path(self):
            return ""

    async def scanner_provider():
        raise AssertionError("disabled wildcard libraries must not be scanned")

    handler = WildcardsHandler(
        service=StubService(),
        settings=StubSettings(),
        scanner_provider=scanner_provider,
    )
    response = await handler.search_wildcards(FakeRequest())
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["meta"]["management_enabled"] is False
    assert payload["meta"]["library_configured"] is False
    assert payload["meta"]["library_resource_count"] == 0
    assert payload["meta"]["active_resource_count"] == 0
