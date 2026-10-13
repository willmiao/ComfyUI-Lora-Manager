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
    assert payload == {
        "success": True,
        "is_diffusion_model": True,
        "root_kind": "unet",
        # No rule matches "Anima", so the resolved root falls back to the
        # auto-configured default unet root.
        "resolved_root": get_settings_manager().get("default_unet_root"),
        "matched_rule": None,
    }


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
async def test_unknown_base_model_routes_to_unet_by_default():
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(
            {
                "model_type": "checkpoint",
                "base_model": "Brand New Arch",
                "file_types": ["Model"],
            }
        )
    )
    payload = json.loads(response.text)
    assert payload["is_diffusion_model"] is True
    assert payload["root_kind"] == "unet"


@pytest.mark.asyncio
async def test_unknown_base_model_honors_checkpoint_routing_setting():
    get_settings_manager().settings["unknown_base_model_routing"] = "checkpoint"

    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(
            {
                "model_type": "checkpoint",
                "base_model": "Brand New Arch",
                "file_types": ["Model"],
            }
        )
    )
    payload = json.loads(response.text)
    assert payload["is_diffusion_model"] is False
    assert payload["root_kind"] == "checkpoint"


@pytest.mark.asyncio
async def test_unet_model_type_uses_checkpoint_branch():
    """CivitAI ModelType.UNet has no branch of its own: it goes through the
    checkpoint branch, where its UNet-typed files route to the unet roots."""
    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(
            {"model_type": "unet", "base_model": "MiniMax H3", "file_types": ["UNet"]}
        )
    )
    payload = json.loads(response.text)
    assert payload["is_diffusion_model"] is True
    assert payload["root_kind"] == "unet"


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


@pytest.mark.asyncio
async def test_resolved_root_falls_back_to_default_root():
    manager = get_settings_manager()
    manager.settings["default_lora_root"] = "/loras-main"

    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "lora", "base_model": "Pony", "file_types": []})
    )
    payload = json.loads(response.text)
    assert payload["resolved_root"] == "/loras-main"


@pytest.mark.asyncio
async def test_resolved_root_applies_download_root_rules():
    manager = get_settings_manager()
    manager.settings["folder_paths"] = {"loras": ["/loras-main", "/lora-archive"]}
    manager.settings["default_lora_root"] = "/loras-main"
    manager.settings["download_root_rules"] = {
        "loras": [
            {"match_type": "base_model", "match": ["Flux.1 D"], "root": "/lora-archive"}
        ]
    }

    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "lora", "base_model": "Flux.1 D", "file_types": []})
    )
    payload = json.loads(response.text)
    assert payload["resolved_root"] == "/lora-archive"


@pytest.mark.asyncio
async def test_resolved_root_applies_unet_rules_after_diffusion_routing():
    manager = get_settings_manager()
    manager.settings["folder_paths"] = {"unet": ["/unet-main", "/unet-archive"]}
    manager.settings["default_unet_root"] = "/unet-main"
    manager.settings["download_root_rules"] = {
        "unet": [
            {"match_type": "base_model", "match": ["Flux.1 D"], "root": "/unet-archive"}
        ]
    }

    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(
            {"model_type": "checkpoint", "base_model": "Flux.1 D", "file_types": ["Model"]}
        )
    )
    payload = json.loads(response.text)
    assert payload["root_kind"] == "unet"
    assert payload["resolved_root"] == "/unet-archive"


@pytest.mark.asyncio
async def test_matched_rule_is_null_when_no_rule_matches():
    manager = get_settings_manager()
    manager.settings["default_lora_root"] = "/loras-main"

    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "lora", "base_model": "Pony", "file_types": []})
    )
    payload = json.loads(response.text)
    assert payload["matched_rule"] is None


@pytest.mark.asyncio
async def test_matched_rule_reports_base_model_hit():
    manager = get_settings_manager()
    manager.settings["folder_paths"] = {"loras": ["/loras-main", "/lora-archive"]}
    manager.settings["default_lora_root"] = "/loras-main"
    manager.settings["download_root_rules"] = {
        "loras": [
            {"match_type": "base_model", "match": ["Flux.1 D"], "root": "/lora-archive"}
        ]
    }

    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest({"model_type": "lora", "base_model": "Flux.1 D", "file_types": []})
    )
    payload = json.loads(response.text)
    assert payload["resolved_root"] == "/lora-archive"
    assert payload["matched_rule"] == {
        "match_type": "base_model",
        "match": ["Flux.1 D"],
    }


@pytest.mark.asyncio
async def test_matched_rule_reports_tag_hit_from_payload_tags():
    manager = get_settings_manager()
    manager.settings["folder_paths"] = {"loras": ["/loras-main", "/lora-archive"]}
    manager.settings["default_lora_root"] = "/loras-main"
    manager.settings["download_root_rules"] = {
        "loras": [
            {"match_type": "tag", "match": ["character"], "root": "/lora-archive"}
        ]
    }

    handler = DownloadRoutingHandler()
    response = await handler.get_download_routing(
        FakeRequest(
            {
                "model_type": "lora",
                "base_model": "Pony",
                "file_types": [],
                "tags": ["Style", "Character"],
            }
        )
    )
    payload = json.loads(response.text)
    assert payload["resolved_root"] == "/lora-archive"
    assert payload["matched_rule"] == {"match_type": "tag", "match": ["character"]}

    # Without a matching tag the same rule does not fire.
    response = await handler.get_download_routing(
        FakeRequest(
            {
                "model_type": "lora",
                "base_model": "Pony",
                "file_types": [],
                "tags": ["style"],
            }
        )
    )
    payload = json.loads(response.text)
    assert payload["resolved_root"] == "/loras-main"
    assert payload["matched_rule"] is None
