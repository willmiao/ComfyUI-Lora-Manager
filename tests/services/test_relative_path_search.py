import pytest

from py.services.base_model_service import BaseModelService
from py.utils.models import BaseModelMetadata


class DummyService(BaseModelService):
    async def format_response(self, model_data):
        return model_data


class FakeCache:
    def __init__(self, raw_data):
        self.raw_data = list(raw_data)


class FakeScanner:
    def __init__(self, raw_data, roots):
        self._cache = FakeCache(raw_data)
        self._roots = list(roots)

    async def get_cached_data(self, *_args, **_kwargs):
        return self._cache

    def get_model_roots(self):
        return list(self._roots)


@pytest.mark.asyncio
async def test_search_relative_paths_supports_multiple_tokens():
    scanner = FakeScanner(
        [
            {"file_path": "/models/flux/detail-model.safetensors"},
            {"file_path": "/models/flux/only-flux.safetensors"},
            {"file_path": "/models/detail/flux-trained.safetensors"},
            {"file_path": "/models/detail/standalone.safetensors"},
        ],
        ["/models"],
    )
    service = DummyService("stub", scanner, BaseModelMetadata)

    matching = await service.search_relative_paths("flux detail")

    assert matching == [
        "flux/detail-model.safetensors",
        "detail/flux-trained.safetensors",
    ]


@pytest.mark.asyncio
async def test_search_relative_paths_excludes_tokens():
    scanner = FakeScanner(
        [
            {"file_path": "/models/flux/detail-model.safetensors"},
            {"file_path": "/models/flux/keep-me.safetensors"},
        ],
        ["/models"],
    )
    service = DummyService("stub", scanner, BaseModelMetadata)

    matching = await service.search_relative_paths("flux -detail")

    assert matching == ["flux/keep-me.safetensors"]
