"""Smoke tests for the recipe routing scaffolding.

The cases keep the registrar/controller contract aligned with
``docs/architecture/recipe_routes.md`` so future refactors can focus on handler
logic.
"""

from __future__ import annotations

import asyncio
import types
from collections import Counter
from typing import Any, Awaitable, Callable, Dict

import pytest
from aiohttp import web

from py.routes import base_recipe_routes, recipe_route_registrar, recipe_routes
from py.services import service_registry
from py.services.server_i18n import server_i18n


@pytest.fixture(autouse=True)
def reset_service_registry(monkeypatch: pytest.MonkeyPatch):
    """Ensure each test starts from a clean registry state."""

    registry = service_registry.ServiceRegistry
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
    registry = service_registry.ServiceRegistry

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
        routes = base_recipe_routes.BaseRecipeRoutes()

        await routes.attach_dependencies()
        await routes.attach_dependencies()  # idempotent

        assert routes.recipe_scanner is scanner
        assert routes.lora_scanner is scanner._lora_scanner
        assert routes.civitai_client is civitai_client
        assert routes.template_env.filters["t"] is not None
        assert filter_calls["create_filter"] == 1

    asyncio.run(scenario())


def test_register_startup_hooks_appends_once():
    routes = base_recipe_routes.BaseRecipeRoutes()

    app = web.Application()
    routes.register_startup_hooks(app)
    routes.register_startup_hooks(app)

    startup_bound_to_routes = [
        callback for callback in app.on_startup if getattr(callback, "__self__", None) is routes
    ]

    assert routes.attach_dependencies in startup_bound_to_routes
    assert routes.prewarm_cache in startup_bound_to_routes
    assert len(startup_bound_to_routes) == 2


def test_to_route_mapping_uses_handler_set():
    class DummyHandlerSet:
        def __init__(self):
            self.calls = 0

        def to_route_mapping(self):
            self.calls += 1

            async def render_page(request):  # pragma: no cover - simple coroutine
                return web.Response(text="ok")

            return {"render_page": render_page}

    class DummyRoutes(base_recipe_routes.BaseRecipeRoutes):
        def __init__(self):
            super().__init__()
            self.created = 0

        def _create_handler_set(self):  # noqa: D401 - simple override for test
            self.created += 1
            return DummyHandlerSet()

    routes = DummyRoutes()
    mapping = routes.to_route_mapping()

    assert set(mapping.keys()) == {"render_page"}
    assert asyncio.iscoroutinefunction(mapping["render_page"])
    # Cached mapping reused on subsequent calls
    assert routes.to_route_mapping() is mapping
    # Handler set cached for get_handler_owner callers
    assert isinstance(routes.get_handler_owner(), DummyHandlerSet)
    assert routes.created == 1


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
    registrar = recipe_route_registrar.RecipeRouteRegistrar(app)

    handler_mapping = {
        definition.handler_name: object()
        for definition in recipe_route_registrar.ROUTE_DEFINITIONS
    }

    registrar.register_routes(handler_mapping)

    assert {
        (method, path)
        for method, path, _ in app.router.calls
    } == {(d.method, d.path) for d in recipe_route_registrar.ROUTE_DEFINITIONS}


def test_recipe_routes_setup_routes_uses_registrar(monkeypatch: pytest.MonkeyPatch):
    registered_mappings: list[Dict[str, Callable[..., Awaitable[Any]]]] = []

    class DummyRegistrar:
        def __init__(self, app):
            self.app = app

        def register_routes(self, mapping):
            registered_mappings.append(mapping)

    monkeypatch.setattr(recipe_routes, "RecipeRouteRegistrar", DummyRegistrar)

    expected_mapping = {name: object() for name in ("render_page", "list_recipes")}

    def fake_to_route_mapping(self):
        return expected_mapping

    monkeypatch.setattr(base_recipe_routes.BaseRecipeRoutes, "to_route_mapping", fake_to_route_mapping)
    monkeypatch.setattr(
        base_recipe_routes.BaseRecipeRoutes,
        "_HANDLER_NAMES",
        tuple(expected_mapping.keys()),
    )

    app = web.Application()
    recipe_routes.RecipeRoutes.setup_routes(app)

    assert registered_mappings == [expected_mapping]
    recipe_callbacks = {
        cb
        for cb in app.on_startup
        if isinstance(getattr(cb, "__self__", None), recipe_routes.RecipeRoutes)
    }
    assert {type(cb.__self__) for cb in recipe_callbacks} == {recipe_routes.RecipeRoutes}
    assert {cb.__name__ for cb in recipe_callbacks} == {"attach_dependencies", "prewarm_cache"}
