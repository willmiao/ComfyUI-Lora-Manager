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


class QueryParams(dict):
    """Minimal stand-in for aiohttp's MultiDict query (supports getall)."""

    def getall(self, key, default=None):
        value = self.get(key)
        if value is None:
            return list(default) if default else []
        return value if isinstance(value, list) else [value]


class ScopedScanService:
    """Stub service recording the scan scope the handler resolves."""

    model_type = "lora"

    def __init__(self, roots=None, summary=None, cancelled=False):
        self._roots = list(roots or [])
        self._summary = summary
        self.cancelled = cancelled
        self.scanner = SimpleNamespace(is_cancelled=lambda: self.cancelled)
        self.received_scope = "not-called"
        self.received_rebuild = None

    def get_model_roots(self):
        return list(self._roots)

    def describe_model_roots(self):
        return [
            {"path": root, "label": root.rsplit("/", 1)[-1], "reachable": True, "models": 7}
            for root in self._roots
        ]

    async def scan_models(self, force_refresh=False, rebuild_cache=False, scope=None):
        self.received_scope = scope
        self.received_rebuild = rebuild_cache
        return self._summary


SUMMARY = {
    "added": 3,
    "removed": 0,
    "repaired": 1,
    "scanned_roots": ["a"],
    "skipped_roots": [],
    "unavailable_paths": [],
    "unavailable_paths_total": 0,
    "kept_unreachable": 0,
}


@pytest.mark.asyncio
async def test_scan_models_accepts_roots_param():
    service = ScopedScanService(roots=["/mnt/a", "/mnt/b"], summary=SUMMARY)
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.scan_models(
        SimpleNamespace(query=QueryParams({"roots": ["/mnt/a"]}))
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["status"] == "success"
    assert payload["added"] == 3
    assert payload["scanned_roots"] == ["a"]
    assert service.received_scope is not None
    assert service.received_scope.roots == ("/mnt/a",)
    assert service.received_rebuild is False


@pytest.mark.asyncio
async def test_scan_models_without_roots_scans_every_root():
    service = ScopedScanService(roots=["/mnt/a"], summary=SUMMARY)
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    await handler.scan_models(SimpleNamespace(query=QueryParams({})))

    assert service.received_scope is None


@pytest.mark.asyncio
async def test_scan_models_rejects_unknown_root():
    service = ScopedScanService(roots=["/mnt/a"], summary=SUMMARY)
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.scan_models(
        SimpleNamespace(query=QueryParams({"roots": ["/mnt/nope"]}))
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["roots"] == ["/mnt/nope"]
    assert service.received_scope == "not-called"


@pytest.mark.asyncio
async def test_scan_models_rejects_roots_with_full_rebuild():
    service = ScopedScanService(roots=["/mnt/a"], summary=SUMMARY)
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.scan_models(
        SimpleNamespace(
            query=QueryParams({"roots": ["/mnt/a"], "full_rebuild": "true"})
        )
    )

    assert response.status == 400
    assert service.received_scope == "not-called"


@pytest.mark.asyncio
async def test_scan_models_accepts_folder_param():
    service = ScopedScanService(roots=["/mnt/a", "/mnt/b"], summary=SUMMARY)
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.scan_models(
        SimpleNamespace(query=QueryParams({"folder": "pack\\sub"}))
    )

    assert response.status == 200
    assert service.received_scope is not None
    # Backslashes are normalized and no root is pinned: the backend walks this
    # relative folder under every root that holds it.
    assert service.received_scope.folder == "pack/sub"
    assert service.received_scope.roots is None


@pytest.mark.asyncio
async def test_scan_models_rejects_absolute_folder():
    service = ScopedScanService(roots=["/mnt/a"], summary=SUMMARY)
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    for folder in ("/mnt/a/pack", "../pack", "C:/models/pack"):
        response = await handler.scan_models(
            SimpleNamespace(query=QueryParams({"folder": folder}))
        )
        assert response.status == 400, folder
        assert "error" in json.loads(response.text)

    assert service.received_scope == "not-called"


@pytest.mark.asyncio
async def test_scan_models_rejects_folder_with_full_rebuild():
    service = ScopedScanService(roots=["/mnt/a"], summary=SUMMARY)
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.scan_models(
        SimpleNamespace(query=QueryParams({"folder": "pack", "full_rebuild": "true"}))
    )

    assert response.status == 400
    assert service.received_scope == "not-called"


@pytest.mark.asyncio
async def test_scan_models_combines_folder_and_roots():
    service = ScopedScanService(roots=["/mnt/a", "/mnt/b"], summary=SUMMARY)
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.scan_models(
        SimpleNamespace(query=QueryParams({"folder": "pack", "roots": ["/mnt/b"]}))
    )

    assert response.status == 200
    assert service.received_scope.folder == "pack"
    assert service.received_scope.roots == ("/mnt/b",)


@pytest.mark.asyncio
async def test_get_model_roots_reports_details():
    service = ScopedScanService(roots=["/mnt/a", "/mnt/b"])
    handler = ModelQueryHandler(service=service, logger=logging.getLogger(__name__))

    response = await handler.get_model_roots(SimpleNamespace(query=QueryParams({})))
    payload = json.loads(response.text)

    # `roots` stays a plain list of paths for the existing callers.
    assert payload["roots"] == ["/mnt/a", "/mnt/b"]
    assert [detail["label"] for detail in payload["root_details"]] == ["a", "b"]
    assert all(detail["models"] == 7 for detail in payload["root_details"])
