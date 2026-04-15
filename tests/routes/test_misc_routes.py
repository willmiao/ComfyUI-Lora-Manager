import io
import json
import logging
import os
import subprocess
import zipfile
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from aiohttp import web

from py.routes.handlers.misc_handlers import (
    BackupHandler,
    DoctorHandler,
    FileSystemHandler,
    LoraCodeHandler,
    ModelLibraryHandler,
    NodeRegistry,
    NodeRegistryHandler,
    ServiceRegistryAdapter,
    SettingsHandler,
    _collect_comfyui_session_logs,
    _is_wsl,
    _wsl_to_windows_path,
    _is_docker,
)
from py.utils.session_logging import (
    reset_standalone_session_logging_for_tests,
    setup_standalone_session_logging,
)
from py.routes.misc_route_registrar import MISC_ROUTE_DEFINITIONS, MiscRouteRegistrar
from py.routes.misc_routes import MiscRoutes


class FakeRequest:
    def __init__(self, *, json_data=None, query=None, method="POST"):
        self._json_data = json_data or {}
        self.query = query or {}
        self.method = method

    async def json(self):
        return self._json_data


class DummySettings:
    def __init__(self, data=None):
        self.data = data or {}
        self.settings = self.data

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)

    def keys(self):
        return self.data.keys()


class DummyDownloader:
    def __init__(self):
        self.refreshed = False

    async def refresh_session(self):
        self.refreshed = True


async def noop_async(*_args, **_kwargs):
    return None


async def dummy_downloader_factory():
    return DummyDownloader()


class DummyDoctorScanner:
    def __init__(self, *, model_type='lora', raw_data=None, rebuild_error=None):
        self.model_type = model_type
        self._raw_data = list(raw_data or [])
        self._rebuild_error = rebuild_error
        self._persistent_cache = SimpleNamespace(
            load_cache=lambda _model_type: SimpleNamespace(raw_data=list(self._raw_data))
        )

    async def get_cached_data(self, force_refresh=False, rebuild_cache=False):
        if rebuild_cache and self._rebuild_error:
            raise self._rebuild_error
        return SimpleNamespace(raw_data=list(self._raw_data))


class DummyCivitaiClient:
    def __init__(self, *, success=True, result=None):
        self.base_url = 'https://civitai.com/api/v1'
        self._success = success
        self._result = result if result is not None else {'items': []}

    async def _make_request(self, *_args, **_kwargs):
        return self._success, self._result


@pytest.mark.asyncio
async def test_get_settings_excludes_no_sync_keys():
    """Verify that settings in _NO_SYNC_KEYS are not synced, but others are."""
    settings_service = DummySettings({
        "civitai_api_key": "abc",
        "hash_chunk_size_mb": 10,
        "folder_paths": {"/some/path"},
        "regular_setting": "value",
    })
    handler = SettingsHandler(
        settings_service=settings_service,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
    )

    response = await handler.get_settings(FakeRequest())
    payload = json.loads(response.text)

    assert payload["success"] is True
    # Regular settings should be synced
    assert payload["settings"]["civitai_api_key"] == "abc"
    assert payload["settings"]["regular_setting"] == "value"
    # _NO_SYNC_KEYS should not be synced
    assert "hash_chunk_size_mb" not in payload["settings"]
    assert "folder_paths" not in payload["settings"]


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


@pytest.mark.asyncio
async def test_doctor_handler_reports_key_cache_and_ui_issues():
    settings_service = DummySettings({"civitai_api_key": ""})
    invalid_entry = {"file_path": "/tmp/missing.safetensors"}

    async def civitai_factory():
        return DummyCivitaiClient()

    async def scanner_factory():
        return DummyDoctorScanner(model_type="lora", raw_data=[invalid_entry])

    handler = DoctorHandler(
        settings_service=settings_service,
        civitai_client_factory=civitai_factory,
        scanner_factories=(("lora", "LoRAs", scanner_factory),),
        app_version_getter=lambda: "1.2.3-server",
    )

    response = await handler.get_doctor_diagnostics(
        FakeRequest(query={"clientVersion": "1.2.2-client"}, method="GET")
    )
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert payload["summary"]["status"] == "error"
    diagnostic_map = {item["id"]: item for item in payload["diagnostics"]}
    assert diagnostic_map["civitai_api_key"]["status"] == "warning"
    assert diagnostic_map["cache_health"]["status"] == "error"
    assert diagnostic_map["ui_version"]["status"] == "warning"


