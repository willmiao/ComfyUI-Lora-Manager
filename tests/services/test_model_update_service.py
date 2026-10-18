import logging
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from py.services.errors import ResourceNotFoundError
from py.services.model_update_service import (
    ModelUpdateRecord,
    ModelUpdateService,
    ModelVersionRecord,
)


class DummyScanner:
    def __init__(self, raw_data):
        self._cache = SimpleNamespace(raw_data=raw_data, version_index={})
        self._cancelled = False

    def is_cancelled(self) -> bool:
        return self._cancelled

    def reset_cancellation(self) -> None:
        self._cancelled = False

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


class NotFoundProvider:
    def __init__(self):
        self.calls = 0
        self.bulk_calls: list[list[int]] = []

    async def get_model_versions(self, model_id):
        self.calls += 1
        raise ResourceNotFoundError("Resource not found")

    async def get_model_versions_bulk(self, model_ids):
        self.bulk_calls.append(list(model_ids))
        return {}


def make_version(
    version_id,
    *,
    in_library,
    base_model=None,
    should_ignore=False,
    early_access_ends_at=None,
    is_early_access=False,
    is_paid=False,
    paid_access=None,
):
    return ModelVersionRecord(
        version_id=version_id,
        name=None,
        base_model=base_model,
        released_at=None,
        size_bytes=None,
        preview_url=None,
        is_in_library=in_library,
        should_ignore=should_ignore,
        early_access_ends_at=early_access_ends_at,
        is_early_access=is_early_access,
        is_paid=is_paid,
        paid_access=paid_access,
    )


def make_record(*versions, should_ignore_model=False):
    return ModelUpdateRecord(
        model_type="lora",
        model_id=999,
        versions=list(versions),
        last_checked_at=None,
        should_ignore_model=should_ignore_model,
    )


def test_extract_size_bytes_prefers_primary_model_file(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))

    response = {
        "modelVersions": [
            {
                "id": 42,
                "files": [
                    {"sizeKB": 2018.0400390625, "type": "Training Data", "primary": False},
                    {
                        "sizeKB": 1152322.3515625,
                        "type": "Model",
                        "primary": "True",
                    },
                ],
                "images": [],
            }
        ]
    }

    versions = service._extract_versions(response)
    assert versions is not None
    assert versions[0].size_bytes == int(1152322.3515625 * 1024)


def test_extract_size_bytes_falls_back_without_primary(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))

    response = {
        "modelVersions": [
            {
                "id": 43,
                "files": [
                    {
                        "sizeKB": 2048,
                        "type": "Training Data",
                        "primary": True,
                    },
                    {"sizeKB": 1024, "type": "Archive", "primary": False},
                ],
                "images": [],
            }
        ]
    }

    versions = service._extract_versions(response)
    assert versions is not None
    assert versions[0].size_bytes == int(2048 * 1024)


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


def test_has_update_for_base_matches_same_base_model():
    record = make_record(
        make_version(5, in_library=True, base_model="Pony"),
        make_version(6, in_library=False, base_model="Pony"),
        make_version(7, in_library=False, base_model="Flux.1"),
    )

    assert record.has_update_for_base(5, "Pony") is True


def test_has_update_for_base_rejects_other_base_models():
    record = make_record(
        make_version(10, in_library=True, base_model="Flux"),
        make_version(20, in_library=False, base_model="SDXL"),
    )

    assert record.has_update_for_base(10, "Flux") is False


def test_has_update_for_local_bases_detects_same_base_newer_version():
    record = make_record(
        make_version(5, in_library=True, base_model="Pony"),
        make_version(6, in_library=False, base_model="pony"),
    )

    assert record.has_update_for_local_bases() is True


def test_has_update_for_local_bases_rejects_cross_base_only_update():
    """Issue #1083: a newer remote version targeting another base model must
    not count when the report is scoped like the Updates filter."""
    record = make_record(
        make_version(5, in_library=True, base_model="Pony"),
        make_version(6, in_library=False, base_model="Flux.1"),
    )

    assert record.has_update_for_local_bases() is False
    assert record.has_update() is True


def test_has_update_for_local_bases_hits_when_any_scope_qualifies():
    record = make_record(
        make_version(5, in_library=True, base_model="Pony"),
        make_version(6, in_library=False, base_model="Flux.1"),
        make_version(7, in_library=False, base_model="Pony"),
    )

    assert record.has_update_for_local_bases() is True


def test_has_update_for_local_bases_respects_ignore_and_hides():
    ignored = make_record(
        make_version(5, in_library=True, base_model="Pony"),
        make_version(6, in_library=False, base_model="Pony", should_ignore=True),
    )
    assert ignored.has_update_for_local_bases() is False

    paid = make_record(
        make_version(5, in_library=True, base_model="Pony"),
        make_version(
            6,
            in_library=False,
            base_model="Pony",
            is_paid=True,
            paid_access='{"permanent": true, "endsAt": null}',
        ),
    )
    assert paid.has_update_for_local_bases() is True
    assert paid.has_update_for_local_bases(hide_paid=True) is False

    timed_early_access = make_record(
        make_version(5, in_library=True, base_model="Pony"),
        make_version(
            6,
            in_library=False,
            base_model="Pony",
            early_access_ends_at="2099-01-01T00:00:00Z",
            is_early_access=True,
        ),
    )
    assert timed_early_access.has_update_for_local_bases() is True
    assert timed_early_access.has_update_for_local_bases(hide_early_access=True) is False


