"""Smoke tests for the recipe routing scaffolding.

The cases keep the registrar/controller contract aligned with
``docs/architecture/recipe_routes.md`` so future refactors can focus on handler
logic.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from collections import Counter
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

import pytest
from aiohttp import web


REPO_ROOT = Path(__file__).resolve().parents[2]
PY_PACKAGE_PATH = REPO_ROOT / "py"

spec = importlib.util.spec_from_file_location(
    "py_local",
    PY_PACKAGE_PATH / "__init__.py",
    submodule_search_locations=[str(PY_PACKAGE_PATH)],
)
py_local = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(py_local)
sys.modules.setdefault("py_local", py_local)

base_routes_module = importlib.import_module("py_local.routes.base_recipe_routes")
recipe_routes_module = importlib.import_module("py_local.routes.recipe_routes")
registrar_module = importlib.import_module("py_local.routes.recipe_route_registrar")


@pytest.fixture(autouse=True)
def reset_service_registry(monkeypatch: pytest.MonkeyPatch):
    """Ensure each test starts from a clean registry state."""

    services_module = importlib.import_module("py_local.services.service_registry")
    registry = services_module.ServiceRegistry
    previous_services = dict(registry._services)
    previous_locks = dict(registry._locks)
    registry._services.clear()
    registry._locks.clear()
    try:
        yield
    finally:
        registry._services = previous_services
        registry._locks = previous_locks


def _make_stub_scanner():
    class _StubScanner:
        def __init__(self):
            self._cache = types.SimpleNamespace()

            async def _lora_get_cached_data():  # pragma: no cover - smoke hook
                return None

            self._lora_scanner = types.SimpleNamespace(
                get_cached_data=_lora_get_cached_data,
                _hash_index=types.SimpleNamespace(_hash_to_path={}),
            )

        async def get_cached_data(self, force_refresh: bool = False):
            return self._cache

    return _StubScanner()


def test_attach_dependencies_resolves_services_once(monkeypatch: pytest.MonkeyPatch):
    base_module = base_routes_module
    services_module = importlib.import_module("py_local.services.service_registry")
    registry = services_module.ServiceRegistry
    server_i18n = importlib.import_module("py_local.services.server_i18n").server_i18n

    scanner = _make_stub_scanner()
    civitai_client = object()
    filter_calls = Counter()

    async def fake_get_recipe_scanner():
        return scanner

    async def fake_get_civitai_client():
        return civitai_client

    def fake_create_filter():
        filter_calls["create_filter"] += 1
        return object()

    monkeypatch.setattr(registry, "get_recipe_scanner", fake_get_recipe_scanner)
    monkeypatch.setattr(registry, "get_civitai_client", fake_get_civitai_client)
    monkeypatch.setattr(server_i18n, "create_template_filter", fake_create_filter)

    async def scenario():
        routes = base_module.BaseRecipeRoutes()

        await routes.attach_dependencies()
        await routes.attach_dependencies()  # idempotent

        assert routes.recipe_scanner is scanner
        assert routes.lora_scanner is scanner._lora_scanner
        assert routes.civitai_client is civitai_client
        assert routes.template_env.filters["t"] is not None
        assert filter_calls["create_filter"] == 1

    asyncio.run(scenario())


def test_register_startup_hooks_appends_once():
    routes = base_routes_module.BaseRecipeRoutes()

    app = web.Application()
    routes.register_startup_hooks(app)
    routes.register_startup_hooks(app)

    startup_bound_to_routes = [
        callback for callback in app.on_startup if getattr(callback, "__self__", None) is routes
    ]

    assert routes.attach_dependencies in startup_bound_to_routes
    assert routes.prewarm_cache in startup_bound_to_routes
    assert len(startup_bound_to_routes) == 2


def test_to_route_mapping_uses_handler_owner(monkeypatch: pytest.MonkeyPatch):
    class DummyOwner:
        async def render_page(self, request):
            return web.Response(text="ok")

        async def list_recipes(self, request):  # pragma: no cover - invoked via mapping
            return web.json_response({})

    class DummyRoutes(base_routes_module.BaseRecipeRoutes):
        def get_handler_owner(self):  # noqa: D401 - simple override for test
            return DummyOwner()

    monkeypatch.setattr(
        base_routes_module.BaseRecipeRoutes,
        "_HANDLER_NAMES",
        ("render_page", "list_recipes"),
    )

    routes = DummyRoutes()
    mapping = routes.to_route_mapping()

    assert set(mapping.keys()) == {"render_page", "list_recipes"}
    assert asyncio.iscoroutinefunction(mapping["render_page"])
    # Cached mapping reused on subsequent calls
    assert routes.to_route_mapping() is mapping


def test_recipe_route_registrar_binds_every_route():
    class FakeRouter:
        def __init__(self):
            self.calls: list[tuple[str, str, Callable[..., Awaitable[Any]]]] = []

        def add_get(self, path, handler):
            self.calls.append(("GET", path, handler))

        def add_post(self, path, handler):
            self.calls.append(("POST", path, handler))

        def add_put(self, path, handler):
            self.calls.append(("PUT", path, handler))

        def add_delete(self, path, handler):
            self.calls.append(("DELETE", path, handler))

    class FakeApp:
        def __init__(self):
            self.router = FakeRouter()

    app = FakeApp()
    registrar = registrar_module.RecipeRouteRegistrar(app)

    handler_mapping = {
        definition.handler_name: object()
        for definition in registrar_module.ROUTE_DEFINITIONS
    }

    registrar.register_routes(handler_mapping)

    assert {
        (method, path)
        for method, path, _ in app.router.calls
    } == {(d.method, d.path) for d in registrar_module.ROUTE_DEFINITIONS}


def test_recipe_routes_setup_routes_uses_registrar(monkeypatch: pytest.MonkeyPatch):
    registered_mappings: list[Dict[str, Callable[..., Awaitable[Any]]]] = []

    class DummyRegistrar:
        def __init__(self, app):
            self.app = app

        def register_routes(self, mapping):
            registered_mappings.append(mapping)

    monkeypatch.setattr(recipe_routes_module, "RecipeRouteRegistrar", DummyRegistrar)

    expected_mapping = {name: object() for name in ("render_page", "list_recipes")}

    def fake_to_route_mapping(self):
        return expected_mapping

    monkeypatch.setattr(base_routes_module.BaseRecipeRoutes, "to_route_mapping", fake_to_route_mapping)
    monkeypatch.setattr(
        base_routes_module.BaseRecipeRoutes,
        "_HANDLER_NAMES",
        tuple(expected_mapping.keys()),
    )

    app = web.Application()
    recipe_routes_module.RecipeRoutes.setup_routes(app)

    assert registered_mappings == [expected_mapping]
    recipe_callbacks = {
        cb
        for cb in app.on_startup
        if isinstance(getattr(cb, "__self__", None), recipe_routes_module.RecipeRoutes)
    }
    assert {type(cb.__self__) for cb in recipe_callbacks} == {recipe_routes_module.RecipeRoutes}
    assert {cb.__name__ for cb in recipe_callbacks} == {"attach_dependencies", "prewarm_cache"}
