import json
from types import SimpleNamespace

import pytest
from aiohttp import web

from py.routes.handlers.misc_handlers import (
    LoraCodeHandler,
    ModelLibraryHandler,
    NodeRegistry,
    NodeRegistryHandler,
    ServiceRegistryAdapter,
    SettingsHandler,
)
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


@pytest.mark.asyncio
async def test_register_nodes_requires_graph_id():
    node_registry = NodeRegistry()
    handler = NodeRegistryHandler(
        node_registry=node_registry,
        prompt_server=FakePromptServer,
        standalone_mode=False,
    )

    request = FakeRequest(json_data={"nodes": [{"node_id": 1}]})
    response = await handler.register_nodes(request)
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False
    assert "graph_id" in payload["error"]


@pytest.mark.asyncio
async def test_register_nodes_stores_graph_identifier():
    node_registry = NodeRegistry()
    handler = NodeRegistryHandler(
        node_registry=node_registry,
        prompt_server=FakePromptServer,
        standalone_mode=False,
    )

    request = FakeRequest(
        json_data={
            "nodes": [
                {
                    "node_id": 7,
                    "graph_id": "graph-123",
                    "graph_name": "Character Subgraph",
                    "type": "Lora Loader (LoraManager)",
                    "title": "Loader",
                }
            ]
        }
    )

    response = await handler.register_nodes(request)
    payload = json.loads(response.text)

    assert payload["success"] is True

    registry = await node_registry.get_registry()
    assert registry["node_count"] == 1
    stored_node = next(iter(registry["nodes"].values()))
    assert stored_node["graph_id"] == "graph-123"
    assert stored_node["unique_id"] == "graph-123:7"
    assert stored_node["graph_name"] == "Character Subgraph"


@pytest.mark.asyncio
async def test_register_nodes_defaults_graph_name_to_none():
    node_registry = NodeRegistry()
    handler = NodeRegistryHandler(
        node_registry=node_registry,
        prompt_server=FakePromptServer,
        standalone_mode=False,
    )

    request = FakeRequest(
        json_data={
            "nodes": [
                {
                    "node_id": 8,
                    "graph_id": "root",
                    "type": "Lora Loader (LoraManager)",
                    "title": "Root Loader",
                }
            ]
        }
    )

    response = await handler.register_nodes(request)
    payload = json.loads(response.text)

    assert payload["success"] is True

    registry = await node_registry.get_registry()
    stored_node = next(iter(registry["nodes"].values()))
    assert stored_node["graph_name"] is None


@pytest.mark.asyncio
async def test_register_nodes_includes_capabilities():
    node_registry = NodeRegistry()
    handler = NodeRegistryHandler(
        node_registry=node_registry,
        prompt_server=FakePromptServer,
        standalone_mode=False,
    )

    request = FakeRequest(
        json_data={
            "nodes": [
                {
                    "node_id": 9,
                    "graph_id": "root",
                    "type": "CheckpointLoaderSimple",
                    "title": "Checkpoint Loader",
                    "capabilities": {"supports_lora": False, "widget_names": ["ckpt_name", "", 42]},
                }
            ]
        }
    )

    response = await handler.register_nodes(request)
    payload = json.loads(response.text)

    assert payload["success"] is True

    registry = await node_registry.get_registry()
    stored_node = next(iter(registry["nodes"].values()))
    assert stored_node["capabilities"] == {"supports_lora": False, "widget_names": ["ckpt_name"]}
    assert stored_node["widget_names"] == ["ckpt_name"]


@pytest.mark.asyncio
async def test_update_node_widget_sends_payload():
    send_calls: list[tuple[str, dict]] = []

    class RecordingPromptServer:
        class Instance:
            def send_sync(self, event, payload):
                send_calls.append((event, payload))

        instance = Instance()

    handler = NodeRegistryHandler(
        node_registry=NodeRegistry(),
        prompt_server=RecordingPromptServer,
        standalone_mode=False,
    )

    request = FakeRequest(
        json_data={
            "widget_name": "ckpt_name",
            "value": "models/checkpoints/model.ckpt",
            "node_ids": [{"node_id": 12, "graph_id": "root"}],
        }
    )

    response = await handler.update_node_widget(request)
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert send_calls == [
        (
            "lm_widget_update",
            {"id": 12, "widget_name": "ckpt_name", "value": "models/checkpoints/model.ckpt", "graph_id": "root"},
        )
    ]