def test_has_update_for_local_bases_falls_back_when_no_local_scopes_known():
    """Without any known in-library base (e.g. a local version delisted from
    Civitai before its first refresh), the aggregate falls back to the
    unscoped predicate so the summary cannot silently drop models the
    item-level Updates filter may still flag from file metadata."""
    delisted_local = make_record(
        make_version(5, in_library=True, base_model=None),
        make_version(6, in_library=False, base_model="Pony"),
    )
    assert delisted_local.has_update_for_local_bases() is True

    remote_only = make_record(make_version(6, in_library=False, base_model="Pony"))
    assert remote_only.has_update_for_local_bases() is True


def test_build_record_from_remote_synthesizes_base_from_local_map(tmp_path):
    """Versions missing from the remote listing are synthesized with the base
    model collected from cache items, so same-base scoping survives a version
    being delisted upstream."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))
    remote = [make_version(6, in_library=False, base_model="Pony")]

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=1,
        local_versions=[5],
        remote_versions=remote,
        existing=None,
        timestamp=1.0,
        local_base_models={5: "Pony"},
    )
    v5 = next(v for v in record.versions if v.version_id == 5)
    assert v5.base_model == "Pony"

    record_without_map = service._build_record_from_remote(
        model_type="lora",
        model_id=1,
        local_versions=[5],
        remote_versions=remote,
        existing=None,
        timestamp=1.0,
    )
    v5_plain = next(v for v in record_without_map.versions if v.version_id == 5)
    assert v5_plain.base_model is None


@pytest.mark.asyncio
async def test_refresh_synthesizes_base_model_from_cache_items(tmp_path):
    """End-to-end: a locally-held version absent from the remote listing keeps
    its cache-item base model, keeping it countable under same-base scoping."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=0)
    raw_data = [{"civitai": {"modelId": 1, "id": 11}, "base_model": "Pony"}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider(
        {
            "modelVersions": [
                {"id": 12, "baseModel": "Pony", "files": [], "images": []},
            ]
        }
    )

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 1)

    assert record is not None
    v11 = next(v for v in record.versions if v.version_id == 11)
    assert v11.base_model == "Pony"
    assert record.has_update() is True
    assert record.has_update_for_local_bases() is True


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
async def test_refresh_filters_to_requested_models(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [
        {"civitai": {"modelId": 1, "id": 11}},
        {"civitai": {"modelId": 2, "id": 21}},
    ]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider({"modelVersions": []})

    result = await service.refresh_for_model_type(
        "lora",
        scanner,
        provider,
        target_model_ids=[2],
    )

    assert list(result.keys()) == [2]
    assert provider.bulk_calls == [[2]]


@pytest.mark.asyncio
async def test_refresh_returns_empty_when_targets_missing(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [{"civitai": {"modelId": 1, "id": 11}}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider({"modelVersions": []})

    result = await service.refresh_for_model_type(
        "lora",
        scanner,
        provider,
        target_model_ids=[5],
    )

    assert result == {}
    assert provider.bulk_calls == []


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
async def test_refresh_marks_model_ignored_when_remote_missing(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [{"civitai": {"modelId": 5, "id": 51}}]
    scanner = DummyScanner(raw_data)
    provider = NotFoundProvider()

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 5)

    assert provider.bulk_calls == [[5]]
    assert provider.calls == 1
    assert record is not None
    assert record.should_ignore_model is True
    assert record.in_library_version_ids == [51]
    assert record.last_checked_at is not None


@pytest.mark.asyncio
async def test_refresh_logs_info_for_missing_remote(tmp_path, caplog):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [{"civitai": {"modelId": 6, "id": 61}}]
    scanner = DummyScanner(raw_data)
    provider = NotFoundProvider()

    with caplog.at_level(logging.INFO, logger="py.services.model_update_service"):
        await service.refresh_for_model_type("lora", scanner, provider)

    relevant = [
        record for record in caplog.records if "Single lookup for model" in record.message
    ]
    assert relevant, "expected single lookup log entry"
    assert all(record.levelno == logging.INFO for record in relevant)


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

    assert record is not None
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
async def test_has_updates_bulk_handles_more_than_sqlite_max_variables(tmp_path):
    """Bulk query with >999 model IDs must not raise 'too many SQL variables'."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)

    model_ids = list(range(1, 1201))
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT INTO model_update_status (model_id, model_type) VALUES (?, ?)", (1, "lora"))
        conn.execute("INSERT INTO model_update_versions (model_id, version_id, sort_index, name) VALUES (?, ?, ?, ?)", (1, 10, 0, "v1"))

    mapping = await service.has_updates_bulk("lora", model_ids)

    assert mapping[1] is True
    assert len(mapping) == len(model_ids)
    assert all(v is False for k, v in mapping.items() if k != 1)


@pytest.mark.asyncio
async def test_get_records_bulk_handles_more_than_sqlite_max_variables(tmp_path):
    """Bulk record fetch with >999 model IDs must not raise 'too many SQL variables'."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)

    model_ids = list(range(1, 1201))
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT INTO model_update_status (model_id, model_type) VALUES (?, ?)", (1, "lora"))
        conn.execute("INSERT INTO model_update_versions (model_id, version_id, sort_index, name) VALUES (?, ?, ?, ?)", (1, 10, 0, "v1"))

    records = await service.get_records_bulk("lora", model_ids)

    assert 1 in records
    assert records[1].model_id == 1
    assert len(records) == 1


@pytest.mark.asyncio
async def test_refresh_allows_duplicate_version_ids_across_models(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=0)
    raw_data = [
        {"civitai": {"modelId": 1, "id": 42}},
        {"civitai": {"modelId": 2, "id": 42}},
    ]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider(
        {
            "modelVersions": [
                {
                    "id": 42,
                    "name": "shared",
                    "baseModel": "SD15",
                    "publishedAt": "2024-03-01T00:00:00Z",
                    "files": [{"sizeKB": 256}],
                    "images": [],
                }
            ]
        }
    )

    results = await service.refresh_for_model_type("lora", scanner, provider)

    assert set(results.keys()) == {1, 2}
    assert results[1].version_ids == [42]
    assert results[2].version_ids == [42]

    with sqlite3.connect(str(db_path)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM model_update_versions WHERE version_id = 42"
        ).fetchone()[0]

    assert count == 2


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

@pytest.mark.asyncio
async def test_update_in_library_versions_populates_metadata(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))

    version_info = {
        "id": 123,
        "name": "v1.0",
        "baseModel": "SD 1.5",
        "publishedAt": "2024-03-01T00:00:00Z",
        "files": [{"sizeKB": 1024, "type": "Model", "primary": True}],
        "images": [{"url": "https://example.com/preview.png"}],
    }

    await service.update_in_library_versions("lora", 1, [123], version_info=version_info)
    record = await service.get_record("lora", 1)

    assert record is not None
    assert len(record.versions) == 1
    version = record.versions[0]
    assert version.version_id == 123
    assert version.name == "v1.0"
    assert version.base_model == "SD 1.5"
    assert version.size_bytes == 1024 * 1024
    assert version.preview_url == "https://example.com/preview.png"
    assert version.is_in_library is True


@pytest.mark.asyncio
async def test_refresh_folder_filter_considers_cross_folder_versions(tmp_path):
    """When refreshing by folder, versions in other folders must still be
    considered in-library so they aren't reported as available updates."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=0)
    # Same model (modelId=1) in two folders with different versions
    raw_data = [
        {"civitai": {"modelId": 1, "id": 11}, "folder": "folder_a"},
        {"civitai": {"modelId": 1, "id": 15}, "folder": "folder_b"},
    ]
    scanner = DummyScanner(raw_data)
    # Remote offers: 11 (in folder_a), 15 (in folder_b), 20 (truly new)
    provider = DummyProvider(
        {
            "modelVersions": [
                {"id": 11, "files": [], "images": []},
                {"id": 15, "files": [], "images": []},
                {"id": 20, "files": [], "images": []},
            ]
        }
    )

    await service.refresh_for_model_type(
        "lora", scanner, provider, folder_path="folder_a",
    )
    record = await service.get_record("lora", 1)

    assert record is not None

    # Version 15 is in folder_b — must be in_library even when filtering by folder_a
    v15 = next(v for v in record.versions if v.version_id == 15)
    assert v15.is_in_library is True

    # Version 20 is truly new — should not be in_library
    v20 = next(v for v in record.versions if v.version_id == 20)
    assert v20.is_in_library is False

    # has_update must be True (version 20 > max_in_library=15)
    assert record.has_update() is True


def test_extract_single_version_paid_access_timed(tmp_path):
    """A timed paidAccess gate (permanent=False + future endsAt) is detected
    as early access while availability stays 'Public'."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))

    entry = {
        "id": 42,
        "name": "v1 paid",
        "availability": "Public",
        "paidAccess": {
            "permanent": False,
            "endsAt": "2026-08-22T18:30:00.000Z",
        },
        "files": [],
        "images": [],
    }

    version = service._extract_single_version(entry, index=0)

    assert version is not None
    assert version.is_early_access is True
    assert version.early_access_ends_at == "2026-08-22T18:30:00.000Z"
    assert version.is_paid is False
    assert version.paid_access is not None


def test_extract_single_version_paid_access_permanent(tmp_path):
    """A permanent paidAccess gate (permanent=True, no endsAt) is detected and
    flagged as paid but is NOT early access and carries no end date."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))

    entry = {
        "id": 42,
        "name": "v1 paid",
        "availability": "Public",
        "paidAccess": {"permanent": True, "endsAt": None},
        "files": [],
        "images": [],
    }

    version = service._extract_single_version(entry, index=0)

    assert version is not None
    assert version.is_early_access is False
    assert version.is_paid is True
    assert version.early_access_ends_at is None
    assert version.paid_access is not None


def test_extract_single_version_paid_access_pending_end(tmp_path):
    """A timed gate whose window end is not recorded yet
    ({"permanent": false, "endsAt": null}) is still an active gate, so it is
    early access with no known end date rather than a free version."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))

    entry = {
        "id": 42,
        "name": "v1 paid",
        "availability": "Public",
        "paidAccess": {"permanent": False, "endsAt": None},
        "files": [],
        "images": [],
    }

    version = service._extract_single_version(entry, index=0)

    assert version is not None
    assert version.is_early_access is True
    assert version.is_paid is False
    assert version.early_access_ends_at is None
    assert version.paid_access == '{"permanent": false, "endsAt": null}'
    assert ModelUpdateRecord._is_early_access_active(version) is True


def test_normalize_paid_access_accepts_json_string():
    """The by-hash enrichment path may hand paidAccess to _normalize_paid_access
    as a JSON string; both the permanent and timed shapes must normalize."""
    service = ModelUpdateService.__new__(ModelUpdateService)

    permanent = ModelUpdateService._normalize_paid_access(
        '{"permanent": true, "endsAt": null}'
    )
    assert permanent == {"permanent": True, "endsAt": None}

    timed = ModelUpdateService._normalize_paid_access(
        '{"permanent": false, "endsAt": "2026-08-22T18:30:00.000Z"}'
    )
    assert timed == {"permanent": False, "endsAt": "2026-08-22T18:30:00.000Z"}

    # A timed gate whose window end is not recorded yet. CivitAI only returns a
    # non-null DTO for an ACTIVE gate (tombstones come back as null) and enforces
    # this shape too - the model page reports canDownload: false for it - so it
    # must be kept. Dropping it was the #1060 class of bug.
    pending_end = ModelUpdateService._normalize_paid_access(
        '{"permanent": false, "endsAt": null}'
    )
    assert pending_end == {"permanent": False, "endsAt": None}

    malformed = ModelUpdateService._normalize_paid_access("{not json")
    assert malformed is None

    # No gate keys at all is not a gate signal.
    assert ModelUpdateService._normalize_paid_access("{}") is None


def test_has_update_for_base_hide_paid():
    """hide_paid also suppresses permanent paid versions in the same-base
    update path (has_update_for_base)."""
    record = make_record(
        make_version(5, in_library=True, base_model="illustrious"),
        make_version(
            7,
            in_library=False,
            base_model="illustrious",
            is_paid=True,
            paid_access='{"permanent": true, "endsAt": null}',
        ),
    )

    assert record.has_update_for_base(5, "illustrious") is True
    assert record.has_update_for_base(5, "illustrious", hide_paid=True) is False


def test_has_update_hide_paid():
    """hide_paid suppresses update flags raised by a permanent paid version."""
    record = make_record(
        make_version(5, in_library=True),
        make_version(
            7,
            in_library=False,
            is_paid=True,
            paid_access='{"permanent": true, "endsAt": null}',
        ),
    )

    assert record.has_update() is True
    assert record.has_update(hide_paid=True) is False


def test_has_update_hide_early_access_paid_timed():
    """hide_early_access suppresses a newer timed paidAccess version."""
    record = make_record(
        make_version(5, in_library=True),
        make_version(
            7,
            in_library=False,
            is_early_access=True,
            early_access_ends_at="2099-01-01T00:00:00Z",
        ),
    )

    assert record.has_update() is True
    assert record.has_update(hide_early_access=True) is False



def test_build_record_from_remote_preserves_paid_fields(tmp_path):
    """_build_record_from_remote must carry paid_access/is_paid from the
    parsed remote versions into the rebuilt record, or the refresh path
    silently drops paid data before persistence."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))

    remote_version = ModelVersionRecord(
        version_id=7,
        name="v7",
        base_model=None,
        released_at=None,
        size_bytes=None,
        preview_url=None,
        is_in_library=False,
        should_ignore=False,
        early_access_ends_at=None,
        is_early_access=True,
        usage_control="Download",
        paid_access='{"permanent": true, "endsAt": null}',
        is_paid=True,
    )

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=123,
        local_versions=[],
        remote_versions=[remote_version],
        existing=None,
        timestamp=1.0,
    )

    rebuilt = record.versions[0]
    assert rebuilt.paid_access == '{"permanent": true, "endsAt": null}'
    assert rebuilt.is_paid is True


def test_extract_file_count_counts_weight_files(tmp_path):
    """file_count counts only weight-type files; a missing files array stays
    None (unknown) so the UI can distinguish it from "no weight files"."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))

    response = {
        "modelVersions": [
            {
                "id": 42,
                "files": [
                    {"sizeKB": 100, "type": "Model", "primary": True},
                    {"sizeKB": 10, "type": "Training Data"},
                    {"sizeKB": 50, "type": "Pruned Model"},
                ],
                "images": [],
            },
            {"id": 43, "images": []},
            {"id": 44, "files": [], "images": []},
        ]
    }

    versions = service._extract_versions(response)
    assert versions is not None
    assert versions[0].file_count == 2
    assert versions[1].file_count is None
    assert versions[2].file_count == 0


@pytest.mark.asyncio
async def test_refresh_persists_file_count(tmp_path):
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path), ttl_seconds=3600)
    raw_data = [{"civitai": {"modelId": 1, "id": 11}}]
    scanner = DummyScanner(raw_data)
    provider = DummyProvider(
        {
            "modelVersions": [
                {
                    "id": 11,
                    "name": "v1",
                    "baseModel": "SD15",
                    "files": [
                        {"sizeKB": 1024, "type": "Model", "primary": True},
                        {"sizeKB": 2048, "type": "Model"},
                        {"sizeKB": 128, "type": "Training Data"},
                    ],
                    "images": [],
                }
            ]
        }
    )

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 1)

    assert record is not None
    assert record.versions[0].file_count == 2


