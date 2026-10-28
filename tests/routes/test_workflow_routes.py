import json
import os

import pytest
from aiohttp import web

from py.routes.workflow_routes import WorkflowRoutes
from py.services.workflow_service import WorkflowService


class DummyRequest:
    def __init__(self, *, match_info=None, method="POST", query=None, body=None):
        self.match_info = match_info or {}
        self.method = method
        self.query = query or {}
        self._body = body

    async def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class StubScanner:
    def __init__(self, roots=None):
        self._roots = roots or []

    def get_model_roots(self):
        return list(self._roots)


class StubWorkflowService:
    def __init__(self, roots=None):
        self.info = {}
        self.scanner = StubScanner(roots)

    async def get_model_info_by_name(self, name):
        value = self.info.get(name)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def routes():
    handler = WorkflowRoutes()
    handler.service = StubWorkflowService()  # pyright: ignore[reportAttributeAccessIssue]
    return handler


@pytest.fixture(autouse=True)
def enable_workflows():
    """Workflow management is opt-in; these tests exercise the enabled state."""
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    manager.set("enable_workflows", True)
    yield
    manager.set("enable_workflows", False)


@pytest.fixture
def plugin_mode(monkeypatch):
    """send_to_comfy refuses to run in standalone mode; default to plugin mode."""
    monkeypatch.delenv("LORA_MANAGER_STANDALONE", raising=False)


def test_common_and_specific_routes_registered():
    """Registration smoke test: /api/lm/workflows/* surface plus the page."""
    app = web.Application()
    WorkflowRoutes().setup_routes(app)

    registered = {(route.method, route.resource.canonical) for route in app.router.routes()}

    assert ("GET", "/workflows") in registered
    assert ("GET", "/api/lm/workflows/list") in registered
    assert ("GET", "/api/lm/workflows/model-types") in registered
    assert ("GET", "/api/lm/workflows/roots") in registered
    assert ("POST", "/api/lm/workflows/fetch-civitai") in registered
    assert ("POST", "/api/lm/workflows/delete") in registered
    assert ("POST", "/api/lm/workflows/move_model") in registered
    assert ("GET", "/api/lm/workflows/info/{name}") in registered
    # The companion browser extension is GET-only (see AGENTS.md).
    assert ("POST", "/api/lm/workflows/send-to-comfy") in registered
    assert ("GET", "/api/lm/workflows/send-to-comfy") in registered


def test_template_name_is_workflows_page():
    assert WorkflowRoutes().template_name == "workflows.html"


@pytest.mark.parametrize(
    "model_type",
    ["Workflows", "workflows", "ComfyWorkflows", "comfyworkflows"],
)
def test_validate_civitai_model_type_accepts_workflow_types(model_type):
    assert WorkflowRoutes()._validate_civitai_model_type(model_type) is True


@pytest.mark.parametrize(
    "model_type", ["Lora", "Checkpoint", "TextualInversion", "VAE", "Other"]
)
def test_validate_civitai_model_type_rejects_foreign_types(model_type):
    assert WorkflowRoutes()._validate_civitai_model_type(model_type) is False


def test_validate_rejects_everything_when_feature_disabled():
    from py.services.settings_manager import get_settings_manager

    get_settings_manager().set("enable_workflows", False)

    handler = WorkflowRoutes()
    for model_type in ("Workflows", "ComfyWorkflows"):
        assert handler._validate_civitai_model_type(model_type) is False


def test_page_context_reports_feature_state(monkeypatch):
    from py.config import config
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    handler = WorkflowRoutes()
    provider = handler._get_page_context_provider()

    monkeypatch.setattr(config, "workflows_roots", ["/library/workflows"], raising=False)
    context = provider(None)
    assert context["workflows_disabled"] is False
    assert context["workflows_no_paths"] is False

    # Enabled but nothing configured: the page must explain how to fix it.
    monkeypatch.setattr(config, "workflows_roots", [], raising=False)
    context = provider(None)
    assert context["workflows_disabled"] is False
    assert context["workflows_no_paths"] is True

    manager.set("enable_workflows", False)
    assert provider(None) == {"workflows_disabled": True, "workflows_no_paths": False}


def test_page_context_exposes_settings_file_in_standalone(monkeypatch):
    """Standalone users must edit settings.json by hand; the empty state
    needs the real file path to point them at."""
    from py.config import config
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    handler = WorkflowRoutes()
    provider = handler._get_page_context_provider()

    monkeypatch.setattr(config, "workflows_roots", [], raising=False)
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")

    context = provider(None)
    assert context["workflows_no_paths"] is True
    assert context["standalone_mode"] is True
    assert context["settings_file"] == manager.settings_file


def test_get_expected_model_types_mentions_workflows():
    expected = WorkflowRoutes()._get_expected_model_types()
    assert "Workflows" in expected
    assert "ComfyWorkflows" in expected


def test_find_model_file_prefers_config_json_then_archive_zip():
    handler = WorkflowRoutes()
    files = [
        {"id": 3, "type": "Archive", "name": "bundle.zip"},
        {"id": 2, "type": "Config", "name": "workflow.json"},
        {"id": 1, "type": "Model", "name": "weights.safetensors"},
    ]
    assert handler._find_model_file(files)["name"] == "workflow.json"

    # Without a Config .json, the Archive .zip is the CivitAI default pick.
    assert handler._find_model_file(files[0:1] + files[2:])["name"] == "bundle.zip"


