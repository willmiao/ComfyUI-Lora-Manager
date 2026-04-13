import copy
import json
import logging
from types import SimpleNamespace

import pytest

from py.config import config
from py.routes.handlers.model_handlers import ModelCivitaiHandler, ModelUpdateHandler
from py.services.service_registry import ServiceRegistry
from py.utils.metadata_manager import MetadataManager
from py.services.model_update_service import ModelUpdateRecord, ModelVersionRecord


class DummyScanner:
    def __init__(self, cache):
        self._cache = cache
        self._cancelled = False

    def is_cancelled(self) -> bool:
        return self._cancelled

    def reset_cancellation(self) -> None:
        self._cancelled = False

    async def get_cached_data(self):
        return self._cache


class DummyService:
    def __init__(self, cache):
        self.model_type = "lora"
        self.scanner = DummyScanner(cache)


class DummyUpdateService:
    def __init__(self, records):
        self.records = records
        self.calls = []

    async def refresh_for_model_type(
        self,
        model_type,
        scanner,
        provider,
        *,
        force_refresh=False,
        target_model_ids=None,
    ):
        self.calls.append(
            {
                "model_type": model_type,
                "scanner": scanner,
                "provider": provider,
                "force_refresh": force_refresh,
                "target_model_ids": target_model_ids,
            }
        )
        return self.records


@pytest.mark.asyncio
async def test_build_version_context_includes_static_urls():
    cache = SimpleNamespace(version_index={123: {"preview_url": "/tmp/previews/example.png"}})
    service = DummyService(cache)
    handler = ModelUpdateHandler(
        service=service,
        update_service=SimpleNamespace(),
        metadata_provider_selector=lambda *_: None,
        settings_service=SimpleNamespace(get=lambda *_: False),
        logger=logging.getLogger(__name__),
    )

    record = ModelUpdateRecord(
        model_type="lora",
        model_id=42,
        versions=[
            ModelVersionRecord(
                version_id=123,
                name=None,
                base_model=None,
                released_at=None,
                size_bytes=None,
                preview_url=None,
                is_in_library=True,
                should_ignore=False,
            )
        ],
        last_checked_at=None,
        should_ignore_model=False,
    )

    overrides = await handler._build_version_context(record)
    expected = config.get_preview_static_url("/tmp/previews/example.png")
    assert overrides == {
        123: {
            "file_path": None,
            "file_name": None,
            "preview_override": expected,
            "has_been_downloaded": False,
        }
    }


@pytest.mark.asyncio
async def test_build_version_context_includes_download_history(monkeypatch):
    cache = SimpleNamespace(version_index={})
    service = DummyService(cache)
    handler = ModelUpdateHandler(
        service=service,
        update_service=SimpleNamespace(),
        metadata_provider_selector=lambda *_: None,
        settings_service=SimpleNamespace(get=lambda *_: False),
        logger=logging.getLogger(__name__),
    )

    class DummyHistoryService:
        async def get_downloaded_version_ids(self, model_type, model_id):
            assert model_type == "lora"
            assert model_id == 42
            return [123]

    async def fake_history_service_factory():
        return DummyHistoryService()

    monkeypatch.setattr(
        ServiceRegistry,
        "get_downloaded_version_history_service",
        staticmethod(fake_history_service_factory),
    )

    record = ModelUpdateRecord(
        model_type="lora",
        model_id=42,
        versions=[
            ModelVersionRecord(
                version_id=123,
                name="Downloaded",
                base_model=None,
                released_at=None,
                size_bytes=None,
                preview_url=None,
                is_in_library=False,
                should_ignore=False,
            ),
            ModelVersionRecord(
                version_id=124,
                name="Fresh",
                base_model=None,
                released_at=None,
                size_bytes=None,
                preview_url=None,
                is_in_library=False,
                should_ignore=False,
            ),
        ],
        last_checked_at=None,
        should_ignore_model=False,
    )

    overrides = await handler._build_version_context(record)
    assert overrides[123]["has_been_downloaded"] is True
    assert overrides[124]["has_been_downloaded"] is False


