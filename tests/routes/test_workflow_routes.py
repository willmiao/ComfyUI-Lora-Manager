import hashlib
import json
import os
from types import SimpleNamespace

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
        self.registered = []

    def get_model_roots(self):
        return list(self._roots)

    async def register_local_artifact(self, file_path):
        self.registered.append(file_path)
        return SimpleNamespace(
            file_path=file_path.replace(os.sep, "/"), preview_url=""
        )


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
    assert ("GET", "/api/lm/workflows/content") in registered
    # "Create LM-managed workflow" from the ComfyUI Graph menu.
    assert ("POST", "/api/lm/workflows/create") in registered
    assert ("GET", "/api/lm/workflows/link-status") in registered
    # Write-back from the ComfyUI-side "Update LM-managed workflow" entry.
    assert ("PUT", "/api/lm/workflows/content") in registered
    # Link-state reporting + LM-page-triggered write-back ("Update from ComfyUI").
    assert ("POST", "/api/lm/workflows/comfyui-state") in registered
    assert ("GET", "/api/lm/workflows/comfyui-state") in registered
    assert ("POST", "/api/lm/workflows/update-from-comfy") in registered
    assert ("POST", "/api/lm/workflows/collect-result") in registered
    # Restore to downloaded state ("Restore Downloaded Version" card menu entry).
    assert ("POST", "/api/lm/workflows/restore") in registered


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
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    handler = WorkflowRoutes()
    provider = handler._get_page_context_provider()

    monkeypatch.setattr(
        manager, "get_workflow_path", lambda: "/library/workflows"
    )
    context = provider(None)
    assert context["workflows_disabled"] is False
    assert context["workflows_no_paths"] is False

    # Enabled but nothing configured: the page must explain how to fix it.
    monkeypatch.setattr(manager, "get_workflow_path", lambda: "")
    context = provider(None)
    assert context["workflows_disabled"] is False
    assert context["workflows_no_paths"] is True

    manager.set("enable_workflows", False)
    assert provider(None) == {"workflows_disabled": True, "workflows_no_paths": False}


def test_page_context_reports_standalone_mode(monkeypatch):
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    handler = WorkflowRoutes()
    provider = handler._get_page_context_provider()

    monkeypatch.setattr(manager, "get_workflow_path", lambda: "")
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")

    context = provider(None)
    assert context["workflows_no_paths"] is True
    assert context["standalone_mode"] is True
    # The empty state points at Settings > Library in both modes; no
    # settings.json editing hint/fallback is exposed.
    assert "settings_file" not in context


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
    send_sync.assert_called_once()
    channel, message = send_sync.call_args.args
    assert channel == "lm_load_workflow"
    assert message["workflow"] == workflow
    assert message["name"] == "flow"
    # Provenance marker for the ComfyUI-side write-back entry point.
    assert message["lm_source"]["file_path"] == str(target)
    import hashlib

    assert message["lm_source"]["sha256"] == hashlib.sha256(
        target.read_bytes()
    ).hexdigest()


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
    send_sync.assert_called_once()
    channel, message = send_sync.call_args.args
    assert channel == "lm_load_workflow"
    assert message["workflow"] == workflow
    assert message["name"] == "pack"
    # The marker hashes the derived document (what the write-back edits), not
    # the zip bytes.
    derived = root / "pack.workflow.json"
    assert derived.exists()
    import hashlib

    assert message["lm_source"] == {
        "file_path": str(target),
        "sha256": hashlib.sha256(derived.read_bytes()).hexdigest(),
    }


