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

    response = await handler.get_base_models(
        SimpleNamespace(query={"limit": "0"})  # pyright: ignore[reportArgumentType]
    )
    text = response.text
    assert text is not None
    payload = json.loads(text)

    assert payload["success"] is True
    assert service.received_limit == 0


@pytest.mark.asyncio
async def test_model_query_handler_rejects_negative_limit_for_base_models():
    service = DummyService()
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    await handler.get_base_models(
        SimpleNamespace(query={"limit": "-1"})  # pyright: ignore[reportArgumentType]
    )

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
        SimpleNamespace(query={"q": "ani", "limit": "50"})  # pyright: ignore[reportArgumentType]
    )
    text = response.text
    assert text is not None
    payload = json.loads(text)

    assert payload["success"] is True
    assert payload["tags"] == [{"tag": "anime", "count": 3}]
    assert service.received_query == "ani"
    assert service.received_limit == 50


@pytest.mark.asyncio
async def test_model_query_handler_search_tags_defaults_limit_to_20():
    service = DummySearchTagsService()
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    await handler.search_tags(SimpleNamespace(query={})  # pyright: ignore[reportArgumentType]
    )

    assert service.received_limit == 20


@pytest.mark.asyncio
async def test_model_query_handler_search_tags_clamps_negative_limit():
    service = DummySearchTagsService()
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    await handler.search_tags(
        SimpleNamespace(query={"limit": "-5"})  # pyright: ignore[reportArgumentType]
    )

    assert service.received_limit == 20


class DummyFolderCache:
    def __init__(self, folders):
        self.folders = list(folders)


class DummyFolderService:
    """Minimal service stub for the folders/tree endpoints."""

    def __init__(self, folders, all_folders):
        self.scanner = SimpleNamespace()
        cache = DummyFolderCache(folders)

        async def get_cached_data(*_, **__):
            return cache

        async def get_all_folders():
            return list(all_folders)

        self.scanner.get_cached_data = get_cached_data
        self.scanner.get_all_folders = get_all_folders
        self.received_include_empty = None

    async def get_folder_tree(self, model_root, include_empty=False):
        self.received_include_empty = include_empty
        return {"tree": "per-root"}

    async def get_unified_folder_tree(self, include_empty=False):
        self.received_include_empty = include_empty
        return {"tree": "unified"}


@pytest.mark.asyncio
async def test_get_folders_defaults_to_models_only_folders():
    service = DummyFolderService(["a"], ["a", "empty"])
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.get_folders(
        SimpleNamespace(query={})  # pyright: ignore[reportArgumentType]
    )
    payload = json.loads(response.text)

    assert payload["folders"] == ["a"]


@pytest.mark.asyncio
async def test_get_folders_include_empty_returns_all_folders():
    service = DummyFolderService(["a"], ["a", "empty"])
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.get_folders(
        SimpleNamespace(query={"include_empty": "1"})  # pyright: ignore[reportArgumentType]
    )
    payload = json.loads(response.text)

    assert payload["folders"] == ["a", "empty"]


@pytest.mark.asyncio
async def test_get_unified_folder_tree_threads_include_empty():
    service = DummyFolderService(["a"], ["a", "empty"])
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.get_unified_folder_tree(
        SimpleNamespace(query={"include_empty": "1"})  # pyright: ignore[reportArgumentType]
    )
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert service.received_include_empty is True


@pytest.mark.asyncio
async def test_get_unified_folder_tree_defaults_include_empty_false():
    service = DummyFolderService(["a"], ["a", "empty"])
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.get_unified_folder_tree(
        SimpleNamespace(query={})  # pyright: ignore[reportArgumentType]
    )
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert service.received_include_empty is False


@pytest.mark.asyncio
async def test_get_folder_tree_threads_include_empty():
    service = DummyFolderService(["a"], ["a", "empty"])
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.get_folder_tree(
        SimpleNamespace(query={"model_root": "/models/loras", "include_empty": "true"})  # pyright: ignore[reportArgumentType]
    )
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert service.received_include_empty is True
