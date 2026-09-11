"""Tests for the download routing HTTP handler."""

import json

import pytest

from py.routes.handlers.download_routing_handlers import DownloadRoutingHandler


class FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.mark.asyncio
async def test_diffusion_base_model_routes_to_unet():
    """The reported Anima case: file type "Model", baseModel "Anima"."""
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(
            {"model_type": "checkpoint", "base_model": "Anima", "file_types": ["Model"]}
        )
    )
    payload = json.loads(response.text)
    assert response.status == 200
    assert payload == {"success": True, "is_diffusion_model": True, "root_kind": "unet"}


@pytest.mark.asyncio
async def test_unet_file_type_routes_to_unet():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(
            {"model_type": "checkpoint", "base_model": "SDXL 1.0", "file_types": ["UNet"]}
        )
    )
    payload = json.loads(response.text)
    assert payload["is_diffusion_model"] is True
    assert payload["root_kind"] == "unet"


@pytest.mark.asyncio
async def test_regular_checkpoint_stays_on_checkpoint_root():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(
            {"model_type": "checkpoint", "base_model": "SDXL 1.0", "file_types": ["Model"]}
        )
    )
    payload = json.loads(response.text)
    assert payload["is_diffusion_model"] is False
    assert payload["root_kind"] == "checkpoint"


@pytest.mark.asyncio
async def test_lora_is_never_diffusion():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "lora", "base_model": "Anima", "file_types": []})
    )
    payload = json.loads(response.text)
    assert payload["is_diffusion_model"] is False
    assert payload["root_kind"] == "lora"


@pytest.mark.asyncio
async def test_missing_model_type_rejected():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(FakeRequest({"base_model": "Anima"}))
    assert response.status == 400


@pytest.mark.asyncio
async def test_invalid_file_types_rejected():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "checkpoint", "file_types": "Model"})
    )
    assert response.status == 400


@pytest.mark.asyncio
async def test_invalid_json_rejected():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(json.JSONDecodeError("bad", "", 0))
    )
    assert response.status == 400