def test_build_record_from_remote_preserves_file_count(tmp_path):
    """A remote payload without files data must not clobber the previously
    persisted file_count; a populated payload wins."""
    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))

    existing = make_record(
        ModelVersionRecord(
            version_id=7,
            name="v7",
            base_model=None,
            released_at=None,
            size_bytes=None,
            preview_url=None,
            is_in_library=True,
            should_ignore=False,
            file_count=3,
        )
    )
    remote_without_count = ModelVersionRecord(
        version_id=7,
        name="v7",
        base_model=None,
        released_at=None,
        size_bytes=None,
        preview_url=None,
        is_in_library=False,
        should_ignore=False,
        file_count=None,
    )

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[7],
        remote_versions=[remote_without_count],
        existing=existing,
        timestamp=1.0,
    )
    assert record.versions[0].file_count == 3

    remote_with_count = ModelVersionRecord(
        version_id=7,
        name="v7",
        base_model=None,
        released_at=None,
        size_bytes=None,
        preview_url=None,
        is_in_library=False,
        should_ignore=False,
        file_count=1,
    )
    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[7],
        remote_versions=[remote_with_count],
        existing=existing,
        timestamp=2.0,
    )
    assert record.versions[0].file_count == 1


# --- Gate-state transitions and price persistence ---------------------------