@pytest.mark.asyncio
async def test_get_civitai_versions_degrades_when_download_history_unavailable(monkeypatch):
    cache = SimpleNamespace(version_index={})
    service = DummyService(cache)

    class DummyProvider:
        async def get_model_versions(self, model_id):
            assert model_id == "42"
            return {
                "type": "lora",
                "modelVersions": [
                    {
                        "id": 7,
                        "name": "Version 7",
                        "files": [],
                    }
                ],
            }

    async def fake_history_service_factory():
        raise RuntimeError("download history unavailable")

    monkeypatch.setattr(
        ServiceRegistry,
        "get_downloaded_version_history_service",
        staticmethod(fake_history_service_factory),
    )

    async def metadata_provider_factory():
        return DummyProvider()

    handler = ModelCivitaiHandler(
        service=service,
        settings_service=SimpleNamespace(get=lambda *_: False),
        ws_manager=SimpleNamespace(),
        logger=logging.getLogger(__name__),
        metadata_provider_factory=metadata_provider_factory,
        validate_model_type=lambda *_: True,
        expected_model_types=lambda: "LoRA",
        find_model_file=lambda *_: None,
        metadata_sync=SimpleNamespace(),
        metadata_refresh_use_case=SimpleNamespace(),
        metadata_progress_callback=lambda *_args, **_kwargs: None,
    )

    response = await handler.get_civitai_versions(
        SimpleNamespace(match_info={"model_id": "42"})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload[0]["id"] == 7
    assert payload[0]["existsLocally"] is False
    assert payload[0]["hasBeenDownloaded"] is False


@pytest.mark.asyncio
async def test_refresh_model_updates_filters_records_without_updates():
    cache = SimpleNamespace(version_index={})
    service = DummyService(cache)

    record_with_update = ModelUpdateRecord(
        model_type="lora",
        model_id=1,
        versions=[
            ModelVersionRecord(
                version_id=10,
                name="v1",
                base_model=None,
                released_at=None,
                size_bytes=None,
                preview_url=None,
                is_in_library=False,
                should_ignore=False,
            )
        ],
        last_checked_at=None,
        should_ignore_model=False,
    )
    record_without_update = ModelUpdateRecord(
        model_type="lora",
        model_id=2,
        versions=[
            ModelVersionRecord(
                version_id=20,
                name="v2",
                base_model=None,
                released_at=None,
                size_bytes=None,
                preview_url=None,
                is_in_library=True,
                should_ignore=False,
            )
        ],
        last_checked_at=None,
        should_ignore_model=False,
    )

    update_service = DummyUpdateService({1: record_with_update, 2: record_without_update})

    async def metadata_selector(name):
        assert name == "civitai_api"
        return object()

    handler = ModelUpdateHandler(
        service=service,
        update_service=update_service,
        metadata_provider_selector=metadata_selector,
        settings_service=SimpleNamespace(get=lambda *_: False),
        logger=logging.getLogger(__name__),
    )

    class DummyRequest:
        can_read_body = True
        query = {}

        async def json(self):
            return {}

    response = await handler.refresh_model_updates(DummyRequest())
    assert response.status == 200

    payload = json.loads(response.text)
    assert payload["success"] is True
    assert len(payload["records"]) == 1
    assert payload["records"][0]["modelId"] == 1
    assert payload["records"][0]["hasUpdate"] is True

    assert len(update_service.calls) == 1
    call = update_service.calls[0]
    assert call["model_type"] == "lora"
    assert call["scanner"] is service.scanner
    assert call["force_refresh"] is False
    assert call["provider"] is not None
    assert call["target_model_ids"] is None


@pytest.mark.asyncio
async def test_refresh_model_updates_with_target_ids():
    cache = SimpleNamespace(version_index={})
    service = DummyService(cache)

    record_with_update = ModelUpdateRecord(
        model_type="lora",
        model_id=1,
        versions=[
            ModelVersionRecord(
                version_id=10,
                name="v1",
                base_model=None,
                released_at=None,
                size_bytes=None,
                preview_url=None,
                is_in_library=False,
                should_ignore=False,
            )
        ],
        last_checked_at=None,
        should_ignore_model=False,
    )

    update_service = DummyUpdateService({1: record_with_update})

    async def metadata_selector(name):
        assert name == "civitai_api"
        return object()

    handler = ModelUpdateHandler(
        service=service,
        update_service=update_service,
        metadata_provider_selector=metadata_selector,
        settings_service=SimpleNamespace(get=lambda *_: False),
        logger=logging.getLogger(__name__),
    )

    class DummyRequest:
        can_read_body = True
        query = {}

        async def json(self):
            return {"modelIds": [1, "2", None]}

    response = await handler.refresh_model_updates(DummyRequest())
    assert response.status == 200

    call = update_service.calls[0]
    assert call["target_model_ids"] == [1, 2]


@pytest.mark.asyncio
async def test_refresh_model_updates_accepts_snake_case_ids():
    cache = SimpleNamespace(version_index={})
    service = DummyService(cache)

    record_with_update = ModelUpdateRecord(
        model_type="lora",
        model_id=3,
        versions=[
            ModelVersionRecord(
                version_id=30,
                name="v3",
                base_model=None,
                released_at=None,
                size_bytes=None,
                preview_url=None,
                is_in_library=False,
                should_ignore=False,
            )
        ],
        last_checked_at=None,
        should_ignore_model=False,
    )

    update_service = DummyUpdateService({3: record_with_update})

    async def metadata_selector(name):
        assert name == "civitai_api"
        return object()

    handler = ModelUpdateHandler(
        service=service,
        update_service=update_service,
        metadata_provider_selector=metadata_selector,
        settings_service=SimpleNamespace(get=lambda *_: False),
        logger=logging.getLogger(__name__),
    )

    class DummyRequest:
        can_read_body = True
        query = {}

        async def json(self):
            return {"model_ids": [3, "4", "abc", None]}

    response = await handler.refresh_model_updates(DummyRequest())
    assert response.status == 200

    call = update_service.calls[0]
    assert call["target_model_ids"] == [3, 4]


@pytest.mark.asyncio
async def test_fetch_missing_license_data_updates_metadata(monkeypatch):
    cache = SimpleNamespace(
        raw_data=[
            {"file_path": "/tmp/model1.safetensors", "civitai": {"modelId": 10}},
            {"file_path": "/tmp/model2.safetensors", "civitai": {"modelId": 10}},
            {"file_path": "/tmp/model3.safetensors", "civitai": {"modelId": 20}},
        ],
        version_index={},
    )

    metadata_store = {
        "/tmp/model1.safetensors": {"civitai": {"model": {}}},
        "/tmp/model2.safetensors": {"civitai": {"model": {}}},
        "/tmp/model3.safetensors": {"civitai": {"model": {}}},
    }

    async def fake_load(path: str):
        data = metadata_store.get(path)
        if data is None:
            return None, False
        return SimpleNamespace(to_dict=lambda: copy.deepcopy(data)), False

    saved: list[tuple[str, dict]] = []

    async def fake_save(path: str, metadata: dict):
        saved.append((path, copy.deepcopy(metadata)))
        return True

    monkeypatch.setattr(MetadataManager, "load_metadata", staticmethod(fake_load))
    monkeypatch.setattr(MetadataManager, "save_metadata", staticmethod(fake_save))

    provider_calls: list[list[int]] = []

    async def fake_bulk(model_ids):
        provider_calls.append(list(model_ids))
        return {
            10: {
                "allowNoCredit": True,
                "allowCommercialUse": ["Sell"],
                "allowDerivatives": True,
                "allowDifferentLicense": True,
            },
            20: {
                "allowNoCredit": False,
                "allowCommercialUse": ["Image"],
                "allowDerivatives": False,
                "allowDifferentLicense": False,
            },
        }

    provider = SimpleNamespace()
    provider.get_model_versions_bulk = fake_bulk

    async def metadata_selector(name):
        assert name == "civitai_api"
        return provider

    handler = ModelUpdateHandler(
        service=DummyService(cache),
        update_service=SimpleNamespace(),
        metadata_provider_selector=metadata_selector,
        settings_service=SimpleNamespace(get=lambda *_: False),
        logger=logging.getLogger(__name__),
    )

    class DummyRequest:
        can_read_body = True
        query = {}

        async def json(self):
            return {}

    response = await handler.fetch_missing_civitai_license_data(DummyRequest())
    assert response.status == 200

    payload = json.loads(response.text)
    assert payload["success"] is True
    assert len(payload["updated"]) == 3
    assert provider_calls == [[10, 20]]
    assert len(saved) == 3

    first_metadata = saved[0][1]
    assert first_metadata["civitai"]["model"]["allowNoCredit"] is True
    assert first_metadata["civitai"]["model"]["allowCommercialUse"] == ["Sell"]
    assert "missingModelIds" not in payload
    assert "errors" not in payload


@pytest.mark.asyncio
async def test_fetch_missing_license_data_filters_model_ids(monkeypatch):
    cache = SimpleNamespace(
        raw_data=[
            {"file_path": "/tmp/model1.safetensors", "civitai": {"modelId": 10}},
            {"file_path": "/tmp/model2.safetensors", "civitai": {"modelId": 20}},
        ],
        version_index={},
    )

    metadata_store = {
        "/tmp/model1.safetensors": {"civitai": {"model": {}}},
        "/tmp/model2.safetensors": {"civitai": {"model": {}}},
    }

    async def fake_load(path: str):
        data = metadata_store.get(path)
        if data is None:
            return None, False
        return SimpleNamespace(to_dict=lambda: copy.deepcopy(data)), False

    saved: list[tuple[str, dict]] = []

    async def fake_save(path: str, metadata: dict):
        saved.append((path, copy.deepcopy(metadata)))
        return True

    monkeypatch.setattr(MetadataManager, "load_metadata", staticmethod(fake_load))
    monkeypatch.setattr(MetadataManager, "save_metadata", staticmethod(fake_save))

    provider_calls: list[list[int]] = []

    async def fake_bulk(model_ids):
        provider_calls.append(list(model_ids))
        return {
            10: {
                "allowNoCredit": True,
                "allowCommercialUse": ["Sell"],
                "allowDerivatives": True,
                "allowDifferentLicense": True,
            },
            20: {
                "allowNoCredit": False,
                "allowCommercialUse": ["Image"],
                "allowDerivatives": False,
                "allowDifferentLicense": False,
            },
        }

    provider = SimpleNamespace()
    provider.get_model_versions_bulk = fake_bulk

    async def metadata_selector(name):
        assert name == "civitai_api"
        return provider

    handler = ModelUpdateHandler(
        service=DummyService(cache),
        update_service=SimpleNamespace(),
        metadata_provider_selector=metadata_selector,
        settings_service=SimpleNamespace(get=lambda *_: False),
        logger=logging.getLogger(__name__),
    )

    class DummyRequest:
        can_read_body = True
        query = {}

        async def json(self):
            return {"modelIds": [20]}

    response = await handler.fetch_missing_civitai_license_data(DummyRequest())
    assert response.status == 200

    payload = json.loads(response.text)
    assert payload["success"] is True
    assert len(payload["updated"]) == 1
    assert provider_calls == [[20]]
    assert len(saved) == 1