@pytest.mark.asyncio
async def test_doctor_handler_can_repair_cache():
    scanner = DummyDoctorScanner(model_type="lora", raw_data=[])

    async def civitai_factory():
        return DummyCivitaiClient()

    async def scanner_factory():
        return scanner

    handler = DoctorHandler(
        settings_service=DummySettings({"civitai_api_key": "token"}),
        civitai_client_factory=civitai_factory,
        scanner_factories=(("lora", "LoRAs", scanner_factory),),
    )

    response = await handler.repair_doctor_cache(FakeRequest())
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["repaired"] == [{"model_type": "lora", "label": "LoRAs"}]


@pytest.mark.asyncio
async def test_doctor_handler_exports_support_bundle():
    async def civitai_factory():
        return DummyCivitaiClient()

    handler = DoctorHandler(
        settings_service=DummySettings({"civitai_api_key": "secret-key"}),
        civitai_client_factory=civitai_factory,
        scanner_factories=(),
        app_version_getter=lambda: "9.9.9-test",
    )

    response = await handler.export_doctor_bundle(
        FakeRequest(
            json_data={
                "summary": {"status": "warning"},
                "diagnostics": [{"id": "cache_health", "status": "warning"}],
                "frontend_logs": [{"level": "error", "message": "boom"}],
                "client_context": {"app_version": "9.9.8-old"},
            }
        )
    )

    assert response.status == 200
    with zipfile.ZipFile(io.BytesIO(response.body), "r") as archive:
        names = set(archive.namelist())
        assert "doctor-report.json" in names
        assert "settings-sanitized.json" in names
        assert "backend-log-source.json" in names
        settings_payload = json.loads(archive.read("settings-sanitized.json").decode("utf-8"))
        assert settings_payload["civitai_api_key"].startswith("secr")


@pytest.mark.asyncio
async def test_doctor_handler_redacts_string_secrets_in_bundle():
    async def civitai_factory():
        return DummyCivitaiClient()

    handler = DoctorHandler(
        settings_service=DummySettings({"civitai_api_key": "secret-key"}),
        civitai_client_factory=civitai_factory,
        scanner_factories=(),
        app_version_getter=lambda: "9.9.9-test",
    )

    response = await handler.export_doctor_bundle(
        FakeRequest(
            json_data={
                "frontend_logs": [
                    {
                        "level": "error",
                        "message": "Authorization: Bearer abcdef123456 token=xyz password=hunter2",
                    }
                ],
            }
        )
    )

    assert response.status == 200
    with zipfile.ZipFile(io.BytesIO(response.body), "r") as archive:
        frontend_logs = archive.read("frontend-console.json").decode("utf-8")
        assert "abcdef123456" not in frontend_logs
        assert "hunter2" not in frontend_logs
        assert "Bearer ***" in frontend_logs
        backend_logs = archive.read("backend-logs.txt").decode("utf-8")
        assert "hunter2" not in backend_logs


