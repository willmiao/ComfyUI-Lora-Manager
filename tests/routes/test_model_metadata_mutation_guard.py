"""Guard metadata mutations against stale model paths."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from py.routes.handlers.model_handlers import ModelManagementHandler


class FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def make_handler() -> ModelManagementHandler:
    metadata_sync = SimpleNamespace(
        save_metadata_updates=AsyncMock(return_value={"tags": ["new"]}),
        load_local_metadata=AsyncMock(return_value={}),
    )
    return ModelManagementHandler(
        service=SimpleNamespace(scanner=SimpleNamespace(update_single_model_cache=AsyncMock())),
        logger=logging.getLogger(__name__),
        metadata_sync=metadata_sync,
        preview_service=None,
        tag_update_service=SimpleNamespace(add_tags=AsyncMock(return_value=(["new"], []))),
        lifecycle_service=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["save_metadata", "add_tags"])
async def test_missing_model_does_not_create_ghost_sidecar(tmp_path, method_name):
    model_path = tmp_path / "old-folder" / "model.safetensors"
    sidecar_path = model_path.with_suffix(".metadata.json")
    handler = make_handler()

    response = await getattr(handler, method_name)(
        FakeRequest({"file_path": str(model_path), "tags": ["new"]})
    )

    assert response.status == 409
    assert json.loads(response.text)["success"] is False
    assert not sidecar_path.exists()
    assert not model_path.parent.exists()
    handler._metadata_sync.save_metadata_updates.assert_not_called()
    handler._tag_update_service.add_tags.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["save_metadata", "add_tags"])
async def test_existing_model_can_update_metadata(tmp_path, method_name):
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(b"model")
    handler = make_handler()

    response = await getattr(handler, method_name)(
        FakeRequest({"file_path": str(model_path), "tags": ["new"]})
    )

    assert response.status == 200
    assert json.loads(response.text)["success"] is True
    if method_name == "save_metadata":
        handler._metadata_sync.save_metadata_updates.assert_awaited_once()
        handler._tag_update_service.add_tags.assert_not_called()
    else:
        handler._tag_update_service.add_tags.assert_awaited_once()
        handler._metadata_sync.save_metadata_updates.assert_not_called()