def _remote_gated(version_id, *, price_checked_at=None, price_buzz=None):
    return ModelVersionRecord(
        version_id=version_id,
        name=f"v{version_id}",
        base_model=None,
        released_at=None,
        size_bytes=None,
        preview_url=None,
        is_in_library=False,
        should_ignore=False,
        paid_access='{"permanent": false, "endsAt": "2026-10-10T13:10:17.404Z"}',
        is_early_access=True,
        early_access_ends_at="2026-10-10T13:10:17.404Z",
        price_checked_at=price_checked_at,
        price_buzz=price_buzz,
    )


def _remote_free(version_id):
    return ModelVersionRecord(
        version_id=version_id,
        name=f"v{version_id}",
        base_model=None,
        released_at=None,
        size_bytes=None,
        preview_url=None,
        is_in_library=False,
        should_ignore=False,
    )


def test_build_record_emits_became_free_event(tmp_path):
    """A version whose gate lapsed produces a became_free event, keeps a lapse
    timestamp, and drops the now-meaningless stored price."""

    service = ModelUpdateService(str(tmp_path / "updates.sqlite"))
    existing = make_record(
        replace(
            _remote_gated(7, price_checked_at=100.0, price_buzz=500),
        )
    )

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[],
        remote_versions=[_remote_free(7)],
        existing=existing,
        timestamp=1000.0,
    )

    version = record.versions[0]
    assert version.gate_lapsed_at is not None
    assert version.price_buzz is None
    assert version.price_checked_at is None
    assert [event["kind"] for event in record.events] == ["became_free"]
    assert record.events[0]["versionId"] == 7
    assert record.events[0]["isInLibrary"] is False


