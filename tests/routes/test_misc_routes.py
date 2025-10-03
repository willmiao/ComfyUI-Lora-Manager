import json
from types import SimpleNamespace

import pytest
from aiohttp import web

from py.routes.handlers.misc_handlers import SettingsHandler, ServiceRegistryAdapter
from py.routes.misc_route_registrar import MISC_ROUTE_DEFINITIONS, MiscRouteRegistrar
from py.routes.misc_routes import MiscRoutes


class FakeRequest:
    def __init__(self, *, json_data=None, query=None):
        self._json_data = json_data or {}
        self.query = query or {}

    async def json(self):
        return self._json_data


class DummySettings:
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)


class DummyDownloader:
    def __init__(self):
        self.refreshed = False

    async def refresh_session(self):
        self.refreshed = True


async def noop_async(*_args, **_kwargs):
    return None


async def dummy_downloader_factory():
    return DummyDownloader()


@pytest.mark.asyncio
async def test_get_settings_filters_sync_keys():
    settings_service = DummySettings({"civitai_api_key": "abc", "extraneous": "value"})
    handler = SettingsHandler(
        settings_service=settings_service,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
    )

    response = await handler.get_settings(FakeRequest())
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert payload["settings"] == {"civitai_api_key": "abc"}


@pytest.mark.asyncio
async def test_update_settings_rejects_missing_example_path(tmp_path):
    settings_service = DummySettings()
    handler = SettingsHandler(
        settings_service=settings_service,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
    )

    missing_path = tmp_path / "does-not-exist"
    request = FakeRequest(json_data={"example_images_path": str(missing_path)})

    response = await handler.update_settings(request)
    payload = json.loads(response.text)

    assert payload["success"] is False
    assert "Path does not exist" in payload["error"]


class RecordingRouter:
    def __init__(self):
        self.calls = []

    def add_get(self, path, handler):
        self.calls.append(("GET", path, handler))

    def add_post(self, path, handler):
        self.calls.append(("POST", path, handler))

    def add_put(self, path, handler):
        self.calls.append(("PUT", path, handler))

    def add_delete(self, path, handler):
        self.calls.append(("DELETE", path, handler))


def test_misc_route_registrar_registers_all_routes():
    app = SimpleNamespace(router=RecordingRouter())
    registrar = MiscRouteRegistrar(app)  # type: ignore[arg-type]

    async def dummy_handler(_request):
        return web.Response()

    handler_mapping = {definition.handler_name: dummy_handler for definition in MISC_ROUTE_DEFINITIONS}
    registrar.register_routes(handler_mapping)

    registered = {(method, path) for method, path, _ in app.router.calls}
    expected = {(definition.method, definition.path) for definition in MISC_ROUTE_DEFINITIONS}

    assert registered == expected


class FakePromptServer:
    sent = []

    class Instance:
        def send_sync(self, event, payload):
            FakePromptServer.sent.append((event, payload))

    instance = Instance()


class FakeScanner:
    async def check_model_version_exists(self, _version_id):
        return False

    async def get_model_versions_by_id(self, _model_id):
        return []


async def fake_scanner_factory():
    return FakeScanner()


class FakeMetadataProvider:
    async def get_model_versions(self, _model_id):
        return {"modelVersions": [], "name": "", "type": "lora"}


async def fake_metadata_provider_factory():
    return FakeMetadataProvider()


class FakeMetadataArchiveManager:
    async def download_and_extract_database(self, _callback):
        return True

    async def remove_database(self):
        return True

    def is_database_available(self):
        return False

    def get_database_path(self):
        return None


async def fake_metadata_archive_manager_factory():
    return FakeMetadataArchiveManager()


class RecordingRegistrar:
    def __init__(self, _app):
        self.registered_mapping = None

    def register_routes(self, mapping):
        self.registered_mapping = mapping


