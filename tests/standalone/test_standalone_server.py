"""Tests covering the standalone bootstrap flow."""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import List, Tuple

import pytest
from aiohttp import web

from py.utils.settings_paths import ensure_settings_file


ROUTE_CALLS_KEY: web.AppKey[List[Tuple[str, dict]]] = web.AppKey("route_calls")


@pytest.fixture
def standalone_module(monkeypatch) -> ModuleType:
    """Load the ``standalone`` module with a lightweight ``LoraManager`` stub."""

    import importlib
    import sys
    from types import ModuleType

    original_lora_manager = sys.modules.get("py.lora_manager")

    stub_module = ModuleType("py.lora_manager")

    class _StubLoraManager:
        @classmethod
        def add_routes(cls):  # pragma: no cover - compatibility shim
            return None

        @classmethod
        async def _initialize_services(cls):  # pragma: no cover - compatibility shim
            return None

        @classmethod
        async def _cleanup(cls, app):  # pragma: no cover - compatibility shim
            return None

    stub_module.LoraManager = _StubLoraManager
    sys.modules["py.lora_manager"] = stub_module

    module = importlib.import_module("standalone")
    yield module

    sys.modules.pop("standalone", None)
    if original_lora_manager is not None:
        sys.modules["py.lora_manager"] = original_lora_manager
    else:
        sys.modules.pop("py.lora_manager", None)


def _write_settings(contents: dict) -> Path:
    """Persist *contents* into the isolated settings.json."""

    settings_path = Path(ensure_settings_file())
    settings_path.write_text(json.dumps(contents))
    return settings_path


async def test_standalone_server_sets_up_routes(tmp_path, standalone_module):
    """``StandaloneServer.setup`` wires the HTTP routes and lifecycle hooks."""

    example_images_dir = tmp_path / "example_images"
    example_images_dir.mkdir()
    (example_images_dir / "preview.png").write_text("placeholder")

    _write_settings({"example_images_path": str(example_images_dir)})

    server = standalone_module.StandaloneServer()
    await server.setup()

    canonical_routes = {resource.canonical for resource in server.app.router.resources()}

    assert "/" in canonical_routes, "status endpoint should be registered"
    assert (
        "/example_images_static" in canonical_routes
    ), "static example image route should be exposed when the directory exists"
    assert server.app.on_startup, "startup callbacks must be attached"
    assert server.app.on_shutdown, "shutdown callbacks must be attached"


def test_standalone_server_raises_header_limits(standalone_module):
    """``StandaloneServer`` configures ``handler_args`` to tolerate large headers."""

    server = standalone_module.StandaloneServer()

    assert server.app._handler_args["max_field_size"] == standalone_module.HEADER_SIZE_LIMIT
    assert server.app._handler_args["max_line_size"] == standalone_module.HEADER_SIZE_LIMIT


def test_validate_settings_warns_for_missing_model_paths(caplog, standalone_module):
    """Missing model folders trigger the configuration warning."""

    caplog.set_level("WARNING")

    _write_settings(
        {
            "folder_paths": {
                "loras": ["/non/existent"],
                "checkpoints": [],
                "embeddings": [],
            }
        }
    )

    assert standalone_module.validate_settings() is True
    warning_lines = [record.message for record in caplog.records if record.levelname == "WARNING"]
    assert any("Standalone mode is using fallback" in line for line in warning_lines)
    assert any("Model folders need setup" in line for line in warning_lines)


def test_standalone_lora_manager_registers_routes(monkeypatch, tmp_path, standalone_module):
    """``StandaloneLoraManager.add_routes`` registers static and websocket routes."""

    app = web.Application()
    route_calls: List[Tuple[str, dict]] = []
    app[ROUTE_CALLS_KEY] = route_calls

    locales_dir = tmp_path / "locales"
    locales_dir.mkdir()
    static_dir = tmp_path / "static"
    static_dir.mkdir()

    monkeypatch.setattr(
        standalone_module,
        "config",
        SimpleNamespace(i18n_path=str(locales_dir), static_path=str(static_dir)),
    )

    register_calls: List[str] = []

    import py.services.model_service_factory as factory_module

    def fake_register_default_model_types() -> None:
        register_calls.append("called")

    monkeypatch.setattr(
        factory_module,
        "register_default_model_types",
        fake_register_default_model_types,
    )

    def fake_setup_all_routes(cls, app_arg):
        route_calls.append(("ModelServiceFactory.setup_all_routes", {"app": app_arg}))

    monkeypatch.setattr(
        factory_module.ModelServiceFactory,
        "setup_all_routes",
        classmethod(fake_setup_all_routes),
    )

    class DummyRecipeRoutes:
        @staticmethod
        def setup_routes(app_arg):
            route_calls.append(("RecipeRoutes", {}))

    class DummyUpdateRoutes:
        @staticmethod
        def setup_routes(app_arg):
            route_calls.append(("UpdateRoutes", {}))

    class DummyMiscRoutes:
        @staticmethod
        def setup_routes(app_arg):
            route_calls.append(("MiscRoutes", {}))

    class DummyExampleImagesRoutes:
        @staticmethod
        def setup_routes(app_arg, **kwargs):
            route_calls.append(("ExampleImagesRoutes", kwargs))

    class DummyPreviewRoutes:
        @staticmethod
        def setup_routes(app_arg):
            route_calls.append(("PreviewRoutes", {}))

    class DummyStatsRoutes:
        def setup_routes(self, app_arg):
            route_calls.append(("StatsRoutes", {}))

    monkeypatch.setattr("py.routes.recipe_routes.RecipeRoutes", DummyRecipeRoutes)
    monkeypatch.setattr("py.routes.update_routes.UpdateRoutes", DummyUpdateRoutes)
    monkeypatch.setattr("py.routes.misc_routes.MiscRoutes", DummyMiscRoutes)
    monkeypatch.setattr(
        "py.routes.example_images_routes.ExampleImagesRoutes",
        DummyExampleImagesRoutes,
    )
    monkeypatch.setattr("py.routes.preview_routes.PreviewRoutes", DummyPreviewRoutes)
    monkeypatch.setattr("py.routes.stats_routes.StatsRoutes", DummyStatsRoutes)

    async def _noop_ws_handler(request):
        return web.Response(status=204)

    ws_manager_stub = SimpleNamespace(
        handle_connection=_noop_ws_handler,
        handle_download_connection=_noop_ws_handler,
        handle_init_connection=_noop_ws_handler,
    )
    monkeypatch.setattr("py.services.websocket_manager.ws_manager", ws_manager_stub)

    server = SimpleNamespace(app=app)

    standalone_module.StandaloneLoraManager.add_routes(server)

    assert register_calls, "default model types should be registered"

    canonical_routes = {resource.canonical for resource in app.router.resources()}
    assert "/locales" in canonical_routes
    assert "/loras_static" in canonical_routes

    websocket_paths = {route.resource.canonical for route in app.router.routes() if "ws" in route.resource.canonical}
    assert {
        "/ws/fetch-progress",
        "/ws/download-progress",
        "/ws/init-progress",
    } <= websocket_paths

    assert any(call[0] == "ModelServiceFactory.setup_all_routes" for call in route_calls)
    assert any(call[0] == "RecipeRoutes" for call in route_calls)
    assert any(call[0] == "StatsRoutes" for call in route_calls)

    prompt_server = pytest.importorskip("server").PromptServer
    assert getattr(prompt_server, "instance", None) is server

    assert app.on_startup, "service initialization hook should be scheduled"
    assert app.on_shutdown, "cleanup hook should be scheduled"
