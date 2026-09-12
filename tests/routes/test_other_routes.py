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
