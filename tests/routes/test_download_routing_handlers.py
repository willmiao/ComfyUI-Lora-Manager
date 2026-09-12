"""Tests for the download routing HTTP handler."""

import json

import pytest

from py.routes.handlers.download_routing_handlers import DownloadRoutingHandler
from py.services.settings_manager import get_settings_manager


@pytest.fixture(autouse=True)
def enable_other_models():
    """Other Models is opt-in; enable every sub_type for the routing tests."""
    manager = get_settings_manager()
    manager.settings["enable_other_models"] = True
    manager.settings["enabled_other_sub_types"] = [
        "vae",
        "upscaler",
        "text_encoder",
        "clip_vision",
        "controlnet",
    ]
    yield


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


@pytest.mark.asyncio
async def test_other_model_type_returns_sub_type():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "TextEncoder", "file_types": ["Model"]})
    )
    payload = json.loads(response.text)
    assert response.status == 200
    assert payload == {"success": True, "root_kind": "other", "sub_type": "text_encoder"}


@pytest.mark.asyncio
async def test_other_explicit_file_pick_wins():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(
            {
                "model_type": "Other",
                "file_types": ["Model"],
                "selected_file_type": "VAE",
            }
        )
    )
    payload = json.loads(response.text)
    assert payload["root_kind"] == "other"
    assert payload["sub_type"] == "vae"


@pytest.mark.asyncio
async def test_other_file_type_fallback_when_model_type_unmapped():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "Other", "file_types": ["Model", "Upscaler"]})
    )
    payload = json.loads(response.text)
    assert payload["sub_type"] == "upscaler"


@pytest.mark.asyncio
async def test_other_undecidable_sub_type_is_none():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "Other", "file_types": ["Model"]})
    )
    payload = json.loads(response.text)
    assert response.status == 200
    assert payload == {"success": True, "root_kind": "other", "sub_type": None}


@pytest.mark.asyncio
async def test_other_invalid_selected_file_type_rejected():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "VAE", "selected_file_type": 123})
    )
    assert response.status == 400


@pytest.mark.asyncio
async def test_other_routing_disabled_when_feature_off():
    get_settings_manager().settings["enable_other_models"] = False

    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "VAE", "file_types": ["Model"]})
    )
    payload = json.loads(response.text)
    assert payload["sub_type"] is None
    assert payload["disabled"] is True
    assert payload["reason"] == "other_models_disabled"


@pytest.mark.asyncio
async def test_other_routing_disabled_for_switched_off_sub_type():
    get_settings_manager().settings["enabled_other_sub_types"] = ["vae"]

    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "Upscaler", "file_types": ["Model"]})
    )
    payload = json.loads(response.text)
    assert payload["sub_type"] is None
    assert payload["disabled"] is True
    assert payload["reason"] == "other_sub_type_disabled"
    assert payload["requested_sub_type"] == "upscaler"