def test_build_record_emits_new_gate_event(tmp_path):
    service = ModelUpdateService(str(tmp_path / "updates.sqlite"))
    existing = make_record(_remote_free(7))

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[],
        remote_versions=[_remote_gated(7)],
        existing=existing,
        timestamp=1000.0,
    )

    assert [event["kind"] for event in record.events] == ["new_gate"]
    assert record.versions[0].gate_lapsed_at is None


def test_build_record_no_events_without_previous_snapshot(tmp_path):
    """First sight of a model must not report every existing gate as a new one."""

    service = ModelUpdateService(str(tmp_path / "updates.sqlite"))

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[],
        remote_versions=[_remote_gated(7), _remote_free(8)],
        existing=None,
        timestamp=1000.0,
    )

    assert record.events == []


def test_build_record_keeps_lapse_marker_and_skips_ignored(tmp_path):
    """An already-free version keeps its original lapse marker and an ignored
    version reports nothing at all."""

    service = ModelUpdateService(str(tmp_path / "updates.sqlite"))
    lapsed = replace(_remote_free(7), gate_lapsed_at="2026-09-01T00:00:00.000Z")
    existing = make_record(lapsed, replace(_remote_gated(8), should_ignore=True))

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[],
        remote_versions=[_remote_free(7), _remote_free(8)],
        existing=existing,
        timestamp=1000.0,
    )

    by_id = {version.version_id: version for version in record.versions}
    assert by_id[7].gate_lapsed_at == "2026-09-01T00:00:00.000Z"
    assert record.events == []


def test_build_record_preserves_price_when_fetch_skipped(tmp_path):
    """A refresh that did not run a price fetch (no price_checked_at) must keep the
    stored price instead of wiping it."""

    service = ModelUpdateService(str(tmp_path / "updates.sqlite"))
    existing = make_record(
        replace(_remote_gated(7, price_checked_at=100.0, price_buzz=500))
    )

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[],
        remote_versions=[_remote_gated(7)],
        existing=existing,
        timestamp=1000.0,
    )

    assert record.versions[0].price_buzz == 500
    assert record.versions[0].price_checked_at == 100.0
    assert record.events == []


def test_build_record_applies_fresh_price(tmp_path):
    service = ModelUpdateService(str(tmp_path / "updates.sqlite"))
    existing = make_record(
        replace(_remote_gated(7, price_checked_at=100.0, price_buzz=500))
    )

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[],
        remote_versions=[_remote_gated(7, price_checked_at=200.0, price_buzz=250)],
        existing=existing,
        timestamp=1000.0,
    )

    assert record.versions[0].price_buzz == 250
    assert record.versions[0].price_checked_at == 200.0


def _legacy_version_table_sql() -> str:
    """The model_update_versions schema before gate-lapse/price columns."""

    return """
        CREATE TABLE model_update_versions (
            model_id INTEGER NOT NULL,
            version_id INTEGER NOT NULL,
            sort_index INTEGER NOT NULL DEFAULT 0,
            name TEXT,
            base_model TEXT,
            released_at TEXT,
            size_bytes INTEGER,
            preview_url TEXT,
            is_in_library INTEGER NOT NULL DEFAULT 0,
            should_ignore INTEGER NOT NULL DEFAULT 0,
            early_access_ends_at TEXT,
            is_early_access INTEGER NOT NULL DEFAULT 0,
            usage_control TEXT,
            paid_access TEXT,
            is_paid INTEGER NOT NULL DEFAULT 0,
            file_count INTEGER,
            PRIMARY KEY (model_id, version_id)
        )
    """


def test_migration_adds_price_columns_to_legacy_db(tmp_path):
    """Opening a database written before this feature must add the columns and keep
    the existing rows (the migration path real users hit)."""

    db_path = tmp_path / "updates.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE model_update_status ("
        "model_id INTEGER PRIMARY KEY, model_type TEXT NOT NULL, "
        "last_checked_at REAL, should_ignore_model INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(_legacy_version_table_sql())
    conn.execute(
        "INSERT INTO model_update_status (model_id, model_type, last_checked_at) "
        "VALUES (999, 'lora', 1.0)"
    )
    conn.execute(
        "INSERT INTO model_update_versions ("
        "model_id, version_id, is_in_library, is_early_access, paid_access, is_paid"
        ") VALUES (999, 7, 1, 1, '{\"permanent\": false, \"endsAt\": null}', 0)"
    )
    conn.commit()
    conn.close()

    service = ModelUpdateService(str(db_path))
    columns = service._get_table_columns(
        service._connect(), "model_update_versions"
    )
    for column in (
        "gate_lapsed_at",
        "price_buzz",
        "list_price_buzz",
        "generation_price_buzz",
        "accepts_blue_buzz",
        "price_sale_ends_at",
        "price_checked_at",
        "price_check_attempted_at",
    ):
        assert column in columns
    # The alert-state columns were removed together with the threshold they served.
    assert "price_alert_state" not in columns
    assert "price_alert_since" not in columns

    record = service._get_record("lora", 999)
    assert record is not None
    assert [version.version_id for version in record.versions] == [7]
    version = record.versions[0]
    assert version.paid_access == '{"permanent": false, "endsAt": null}'
    assert version.price_buzz is None
    assert version.price_checked_at is None
    assert version.gate_lapsed_at is None
    assert version.accepts_blue_buzz is False


