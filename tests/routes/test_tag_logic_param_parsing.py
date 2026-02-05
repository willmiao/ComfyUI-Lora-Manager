"""Tests for tag_logic parameter parsing in model handlers."""

import pytest
from unittest.mock import Mock
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import sys
import types

folder_paths_stub = types.SimpleNamespace(get_folder_paths=lambda *_: [])
sys.modules.setdefault("folder_paths", folder_paths_stub)

from py.routes.handlers.model_handlers import ModelListingHandler


class MockService:
    """Mock service for testing."""

    def __init__(self):
        self.model_type = "test-model"

    async def get_paginated_data(self, **kwargs):
        # Store the kwargs for verification
        self.last_call_kwargs = kwargs
        return {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
        }

    async def format_response(self, item):
        return item


def parse_specific_params(request):
    """No specific params for testing."""
    return {}


@pytest.fixture
def handler():
    service = MockService()
    logger = Mock()
    return ModelListingHandler(
        service=service,
        parse_specific_params=parse_specific_params,
        logger=logger,
    ), service


async def make_request(handler, query_string=""):
    """Helper to create a request and call get_models."""
    app = web.Application()

    async def test_handler(request):
        return await handler.get_models(request)

    app.router.add_get("/test", test_handler)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        response = await client.get(f"/test?{query_string}")
        return response
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_tag_logic_param_default_is_any(handler):
    """Test that tag_logic defaults to 'any' when not provided."""
    h, service = handler

    response = await make_request(h, "tag_include=anime&tag_include=realistic")
    assert response.status == 200

    # Verify tag_logic was set to 'any' by default
    assert service.last_call_kwargs["tag_logic"] == "any"


@pytest.mark.asyncio
async def test_tag_logic_param_explicit_any(handler):
    """Test that tag_logic='any' is correctly parsed."""
    h, service = handler

    response = await make_request(h, "tag_include=anime&tag_logic=any")
    assert response.status == 200

    assert service.last_call_kwargs["tag_logic"] == "any"


@pytest.mark.asyncio
async def test_tag_logic_param_explicit_all(handler):
    """Test that tag_logic='all' is correctly parsed."""
    h, service = handler

    response = await make_request(h, "tag_include=anime&tag_include=realistic&tag_logic=all")
    assert response.status == 200

    assert service.last_call_kwargs["tag_logic"] == "all"


@pytest.mark.asyncio
async def test_tag_logic_param_case_insensitive(handler):
    """Test that tag_logic values are case insensitive."""
    h, service = handler

    # Test uppercase
    response = await make_request(h, "tag_logic=ALL")
    assert response.status == 200
    assert service.last_call_kwargs["tag_logic"] == "all"

    # Test mixed case
    response = await make_request(h, "tag_logic=Any")
    assert response.status == 200
    assert service.last_call_kwargs["tag_logic"] == "any"


@pytest.mark.asyncio
async def test_tag_logic_param_invalid_value_defaults_to_any(handler):
    """Test that invalid tag_logic values default to 'any'."""
    h, service = handler

    response = await make_request(h, "tag_logic=invalid")
    assert response.status == 200

    # Should default to 'any' for invalid values
    assert service.last_call_kwargs["tag_logic"] == "any"


@pytest.mark.asyncio
async def test_tag_logic_param_with_other_filters(handler):
    """Test that tag_logic works correctly with other filter parameters."""
    h, service = handler

    query = (
        "tag_include=anime&"
        "tag_include=character&"
        "tag_exclude=nsfw&"
        "base_model=SDXL&"
        "tag_logic=all"
    )
    response = await make_request(h, query)
    assert response.status == 200

    assert service.last_call_kwargs["tag_logic"] == "all"
    assert service.last_call_kwargs["base_models"] == ["SDXL"]
    assert "anime" in service.last_call_kwargs["tags"]
    assert "character" in service.last_call_kwargs["tags"]
    assert "nsfw" in service.last_call_kwargs["tags"]


@pytest.mark.asyncio
async def test_tag_logic_without_include_tags(handler):
    """Test that tag_logic is still passed even without include tags."""
    h, service = handler

    response = await make_request(h, "tag_logic=all&base_model=SDXL")
    assert response.status == 200

    # tag_logic should still be set even without tag filters
    assert service.last_call_kwargs["tag_logic"] == "all"