async def test_get_workflow_content_returns_document(routes, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    workflow = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    target = root / "flow.json"
    target.write_text(json.dumps(workflow), encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.get_workflow_content(
        DummyRequest(method="GET", query={"file_path": str(target)})
    )
    payload = json.loads(response.text)

    assert payload == {"success": True, "workflow": workflow}


async def test_get_workflow_content_works_in_standalone(routes, tmp_path, monkeypatch):
    """The copy-to-clipboard flow needs no ComfyUI, unlike send-to-comfy."""
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")

    root = tmp_path / "workflows"
    root.mkdir()
    workflow = {"nodes": [{"id": 1, "type": "CLIPTextEncode"}], "links": []}
    target = root / "flow.json"
    target.write_text(json.dumps(workflow), encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.get_workflow_content(
        DummyRequest(method="GET", query={"file_path": str(target)})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload == {"success": True, "workflow": workflow}


async def test_get_workflow_content_reads_derived_document_for_zip(routes, tmp_path):
    import zipfile

    root = tmp_path / "workflows"
    root.mkdir()
    workflow = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    target = root / "pack.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("workflow.json", json.dumps(workflow))
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.get_workflow_content(
        DummyRequest(method="GET", query={"file_path": str(target)})
    )
    payload = json.loads(response.text)

    assert payload == {"success": True, "workflow": workflow}


async def test_get_workflow_content_404_for_non_workflow_json(routes, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "config.json"
    target.write_text(json.dumps({"some": "config"}), encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.get_workflow_content(
        DummyRequest(method="GET", query={"file_path": str(target)})
    )
    payload = json.loads(response.text)

    assert response.status == 404
    assert payload["error"] == "not_a_workflow"


async def test_get_workflow_content_rejects_path_outside_library(routes, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.get_workflow_content(
        DummyRequest(method="GET", query={"file_path": str(tmp_path / "elsewhere.json")})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


async def test_get_workflow_content_rejected_when_feature_disabled(routes, tmp_path):
    from py.services.settings_manager import get_settings_manager

    get_settings_manager().set("enable_workflows", False)
    response = await routes.get_workflow_content(
        DummyRequest(method="GET", query={"file_path": "/library/workflows/flow.json"})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


async def test_update_workflow_content_rewrites_json_artifact(routes, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    original = {"nodes": [{"id": 1, "type": "CLIPTextEncode"}], "links": []}
    target = root / "flow.json"
    target.write_text(json.dumps(original), encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    updated = {
        "nodes": [
            {"id": 1, "type": "CLIPTextEncode"},
            {"id": 2, "type": "KSampler"},
        ],
        "links": [],
        # The client-side provenance marker must be stripped before persisting.
        "extra": {"lm_source": {"file_path": str(target), "sha256": "x"}},
    }
    response = await routes.update_workflow_content(
        DummyRequest(method="PUT", body={"file_path": str(target), "workflow": updated})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["nodes"] == updated["nodes"]
    assert "lm_source" not in written.get("extra", {})


async def test_update_workflow_content_conflict_then_force(routes, tmp_path):
    import hashlib

    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "flow.json"
    workflow = {"nodes": [{"id": 1, "type": "CLIPTextEncode"}], "links": []}
    target.write_text(json.dumps(workflow), encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    stale_hash = hashlib.sha256(b"old-bytes").hexdigest()
    response = await routes.update_workflow_content(
        DummyRequest(
            method="PUT",
            body={
                "file_path": str(target),
                "workflow": workflow,
                "base_sha256": stale_hash,
            },
        )
    )
    payload = json.loads(response.text)

    assert response.status == 409
    assert payload["error"] == "conflict"
    assert payload["current_sha256"] == hashlib.sha256(
        target.read_bytes()
    ).hexdigest()

    forced = await routes.update_workflow_content(
        DummyRequest(
            method="PUT",
            body={
                "file_path": str(target),
                "workflow": workflow,
                "base_sha256": stale_hash,
                "force": True,
            },
        )
    )
    assert json.loads(forced.text)["success"] is True


async def test_update_workflow_content_writes_derived_sidecar_for_zip(routes, tmp_path):
    """Container artifacts stay byte-identical; edits land in the sidecar."""
    import zipfile

    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "pack.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(
            "workflow.json",
            json.dumps({"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}),
        )
    original_bytes = target.read_bytes()
    routes.service.scanner = StubScanner([str(root)])

    updated = {"nodes": [{"id": 1, "type": "KSampler"}], "links": []}
    response = await routes.update_workflow_content(
        DummyRequest(method="PUT", body={"file_path": str(target), "workflow": updated})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert target.read_bytes() == original_bytes
    derived = root / "pack.workflow.json"
    assert json.loads(derived.read_text(encoding="utf-8"))["nodes"] == updated["nodes"]


async def test_update_workflow_content_rejects_non_workflow(routes, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "flow.json"
    target.write_text("{}", encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.update_workflow_content(
        DummyRequest(
            method="PUT",
            body={"file_path": str(target), "workflow": {"some": "config"}},
        )
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


async def test_update_workflow_content_rejects_path_outside_library(routes, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.update_workflow_content(
        DummyRequest(
            method="PUT",
            body={
                "file_path": str(tmp_path / "elsewhere.json"),
                "workflow": {"nodes": [{"id": 1, "type": "KSampler"}], "links": []},
            },
        )
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


async def test_update_workflow_content_rejected_when_feature_disabled(routes):
    from py.services.settings_manager import get_settings_manager

    get_settings_manager().set("enable_workflows", False)
    response = await routes.update_workflow_content(
        DummyRequest(
            method="PUT",
            body={"file_path": "/library/workflows/flow.json", "workflow": {}},
        )
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# ComfyUI link-state reporting + LM-page-triggered write-back
# ---------------------------------------------------------------------------


@pytest.fixture
def link_registry():
    from py.services.workflow_link_registry import WorkflowLinkRegistry

    WorkflowLinkRegistry.reset_instance()
    yield
    WorkflowLinkRegistry.reset_instance()


def _mock_prompt_server(monkeypatch, sids=("c1",)):
    import server
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    send_sync = MagicMock()
    monkeypatch.setattr(
        server.PromptServer,
        "instance",
        SimpleNamespace(sockets={sid: object() for sid in sids}, send_sync=send_sync),
    )
    return send_sync


async def test_comfyui_state_report_and_query_roundtrip(
    routes, plugin_mode, link_registry, monkeypatch
):
    _mock_prompt_server(monkeypatch, sids=("c1",))

    response = await routes.report_comfyui_state(
        DummyRequest(
            body={
                "client_id": "c1",
                "state": {
                    "file_path": "/lib/flow.json",
                    "sha256": "abc",
                    "dirty": True,
                },
            }
        )
    )
    assert json.loads(response.text)["success"] is True

    response = await routes.get_comfyui_state(DummyRequest(method="GET"))
    payload = json.loads(response.text)

    assert payload["success"] is True
    assert len(payload["states"]) == 1
    state = payload["states"][0]
    assert state["client_id"] == "c1"
    assert state["file_path"] == "/lib/flow.json"
    assert state["dirty"] is True


async def test_comfyui_state_prunes_disconnected_clients(
    routes, plugin_mode, link_registry, monkeypatch
):
    _mock_prompt_server(monkeypatch, sids=("c1",))

    await routes.report_comfyui_state(
        DummyRequest(
            body={"client_id": "gone", "state": {"file_path": "/lib/a.json", "dirty": True}}
        )
    )
    response = await routes.get_comfyui_state(DummyRequest(method="GET"))

    assert json.loads(response.text)["states"] == []


async def test_comfyui_state_null_clears_entry(
    routes, plugin_mode, link_registry, monkeypatch
):
    _mock_prompt_server(monkeypatch, sids=("c1",))

    await routes.report_comfyui_state(
        DummyRequest(
            body={"client_id": "c1", "state": {"file_path": "/lib/a.json", "dirty": True}}
        )
    )
    await routes.report_comfyui_state(DummyRequest(body={"client_id": "c1", "state": None}))

    response = await routes.get_comfyui_state(DummyRequest(method="GET"))
    assert json.loads(response.text)["states"] == []


async def test_report_comfyui_state_requires_client_id(routes, plugin_mode, link_registry):
    response = await routes.report_comfyui_state(DummyRequest(body={"state": None}))
    assert response.status == 400


async def test_get_comfyui_state_empty_in_standalone(routes, monkeypatch, link_registry):
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")

    response = await routes.get_comfyui_state(DummyRequest(method="GET"))
    payload = json.loads(response.text)

    assert payload == {"success": True, "states": []}


async def test_collect_result_unknown_request(routes, plugin_mode, link_registry):
    response = await routes.collect_result(
        DummyRequest(body={"request_id": "nope", "success": True})
    )
    payload = json.loads(response.text)

    assert payload == {"success": True, "resolved": False}


async def test_update_from_comfy_not_open(routes, plugin_mode, link_registry, tmp_path, monkeypatch):
    _mock_prompt_server(monkeypatch)

    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "flow.json"
    target.write_text("{}", encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.update_from_comfy(
        DummyRequest(body={"file_path": str(target)})
    )
    payload = json.loads(response.text)

    assert response.status == 404
    assert payload["error"] == "not_open"


async def test_update_from_comfy_roundtrip(
    routes, plugin_mode, link_registry, tmp_path, monkeypatch
):
    import asyncio

    send_sync = _mock_prompt_server(monkeypatch, sids=("c1",))

    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "flow.json"
    target.write_text("{}", encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    await routes.report_comfyui_state(
        DummyRequest(
            body={
                "client_id": "c1",
                "state": {"file_path": str(target), "sha256": "abc", "dirty": True},
            }
        )
    )

    task = asyncio.create_task(
        routes.update_from_comfy(DummyRequest(body={"file_path": str(target)}))
    )
    for _ in range(100):
        if send_sync.call_count:
            break
        await asyncio.sleep(0.01)
    assert send_sync.call_count == 1

    channel, message = send_sync.call_args.args[:2]
    assert channel == "lm_collect_workflow"
    assert message["file_path"] == str(target)
    assert send_sync.call_args.kwargs.get("sid") == "c1"

    await routes.collect_result(
        DummyRequest(
            body={
                "request_id": message["request_id"],
                "success": True,
                "sha256": "new-hash",
            }
        )
    )
    response = await asyncio.wait_for(task, timeout=5)
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["sha256"] == "new-hash"


async def test_update_from_comfy_no_changes_is_200(
    routes, plugin_mode, link_registry, tmp_path, monkeypatch
):
    import asyncio

    send_sync = _mock_prompt_server(monkeypatch, sids=("c1",))

    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "flow.json"
    target.write_text("{}", encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    await routes.report_comfyui_state(
        DummyRequest(
            body={"client_id": "c1", "state": {"file_path": str(target), "dirty": True}}
        )
    )

    task = asyncio.create_task(
        routes.update_from_comfy(DummyRequest(body={"file_path": str(target)}))
    )
    for _ in range(100):
        if send_sync.call_count:
            break
        await asyncio.sleep(0.01)

    request_id = send_sync.call_args.args[1]["request_id"]
    await routes.collect_result(
        DummyRequest(
            body={"request_id": request_id, "success": False, "error": "no_changes"}
        )
    )
    response = await asyncio.wait_for(task, timeout=5)

    assert response.status == 200
    assert json.loads(response.text)["error"] == "no_changes"


async def test_update_from_comfy_rejected_in_standalone(routes, monkeypatch, link_registry):
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")

    response = await routes.update_from_comfy(
        DummyRequest(body={"file_path": "/lib/flow.json"})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


async def test_restore_container_reextracts_pristine_document(routes, tmp_path):
    """Zip artifacts stay byte-identical; restore discards the edited sidecar."""
    import zipfile

    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "pack.zip"
    original_doc = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("workflow.json", json.dumps(original_doc))
    original_bytes = target.read_bytes()
    routes.service.scanner = StubScanner([str(root)])

    # Simulate a write-back: the derived sidecar now carries local edits.
    edited = {"nodes": [{"id": 1, "type": "KSampler"}], "links": []}
    response = await routes.update_workflow_content(
        DummyRequest(method="PUT", body={"file_path": str(target), "workflow": edited})
    )
    assert json.loads(response.text)["success"] is True

    response = await routes.restore_workflow(
        DummyRequest(method="POST", body={"file_path": str(target)})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["restored"] == "extracted"
    assert target.read_bytes() == original_bytes
    derived = root / "pack.workflow.json"
    assert json.loads(derived.read_text(encoding="utf-8")) == original_doc


def _civitai_metadata(target, original_bytes, sha):
    from py.utils.models import WorkflowMetadata

    return WorkflowMetadata(
        file_name="flow",
        model_name="Flow",
        file_path=str(target),
        size=len(original_bytes),
        modified=0,
        sha256=sha,
        base_model="SDXL",
        preview_url="",
        civitai={
            "id": 3431529,
            "files": [
                {
                    "name": "flow.json",
                    "downloadUrl": "https://civitai.test/dl/flow.json",
                    "hashes": {"SHA256": sha},
                }
            ],
        },
    )


async def test_restore_json_requires_civitai_source(routes, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "flow.json"
    target.write_text(
        json.dumps({"nodes": [{"id": 1, "type": "KSampler"}], "links": []}),
        encoding="utf-8",
    )
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.restore_workflow(
        DummyRequest(method="POST", body={"file_path": str(target)})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False
    assert payload["error"] == "no_source"


async def test_restore_json_redownloads_recorded_version(routes, tmp_path, monkeypatch):
    import hashlib

    from py.utils.metadata_manager import MetadataManager

    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "flow.json"
    edited = {"nodes": [{"id": 1, "type": "KSampler"}], "links": []}
    target.write_text(json.dumps(edited), encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])

    original = {"nodes": [{"id": 1, "type": "CLIPTextEncode"}], "links": []}
    original_bytes = json.dumps(original).encode("utf-8")
    original_sha = hashlib.sha256(original_bytes).hexdigest()
    await MetadataManager.save_metadata(
        str(target), _civitai_metadata(target, original_bytes, original_sha)
    )

    async def fake_download(self, url, file_path, *, expected_sha256=None):
        assert url == "https://civitai.test/dl/flow.json"
        assert expected_sha256 == original_sha
        with open(file_path, "wb") as handle:
            handle.write(original_bytes)
        return original_sha

    monkeypatch.setattr(WorkflowRoutes, "_download_and_replace", fake_download)

    response = await routes.restore_workflow(
        DummyRequest(method="POST", body={"file_path": str(target)})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["restored"] == "downloaded"
    assert payload["sha256"] == original_sha
    assert json.loads(target.read_text(encoding="utf-8")) == original

    # Metadata analysis and identity follow the restored document.
    from py.utils.models import WorkflowMetadata

    reloaded, should_skip = await MetadataManager.load_metadata(
        str(target), WorkflowMetadata
    )
    assert not should_skip
    assert reloaded.sha256 == original_sha
    assert reloaded.node_classes == ["CLIPTextEncode"]


async def test_restore_json_download_failure_surfaces_502(routes, tmp_path, monkeypatch):
    import hashlib

    from py.routes.workflow_routes import WorkflowRestoreDownloadError
    from py.utils.metadata_manager import MetadataManager

    root = tmp_path / "workflows"
    root.mkdir()
    target = root / "flow.json"
    edited = {"nodes": [{"id": 1, "type": "KSampler"}], "links": []}
    edited_bytes = json.dumps(edited).encode("utf-8")
    target.write_bytes(edited_bytes)
    routes.service.scanner = StubScanner([str(root)])

    original_sha = hashlib.sha256(b"original").hexdigest()
    await MetadataManager.save_metadata(
        str(target), _civitai_metadata(target, b"original", original_sha)
    )

    async def failing_download(self, url, file_path, *, expected_sha256=None):
        raise WorkflowRestoreDownloadError("Download failed with HTTP 404")

    monkeypatch.setattr(WorkflowRoutes, "_download_and_replace", failing_download)

    response = await routes.restore_workflow(
        DummyRequest(method="POST", body={"file_path": str(target)})
    )
    payload = json.loads(response.text)

    assert response.status == 502
    assert payload["success"] is False
    assert payload["error"] == "download_failed"
    # A failed restore never touches the local file.
    assert target.read_bytes() == edited_bytes


async def test_restore_rejected_when_feature_disabled(routes):
    from py.services.settings_manager import get_settings_manager

    get_settings_manager().set("enable_workflows", False)
    response = await routes.restore_workflow(
        DummyRequest(method="POST", body={"file_path": "/library/workflows/flow.json"})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


async def test_restore_rejects_path_outside_library(routes, tmp_path):
    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = StubScanner([str(root)])

    response = await routes.restore_workflow(
        DummyRequest(method="POST", body={"file_path": str(tmp_path / "elsewhere.json")})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# Create LM-managed workflow
# ---------------------------------------------------------------------------

UI_GRAPH = {
    "nodes": [{"id": 1, "type": "KSampler"}],
    "links": [],
    "extra": {"ds": {"scale": 1}},
}


def _pin_workflow_path(monkeypatch, path):
    from py.services.settings_manager import get_settings_manager

    monkeypatch.setattr(
        get_settings_manager(), "get_workflow_path", lambda: str(path)
    )


def _patch_broadcast(monkeypatch):
    from py.routes.handlers import model_handlers

    calls = []
    monkeypatch.setattr(
        model_handlers, "_broadcast_models_changed", lambda: calls.append(True)
    )
    return calls


async def test_create_workflow_writes_document_and_returns_marker(
    routes, plugin_mode, tmp_path, monkeypatch
):
    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = StubScanner([str(root)])  # pyright: ignore[reportAttributeAccessIssue]
    _pin_workflow_path(monkeypatch, root)
    broadcast_calls = _patch_broadcast(monkeypatch)

    graph = json.loads(json.dumps(UI_GRAPH))
    graph["extra"]["lm_source"] = {
        "file_path": "/old/flow.json",
        "sha256": "old",
    }

    response = await routes.create_workflow(
        DummyRequest(body={"name": "My Flow", "workflow": graph})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["name"] == "My Flow"
    assert payload["preview"] is False

    target = root / "My Flow.json"
    assert target.exists()
    assert payload["file_path"] == str(target).replace(os.sep, "/")
    assert payload["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()

    stored = json.loads(target.read_text(encoding="utf-8"))
    # The client-side provenance marker never lands in the library document.
    assert "lm_source" not in stored["extra"]
    assert stored["extra"]["ds"] == {"scale": 1}

    # The file is registered in the scanner cache before the response.
    assert routes.service.scanner.registered == [  # pyright: ignore[reportAttributeAccessIssue]
        str(target).replace(os.sep, "/")
    ]
    assert broadcast_calls == [True]


async def test_create_workflow_sanitizes_name_and_avoids_collision(
    routes, plugin_mode, tmp_path, monkeypatch
):
    root = tmp_path / "workflows"
    root.mkdir()
    (root / "My Flow.json").write_text("{}", encoding="utf-8")
    routes.service.scanner = StubScanner([str(root)])  # pyright: ignore[reportAttributeAccessIssue]
    _pin_workflow_path(monkeypatch, root)
    _patch_broadcast(monkeypatch)

    response = await routes.create_workflow(
        DummyRequest(body={"name": "My Flow", "workflow": UI_GRAPH})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["name"].startswith("My Flow-")
    assert (root / f"{payload['name']}.json").exists()
    # The existing entry is untouched.
    assert (root / "My Flow.json").read_text(encoding="utf-8") == "{}"

    hostile = await routes.create_workflow(
        DummyRequest(body={"name": "../escape/name", "workflow": UI_GRAPH})
    )
    hostile_payload = json.loads(hostile.text)

    assert hostile.status == 200
    created = (root / f"{hostile_payload['name']}.json").resolve()
    # Path separators are sanitized: the file cannot escape the library root.
    assert created.parent == root.resolve()
    assert ".." not in created.name


async def test_create_workflow_rejected_in_standalone(routes, monkeypatch):
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")
    response = await routes.create_workflow(
        DummyRequest(body={"workflow": UI_GRAPH})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


async def test_create_workflow_rejected_when_feature_disabled(routes, plugin_mode):
    from py.services.settings_manager import get_settings_manager

    get_settings_manager().set("enable_workflows", False)
    response = await routes.create_workflow(
        DummyRequest(body={"workflow": UI_GRAPH})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


async def test_create_workflow_requires_workflow(routes, plugin_mode):
    response = await routes.create_workflow(DummyRequest(body={}))
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload == {"success": False, "error": "workflow is required"}


async def test_create_workflow_rejects_non_graph_document(routes, plugin_mode):
    response = await routes.create_workflow(
        DummyRequest(body={"workflow": {"some": "config"}})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


async def test_create_workflow_requires_configured_folder(
    routes, plugin_mode, monkeypatch
):
    _pin_workflow_path(monkeypatch, "")

    response = await routes.create_workflow(
        DummyRequest(body={"workflow": UI_GRAPH})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert "workflow library folder" in payload["error"].lower()


async def test_create_workflow_enforces_size_limit(
    routes, plugin_mode, tmp_path, monkeypatch
):
    import py.routes.workflow_routes as workflow_routes_module

    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = StubScanner([str(root)])  # pyright: ignore[reportAttributeAccessIssue]
    _pin_workflow_path(monkeypatch, root)
    monkeypatch.setattr(workflow_routes_module, "MAX_WORKFLOW_JSON_BYTES", 10)

    response = await routes.create_workflow(
        DummyRequest(body={"workflow": UI_GRAPH})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["error"] == "workflow exceeds the size limit"
    assert list(root.iterdir()) == []


async def test_create_workflow_rolls_back_when_registration_fails(
    routes, plugin_mode, tmp_path, monkeypatch
):
    class FailingScanner(StubScanner):
        async def register_local_artifact(self, file_path):
            return None

    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = FailingScanner()  # pyright: ignore[reportAttributeAccessIssue]
    _pin_workflow_path(monkeypatch, root)

    response = await routes.create_workflow(
        DummyRequest(body={"workflow": UI_GRAPH})
    )
    payload = json.loads(response.text)

    assert response.status == 500
    assert payload["success"] is False
    # The half-written document is rolled back.
    assert list(root.iterdir()) == []


async def test_create_workflow_sanitizes_reserved_and_blank_names(
    routes, plugin_mode, tmp_path, monkeypatch
):
    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = StubScanner([str(root)])  # pyright: ignore[reportAttributeAccessIssue]
    _pin_workflow_path(monkeypatch, root)
    _patch_broadcast(monkeypatch)

    reserved = await routes.create_workflow(
        DummyRequest(body={"name": "CON", "workflow": UI_GRAPH})
    )
    assert json.loads(reserved.text)["name"] == "_CON"

    blank = await routes.create_workflow(
        DummyRequest(body={"name": "   ", "workflow": UI_GRAPH})
    )
    assert json.loads(blank.text)["name"] == "Untitled"


async def test_update_workflow_content_404s_for_deleted_library_entry(
    routes, plugin_mode, tmp_path
):
    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = StubScanner([str(root)])  # pyright: ignore[reportAttributeAccessIssue]
    target = root / "gone.json"

    response = await routes.update_workflow_content(
        DummyRequest(body={"file_path": str(target), "workflow": UI_GRAPH})
    )
    payload = json.loads(response.text)

    assert response.status == 404
    assert payload["error"] == "not_found"
    # A stale marker must never resurrect a deleted library entry.
    assert not target.exists()


async def test_link_status_reports_existing_and_missing(
    routes, plugin_mode, tmp_path
):
    root = tmp_path / "workflows"
    root.mkdir()
    routes.service.scanner = StubScanner([str(root)])  # pyright: ignore[reportAttributeAccessIssue]
    target = root / "flow.json"
    target.write_text(json.dumps(UI_GRAPH), encoding="utf-8")

    response = await routes.get_workflow_link_status(
        DummyRequest(method="GET", query={"file_path": str(target)})
    )
    assert json.loads(response.text) == {"success": True, "exists": True}

    target.unlink()
    response = await routes.get_workflow_link_status(
        DummyRequest(method="GET", query={"file_path": str(target)})
    )
    assert json.loads(response.text) == {"success": True, "exists": False}

    # A path outside the live library roots is gone as far as the client cares.
    response = await routes.get_workflow_link_status(
        DummyRequest(method="GET", query={"file_path": str(tmp_path / "outside.json")})
    )
    assert json.loads(response.text) == {"success": True, "exists": False}


async def test_create_workflow_attaches_preview_for_matching_prompt(
    routes, plugin_mode, tmp_path, monkeypatch
):
    import io

    from PIL import Image

    import py.routes.workflow_routes as workflow_routes_module
    import py.utils.sidecar_paths as sidecar_paths

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (128, 128, 128)).save(buffer, format="PNG")
    monkeypatch.setattr(
        workflow_routes_module,
        "_resolve_workflow_preview",
        lambda _prompt_id: buffer.getvalue(),
    )

    root = tmp_path / "workflows"
    root.mkdir()
    # Pin preview storage to the workflow folder even if another test left the
    # global sidecar mode centralized.
    monkeypatch.setattr(sidecar_paths, "get_preview_dir", lambda _path: str(root))
    routes.service.scanner = StubScanner([str(root)])  # pyright: ignore[reportAttributeAccessIssue]
    _pin_workflow_path(monkeypatch, root)
    _patch_broadcast(monkeypatch)

    response = await routes.create_workflow(
        DummyRequest(
            body={
                "name": "With Preview",
                "workflow": UI_GRAPH,
                "preview_prompt_id": "p-preview",
            }
        )
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["preview"] is True
    assert (root / "With Preview.preview.webp").exists()


async def test_create_workflow_skips_preview_for_other_prompt(
    routes, plugin_mode, tmp_path, monkeypatch
):
    import py.routes.workflow_routes as workflow_routes_module
    import py.utils.sidecar_paths as sidecar_paths

    monkeypatch.setattr(
        workflow_routes_module, "_resolve_workflow_preview", lambda _prompt_id: None
    )

    root = tmp_path / "workflows"
    root.mkdir()
    # Pin preview storage to the workflow folder even if another test left the
    # global sidecar mode centralized.
    monkeypatch.setattr(sidecar_paths, "get_preview_dir", lambda _path: str(root))
    routes.service.scanner = StubScanner([str(root)])  # pyright: ignore[reportAttributeAccessIssue]
    _pin_workflow_path(monkeypatch, root)
    _patch_broadcast(monkeypatch)

    response = await routes.create_workflow(
        DummyRequest(
            body={
                "name": "No Preview",
                "workflow": UI_GRAPH,
                "preview_prompt_id": "p-preview",
            }
        )
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["preview"] is False
    assert list(root.glob("*.preview.webp")) == []


def test_resolve_workflow_preview_requires_matching_prompt():
    import numpy as np

    from py.routes.workflow_routes import _resolve_workflow_preview

    class FakeRegistry:
        def __init__(self):
            self.current_prompt_id = "p-1"

        def get_first_decoded_image(self, prompt_id=None):
            return np.full((4, 4, 3), 0.5, dtype=np.float32)

    assert _resolve_workflow_preview("p-1", registry_cls=FakeRegistry) is not None
    assert _resolve_workflow_preview("p-2", registry_cls=FakeRegistry) is None
