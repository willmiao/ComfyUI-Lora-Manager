import pytest

from py.services.base_model_service import BaseModelService
from py.services.model_query import (
    ModelCacheRepository,
    ModelFilterSet,
    SearchStrategy,
    SortParams,
)
from py.utils.models import BaseModelMetadata


class StubSettings:
    def __init__(self, values):
        self._values = dict(values)

    def get(self, key, default=None):
        return self._values.get(key, default)


class DummyService(BaseModelService):
    async def format_response(self, model_data):
        return model_data


class StubRepository:
    def __init__(self, data):
        self._data = list(data)
        self.parse_sort_calls = []
        self.fetch_sorted_calls = []

    def parse_sort(self, sort_by):
        params = ModelCacheRepository.parse_sort(sort_by)
        self.parse_sort_calls.append(sort_by)
        return params

    async def fetch_sorted(self, params):
        self.fetch_sorted_calls.append(params)
        return list(self._data)


class StubFilterSet:
    def __init__(self, result):
        self.result = list(result)
        self.calls = []

    def apply(self, data, criteria):
        self.calls.append((list(data), criteria))
        return list(self.result)


class StubSearchStrategy:
    def __init__(self, search_result):
        self.search_result = list(search_result)
        self.normalize_calls = []
        self.apply_calls = []

    def normalize_options(self, options):
        self.normalize_calls.append(options)
        normalized = {"recursive": True}
        if options:
            normalized.update(options)
        return normalized

    def apply(self, data, search_term, options, fuzzy):
        self.apply_calls.append((list(data), search_term, options, fuzzy))
        return list(self.search_result)


class StubUpdateService:
    def __init__(self, decisions):
        self.decisions = dict(decisions)
        self.calls = []

    async def has_update(self, model_type, model_id):
        self.calls.append((model_type, model_id))
        result = self.decisions.get(model_id, False)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.asyncio
async def test_get_paginated_data_uses_injected_collaborators():
    data = [
        {"model_name": "Alpha", "folder": "root"},
        {"model_name": "Beta", "folder": "root"},
    ]
    repository = StubRepository(data)
    filter_set = StubFilterSet([{"model_name": "Filtered"}])
    search_strategy = StubSearchStrategy([{"model_name": "SearchResult"}])
    settings = StubSettings({})

    service = DummyService(
        model_type="stub",
        scanner=object(),
        metadata_class=BaseModelMetadata,
        cache_repository=repository,
        filter_set=filter_set,
        search_strategy=search_strategy,
        settings_provider=settings,
    )

    response = await service.get_paginated_data(
        page=1,
        page_size=5,
        sort_by="name:desc",
        folder="root",
        search="query",
        fuzzy_search=True,
        base_models=["base"],
        tags=["tag"],
        search_options={"recursive": False},
        favorites_only=True,
    )

    assert repository.parse_sort_calls == ["name:desc"]
    assert repository.fetch_sorted_calls and isinstance(repository.fetch_sorted_calls[0], SortParams)
    sort_params = repository.fetch_sorted_calls[0]
    assert sort_params.key == "name" and sort_params.order == "desc"

    assert filter_set.calls, "FilterSet should be invoked"
    call_data, criteria = filter_set.calls[0]
    assert call_data == data
    assert criteria.folder == "root"
    assert criteria.base_models == ["base"]
    assert criteria.tags == ["tag"]
    assert criteria.favorites_only is True
    assert criteria.search_options.get("recursive") is False

    assert search_strategy.normalize_calls == [{"recursive": False}, {"recursive": False}]
    assert search_strategy.apply_calls == [([{"model_name": "Filtered"}], "query", {"recursive": False}, True)]

    assert response["items"] == search_strategy.search_result
    assert response["total"] == len(search_strategy.search_result)
    assert response["page"] == 1
    assert response["page_size"] == 5


class FakeCache:
    def __init__(self, items):
        self.items = list(items)

    async def get_sorted_data(self, sort_key, order):
        if sort_key == "name":
            data = sorted(self.items, key=lambda x: x["model_name"].lower())
            if order == "desc":
                data.reverse()
        else:
            data = list(self.items)
        return data


class FakeScanner:
    def __init__(self, cache):
        self._cache = cache

    async def get_cached_data(self, *_, **__):
        return self._cache


@pytest.mark.asyncio
async def test_get_paginated_data_filters_and_searches_combination():
    items = [
        {
            "model_name": "Alpha",
            "file_name": "alpha.safetensors",
            "folder": "root/sub",
            "tags": ["tag1"],
            "base_model": "v1",
            "favorite": True,
            "preview_nsfw_level": 0,
        },
        {
            "model_name": "Beta",
            "file_name": "beta.safetensors",
            "folder": "root",
            "tags": ["tag2"],
            "base_model": "v2",
            "favorite": False,
            "preview_nsfw_level": 999,
        },
        {
            "model_name": "Gamma",
            "file_name": "gamma.safetensors",
            "folder": "root/sub2",
            "tags": ["tag1", "tag3"],
            "base_model": "v1",
            "favorite": True,
            "preview_nsfw_level": 0,
            "civitai": {"creator": {"username": "artist"}},
        },
    ]

    cache = FakeCache(items)
    scanner = FakeScanner(cache)
    settings = StubSettings({"show_only_sfw": True})

    service = DummyService(
        model_type="stub",
        scanner=scanner,
        metadata_class=BaseModelMetadata,
        cache_repository=ModelCacheRepository(scanner),
        filter_set=ModelFilterSet(settings),
        search_strategy=SearchStrategy(),
        settings_provider=settings,
    )

    response = await service.get_paginated_data(
        page=1,
        page_size=1,
        sort_by="name:asc",
        folder="root",
        search="artist",
        base_models=["v1"],
        tags=["tag1"],
        search_options={"creator": True, "tags": True},
        favorites_only=True,
    )

    assert response["items"] == [items[2]]
    assert response["total"] == 1
    assert response["page"] == 1
    assert response["page_size"] == 1
    assert response["total_pages"] == 1