@pytest.mark.asyncio
async def test_doctor_handler_redacts_json_shaped_string_secrets_in_bundle():
    async def civitai_factory():
        return DummyCivitaiClient()

    handler = DoctorHandler(
        settings_service=DummySettings({"civitai_api_key": "secret-key"}),
        civitai_client_factory=civitai_factory,
        scanner_factories=(),
        app_version_getter=lambda: "9.9.9-test",
    )
    handler._collect_backend_session_logs = lambda: {
        "mode": "standalone",
        "source_method": "standalone_memory",
        "session_started_at": "2026-04-11T10:00:00+00:00",
        "session_id": "session-123",
        "persistent_log_path": None,
        "persistent_log_text": "",
        "session_log_text": '{"token":"abcd1234","authorization":"Bearer qwerty","password":"hunter2"}\n',
        "notes": [],
    }

    response = await handler.export_doctor_bundle(
        FakeRequest(
            json_data={
                "frontend_logs": [
                    {
                        "level": "error",
                        "message": '{"token":"abcd1234","authorization":"Bearer qwerty","password":"hunter2"}',
                    }
                ],
            }
        )
    )

    assert response.status == 200
    with zipfile.ZipFile(io.BytesIO(response.body), "r") as archive:
        frontend_logs = archive.read("frontend-console.json").decode("utf-8")
        backend_logs = archive.read("backend-logs.txt").decode("utf-8")

        assert '"token":"abcd1234"' not in frontend_logs
        assert '"password":"hunter2"' not in frontend_logs
        assert 'Bearer qwerty' not in frontend_logs
        assert '\\"token\\":\\"***\\"' in frontend_logs
        assert '\\"password\\":\\"***\\"' in frontend_logs
        assert 'Bearer ***' in frontend_logs

        assert '"token":"abcd1234"' not in backend_logs
        assert '"password":"hunter2"' not in backend_logs
        assert 'Bearer qwerty' not in backend_logs


@pytest.mark.asyncio
async def test_doctor_handler_exports_backend_session_logs_from_helper():
    async def civitai_factory():
        return DummyCivitaiClient()

    handler = DoctorHandler(
        settings_service=DummySettings({"civitai_api_key": "secret-key"}),
        civitai_client_factory=civitai_factory,
        scanner_factories=(),
        app_version_getter=lambda: "9.9.9-test",
    )
    handler._collect_backend_session_logs = lambda: {
        "mode": "standalone",
        "source_method": "standalone_session_file",
        "session_started_at": "2026-04-11T10:00:00+00:00",
        "session_id": "session-123",
        "persistent_log_path": "/tmp/standalone.log",
        "persistent_log_text": "token=abcd1234\n",
        "session_log_text": "Authorization: Bearer supersecret\n",
        "notes": [],
    }

    response = await handler.export_doctor_bundle(FakeRequest(json_data={}))

    assert response.status == 200
    with zipfile.ZipFile(io.BytesIO(response.body), "r") as archive:
        backend_logs = archive.read("backend-logs.txt").decode("utf-8")
        backend_source = json.loads(
            archive.read("backend-log-source.json").decode("utf-8")
        )

        assert "supersecret" not in backend_logs
        assert backend_source["source_method"] == "standalone_session_file"
        assert backend_source["session_id"] == "session-123"


def test_collect_comfyui_session_logs_only_uses_matching_current_session_file(tmp_path):
    log_file = tmp_path / "comfyui.log"
    log_file.write_text(
        "** ComfyUI startup time: 2026-04-11 12:00:00.000\n"
        "[2026-04-11 12:00:01.000] file log line\n",
        encoding="utf-8",
    )

    result = _collect_comfyui_session_logs(
        log_entries=[
            {
                "t": "2026-04-11 12:05:00.000",
                "m": "** ComfyUI startup time: 2026-04-11 12:05:00.000\n",
            },
            {"t": "2026-04-11 12:05:01.000", "m": "current session line\n"},
        ],
        log_file_path=str(log_file),
    )

    assert result["persistent_log_text"] == ""
    assert any("does not match" in note for note in result["notes"])


def test_setup_standalone_session_logging_creates_current_session_file(tmp_path):
    reset_standalone_session_logging_for_tests()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")

    state = setup_standalone_session_logging(str(settings_file))
    logger = logging.getLogger("lora-manager-standalone-test")
    logger.info("standalone current session line")

    assert state.log_file_path is not None
    assert os.path.isfile(state.log_file_path)
    with open(state.log_file_path, "r", encoding="utf-8") as handle:
        payload = handle.read()

    assert "LoRA Manager standalone startup time:" in payload


