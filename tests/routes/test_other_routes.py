import json

import pytest
from aiohttp import web

from py.routes.other_routes import OtherRoutes
from py.services.other_model_service import OtherModelService


class DummyRequest:
    def __init__(self, *, match_info=None):
        self.match_info = match_info or {}


class StubOtherModelService:
    def __init__(self):
        self.info = {}

    async def get_model_info_by_name(self, name):
        value = self.info.get(name)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def routes():
    handler = OtherRoutes()
    handler.service = StubOtherModelService()  # pyright: ignore[reportAttributeAccessIssue]
    return handler


@pytest.fixture(autouse=True)
def enable_other_models():
    """Other Models is opt-in; these tests exercise the enabled state."""
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    manager.set("enable_other_models", True)
    manager.set(
        "enabled_other_sub_types",
        ["vae", "upscaler", "text_encoder", "clip_vision", "controlnet"],
    )
    yield


def test_common_and_specific_routes_registered():
    """Registration smoke test: /api/lm/other/* surface plus the /other page."""
    app = web.Application()
    OtherRoutes().setup_routes(app)

    registered = {(route.method, route.resource.canonical) for route in app.router.routes()}

    assert ("GET", "/other") in registered
    assert ("GET", "/api/lm/other/list") in registered
    assert ("GET", "/api/lm/other/model-types") in registered
    assert ("GET", "/api/lm/other/roots") in registered
    assert ("POST", "/api/lm/other/fetch-civitai") in registered
    assert ("POST", "/api/lm/other/delete") in registered
    assert ("POST", "/api/lm/other/move_model") in registered
    assert ("GET", "/api/lm/other/info/{name}") in registered


def test_template_name_is_other_page():
    assert OtherRoutes().template_name == "other.html"


@pytest.mark.parametrize(
    "model_type",
    ["VAE", "Upscaler", "TextEncoder", "CLIP", "CLIPVision", "Controlnet", "Other"],
)
def test_validate_civitai_model_type_accepts_other_types(model_type):
    assert OtherRoutes()._validate_civitai_model_type(model_type) is True


@pytest.mark.parametrize("model_type", ["Lora", "Checkpoint", "TextualInversion"])
def test_validate_civitai_model_type_rejects_foreign_types(model_type):
    assert OtherRoutes()._validate_civitai_model_type(model_type) is False


def test_validate_rejects_everything_when_feature_disabled():
    from py.services.settings_manager import get_settings_manager

    get_settings_manager().set("enable_other_models", False)

    handler = OtherRoutes()
    for model_type in ("VAE", "Upscaler", "TextEncoder", "CLIPVision", "Other"):
        assert handler._validate_civitai_model_type(model_type) is False


def test_validate_rejects_switched_off_sub_type():
    from py.services.settings_manager import get_settings_manager

    get_settings_manager().set("enabled_other_sub_types", ["vae"])

    handler = OtherRoutes()
    assert handler._validate_civitai_model_type("VAE") is True
    assert handler._validate_civitai_model_type("Upscaler") is False


def test_page_context_reports_feature_state(monkeypatch):
    from py.config import config
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    handler = OtherRoutes()
    provider = handler._get_page_context_provider()

    monkeypatch.setattr(config, "other_roots", ["/models/vae"], raising=False)
    context = provider(None)
    assert context["other_disabled"] is False
    assert context["other_no_paths"] is False

    # Enabled but nothing resolved: the page must explain how to fix it.
    monkeypatch.setattr(config, "other_roots", [], raising=False)
    context = provider(None)
    assert context["other_disabled"] is False
    assert context["other_no_paths"] is True

    manager.set("enable_other_models", False)
    assert provider(None) == {"other_disabled": True, "other_no_paths": False}


def test_get_expected_model_types_mentions_supported_types():
    expected = OtherRoutes()._get_expected_model_types()
    for name in ("VAE", "Upscaler", "TextEncoder", "CLIPVision", "Controlnet"):
        assert name in expected


async def test_get_other_model_info_success(routes):
    routes.service.info["demo"] = {"name": "demo"}
    response = await routes.get_other_model_info(DummyRequest(match_info={"name": "demo"}))
    payload = json.loads(response.text)
    assert payload == {"name": "demo"}


async def test_get_other_model_info_missing(routes):
    response = await routes.get_other_model_info(DummyRequest(match_info={"name": "missing"}))
    payload = json.loads(response.text)
    assert response.status == 404
    assert payload == {"error": "Model not found"}


async def test_get_other_model_info_error(routes):
    routes.service.info["demo"] = RuntimeError("boom")
    response = await routes.get_other_model_info(DummyRequest(match_info={"name": "demo"}))
    payload = json.loads(response.text)
    assert response.status == 500
    assert payload == {"error": "boom"}


@pytest.mark.asyncio
async def test_initialize_services_builds_other_model_service(monkeypatch):
    from py.services.service_registry import ServiceRegistry

    sentinel_scanner = object()
    sentinel_update_service = object()

    async def fake_scanner():
        return sentinel_scanner

    async def fake_update_service():
        return sentinel_update_service

    monkeypatch.setattr(ServiceRegistry, "get_other_scanner", staticmethod(fake_scanner))
    monkeypatch.setattr(
        ServiceRegistry, "get_model_update_service", staticmethod(fake_update_service)
    )

    handler = OtherRoutes()
    await handler.initialize_services()

    assert isinstance(handler.service, OtherModelService)
    assert handler.service.model_type == "other"
    assert handler.service.scanner is sentinel_scanner


def test_roots_by_subtype_route_registered():
    app = web.Application()
    OtherRoutes().setup_routes(app)

    registered = {(route.method, route.resource.canonical) for route in app.router.routes()}

    assert ("GET", "/api/lm/other/roots_by_subtype") in registered


async def test_get_roots_by_subtype_aggregates_folder_keys(monkeypatch):
    """text_encoders and the legacy clip key both land under text_encoder."""
    from py.config import config

    monkeypatch.setattr(
        config,
        "other_folder_roots",
        {
            "vae": ["/models/vae", "/models/vae2"],
            "text_encoders": ["/models/text_encoders"],
            "clip": ["/models/clip_legacy"],
            "upscale_models": ["/models/upscale"],
            "unknown_key": ["/models/ignored"],
        },
    )

    response = await OtherRoutes().get_roots_by_subtype(DummyRequest())
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert payload["roots_by_subtype"] == {
        "vae": ["/models/vae", "/models/vae2"],
        "text_encoder": ["/models/text_encoders", "/models/clip_legacy"],
        "upscaler": ["/models/upscale"],
    }


async def test_get_roots_by_subtype_empty_config(monkeypatch):
    from py.config import config

    monkeypatch.setattr(config, "other_folder_roots", {})

    response = await OtherRoutes().get_roots_by_subtype(DummyRequest())
    payload = json.loads(response.text)

    assert payload == {"success": True, "roots_by_subtype": {}}
