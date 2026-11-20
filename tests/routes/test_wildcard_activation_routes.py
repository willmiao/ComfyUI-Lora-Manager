from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from py.routes.wildcard_routes import WildcardRoutes
from py.services import wildcard_service as runtime_module
from py.services.wildcard_activation_service import WildcardActivationService
from py.services.wildcard_parser import parse_wildcard_artifact
from py.services.wildcard_service import WildcardService


@pytest.mark.asyncio
async def test_activation_endpoints_use_shared_resource_and_runtime(tmp_path, monkeypatch):
    artifact = tmp_path / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    parsed = parse_wildcard_artifact(str(artifact))
    raw = {
        "file_path": str(artifact),
        "file_name": "colors",
        "model_name": "Colors",
        "wildcard_format": "txt",
        "folder": "",
        "entries": [entry.summary() for entry in parsed.entries],
        "entry_count": 1,
        "value_count": 2,
    }
    cache = SimpleNamespace(raw_data=[raw])

    class Scanner:
        async def get_cached_data(self):
            return cache

        def get_model_roots(self):
            return [str(tmp_path)]

    activation = WildcardActivationService(str(tmp_path / "activations.json"))

    class Service:
        scanner = Scanner()

        async def format_response(self, resource):
            return activation.decorate(resource)

    routes = WildcardRoutes(activation_service=activation)
    routes.service = Service()
    app = web.Application()
    app.router.add_get("/api/lm/wildcards/active", routes.get_active)
    app.router.add_post("/api/lm/wildcards/activate", routes.activate)
    app.router.add_post("/api/lm/wildcards/deactivate", routes.deactivate)
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / "example.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    monkeypatch.setattr(runtime_module, "get_wildcards_dir", lambda create=False: str(manual_dir))
    monkeypatch.setattr(
        "py.services.wildcard_activation_service.get_wildcard_activation_service",
        lambda: activation,
    )
    runtime = WildcardService()
    runtime._cached_signature = None
    runtime._manual_cached_signature = None

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/lm/wildcards/activate",
            json={"file_path": str(artifact), "namespace": "palette"},
        )
        assert response.status == 200, await response.text()
        assert (await response.json())["resource"]["active"] is True
        assert runtime.expand_text("__palette/colors__", seed=0) in ("red", "blue")

        response = await client.get("/api/lm/wildcards/active")
        payload = await response.json()
        assert payload["resources"][0]["active"] is True
        assert payload["resources"][0]["entries"][0]["effective_key"] == "palette/colors"
        assert payload["resources"][0]["wildcard_format"] == "txt"
        assert "activation_aliases" in payload["resources"][0]
        manual_entry = payload["manual"]["entries"][0]
        assert manual_entry["key"] == "example"
        assert manual_entry["values_count"] == 4
        assert manual_entry["source_path"].endswith("example.txt")
        assert manual_entry["sample_values"] == ["one", "two", "three"]

        response = await client.post(
            "/api/lm/wildcards/deactivate", json={"file_path": str(artifact)}
        )
        assert response.status == 200
        wildcards = runtime.get_wildcard_dict()
        assert "palette/colors" not in wildcards
        assert wildcards["example"] == ["one", "two", "three", "four"]

        # Deactivation keeps the activation settings for a later reactivation.
        response = await client.get("/api/lm/wildcards/active")
        payload = await response.json()
        assert payload["resources"][0]["active"] is False
        assert payload["resources"][0]["activation_namespace"] == "palette"

        response = await client.post(
            "/api/lm/wildcards/activate", json={"file_path": str(artifact)}
        )
        assert response.status == 200
        reactivated = (await response.json())["resource"]
        assert reactivated["active"] is True
        assert reactivated["activation_namespace"] == "palette"

        await client.post(
            "/api/lm/wildcards/deactivate", json={"file_path": str(artifact)}
        )
