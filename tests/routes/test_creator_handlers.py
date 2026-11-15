"""Tests for the library creator suggestions endpoint."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from py.routes.handlers.misc_handlers import (
    ModelLibraryHandler,
    ServiceRegistryAdapter,
)


class FakeRequest:
    def __init__(self, query: dict[str, str] | None = None) -> None:
        self.query = query or {}


class FakeScanner:
    def __init__(self, entries: list[dict[str, Any]], version: int = 1) -> None:
        self._cache = SimpleNamespace(raw_data=entries)
        self.cache_version = version

    async def get_cached_data(self):
        return self._cache


def _creator_entry(username: str, *, exclude: bool = False) -> dict[str, Any]:
    return {
        "file_path": f"/models/{username.lower()}.safetensors",
        "civitai": {"creator": {"username": username}},
        **({"exclude": True} if exclude else {}),
    }


async def _unused():
    return None


def make_handler(scanners: dict[str, FakeScanner]) -> ModelLibraryHandler:
    async def get_scanner(name: str):
        return scanners[name]

    return ModelLibraryHandler(
        ServiceRegistryAdapter(
            get_lora_scanner=lambda: get_scanner("lora"),
            get_checkpoint_scanner=lambda: get_scanner("checkpoint"),
            get_embedding_scanner=lambda: get_scanner("embedding"),
            get_other_scanner=lambda: get_scanner("other"),
            get_downloaded_version_history_service=_unused,
        ),
        metadata_provider_factory=_unused,
    )


def test_build_creator_index_folds_case_and_skips_excluded() -> None:
    index = ModelLibraryHandler._build_creator_index(
        {
            "lora": [
                _creator_entry("Lykon"),
                _creator_entry("lykon"),
                _creator_entry("Lykon"),
                _creator_entry("local_artist"),
                _creator_entry("excluded", exclude=True),
                {"civitai": {}},
                {"civitai": {"creator": {"username": "   "}}},
                {},
            ],
            "checkpoint": [
                _creator_entry("LYKON"),
                _creator_entry("Other"),
            ],
        }
    )

    by_name = {entry["username"]: entry["model_count"] for entry in index}
    assert by_name == {
        "Lykon": 4,
        "local_artist": 1,
        "Other": 1,
    }


def test_rank_creators_exact_prefix_substring_then_count() -> None:
    creators = [
        {"username": "TheAlly", "model_count": 15},
        {"username": "lyko", "model_count": 99},
        {"username": "Lykon", "model_count": 24},
    ]

    # No exact match: prefix matches come before the substring match, and
    # model count breaks the prefix tie.
    assert [
        creator["username"]
        for creator in ModelLibraryHandler._rank_creators(creators, "ly")
    ] == ["lyko", "Lykon", "TheAlly"]

    # Exact match wins even against a much more common prefix match.
    assert [
        creator["username"]
        for creator in ModelLibraryHandler._rank_creators(creators, "LYKON")
    ] == ["Lykon"]

    # No query: simply by model count.
    assert [
        creator["username"]
        for creator in ModelLibraryHandler._rank_creators(creators, "")
    ] == ["lyko", "Lykon", "TheAlly"]


@pytest.mark.asyncio
async def test_get_creators_returns_ranked_page_and_total() -> None:
    handler = make_handler(
        {
            "lora": FakeScanner([
                _creator_entry("Lykon"),
                _creator_entry("lyko"),
                _creator_entry("TheAlly"),
                _creator_entry("sasha"),
            ]),
            "checkpoint": FakeScanner([_creator_entry("Lykon")]),
            "embedding": FakeScanner([]),
            "other": FakeScanner([]),
        }
    )

    response = await handler.get_creators(
        FakeRequest({"query": "ly", "limit": "2"})  # pyright: ignore[reportArgumentType]
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["total"] == 3
    assert payload["library_total"] == 4
    assert [item["username"] for item in payload["creators"]] == ["Lykon", "lyko"]
    assert payload["creators"][0]["model_count"] == 2


@pytest.mark.asyncio
async def test_get_creators_caps_limit_and_handles_bad_limit() -> None:
    handler = make_handler(
        {
            "lora": FakeScanner([_creator_entry(f"creator_{i}") for i in range(60)]),
            "checkpoint": FakeScanner([]),
            "embedding": FakeScanner([]),
            "other": FakeScanner([]),
        }
    )

    response = await handler.get_creators(
        FakeRequest({"limit": "500"})  # pyright: ignore[reportArgumentType]
    )
    payload = json.loads(response.text)
    assert len(payload["creators"]) == 50
    assert payload["total"] == 60

    response = await handler.get_creators(
        FakeRequest({"limit": "not-a-number"})  # pyright: ignore[reportArgumentType]
    )
    payload = json.loads(response.text)
    assert len(payload["creators"]) == 8


@pytest.mark.asyncio
async def test_get_creators_rebuilds_index_when_cache_version_changes() -> None:
    scanner = FakeScanner([_creator_entry("Lykon")], version=1)
    handler = make_handler(
        {
            "lora": scanner,
            "checkpoint": FakeScanner([]),
            "embedding": FakeScanner([]),
            "other": FakeScanner([]),
        }
    )

    first = json.loads((await handler.get_creators(FakeRequest())).text)
    assert [entry["username"] for entry in first["creators"]] == ["Lykon"]

    scanner._cache = SimpleNamespace(
        raw_data=[_creator_entry("new_creator"), _creator_entry("Lykon")]
    )
    scanner.cache_version = 2

    second = json.loads((await handler.get_creators(FakeRequest())).text)
    assert [entry["username"] for entry in second["creators"]] == ["Lykon", "new_creator"]