def test_price_fields_round_trip_through_sqlite(tmp_path):
    """Price and lapse columns survive an upsert/read cycle."""

    service = ModelUpdateService(str(tmp_path / "updates.sqlite"))
    version = replace(
        _remote_gated(7, price_checked_at=123.5, price_buzz=500),
        list_price_buzz=600,
        generation_price_buzz=100,
        accepts_blue_buzz=True,
        price_sale_ends_at="2026-10-01T00:00:00.000Z",
        is_in_library=True,
        gate_lapsed_at=None,
    )
    service._upsert_record(make_record(version))

    stored = service._get_record("lora", 999)
    assert stored is not None
    loaded = stored.versions[0]
    assert loaded.price_buzz == 500
    assert loaded.list_price_buzz == 600
    assert loaded.generation_price_buzz == 100
    assert loaded.accepts_blue_buzz is True
    assert loaded.price_sale_ends_at == "2026-10-01T00:00:00.000Z"
    assert loaded.price_checked_at == 123.5
    assert loaded.price_check_attempted_at is None


# --- Optional price capture --------------------------------------------------


class FakeSettings:
    """Minimal stand-in for SettingsManager (only `.get` is used by these paths)."""

    def __init__(self, values=None):
        self._values = dict(values or {})

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value


class PriceProvider(DummyProvider):
    """DummyProvider that can also serve prices."""

    def __init__(self, response, *, prices=None, error=None):
        super().__init__(response)
        self.prices = prices
        self.error = error
        self.price_calls = 0

    async def get_model_prices(self, model_id):
        self.price_calls += 1
        if self.error is not None:
            raise self.error
        return self.prices


GATED_RESPONSE = {
    "modelVersions": [
        {
            "id": 12,
            "baseModel": "Pony",
            "availability": "Public",
            "paidAccess": {"permanent": False, "endsAt": "2999-01-01T00:00:00.000Z"},
            "files": [],
            "images": [],
        }
    ]
}
FREE_RESPONSE = {
    "modelVersions": [
        {"id": 12, "baseModel": "Pony", "availability": "Public", "files": [], "images": []}
    ]
}
LOCAL_RAW_DATA = [{"civitai": {"modelId": 1, "id": 11}, "base_model": "Pony"}]

PRICE_PAYLOAD = {
    12: {
        "price_buzz": 250,
        "list_price_buzz": 500,
        "generation_price_buzz": 100,
        "accepts_blue_buzz": True,
        "price_sale_ends_at": "2999-01-02T00:00:00.000Z",
    }
}


def _price_service(tmp_path, **settings):
    return ModelUpdateService(
        str(tmp_path / "updates.sqlite"),
        ttl_seconds=0,
        settings_manager=FakeSettings(settings),
    )


@pytest.mark.asyncio
async def test_price_capture_off_by_default(tmp_path):
    service = _price_service(tmp_path)
    scanner = DummyScanner(LOCAL_RAW_DATA)
    provider = PriceProvider(GATED_RESPONSE, prices=PRICE_PAYLOAD)

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 1)

    assert provider.price_calls == 0
    assert record.versions[0].price_checked_at is None
    assert record.versions[0].price_buzz is None


@pytest.mark.asyncio
async def test_price_capture_stores_prices_for_gated_versions(tmp_path):
    service = _price_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)
    provider = PriceProvider(GATED_RESPONSE, prices=PRICE_PAYLOAD)

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 1)

    assert provider.price_calls == 1
    version = next(v for v in record.versions if v.version_id == 12)
    assert version.price_buzz == 250
    assert version.list_price_buzz == 500
    assert version.generation_price_buzz == 100
    assert version.accepts_blue_buzz is True
    assert version.price_sale_ends_at == "2999-01-02T00:00:00.000Z"
    assert version.price_checked_at is not None


@pytest.mark.asyncio
async def test_price_capture_skips_ungated_models(tmp_path):
    service = _price_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)
    provider = PriceProvider(FREE_RESPONSE, prices=PRICE_PAYLOAD)

    await service.refresh_for_model_type("lora", scanner, provider)

    assert provider.price_calls == 0


@pytest.mark.asyncio
async def test_price_capture_failure_keeps_stored_price(tmp_path):
    service = _price_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)

    await service.refresh_for_model_type(
        "lora", scanner, PriceProvider(GATED_RESPONSE, prices=PRICE_PAYLOAD)
    )
    first = await service.get_record("lora", 1)
    stored_checked_at = next(
        v for v in first.versions if v.version_id == 12
    ).price_checked_at
    assert stored_checked_at is not None

    # The page is unreadable this time (a changed gate still triggers a fetch):
    # the price must survive untouched rather than being blanked.
    failing = PriceProvider(
        {
            "modelVersions": [
                {
                    "id": 12,
                    "baseModel": "Pony",
                    "availability": "Public",
                    "paidAccess": {
                        "permanent": False,
                        "endsAt": "2999-06-01T00:00:00.000Z",
                    },
                    "files": [],
                    "images": [],
                }
            ]
        },
        prices=None,
    )
    await service.refresh_for_model_type("lora", scanner, failing)

    record = await service.get_record("lora", 1)
    version = next(v for v in record.versions if v.version_id == 12)
    assert failing.price_calls == 1
    assert version.price_buzz == 250
    assert version.price_checked_at == stored_checked_at