class DummyBackupService:
    def __init__(self):
        self.restore_calls = []

    async def create_snapshot(self, *, snapshot_type="manual", persist=False):
        return {
            "archive_name": "backup.zip",
            "archive_bytes": b"zip-bytes",
            "manifest": {"snapshot_type": snapshot_type},
        }

    async def restore_snapshot(self, archive_path):
        self.restore_calls.append(archive_path)
        return {"success": True, "restored_files": 3, "snapshot_type": "manual"}

    def get_status(self):
        return {
            "backupDir": "/tmp/backups",
            "enabled": True,
            "retentionCount": 5,
            "snapshotCount": 1,
        }

    def get_available_snapshots(self):
        return [{"name": "backup.zip", "path": "/tmp/backup.zip", "size": 8, "mtime": 1.0, "is_auto": False}]


@pytest.mark.asyncio
async def test_backup_handler_returns_status_and_exports(monkeypatch):
    service = DummyBackupService()

    async def factory():
        return service

    handler = BackupHandler(backup_service_factory=factory)

    status_response = await handler.get_backup_status(FakeRequest())
    status_payload = json.loads(status_response.text)
    assert status_payload["success"] is True
    assert status_payload["status"]["backupDir"] == "/tmp/backups"
    assert status_payload["status"]["enabled"] is True
    assert status_payload["snapshots"][0]["name"] == "backup.zip"

    export_response = await handler.export_backup(FakeRequest())
    assert export_response.status == 200
    assert export_response.body == b"zip-bytes"


@pytest.mark.asyncio
async def test_backup_handler_rejects_missing_import_archive():
    service = DummyBackupService()

    async def factory():
        return service

    handler = BackupHandler(backup_service_factory=factory)

    class EmptyRequest:
        content_type = "application/octet-stream"

        async def read(self):
            return b""

    response = await handler.import_backup(EmptyRequest())
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_open_backup_location_uses_settings_directory(tmp_path, monkeypatch):
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    backup_dir = settings_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    handler = FileSystemHandler(settings_service=SimpleNamespace(settings_file=str(settings_file)))

    calls = []

    def fake_popen(args):
        calls.append(args)
        return MagicMock()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("py.routes.handlers.misc_handlers._is_docker", lambda: False)
    monkeypatch.setattr("py.routes.handlers.misc_handlers._is_wsl", lambda: False)

    response = await handler.open_backup_location(FakeRequest())
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["path"] == str(backup_dir)
    assert calls == [["xdg-open", str(backup_dir)]]


@pytest.mark.asyncio
async def test_open_wildcards_location_creates_and_opens_directory(tmp_path, monkeypatch):
    wildcards_dir = tmp_path / "settings" / "wildcards"

    handler = FileSystemHandler(settings_service=SimpleNamespace(settings_file=str(tmp_path / "settings.json")))

    calls = []

    def fake_popen(args):
        calls.append(args)
        return MagicMock()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("py.routes.handlers.misc_handlers._is_docker", lambda: False)
    monkeypatch.setattr("py.routes.handlers.misc_handlers._is_wsl", lambda: False)
    monkeypatch.setattr(
        "py.services.wildcard_service.get_wildcards_dir",
        lambda create=False: str(wildcards_dir.mkdir(parents=True, exist_ok=True) or wildcards_dir)
        if create
        else str(wildcards_dir),
    )

    response = await handler.open_wildcards_location(FakeRequest())
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["path"] == str(wildcards_dir)
    assert wildcards_dir.is_dir()
    assert calls == [["xdg-open", str(wildcards_dir)]]


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

    handler_mapping = {
        definition.handler_name: dummy_handler for definition in MISC_ROUTE_DEFINITIONS
    }
    registrar.register_routes(handler_mapping)

    registered = {(method, path) for method, path, _ in app.router.calls}
    expected = {
        (definition.method, definition.path) for definition in MISC_ROUTE_DEFINITIONS
    }

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
                    "capabilities": {
                        "supports_lora": False,
                        "widget_names": ["ckpt_name", "", 42],
                    },
                }
            ]
        }
    )

    response = await handler.register_nodes(request)
    payload = json.loads(response.text)

    assert payload["success"] is True

    registry = await node_registry.get_registry()
    stored_node = next(iter(registry["nodes"].values()))
    assert stored_node["capabilities"] == {
        "supports_lora": False,
        "widget_names": ["ckpt_name"],
    }
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
            {
                "id": 12,
                "widget_name": "ckpt_name",
                "value": "models/checkpoints/model.ckpt",
                "graph_id": "root",
            },
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


