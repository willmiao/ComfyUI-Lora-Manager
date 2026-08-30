"""Tests for the loader-pool endpoint backing the Checkpoint/Unet Loader
nodes' front-end base_model filtering.
"""

import json

import pytest

from py.routes.checkpoint_routes import CheckpointRoutes
from py.services.service_registry import ServiceRegistry


class _FakeCache:
    def __init__(self, raw_data):
        self.raw_data = raw_data


class _FakeScanner:
    def __init__(self, raw_data, model_roots):
        self._raw_data = raw_data
        self._model_roots = model_roots

    async def get_cached_data(self, force_refresh=False):
        return _FakeCache(self._raw_data)

    def get_model_roots(self):
        return self._model_roots


class DummyRequest:
    def __init__(self, query=None):
        self.query = query or {}


@pytest.fixture
def routes(tmp_path, monkeypatch):
    existing = tmp_path / "flux.safetensors"
    existing.write_bytes(b"x")
    missing = tmp_path / "missing.safetensors"  # referenced but never created

    raw_data = [
        {"sub_type": "checkpoint", "file_path": str(existing), "base_model": "Flux.1 D"},
        {"sub_type": "checkpoint", "file_path": str(missing), "base_model": "SDXL 1.0"},
        {
            "sub_type": "diffusion_model",
            "file_path": str(existing),
            "base_model": "Flux.1 D",
        },
    ]

    async def _fake_scanner():
        return _FakeScanner(raw_data, [str(tmp_path)])

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _fake_scanner)
    return CheckpointRoutes()


async def test_loader_pool_checkpoint_subtype(routes):
    response = await routes.get_loader_pool(DummyRequest(query={"sub_type": "checkpoint"}))
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload == {
        "items": [{"name": "flux.safetensors", "base_model": "Flux.1 D"}]
    }


async def test_loader_pool_diffusion_model_subtype(routes):
    response = await routes.get_loader_pool(
        DummyRequest(query={"sub_type": "diffusion_model"})
    )
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload == {
        "items": [{"name": "flux.safetensors", "base_model": "Flux.1 D"}]
    }


async def test_loader_pool_default_subtype_is_checkpoint(routes):
    response = await routes.get_loader_pool(DummyRequest())
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload == {
        "items": [{"name": "flux.safetensors", "base_model": "Flux.1 D"}]
    }


async def test_loader_pool_invalid_subtype(routes):
    response = await routes.get_loader_pool(DummyRequest(query={"sub_type": "lora"}))
    assert response.status == 400