@pytest.mark.asyncio
async def test_price_capture_respects_ttl(tmp_path):
    """A second refresh with an unchanged gate and a fresh price must not refetch."""

    service = _price_service(
        tmp_path, price_tracking_enabled=True, price_check_ttl_hours=24
    )
    scanner = DummyScanner(LOCAL_RAW_DATA)
    provider = PriceProvider(GATED_RESPONSE, prices=PRICE_PAYLOAD)

    await service.refresh_for_model_type("lora", scanner, provider)
    await service.refresh_for_model_type("lora", scanner, provider)

    assert provider.price_calls == 1


@pytest.mark.asyncio
async def test_price_capture_refetches_when_gate_changes(tmp_path):
    service = _price_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)
    provider = PriceProvider(GATED_RESPONSE, prices=PRICE_PAYLOAD)

    await service.refresh_for_model_type("lora", scanner, provider)

    changed_gate = {
        "modelVersions": [
            {
                "id": 12,
                "baseModel": "Pony",
                "availability": "Public",
                "paidAccess": {
                    "permanent": True,
                    "endsAt": None,
                },
                "files": [],
                "images": [],
            }
        ]
    }
    provider.response = changed_gate
    await service.refresh_for_model_type("lora", scanner, provider)

    assert provider.price_calls == 2


@pytest.mark.asyncio
async def test_price_capture_survives_provider_without_support(tmp_path):
    """A provider that cannot serve prices must not break the refresh."""

    service = _price_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)
    provider = DummyProvider(GATED_RESPONSE)

    await service.refresh_for_model_type("lora", scanner, provider)
    record = await service.get_record("lora", 1)

    assert record is not None
    version = next(v for v in record.versions if v.version_id == 12)
    assert version.price_buzz is None


@pytest.mark.asyncio
async def test_price_capture_drops_price_when_version_becomes_free(tmp_path):
    service = _price_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)

    await service.refresh_for_model_type(
        "lora", scanner, PriceProvider(GATED_RESPONSE, prices=PRICE_PAYLOAD)
    )

    await service.refresh_for_model_type("lora", scanner, PriceProvider(FREE_RESPONSE))
    record = await service.get_record("lora", 1)
    version = next(v for v in record.versions if v.version_id == 12)

    assert version.price_buzz is None
    assert version.price_checked_at is None
    assert version.gate_lapsed_at is not None


# --- Price alerts ------------------------------------------------------------


def _gated_response(ends_at: str) -> dict:
    """Gated response with a specific EA end.

    Varying the end date between refreshes is what forces a re-fetch inside a
    single test (a price is otherwise considered fresh for the whole TTL).
    """

    return {
        "modelVersions": [
            {
                "id": 12,
                "baseModel": "Pony",
                "availability": "Public",
                "paidAccess": {"permanent": False, "endsAt": ends_at},
                "files": [],
                "images": [],
            }
        ]
    }


def _prices(price_buzz: int) -> dict:
    return {12: {"price_buzz": price_buzz, "list_price_buzz": price_buzz}}












# --- Price alerts panel semantics (read-time threshold, across types) ---------


def _gated_response_for(version_id: int, ends_at: str) -> dict:
    return {
        "modelVersions": [
            {
                "id": version_id,
                "baseModel": "Pony",
                "availability": "Public",
                "paidAccess": {"permanent": False, "endsAt": ends_at},
                "files": [],
                "images": [],
            }
        ]
    }


def _free_response_for(version_id: int) -> dict:
    return {
        "modelVersions": [
            {
                "id": version_id,
                "baseModel": "Pony",
                "availability": "Public",
                "files": [],
                "images": [],
            }
        ]
    }












@pytest.mark.asyncio
async def test_failed_price_attempt_is_recorded_as_unavailable(tmp_path):
    """A gated version we tried to price and could not must be distinguishable
    from one we never looked at — that is the honest "unavailable" state for
    mature models, whose pages no host will serve anonymously."""

    service = _price_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)
    failing = PriceProvider(GATED_RESPONSE, prices=None)

    await service.refresh_for_model_type("lora", scanner, failing)
    record = await service.get_record("lora", 1)
    version = next(v for v in record.versions if v.version_id == 12)

    assert failing.price_calls == 1
    assert version.price_buzz is None
    assert version.price_checked_at is None
    assert version.price_check_attempted_at is not None


@pytest.mark.asyncio
async def test_successful_price_attempt_sets_both_markers(tmp_path):
    service = _price_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)

    await service.refresh_for_model_type(
        "lora", scanner, PriceProvider(GATED_RESPONSE, prices=PRICE_PAYLOAD)
    )
    record = await service.get_record("lora", 1)
    version = next(v for v in record.versions if v.version_id == 12)

    assert version.price_buzz == 250
    assert version.price_checked_at is not None
    assert version.price_check_attempted_at is not None


@pytest.mark.asyncio
async def test_no_price_attempt_is_recorded_while_tracking_is_off(tmp_path):
    service = _price_service(tmp_path)  # tracking off
    scanner = DummyScanner(LOCAL_RAW_DATA)

    await service.refresh_for_model_type("lora", scanner, DummyProvider(GATED_RESPONSE))
    record = await service.get_record("lora", 1)

    assert record.versions[0].price_check_attempted_at is None