class FakeDownloadHistoryService:
    def __init__(self, downloaded_by_type=None):
        self.downloaded_by_type = downloaded_by_type or {}
        self.marked_downloaded: list[tuple] = []
        self.marked_not_downloaded: list[tuple] = []

    async def has_been_downloaded(self, model_type, version_id):
        return version_id in self.downloaded_by_type.get(model_type, set())

    async def get_downloaded_version_ids(self, model_type, model_id):
        entries = self.downloaded_by_type.get(model_type, {})
        if isinstance(entries, dict):
            return sorted(entries.get(model_id, set()))
        return []

    async def get_downloaded_version_ids_bulk(self, model_type, model_ids):
        entries = self.downloaded_by_type.get(model_type, {})
        if not isinstance(entries, dict):
            return {}
        return {
            model_id: set(entries.get(model_id, set()))
            for model_id in model_ids
            if model_id in entries
        }

    async def mark_downloaded(
        self, model_type, version_id, *, model_id=None, source="manual", file_path=None
    ):
        self.marked_downloaded.append(
            (model_type, version_id, model_id, source, file_path)
        )

    async def mark_not_downloaded(self, model_type, version_id):
        self.marked_not_downloaded.append((model_type, version_id))


async def fake_download_history_service_factory():
    return FakeDownloadHistoryService()


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
        get_downloaded_version_history_service=fake_download_history_service_factory,
    )

    recorded_registrars = []

    def registrar_factory(app):
        registrar = RecordingRegistrar(app)
        recorded_registrars.append(registrar)
        return registrar

    controller = MiscRoutes(
        settings_service=DummySettings(),
        usage_stats_factory=lambda: SimpleNamespace(
            process_execution=noop_async, get_stats=noop_async
        ),
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
            get_downloaded_version_history_service=lambda: fake_download_history_service_factory(),
        ),
        metadata_provider_factory=provider_factory,
    )

    response = await handler.get_civitai_user_models(
        FakeRequest(query={"username": "pixel"})
    )
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
            "hasBeenDownloaded": False,
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
            "hasBeenDownloaded": False,
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
            "hasBeenDownloaded": False,
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
            "hasBeenDownloaded": False,
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
            "hasBeenDownloaded": False,
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
            get_downloaded_version_history_service=fake_download_history_service_factory,
        ),
        metadata_provider_factory=provider_factory,
    )

    response = await handler.get_civitai_user_models(
        FakeRequest(query={"username": "pixel"})
    )
    payload = json.loads(response.text)

    assert payload["success"] is True
    previews_by_version = {
        item["versionId"]: item["thumbnailUrl"] for item in payload["versions"]
    }
    assert (
        previews_by_version[100]
        == "https://image.civitai.com/container/example/width=450,optimized=true/sample.jpeg"
    )
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
            get_downloaded_version_history_service=fake_download_history_service_factory,
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
        usage_stats_factory=lambda: SimpleNamespace(
            process_execution=noop_async, get_stats=noop_async
        ),
        prompt_server=FakePromptServer,
        service_registry_adapter=ServiceRegistryAdapter(
            get_lora_scanner=fake_scanner_factory,
            get_checkpoint_scanner=fake_scanner_factory,
            get_embedding_scanner=fake_scanner_factory,
            get_downloaded_version_history_service=fake_download_history_service_factory,
        ),
        metadata_provider_factory=fake_metadata_provider_factory,
        metadata_archive_manager_factory=fake_metadata_archive_manager_factory,
        metadata_provider_updater=noop_async,
        downloader_factory=dummy_downloader_factory,
        handler_set_factory=RecordingHandlerSet,
    )

    first_mapping = controller._ensure_handler_mapping()
    second_mapping = controller._ensure_handler_mapping()

    assert first_mapping is second_mapping, (
        "Expected cached handler mapping to be reused"
    )
    assert len(call_records) == 1, "Handler set factory should only be invoked once"


