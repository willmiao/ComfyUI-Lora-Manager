"""Unit tests for :mod:`py.services.model_service_factory`."""

from __future__ import annotations

from typing import List

import pytest

from py.services.model_service_factory import ModelServiceFactory


class _RecorderRoute:
    """Route double capturing setup invocations."""

    def __init__(self) -> None:
        self.calls: List[object] = []

    def setup_routes(self, app):
        self.calls.append(app)


class _FailingRoute:
    def setup_routes(self, app):  # pragma: no cover - used in exception path
        raise RuntimeError("boom")


class _DummyService:
    pass


@pytest.fixture(autouse=True)
def _reset_model_service_factory():
    """Ensure each test receives an isolated factory registry."""

    ModelServiceFactory.clear_registrations()
    yield
    ModelServiceFactory.clear_registrations()


def test_register_and_retrieve_model_type():
    """Registering a model type exposes its service and cached routes."""

    ModelServiceFactory.register_model_type("demo", _DummyService, _RecorderRoute)

    assert ModelServiceFactory.get_service_class("demo") is _DummyService
    assert ModelServiceFactory.get_route_class("demo") is _RecorderRoute

    first_instance = ModelServiceFactory.get_route_instance("demo")
    second_instance = ModelServiceFactory.get_route_instance("demo")

    assert isinstance(first_instance, _RecorderRoute)
    assert first_instance is second_instance, "route instances should be memoized"


def test_get_unknown_model_type_raises():
    """Unknown model types raise ``ValueError`` for both accessors."""

    with pytest.raises(ValueError):
        ModelServiceFactory.get_service_class("missing")

    with pytest.raises(ValueError):
        ModelServiceFactory.get_route_class("missing")


def test_setup_all_routes_invokes_registered_routes():
    """``setup_all_routes`` delegates to each registered route instance."""

    ModelServiceFactory.register_model_type("demo", _DummyService, _RecorderRoute)
    app = object()

    ModelServiceFactory.setup_all_routes(app)

    route = ModelServiceFactory.get_route_instance("demo")
    assert route.calls == [app]


def test_setup_all_routes_logs_failures(caplog):
    """Failures while binding a route are logged and do not interrupt others."""

    ModelServiceFactory.register_model_type("ok", _DummyService, _RecorderRoute)
    ModelServiceFactory.register_model_type("broken", _DummyService, _FailingRoute)
    app = object()

    caplog.set_level("ERROR")
    ModelServiceFactory.setup_all_routes(app)

    route = ModelServiceFactory.get_route_instance("ok")
    assert route.calls == [app]
    assert any("Failed to setup routes for broken" in record.message for record in caplog.records)


def test_clear_registrations_resets_all_state():
    """``clear_registrations`` removes services, routes, and cached instances."""

    ModelServiceFactory.register_model_type("demo", _DummyService, _RecorderRoute)

    assert ModelServiceFactory.is_registered("demo")
    ModelServiceFactory.clear_registrations()
    assert not ModelServiceFactory.get_registered_types()
    assert not ModelServiceFactory.is_registered("demo")

    with pytest.raises(ValueError):
        ModelServiceFactory.get_service_class("demo")