@pytest.mark.asyncio
async def test_unavailable_marker_clears_when_the_version_becomes_free(tmp_path):
    service = _price_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)

    await service.refresh_for_model_type(
        "lora", scanner, PriceProvider(GATED_RESPONSE, prices=None)
    )

    await service.refresh_for_model_type("lora", scanner, DummyProvider(FREE_RESPONSE))
    record = await service.get_record("lora", 1)

    assert record.versions[0].price_check_attempted_at is None


def _long_ttl_service(tmp_path, **settings):
    """A service whose metadata TTL does not lapse during the test."""

    return ModelUpdateService(
        str(tmp_path / "updates.sqlite"),
        ttl_seconds=86400,
        settings_manager=FakeSettings(settings),
    )


@pytest.mark.asyncio
async def test_prices_are_fetched_even_when_the_version_list_is_fresh(tmp_path):
    """Enabling price tracking must not wait for the metadata TTL.

    The cached record already carries the gate, so a fresh version list is no
    reason to skip the price: otherwise turning the feature on prices only the
    handful of models that happened to need a metadata refresh that round.
    """

    service = _long_ttl_service(tmp_path, price_tracking_enabled=False)
    scanner = DummyScanner(LOCAL_RAW_DATA)
    provider = PriceProvider(GATED_RESPONSE, prices=PRICE_PAYLOAD)

    await service.refresh_for_model_type("lora", scanner, provider)
    assert provider.price_calls == 0
    metadata_calls = provider.calls
    checked_at_before = (await service.get_record("lora", 1)).last_checked_at

    service._settings.set("price_tracking_enabled", True)
    await service.refresh_for_model_type("lora", scanner, provider)

    record = await service.get_record("lora", 1)
    version = next(v for v in record.versions if v.version_id == 12)

    # The version list came from the cache this round ...
    assert provider.calls == metadata_calls
    # ... and the price was captured anyway.
    assert provider.price_calls == 1
    assert version.price_buzz == 250
    assert version.price_checked_at is not None
    assert version.price_check_attempted_at is not None
    # A price-only pass must not extend the metadata TTL.
    assert record.last_checked_at == checked_at_before


@pytest.mark.asyncio
async def test_failed_price_attempt_is_not_retried_within_the_ttl(tmp_path):
    """A mature model whose page no host will serve must not cost two requests
    on every single update check."""

    service = _long_ttl_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)
    provider = PriceProvider(GATED_RESPONSE, prices=None)

    await service.refresh_for_model_type("lora", scanner, provider)
    assert provider.price_calls == 1

    await service.refresh_for_model_type("lora", scanner, provider)

    assert provider.price_calls == 1




@pytest.mark.asyncio
async def test_forced_refresh_reprices_within_the_ttl(tmp_path):
    service = _long_ttl_service(tmp_path, price_tracking_enabled=True)
    scanner = DummyScanner(LOCAL_RAW_DATA)
    provider = PriceProvider(GATED_RESPONSE, prices=PRICE_PAYLOAD)

    await service.refresh_for_model_type("lora", scanner, provider)
    assert provider.price_calls == 1

    await service.refresh_for_model_type(
        "lora", scanner, provider, force_refresh=True
    )

    assert provider.price_calls == 2


# --- Ownership scoping and the removed threshold -----------------------------


def test_gate_event_is_suppressed_for_a_version_the_user_owns(tmp_path):
    """A version already on disk cannot become cheaper *for this user*, so it must
    not produce an event. More than half of a real library's gated versions are
    owned, so this is the common case, not an edge case."""

    service = ModelUpdateService(str(tmp_path / "updates.sqlite"))
    existing = make_record(replace(_remote_gated(7), is_in_library=True))

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[7],
        remote_versions=[_remote_free(7)],
        existing=existing,
        timestamp=1000.0,
    )

    assert record.events == []
    # The lapse itself is still recorded - it is the *notification* that is
    # pointless for a version the user already has.
    assert record.versions[0].gate_lapsed_at is not None


def test_new_gate_event_is_suppressed_for_a_version_the_user_owns(tmp_path):
    service = ModelUpdateService(str(tmp_path / "updates.sqlite"))
    existing = make_record(replace(_remote_free(7), is_in_library=True))

    record = service._build_record_from_remote(
        model_type="lora",
        model_id=999,
        local_versions=[7],
        remote_versions=[_remote_gated(7)],
        existing=existing,
        timestamp=1000.0,
    )

    assert record.events == []


def test_threshold_setting_is_gone_from_the_defaults():
    """The redesign removed the numeric threshold: every obtainability decision is
    categorical (wait / pay / skip), so no number is stored or compared."""

    from py.services.settings_manager import DEFAULT_SETTINGS

    assert "price_alert_threshold_buzz" not in DEFAULT_SETTINGS
    assert "price_tracking_enabled" in DEFAULT_SETTINGS
    assert "price_check_ttl_hours" in DEFAULT_SETTINGS


def test_obsolete_alert_columns_are_dropped_from_a_development_database(tmp_path):
    """A database created while the feature was unreleased still carries the two
    alert-state columns; opening it must drop them rather than leave dead schema."""

    db_path = tmp_path / "updates.sqlite"
    service = ModelUpdateService(str(db_path))
    with service._connect() as conn:
        conn.execute(
            "ALTER TABLE model_update_versions "
            "ADD COLUMN price_alert_state INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            "ALTER TABLE model_update_versions ADD COLUMN price_alert_since REAL"
        )
        conn.commit()
        assert "price_alert_state" in service._get_table_columns(
            conn, "model_update_versions"
        )

    # A fresh service instance runs the migration on open.
    reopened = ModelUpdateService(str(db_path))
    columns = reopened._get_table_columns(
        reopened._connect(), "model_update_versions"
    )

    assert "price_alert_state" not in columns
    assert "price_alert_since" not in columns
