import asyncio
from types import SimpleNamespace

import pytest

from py.services.model_update_service import ModelUpdateService


class DummyScanner:
    def __init__(self, raw_data):
        self._cache = SimpleNamespace(raw_data=raw_data)

    async def get_cached_data(self, *args, **kwargs):
        return self._cache


class DummyProvider:
    def __init__(self, response, *, support_bulk: bool = True):
        self.response = response
        self.calls: int = 0
        self.bulk_calls: list[list[int]] = []
        self.support_bulk = support_bulk

    async def get_model_versions(self, model_id):
        self.calls += 1
        return self.response

    async def get_model_versions_bulk(self, model_ids):
        if not self.support_bulk:
            raise NotImplementedError
        self.bulk_calls.append(list(model_ids))
        return {model_id: self.response for model_id in model_ids}


@pytest.mark.asyncio
async def test_refresh_persists_versions_and_uses_cache(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [
        {"civitai": {"modelId": 1, "id": 11}},
        {"civitai": {"modelId": 1, "id": 15}},
    ]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider({"modelVersions": [{"id": 11}, {"id": 15}]})

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 1)

    assert provider.calls == 0
    assert provider.bulk_calls == [[1]]
    assert record is not None
    assert record.version_ids == [11, 15]
    assert record.in_library_version_ids == [11, 15]
    assert record.has_update() is False

    await service.refresh_for_model_type("lora", scanner, provider)
    assert provider.calls == 0, "provider should not be called again within TTL"
    assert provider.bulk_calls == [[1]]


@pytest.mark.asyncio
async def test_refresh_respects_ignore_flag(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [{"civitai": {"modelId": 2, "id": 21}}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider({"modelVersions": [{"id": 21}, {"id": 22}]})

    await service.refresh_for_model_type("lora", scanner, provider)
    await service.set_should_ignore("lora", 2, True)

    provider.calls = 0
    provider.bulk_calls = []
    await service.refresh_for_model_type("lora", scanner, provider)
    assert provider.calls == 0
    assert provider.bulk_calls == []


@pytest.mark.asyncio
async def test_refresh_falls_back_when_bulk_not_supported(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [{"civitai": {"modelId": 4, "id": 41}}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider({"modelVersions": [{"id": 41}]}, support_bulk=False)

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 4)

    assert record is not None
    assert provider.calls == 1
    assert provider.bulk_calls == []


@pytest.mark.asyncio
async def test_refresh_batches_large_collections(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [
        {"civitai": {"modelId": idx, "id": idx * 10}}
        for idx in range(1, 151)
    ]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider({"modelVersions": []})

    await service.refresh_for_model_type("lora", scanner, provider)

    # Expect two batches: 100 ids and remaining 50 ids
    assert len(provider.bulk_calls) == 2
    assert len(provider.bulk_calls[0]) == 100
    assert len(provider.bulk_calls[1]) == 50


@pytest.mark.asyncio
async def test_update_in_library_versions_changes_update_state(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=1)
    raw_data = [{"civitai": {"modelId": 3, "id": 31}}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider({"modelVersions": [{"id": 31}, {"id": 35}]})

    await service.refresh_for_model_type("lora", scanner, provider)
    await service.update_in_library_versions("lora", 3, [31])
    record = await service.get_record("lora", 3)

    assert record is not None
    assert record.has_update() is True

    await service.update_in_library_versions("lora", 3, [31, 35])
    record = await service.get_record("lora", 3)

    assert record.has_update() is False