class PassThroughFilterSet:
    def __init__(self):
        self.calls = []

    def apply(self, data, criteria):
        self.calls.append(criteria)
        return list(data)


class NoSearchStrategy:
    def __init__(self):
        self.normalize_calls = []
        self.apply_called = False

    def normalize_options(self, options):
        self.normalize_calls.append(options)
        return {"recursive": True}

    def apply(self, *args, **kwargs):
        self.apply_called = True
        pytest.fail("Search should not be invoked when no search term is provided")


@pytest.mark.asyncio
async def test_get_paginated_data_paginates_without_search():
    items = [
        {"model_name": name, "folder": "root"}
        for name in ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
    ]

    repository = StubRepository(items)
    filter_set = PassThroughFilterSet()
    search_strategy = NoSearchStrategy()
    settings = StubSettings({})

    service = DummyService(
        model_type="stub",
        scanner=object(),
        metadata_class=BaseModelMetadata,
        cache_repository=repository,
        filter_set=filter_set,
        search_strategy=search_strategy,
        settings_provider=settings,
    )

    response = await service.get_paginated_data(
        page=2,
        page_size=2,
        sort_by="name:asc",
    )

    assert repository.parse_sort_calls == ["name:asc"]
    assert len(repository.fetch_sorted_calls) == 1
    assert filter_set.calls and filter_set.calls[0].favorites_only is False
    assert search_strategy.apply_called is False
    assert response["items"] == items[2:4]
    assert response["total"] == len(items)
    assert response["page"] == 2
    assert response["page_size"] == 2
    assert response["total_pages"] == 3


@pytest.mark.asyncio
async def test_get_paginated_data_filters_by_update_status():
    items = [
        {"model_name": "A", "civitai": {"modelId": 1}},
        {"model_name": "B", "civitai": {"modelId": 2}},
        {"model_name": "C", "civitai": {"modelId": 3}},
    ]
    repository = StubRepository(items)
    filter_set = PassThroughFilterSet()
    search_strategy = NoSearchStrategy()
    update_service = StubUpdateService({1: True, 2: False, 3: True})
    settings = StubSettings({})

    service = DummyService(
        model_type="stub",
        scanner=object(),
        metadata_class=BaseModelMetadata,
        cache_repository=repository,
        filter_set=filter_set,
        search_strategy=search_strategy,
        settings_provider=settings,
        update_service=update_service,
    )

    response = await service.get_paginated_data(
        page=1,
        page_size=5,
        sort_by="name:asc",
        has_update=True,
    )

    assert update_service.calls == [("stub", 1), ("stub", 2), ("stub", 3)]
    assert response["items"] == [items[0], items[2]]
    assert response["total"] == 2
    assert response["page"] == 1
    assert response["page_size"] == 5
    assert response["total_pages"] == 1


@pytest.mark.asyncio
async def test_get_paginated_data_has_update_without_service_returns_empty():
    items = [
        {"model_name": "A", "civitai": {"modelId": 1}},
        {"model_name": "B", "civitai": {"modelId": 2}},
    ]
    repository = StubRepository(items)
    filter_set = PassThroughFilterSet()
    search_strategy = NoSearchStrategy()
    settings = StubSettings({})

    service = DummyService(
        model_type="stub",
        scanner=object(),
        metadata_class=BaseModelMetadata,
        cache_repository=repository,
        filter_set=filter_set,
        search_strategy=search_strategy,
        settings_provider=settings,
    )

    response = await service.get_paginated_data(
        page=1,
        page_size=10,
        sort_by="name:asc",
        has_update=True,
    )

    assert response["items"] == []
    assert response["total"] == 0
    assert response["total_pages"] == 0


@pytest.mark.asyncio
async def test_get_paginated_data_skips_items_when_update_check_fails():
    items = [
        {"model_name": "A", "civitai": {"modelId": 1}},
        {"model_name": "B", "civitai": {"modelId": 2}},
    ]
    repository = StubRepository(items)
    filter_set = PassThroughFilterSet()
    search_strategy = NoSearchStrategy()
    update_service = StubUpdateService({1: True, 2: RuntimeError("boom")})
    settings = StubSettings({})

    service = DummyService(
        model_type="stub",
        scanner=object(),
        metadata_class=BaseModelMetadata,
        cache_repository=repository,
        filter_set=filter_set,
        search_strategy=search_strategy,
        settings_provider=settings,
        update_service=update_service,
    )

    response = await service.get_paginated_data(
        page=1,
        page_size=10,
        sort_by="name:asc",
        has_update=True,
    )

    assert update_service.calls == [("stub", 1), ("stub", 2)]
    assert response["items"] == [items[0]]
    assert response["total"] == 1
    assert response["total_pages"] == 1