@pytest.mark.asyncio
async def test_check_model_exists_returns_local_versions():
    versions = [
        {"versionId": 11, "name": "v1", "fileName": "model-one"},
        {"versionId": 12, "name": "v2", "fileName": "model-two"},
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
            get_downloaded_version_history_service=fake_download_history_service_factory,
        ),
        metadata_provider_factory=fake_metadata_provider_factory,
    )

    response = await handler.check_model_exists(FakeRequest(query={"modelId": "5"}))
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert payload["modelType"] == "lora"
    assert payload["versions"] == [
        {"versionId": 11, "name": "v1", "fileName": "model-one", "hasBeenDownloaded": True},
        {"versionId": 12, "name": "v2", "fileName": "model-two", "hasBeenDownloaded": True},
    ]
    assert lora_scanner.version_calls == [5]


@pytest.mark.asyncio
async def test_check_model_exists_model_id_only_does_not_call_metadata_provider():
    async def metadata_provider_factory():
        raise AssertionError("metadata provider should not be called for modelId-only checks")

    handler = ModelLibraryHandler(
        ServiceRegistryAdapter(
            get_lora_scanner=fake_scanner_factory,
            get_checkpoint_scanner=fake_scanner_factory,
            get_embedding_scanner=fake_scanner_factory,
            get_downloaded_version_history_service=fake_download_history_service_factory,
        ),
        metadata_provider_factory=metadata_provider_factory,
    )

    response = await handler.check_model_exists(FakeRequest(query={"modelId": "5"}))
    payload = json.loads(response.text)

    assert payload == {
        "success": True,
        "modelType": None,
        "versions": [],
        "downloadedVersionIds": [],
    }


@pytest.mark.asyncio
async def test_check_model_exists_returns_download_history_when_file_missing():
    history_service = FakeDownloadHistoryService({"checkpoint": {999}})

    async def history_factory():
        return history_service

    handler = ModelLibraryHandler(
        ServiceRegistryAdapter(
            get_lora_scanner=fake_scanner_factory,
            get_checkpoint_scanner=fake_scanner_factory,
            get_embedding_scanner=fake_scanner_factory,
            get_downloaded_version_history_service=history_factory,
        ),
        metadata_provider_factory=fake_metadata_provider_factory,
    )

    response = await handler.check_model_exists(
        FakeRequest(query={"modelId": "5", "modelVersionId": "999"})
    )
    payload = json.loads(response.text)

    assert payload == {
        "success": True,
        "exists": False,
        "modelType": "checkpoint",
        "hasBeenDownloaded": True,
    }


@pytest.mark.asyncio
async def test_model_version_download_status_endpoints():
    history_service = FakeDownloadHistoryService({"lora": {123}})

    async def history_factory():
        return history_service

    handler = ModelLibraryHandler(
        ServiceRegistryAdapter(
            get_lora_scanner=fake_scanner_factory,
            get_checkpoint_scanner=fake_scanner_factory,
            get_embedding_scanner=fake_scanner_factory,
            get_downloaded_version_history_service=history_factory,
        ),
        metadata_provider_factory=fake_metadata_provider_factory,
    )

    get_response = await handler.get_model_version_download_status(
        FakeRequest(query={"modelType": "lora", "modelVersionId": "123"})
    )
    get_payload = json.loads(get_response.text)
    assert get_payload == {
        "success": True,
        "modelType": "lora",
        "modelVersionId": 123,
        "hasBeenDownloaded": True,
    }

    set_response = await handler.set_model_version_download_status(
        FakeRequest(
            json_data={
                "modelType": "checkpoint",
                "modelVersionId": 456,
                "modelId": 78,
                "downloaded": True,
                "filePath": "/tmp/model.safetensors",
            }
        )
    )
    set_payload = json.loads(set_response.text)
    assert set_payload == {
        "success": True,
        "modelType": "checkpoint",
        "modelVersionId": 456,
        "hasBeenDownloaded": True,
    }
    assert history_service.marked_downloaded == [
        ("checkpoint", 456, 78, "manual", "/tmp/model.safetensors")
    ]

    set_get_response = await handler.set_model_version_download_status(
        FakeRequest(
            method="GET",
            query={
                "modelType": "embedding",
                "modelVersionId": "789",
                "modelId": "12",
                "downloaded": "false",
            },
        )
    )
    set_get_payload = json.loads(set_get_response.text)
    assert set_get_payload == {
        "success": True,
        "modelType": "embedding",
        "modelVersionId": 789,
        "hasBeenDownloaded": False,
    }


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
            get_downloaded_version_history_service=fake_download_history_service_factory,
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


