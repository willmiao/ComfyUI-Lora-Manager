import logging
from types import SimpleNamespace

import pytest

from py.config import config
from py.routes.handlers.model_handlers import ModelUpdateHandler
from py.services.model_update_service import ModelUpdateRecord, ModelVersionRecord


class DummyScanner:
    def __init__(self, cache):
        self._cache = cache

    async def get_cached_data(self):
        return self._cache


class DummyService:
    def __init__(self, cache):
        self.model_type = "lora"
        self.scanner = DummyScanner(cache)


@pytest.mark.asyncio
async def test_build_preview_overrides_uses_static_urls():
    cache = SimpleNamespace(version_index={123: {"preview_url": "/tmp/previews/example.png"}})
    service = DummyService(cache)
    handler = ModelUpdateHandler(
        service=service,
        update_service=SimpleNamespace(),
        metadata_provider_selector=lambda *_: None,
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

    overrides = await handler._build_preview_overrides(record)
    expected = config.get_preview_static_url("/tmp/previews/example.png")
    assert overrides == {123: expected}
