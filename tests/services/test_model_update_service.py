from types import SimpleNamespace

import pytest

from py.services.model_update_service import (
    ModelUpdateRecord,
    ModelUpdateService,
    ModelVersionRecord,
)


class DummyScanner:
    def __init__(self, raw_data):
        self._cache = SimpleNamespace(raw_data=raw_data, version_index={})

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


def make_version(version_id, *, in_library, should_ignore=False):
    return ModelVersionRecord(
        version_id=version_id,
        name=None,
        base_model=None,
        released_at=None,
        size_bytes=None,
        preview_url=None,
        is_in_library=in_library,
        should_ignore=should_ignore,
    )


def make_record(*versions, should_ignore_model=False):
    return ModelUpdateRecord(
        model_type="lora",
        model_id=999,
        versions=list(versions),
        last_checked_at=None,
        should_ignore_model=should_ignore_model,
    )


def test_has_update_requires_newer_version_than_library():
    record = make_record(
        make_version(5, in_library=True),
        make_version(4, in_library=False),
        make_version(8, in_library=False, should_ignore=True),
    )

    assert record.has_update() is False


def test_has_update_detects_newer_remote_version():
    record = make_record(
        make_version(5, in_library=True),
        make_version(7, in_library=False),
        make_version(6, in_library=False, should_ignore=True),
    )

    assert record.has_update() is True


@pytest.mark.asyncio
async def test_refresh_persists_versions_and_uses_cache(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [
        {"civitai": {"modelId": 1, "id": 11}},
        {"civitai": {"modelId": 1, "id": 15}},
    ]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider(
        {
            "modelVersions": [
                {
                    "id": 11,
                    "name": "v1",
                    "baseModel": "SD15",
                    "publishedAt": "2024-01-01T00:00:00Z",
                    "files": [{"sizeKB": 1024}],
                    "images": [{"url": "https://example.com/1.png"}],
                },
                {
                    "id": 15,
                    "name": "v1.5",
                    "baseModel": "SD15",
                    "publishedAt": "2024-02-01T00:00:00Z",
                    "files": [{"sizeKB": 512}],
                    "images": [{"url": "https://example.com/2.png"}],
                },
            ]
        }
    )

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 1)

    assert provider.calls == 0
    assert provider.bulk_calls == [[1]]
    assert record is not None
    assert record.version_ids == [11, 15]
    assert record.in_library_version_ids == [11, 15]
    assert [version.name for version in record.versions] == ["v1", "v1.5"]
    assert record.should_ignore_model is False
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
    provider = DummyProvider(
        {
            "modelVersions": [
                {"id": 21, "files": [], "images": []},
                {"id": 22, "files": [], "images": []},
            ]
        }
    )

    await service.refresh_for_model_type("lora", scanner, provider)
    await service.set_should_ignore("lora", 2, True)

    provider.calls = 0
    provider.bulk_calls = []
    await service.refresh_for_model_type("lora", scanner, provider)
    assert provider.calls == 0
    assert provider.bulk_calls == []
    record = await service.get_record("lora", 2)
    assert record is not None
    assert record.should_ignore_model is True


@pytest.mark.asyncio
async def test_refresh_falls_back_when_bulk_not_supported(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [{"civitai": {"modelId": 4, "id": 41}}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider(
        {"modelVersions": [{"id": 41, "files": [], "images": []}]},
        support_bulk=False,
    )

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
    provider = DummyProvider(
        {
            "modelVersions": [
                {"id": 31, "files": [], "images": []},
                {"id": 35, "files": [], "images": []},
            ]
        }
    )

    await service.refresh_for_model_type("lora", scanner, provider)
    await service.update_in_library_versions("lora", 3, [31])
    record = await service.get_record("lora", 3)

    assert record is not None
    assert record.has_update() is True

    await service.update_in_library_versions("lora", 3, [31, 35])
    record = await service.get_record("lora", 3)

    assert record.has_update() is False


@pytest.mark.asyncio
async def test_version_ignore_blocks_update_flag(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=1)
    raw_data = [{"civitai": {"modelId": 5, "id": 51}}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider(
        {
            "modelVersions": [
                {"id": 51, "files": [], "images": []},
                {"id": 55, "files": [], "images": []},
            ]
        }
    )

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 5)
    assert record is not None
    assert record.has_update() is True

    await service.set_version_should_ignore("lora", 5, 55, True)
    record = await service.get_record("lora", 5)
    assert record is not None
    assert record.has_update() is False


@pytest.mark.asyncio
async def test_has_updates_bulk_returns_mapping(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [{"civitai": {"modelId": 9, "id": 91}}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider(
        {
            "modelVersions": [
                {"id": 91, "files": [], "images": []},
                {"id": 92, "files": [], "images": []},
            ]
        }
    )

    await service.refresh_for_model_type("lora", scanner, provider)
    mapping = await service.has_updates_bulk("lora", [9, 9, 42])

    assert mapping == {9: True, 42: False}
    assert await service.has_update("lora", 9) is True


@pytest.mark.asyncio
async def test_refresh_rewrites_remote_preview_urls(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=1)
    raw_data = [{"civitai": {"modelId": 7, "id": 71}}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider(
        {
            "modelVersions": [
                {
                    "id": 71,
                    "files": [],
                    "images": [
                        {
                            "url": "https://image.civitai.com/high/original=true/sample.png",
                            "nsfwLevel": 6,
                            "type": "image",
                        },
                        {
                            "url": "https://image.civitai.com/safe/original=true/preview.png",
                            "nsfwLevel": 1,
                            "type": "image",
                        },
                    ],
                }
            ]
        }
    )

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 7)

    assert record is not None
    assert record.versions
    preview_url = record.versions[0].preview_url
    assert (
        preview_url
        == "https://image.civitai.com/safe/width=450,optimized=true/preview.png"
    )