def test_is_wsl_returns_true_in_wsl_environment():
    version_content = "Linux version 6.6.87.2-microsoft-standard-WSL2"
    with patch("py.routes.handlers.misc_handlers.open") as mock_open:
        mock_file = MagicMock()
        mock_file.read.return_value = version_content
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        result = _is_wsl()
        assert result is True


def test_is_wsl_returns_false_in_non_wsl_environment():
    version_content = "Linux version 6.6.0-25-generic #26-Ubuntu SMP PREEMPT_DYNAMIC"
    with patch("py.routes.handlers.misc_handlers.open") as mock_open:
        mock_file = MagicMock()
        mock_file.read.return_value = version_content
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        result = _is_wsl()
        assert result is False


def test_is_wsl_returns_false_on_read_error():
    with patch("py.routes.handlers.misc_handlers.open", side_effect=OSError()):
        result = _is_wsl()
        assert result is False


def test_is_wsl_returns_false_on_read_error():
    with patch("builtins.open", side_effect=OSError()):
        result = _is_wsl()
        assert result is False


def test_wsl_to_windows_path_converts_successfully():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.stdout = "C:\\Users\\test\\file.txt\n"
        mock_run.return_value = mock_result

        result = _wsl_to_windows_path("/mnt/c/test")
        assert result == "C:\\Users\\test\\file.txt"
        mock_run.assert_called_once()


def test_wsl_to_windows_path_returns_none_on_error():
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = _wsl_to_windows_path("/mnt/c/test")
        assert result is None


def test_wsl_to_windows_path_returns_none_on_subprocess_error():
    with patch(
        "subprocess.run", side_effect=subprocess.CalledProcessError(1, "wslpath")
    ):
        result = _wsl_to_windows_path("/mnt/c/test")
        assert result is None


def test_is_docker_returns_true_when_dockerenv_exists():
    with patch("os.path.exists", return_value=True):
        result = _is_docker()
        assert result is True


def test_is_docker_checks_cgroup_when_dockerenv_missing():
    cgroup_content = "1:name=systemd:/docker/abc123\n"
    with patch("os.path.exists", return_value=False):
        with patch("py.routes.handlers.misc_handlers.open") as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = cgroup_content
            mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            result = _is_docker()
            assert result is True


def test_is_docker_detects_kubernetes():
    cgroup_content = "12:pids:/kubepods/besteffort/pod123/abc123\n"
    with patch("os.path.exists", return_value=False):
        with patch("py.routes.handlers.misc_handlers.open") as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = cgroup_content
            mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            result = _is_docker()
            assert result is True


def test_is_docker_returns_false_when_no_docker_detected():
    cgroup_content = "1:name=systemd:/user.slice/user-1000.slice\n"
    with patch("os.path.exists", return_value=False):
        with patch("py.routes.handlers.misc_handlers.open") as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = cgroup_content
            mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            result = _is_docker()
            assert result is False


def test_is_docker_returns_false_on_cgroup_read_error():
    with patch("os.path.exists", return_value=False):
        with patch("py.routes.handlers.misc_handlers.open", side_effect=OSError()):
            result = _is_docker()
            assert result is False


def test_wsl_to_windows_path_returns_none_on_subprocess_error(tmp_path):
    with patch(
        "subprocess.run", side_effect=subprocess.CalledProcessError(1, "wslpath")
    ):
        result = _wsl_to_windows_path("/mnt/c/test")
        assert result is None
