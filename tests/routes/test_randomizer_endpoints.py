import json
from unittest.mock import MagicMock

import pytest

from py.routes.lora_routes import LoraRoutes


class DummyRequest:
    def __init__(self, *, query=None, match_info=None, json_data=None):
        self.query = query or {}
        self.match_info = match_info or {}
        self._json_data = json_data or {}

    async def json(self):
        return self._json_data


class StubLoraService:
    """Stub service for testing randomizer endpoints"""

    def __init__(self):
        self.random_loras = []
        self.last_get_random_loras_kwargs = {}

    async def get_random_loras(self, **kwargs):
        self.last_get_random_loras_kwargs = kwargs
        return self.random_loras


@pytest.fixture
def routes():
    handler = LoraRoutes()
    handler.service = StubLoraService()
    return handler


async def test_get_random_loras_success(routes):
    """Test successful random LoRA generation"""
    routes.service.random_loras = [
        {
            "name": "test_lora_1",
            "strength": 0.8,
            "clipStrength": 0.8,
            "active": True,
            "expanded": False,
            "locked": False,
        },
        {
            "name": "test_lora_2",
            "strength": 0.6,
            "clipStrength": 0.6,
            "active": True,
            "expanded": False,
            "locked": False,
        },
    ]

    request = DummyRequest(
        json_data={
            "count": 5,
            "model_strength_min": 0.5,
            "model_strength_max": 1.0,
            "use_same_clip_strength": True,
            "locked_loras": [],
        }
    )

    response = await routes.get_random_loras(request)
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert "loras" in payload
    assert payload["count"] == 2


async def test_get_random_loras_with_range(routes):
    """Test random LoRAs with count range"""
    routes.service.random_loras = [
        {
            "name": "test_lora_1",
            "strength": 0.8,
            "clipStrength": 0.8,
            "active": True,
            "expanded": False,
            "locked": False,
        }
    ]

    request = DummyRequest(
        json_data={
            "count_min": 3,
            "count_max": 7,
            "model_strength_min": 0.0,
            "model_strength_max": 1.0,
            "use_same_clip_strength": True,
        }
    )

    response = await routes.get_random_loras(request)
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True


async def test_get_random_loras_invalid_count(routes):
    """Test invalid count parameter"""
    request = DummyRequest(
        json_data={
            "count": 150,  # Over limit
            "model_strength_min": 0.0,
            "model_strength_max": 1.0,
        }
    )

    response = await routes.get_random_loras(request)
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False
    assert "Count must be between 1 and 100" in payload["error"]


async def test_get_random_loras_invalid_strength(routes):
    """Test invalid strength range"""
    request = DummyRequest(
        json_data={
            "count": 5,
            "model_strength_min": -11,  # Invalid (below -10)
            "model_strength_max": 1.0,
        }
    )

    response = await routes.get_random_loras(request)
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False
    assert "Model strength must be between -10 and 10" in payload["error"]


async def test_get_random_loras_with_locked(routes):
    """Test random LoRAs with locked items"""
    routes.service.random_loras = [
        {
            "name": "new_lora",
            "strength": 0.7,
            "clipStrength": 0.7,
            "active": True,
            "expanded": False,
            "locked": False,
        },
        {
            "name": "locked_lora",
            "strength": 0.9,
            "clipStrength": 0.9,
            "active": True,
            "expanded": False,
            "locked": True,
        },
    ]

    request = DummyRequest(
        json_data={
            "count": 5,
            "model_strength_min": 0.5,
            "model_strength_max": 1.0,
            "use_same_clip_strength": True,
            "locked_loras": [
                {
                    "name": "locked_lora",
                    "strength": 0.9,
                    "clipStrength": 0.9,
                    "active": True,
                    "expanded": False,
                    "locked": True,
                }
            ],
        }
    )

    response = await routes.get_random_loras(request)
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True


async def test_get_random_loras_error(routes, monkeypatch):
    """Test error handling"""

    async def failing(*_args, **_kwargs):
        raise RuntimeError("Service error")

    routes.service.get_random_loras = failing
    request = DummyRequest(json_data={"count": 5})

    response = await routes.get_random_loras(request)
    payload = json.loads(response.text)

    assert response.status == 500
    assert payload["success"] is False
    assert "error" in payload


async def test_get_random_loras_with_recommended_strength_enabled(routes):
    """Test random LoRAs with recommended strength feature enabled"""
    request = DummyRequest(
        json_data={
            "count": 5,
            "model_strength_min": 0.5,
            "model_strength_max": 1.0,
            "use_same_clip_strength": True,
            "use_recommended_strength": True,
            "recommended_strength_scale_min": 0.6,
            "recommended_strength_scale_max": 0.8,
            "locked_loras": [],
        }
    )

    response = await routes.get_random_loras(request)
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True

    # Verify parameters were passed to service
    kwargs = routes.service.last_get_random_loras_kwargs
    assert kwargs["use_recommended_strength"] is True
    assert kwargs["recommended_strength_scale_min"] == 0.6
    assert kwargs["recommended_strength_scale_max"] == 0.8


async def test_get_random_loras_with_recommended_strength_disabled(routes):
    """Test random LoRAs with recommended strength feature disabled (default)"""
    request = DummyRequest(
        json_data={
            "count": 5,
            "model_strength_min": 0.5,
            "model_strength_max": 1.0,
            "use_same_clip_strength": True,
            "locked_loras": [],
        }
    )

    response = await routes.get_random_loras(request)
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True

    # Verify default parameters were passed to service
    kwargs = routes.service.last_get_random_loras_kwargs
    assert kwargs["use_recommended_strength"] is False
    assert kwargs["recommended_strength_scale_min"] == 0.5
    assert kwargs["recommended_strength_scale_max"] == 1.0
