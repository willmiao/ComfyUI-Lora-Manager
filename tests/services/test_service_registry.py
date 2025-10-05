import sys
import types

import pytest

from py.services.service_registry import ServiceRegistry


@pytest.fixture(autouse=True)
def clear_service_registry():
    ServiceRegistry.clear_services()
    yield
    ServiceRegistry.clear_services()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,module_path,class_name,service_key",
    [
        ("get_lora_scanner", "py.services.lora_scanner", "LoraScanner", "lora_scanner"),
        ("get_checkpoint_scanner", "py.services.checkpoint_scanner", "CheckpointScanner", "checkpoint_scanner"),
        ("get_recipe_scanner", "py.services.recipe_scanner", "RecipeScanner", "recipe_scanner"),
    ],
)
async def test_lazy_loaded_scanners(monkeypatch, method_name, module_path, class_name, service_key):
    calls = 0
    fake_instance = object()

    class FakeScanner:
        @classmethod
        async def get_instance(cls):
            nonlocal calls
            calls += 1
            return fake_instance

    module = types.ModuleType(module_path)
    setattr(module, class_name, FakeScanner)
    monkeypatch.setitem(sys.modules, module_path, module)

    method = getattr(ServiceRegistry, method_name)

    first = await method()
    assert first is fake_instance
    assert await ServiceRegistry.get_service(service_key) is fake_instance

    second = await method()
    assert second is fake_instance
    assert calls == 1


@pytest.mark.asyncio
async def test_lazy_loaded_websocket_manager(monkeypatch):
    fake_manager = object()
    module = types.ModuleType("py.services.websocket_manager")
    module.ws_manager = fake_manager
    monkeypatch.setitem(sys.modules, "py.services.websocket_manager", module)

    first = await ServiceRegistry.get_websocket_manager()
    assert first is fake_manager

    # Update registry to simulate external registration drift
    sentinel = object()
    ServiceRegistry._services["websocket_manager"] = sentinel

    second = await ServiceRegistry.get_websocket_manager()
    assert second is sentinel