async def test_get_workflow_info_success(routes):
    routes.service.info["demo"] = {"name": "demo"}
    response = await routes.get_workflow_info(DummyRequest(match_info={"name": "demo"}))
    payload = json.loads(response.text)
    assert payload == {"name": "demo"}


async def test_get_workflow_info_missing(routes):
    response = await routes.get_workflow_info(DummyRequest(match_info={"name": "missing"}))
    payload = json.loads(response.text)
    assert response.status == 404
    assert payload == {"error": "Workflow not found"}


async def test_get_workflow_info_error(routes):
    routes.service.info["demo"] = RuntimeError("boom")
    response = await routes.get_workflow_info(DummyRequest(match_info={"name": "demo"}))
    payload = json.loads(response.text)
    assert response.status == 500
    assert payload == {"error": "boom"}


@pytest.mark.asyncio
async def test_initialize_services_builds_workflow_service(monkeypatch):
    from py.services.service_registry import ServiceRegistry

    sentinel_scanner = object()
    sentinel_update_service = object()

    async def fake_scanner():
        return sentinel_scanner

    async def fake_update_service():
        return sentinel_update_service

    monkeypatch.setattr(ServiceRegistry, "get_workflow_scanner", staticmethod(fake_scanner))
    monkeypatch.setattr(
        ServiceRegistry, "get_model_update_service", staticmethod(fake_update_service)
    )

    handler = WorkflowRoutes()
    await handler.initialize_services()

    assert isinstance(handler.service, WorkflowService)
    assert handler.service.model_type == "workflow"
    assert handler.service.scanner is sentinel_scanner


async def test_send_to_comfy_rejected_in_standalone(routes, monkeypatch):
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")
    response = await routes.send_to_comfy(
        DummyRequest(body={"file_path": "/library/workflows/flow.json"})
    )
    payload = json.loads(response.text)
    assert response.status == 400
    assert payload["success"] is False


async def test_send_to_comfy_rejected_when_feature_disabled(routes, plugin_mode):
    from py.services.settings_manager import get_settings_manager

    get_settings_manager().set("enable_workflows", False)
    response = await routes.send_to_comfy(
        DummyRequest(body={"file_path": "/library/workflows/flow.json"})
    )
    payload = json.loads(response.text)
    assert response.status == 400
    assert payload["success"] is False


async def test_send_to_comfy_requires_file_path(routes, plugin_mode):
    response = await routes.send_to_comfy(DummyRequest(body={}))
    payload = json.loads(response.text)
    assert response.status == 400
    assert payload == {"success": False, "error": "file_path is required"}


async def test_send_to_comfy_rejects_path_outside_library(routes, plugin_mode, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.send_to_comfy(
        DummyRequest(body={"file_path": str(tmp_path / "elsewhere.json")})
    )
    payload = json.loads(response.text)
    assert response.status == 400
    assert payload["success"] is False


async def test_send_to_comfy_404_for_non_workflow_json(routes, plugin_mode, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "config.json"
    target.write_text(json.dumps({"some": "config"}), encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.send_to_comfy(DummyRequest(body={"file_path": str(target)}))
    payload = json.loads(response.text)
    assert response.status == 404
    assert payload["error"] == "not_a_workflow"


async def test_send_to_comfy_broadcasts_workflow(routes, plugin_mode, tmp_path, monkeypatch):
    """Pin PromptServer.instance: other suites leak a bare SimpleNamespace onto
    the mocked server module, so never rely on the global mock state."""
    import server
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    send_sync = MagicMock()
    monkeypatch.setattr(
        server.PromptServer, "instance", SimpleNamespace(send_sync=send_sync)
    )

    root = tmp_path / "workflows"
    root.mkdir()
    workflow = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    target = root / "flow.json"
    target.write_text(json.dumps(workflow), encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.send_to_comfy(DummyRequest(body={"file_path": str(target)}))
    payload = json.loads(response.text)

    assert payload == {"success": True, "sent": True}
    send_sync.assert_called_once_with(
        "lm_load_workflow", {"workflow": workflow, "name": "flow"}
    )


async def test_send_to_comfy_accepts_get_with_query(routes, plugin_mode, tmp_path, monkeypatch):
    import server
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    send_sync = MagicMock()
    monkeypatch.setattr(
        server.PromptServer, "instance", SimpleNamespace(send_sync=send_sync)
    )

    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "flow.json"
    target.write_text(
        json.dumps({"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}),
        encoding="utf-8",
    )
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.send_to_comfy(
        DummyRequest(method="GET", query={"file_path": str(target)})
    )
    payload = json.loads(response.text)
    assert payload == {"success": True, "sent": True}
    send_sync.assert_called_once()


async def test_send_to_comfy_reads_derived_document_for_zip(routes, plugin_mode, tmp_path, monkeypatch):
    """Container artifacts send the extracted document, not the zip bytes."""
    import server
    import zipfile
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    send_sync = MagicMock()
    monkeypatch.setattr(
        server.PromptServer, "instance", SimpleNamespace(send_sync=send_sync)
    )

    root = tmp_path / "workflows"
    root.mkdir()
    workflow = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    target = root / "pack.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("workflow.json", json.dumps(workflow))
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.send_to_comfy(DummyRequest(body={"file_path": str(target)}))
    payload = json.loads(response.text)

    assert payload == {"success": True, "sent": True}
    send_sync.assert_called_once_with(
        "lm_load_workflow", {"workflow": workflow, "name": "pack"}
    )
    # The extraction is cached as a derived sidecar document.
    assert (root / "pack.workflow.json").exists()