@pytest.mark.asyncio
async def test_update_lora_code_includes_graph_identifier():
    send_calls: list[tuple[str, dict]] = []

    class RecordingPromptServer:
        class Instance:
            def send_sync(self, event, payload):
                send_calls.append((event, payload))

        instance = Instance()

    handler = LoraCodeHandler(RecordingPromptServer)

    request = FakeRequest(
        json_data={
            "node_ids": [{"node_id": 3, "graph_id": "graph-A"}],
            "lora_code": "<lora>",
            "mode": "replace",
        }
    )

    response = await handler.update_lora_code(request)
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert payload["results"] == [
        {"node_id": 3, "graph_id": "graph-A", "success": True}
    ]
    assert send_calls == [
        (
            "lora_code_update",
            {"id": 3, "graph_id": "graph-A", "lora_code": "<lora>", "mode": "replace"},
        )
    ]


class FakeScanner:
    async def check_model_version_exists(self, _version_id):
        return False

    async def get_model_versions_by_id(self, _model_id):
        return []


async def fake_scanner_factory():
    return FakeScanner()


class RecordingVersionScanner:
    def __init__(self, versions):
        self._versions = versions
        self.version_calls: list[int] = []

    async def check_model_version_exists(self, _version_id):
        return False

    async def get_model_versions_by_id(self, model_id):
        self.version_calls.append(model_id)
        return self._versions


class FakeExistenceScanner:
    def __init__(self, existing=None):
        self._existing = set(existing or [])

    async def check_model_version_exists(self, version_id):
        return version_id in self._existing

    async def get_model_versions_by_id(self, _model_id):
        return []


class FakeMetadataProvider:
    async def get_model_versions(self, _model_id):
        return {"modelVersions": [], "name": "", "type": "lora"}

    async def get_user_models(self, _username):
        return []


class FakeUserModelsProvider(FakeMetadataProvider):
    def __init__(self, models):
        self.models = models
        self.received_usernames: list[str] = []

    async def get_user_models(self, username):
        self.received_usernames.append(username)
        return self.models


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


@pytest.mark.asyncio
async def test_get_civitai_user_models_marks_library_versions():
    models = [
        {
            "id": 1,
            "name": "Model A",
            "type": "LORA",
            "tags": ["style"],
            "modelVersions": [
                {
                    "id": 100,
                    "name": "v1",
                    "baseModel": "Flux.1",
                    "images": [{"url": "http://example.com/a1.jpg"}],
                },
                {
                    "id": 101,
                    "name": "v2",
                    "baseModel": "Flux.1",
                    "images": [{"url": "http://example.com/a2.jpg"}],
                },
            ],
        },
        {
            "id": 2,
            "name": "Embedding",
            "type": "TextualInversion",
            "tags": ["embedding"],
            "modelVersions": [
                {
                    "id": 200,
                    "name": "v1",
                    "baseModel": None,
                    "images": [{"url": "http://example.com/e1.jpg"}],
                },
                {
                    "id": 202,
                    "name": "v2",
                    "baseModel": None,
                },
            ],
        },
        {
            "id": 3,
            "name": "Checkpoint",
            "type": "Checkpoint",
            "tags": ["checkpoint"],
            "modelVersions": [
                {
                    "id": 300,
                    "name": "v1",
                    "baseModel": "SDXL",
                    "images": [],
                }
            ],
        },
        {
            "id": 4,
            "name": "Unsupported",
            "type": "Other",
            "modelVersions": [
                {
                    "id": 400,
                    "name": "v1",
                }
            ],
        },
    ]

    provider = FakeUserModelsProvider(models)

    async def provider_factory():
        return provider

    lora_scanner = FakeExistenceScanner({101})
    checkpoint_scanner = FakeExistenceScanner()
    embedding_scanner = FakeExistenceScanner({202})

    async def lora_factory():
        return lora_scanner

    async def checkpoint_factory():
        return checkpoint_scanner

    async def embedding_factory():
        return embedding_scanner

    handler = ModelLibraryHandler(
        ServiceRegistryAdapter(
            get_lora_scanner=lora_factory,
            get_checkpoint_scanner=checkpoint_factory,
            get_embedding_scanner=embedding_factory,
        ),
        metadata_provider_factory=provider_factory,
    )

    response = await handler.get_civitai_user_models(FakeRequest(query={"username": "pixel"}))
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert payload["username"] == "pixel"
    assert payload["versions"] == [
        {
            "modelId": 1,
            "versionId": 100,
            "modelName": "Model A",
            "versionName": "v1",
            "type": "LORA",
            "tags": ["style"],
            "baseModel": "Flux.1",
            "thumbnailUrl": "http://example.com/a1.jpg",
            "inLibrary": False,
        },
        {
            "modelId": 1,
            "versionId": 101,
            "modelName": "Model A",
            "versionName": "v2",
            "type": "LORA",
            "tags": ["style"],
            "baseModel": "Flux.1",
            "thumbnailUrl": "http://example.com/a2.jpg",
            "inLibrary": True,
        },
        {
            "modelId": 2,
            "versionId": 200,
            "modelName": "Embedding",
            "versionName": "v1",
            "type": "TextualInversion",
            "tags": ["embedding"],
            "baseModel": None,
            "thumbnailUrl": "http://example.com/e1.jpg",
            "inLibrary": False,
        },
        {
            "modelId": 2,
            "versionId": 202,
            "modelName": "Embedding",
            "versionName": "v2",
            "type": "TextualInversion",
            "tags": ["embedding"],
            "baseModel": None,
            "thumbnailUrl": None,
            "inLibrary": True,
        },
        {
            "modelId": 3,
            "versionId": 300,
            "modelName": "Checkpoint",
            "versionName": "v1",
            "type": "Checkpoint",
            "tags": ["checkpoint"],
            "baseModel": "SDXL",
            "thumbnailUrl": None,
            "inLibrary": False,
        },
    ]

    assert provider.received_usernames == ["pixel"]