@pytest.mark.asyncio
async def test_misc_routes_bind_produces_expected_handlers():
    service_registry_adapter = ServiceRegistryAdapter(
        get_lora_scanner=fake_scanner_factory,
        get_checkpoint_scanner=fake_scanner_factory,
        get_embedding_scanner=fake_scanner_factory,
    )

    recorded_registrars = []

    def registrar_factory(app):
        registrar = RecordingRegistrar(app)
        recorded_registrars.append(registrar)
        return registrar

    controller = MiscRoutes(
        settings_service=DummySettings(),
        usage_stats_factory=lambda: SimpleNamespace(process_execution=noop_async, get_stats=noop_async),
        prompt_server=FakePromptServer,
        service_registry_adapter=service_registry_adapter,
        metadata_provider_factory=fake_metadata_provider_factory,
        metadata_archive_manager_factory=fake_metadata_archive_manager_factory,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
        registrar_factory=registrar_factory,
    )

    app = SimpleNamespace(router=RecordingRouter())
    controller.bind(app)  # type: ignore[arg-type]

    assert recorded_registrars, "Expected registrar to be created"
    mapping = recorded_registrars[0].registered_mapping
    assert mapping is not None

    expected_names = {definition.handler_name for definition in MISC_ROUTE_DEFINITIONS}
    assert set(mapping.keys()) == expected_names


def test_ensure_handler_mapping_caches_result():
    call_records = []

    class RecordingHandlerSet:
        def __init__(self, **handlers):
            call_records.append(handlers)
            self._handlers = handlers

        def to_route_mapping(self):
            return {"health_check": self._handlers["health"].health_check}

    controller = MiscRoutes(
        settings_service=DummySettings(),
        usage_stats_factory=lambda: SimpleNamespace(process_execution=noop_async, get_stats=noop_async),
        prompt_server=FakePromptServer,
        service_registry_adapter=ServiceRegistryAdapter(
            get_lora_scanner=fake_scanner_factory,
            get_checkpoint_scanner=fake_scanner_factory,
            get_embedding_scanner=fake_scanner_factory,
        ),
        metadata_provider_factory=fake_metadata_provider_factory,
        metadata_archive_manager_factory=fake_metadata_archive_manager_factory,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
        handler_set_factory=RecordingHandlerSet,
    )

    first_mapping = controller._ensure_handler_mapping()
    second_mapping = controller._ensure_handler_mapping()

    assert first_mapping is second_mapping, "Expected cached handler mapping to be reused"
    assert len(call_records) == 1, "Handler set factory should only be invoked once"


def test_create_handler_set_uses_provided_dependencies():
    recorded_handlers: list[dict] = []

    class RecordingHandlerSet:
        def __init__(self, **handlers):
            recorded_handlers.append(handlers)

        def to_route_mapping(self):
            return {}

    class CustomPromptServer:
        instance = SimpleNamespace()

    class FakeUsageStats:
        async def process_execution(self, _prompt_id):  # pragma: no cover - helper
            return None

        async def get_stats(self):  # pragma: no cover - helper
            return {}

    fake_node_registry = SimpleNamespace()

    controller = MiscRoutes(
        settings_service=DummySettings(),
        usage_stats_factory=lambda: FakeUsageStats(),
        prompt_server=CustomPromptServer,
        service_registry_adapter=ServiceRegistryAdapter(
            get_lora_scanner=fake_scanner_factory,
            get_checkpoint_scanner=fake_scanner_factory,
            get_embedding_scanner=fake_scanner_factory,
        ),
        metadata_provider_factory=fake_metadata_provider_factory,
        metadata_archive_manager_factory=fake_metadata_archive_manager_factory,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
        handler_set_factory=RecordingHandlerSet,
        node_registry=fake_node_registry,
        standalone_mode_flag=True,
    )

    controller._create_handler_set()

    assert recorded_handlers, "Expected handler factory to capture handler instances"
    handler_kwargs = recorded_handlers[0]
    node_registry_handler = handler_kwargs["node_registry"]

    assert node_registry_handler._node_registry is fake_node_registry
    assert node_registry_handler._prompt_server is CustomPromptServer
    assert node_registry_handler._standalone_mode is True