@pytest.mark.asyncio
async def test_get_civitai_user_models_rewrites_civitai_previews():
    image_url = "https://image.civitai.com/container/example/original=true/sample.jpeg"
    video_url = "https://image.civitai.com/container/example/original=true/sample.mp4"

    models = [
        {
            "id": 1,
            "name": "Model A",
            "type": "LORA",
            "tags": ["style"],
            "modelVersions": [
                {
                    "id": 100,
                    "name": "preview-image",
                    "baseModel": "Flux.1",
                    "images": [
                        {"url": image_url, "type": "image"},
                    ],
                },
                {
                    "id": 101,
                    "name": "preview-video",
                    "baseModel": "Flux.1",
                    "images": [
                        {"url": video_url, "type": "video"},
                    ],
                },
            ],
        },
    ]

    provider = FakeUserModelsProvider(models)

    async def provider_factory():
        return provider

    handler = ModelLibraryHandler(
        ServiceRegistryAdapter(
            get_lora_scanner=fake_scanner_factory,
            get_checkpoint_scanner=fake_scanner_factory,
            get_embedding_scanner=fake_scanner_factory,
        ),
        metadata_provider_factory=provider_factory,
    )

    response = await handler.get_civitai_user_models(FakeRequest(query={"username": "pixel"}))
    payload = json.loads(response.text)

    assert payload["success"] is True
    previews_by_version = {item["versionId"]: item["thumbnailUrl"] for item in payload["versions"]}
    assert previews_by_version[100] == "https://image.civitai.com/container/example/width=450,optimized=true/sample.jpeg"
    assert (
        previews_by_version[101]
        == "https://image.civitai.com/container/example/transcode=true,width=450,optimized=true/sample.mp4"
    )


@pytest.mark.asyncio
async def test_get_civitai_user_models_requires_username():
    provider = FakeUserModelsProvider([])

    async def provider_factory():
        return provider

    handler = ModelLibraryHandler(
        ServiceRegistryAdapter(
            get_lora_scanner=fake_scanner_factory,
            get_checkpoint_scanner=fake_scanner_factory,
            get_embedding_scanner=fake_scanner_factory,
        ),
        metadata_provider_factory=provider_factory,
    )

    response = await handler.get_civitai_user_models(FakeRequest())
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False
    assert "username" in payload["error"].lower()


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


@pytest.mark.asyncio
async def test_check_model_exists_returns_local_versions():
    versions = [
        {'versionId': 11, 'name': 'v1', 'fileName': 'model-one'},
        {'versionId': 12, 'name': 'v2', 'fileName': 'model-two'},
    ]

    lora_scanner = RecordingVersionScanner(versions)
    checkpoint_scanner = RecordingVersionScanner([])
    embedding_scanner = RecordingVersionScanner([])

    async def lora_factory():
        return lora_scanner

    async def checkpoint_factory():
        return checkpoint_scanner

    async def embedding_factory():
        return embedding_scanner

    handler = ModelLibraryHandler(
        ServiceRegistryAdapter(
            get_lora_scanner=lora_factory,
            get_checkpoint_scanner=checkpoint_factory,
            get_embedding_scanner=embedding_factory,
        ),
        metadata_provider_factory=fake_metadata_provider_factory,
    )

    response = await handler.check_model_exists(FakeRequest(query={'modelId': '5'}))
    payload = json.loads(response.text)

    assert payload['success'] is True
    assert payload['modelType'] == 'lora'
    assert payload['versions'] == versions
    assert lora_scanner.version_calls == [5]


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
