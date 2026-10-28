import asyncio
import hashlib
import json
import logging
import os
import tempfile
from typing import Any, Dict, Optional

from aiohttp import web

from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar
from ..config import config
from ..services.model_lifecycle_service import _require_path_in_library_roots
from ..services.service_registry import ServiceRegistry
from ..services.workflow_service import WorkflowService
from ..utils.constants import WORKFLOW_CIVITAI_TYPES
from ..utils.file_utils import calculate_sha256
from ..utils.metadata_manager import MetadataManager
from ..utils.models import WorkflowMetadata
from ..utils.workflow_analysis import MAX_WORKFLOW_JSON_BYTES, analyze_workflow
from ..utils.workflow_extraction import (
    get_workflow_document_path,
    load_artifact_workflow_document,
)

logger = logging.getLogger(__name__)


class WorkflowRoutes(BaseModelRoutes):
    """Workflow-specific route controller (ComfyUI workflow JSON resources).

    Workflow management is opt-in (``enable_workflows``): while disabled the
    page renders an enable-now empty state and CivitAI linking is rejected.
    """

    def __init__(self):
        """Initialize Workflow routes with Workflow service"""
        super().__init__()
        self.template_name = "workflows.html"

    async def initialize_services(self):
        """Initialize services from ServiceRegistry"""
        workflow_scanner = await ServiceRegistry.get_workflow_scanner()
        update_service = await ServiceRegistry.get_model_update_service()
        self.service = WorkflowService(workflow_scanner, update_service=update_service)
        self.set_model_update_service(update_service)

        # Attach service dependencies
        self.attach_service(self.service)

    def setup_routes(self, app: web.Application, prefix: str = "workflows"):
        """Setup Workflow routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())

        # Setup common routes with 'workflows' prefix (includes page route)
        super().setup_routes(app, prefix)

    def setup_specific_routes(self, registrar: ModelRouteRegistrar, prefix: str):
        """Setup Workflow-specific routes"""
        # Workflow info by name
        registrar.add_prefixed_route(
            'GET', '/api/lm/{prefix}/info/{name}', prefix, self.get_workflow_info
        )
        # Push a workflow into the ComfyUI graph (plugin mode only). Accepts
        # GET as well: the companion browser extension is GET-only by
        # convention (see AGENTS.md).
        registrar.add_prefixed_route(
            'POST', '/api/lm/{prefix}/send-to-comfy', prefix, self.send_to_comfy
        )
        registrar.add_prefixed_route(
            'GET', '/api/lm/{prefix}/send-to-comfy', prefix, self.send_to_comfy
        )
        # Read the workflow document itself (copy-to-clipboard flow); works in
        # standalone mode too since no ComfyUI connection is involved.
        registrar.add_prefixed_route(
            'GET', '/api/lm/{prefix}/content', prefix, self.get_workflow_content
        )
        # Write the current ComfyUI graph back into the managed workflow
        # document (ComfyUI-side "Update LM-managed workflow" entry point).
        registrar.add_prefixed_route(
            'PUT', '/api/lm/{prefix}/content', prefix, self.update_workflow_content
        )

    def _validate_civitai_model_type(self, model_type: str) -> bool:
        """Validate CivitAI model type for workflows (opt-in gated)."""
        if not self._settings.is_workflows_enabled():
            return False
        return (model_type or "").strip().lower() in WORKFLOW_CIVITAI_TYPES

    def _get_expected_model_types(self) -> str:
        """Get expected model types string for error messages"""
        return "Workflows or ComfyWorkflows"

    def _find_model_file(self, files):
        """Prefer a single-workflow Config .json, then an Archive .zip.

        Mirrors CivitAI's own default pick for Workflow resources
        (resource-file.service.ts pickDefaultResourceFile); falls back to the
        base-class weight-file behaviour for anything else.
        """
        def rank(file_info):
            file_type = file_info.get("type")
            name = (file_info.get("name") or "").lower()
            if file_type == "Config" and name.endswith(".json"):
                return 0
            if file_type == "Archive" and name.endswith(".zip"):
                return 1
            return 2

        candidates = [f for f in files if rank(f) < 2]
        if candidates:
            candidates.sort(key=lambda f: (rank(f), f.get("id", 0)))
            return candidates[0]
        return super()._find_model_file(files)

    def _get_page_context_provider(self):
        """Expose the opt-in feature state to the Workflows page template."""
        return self._page_context_for_workflows

    def _page_context_for_workflows(self, request: web.Request) -> Dict[str, Any]:
        if not self._settings.is_workflows_enabled():
            return {"workflows_disabled": True, "workflows_no_paths": False}

        standalone_mode = os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"
        context = {
            "workflows_disabled": False,
            "workflows_no_paths": not bool(config.workflows_roots),
            "standalone_mode": standalone_mode,
        }
        if standalone_mode:
            context["settings_file"] = getattr(self._settings, "settings_file", "") or ""
        return context

    async def get_workflow_info(self, request: web.Request) -> web.Response:
        """Get detailed information for a specific workflow by name"""
        try:
            name = request.match_info.get('name', '')
            workflow_info = await self.service.get_model_info_by_name(name)  # pyright: ignore[reportAttributeAccessIssue]

            if workflow_info:
                return web.json_response(workflow_info)
            else:
                return web.json_response({"error": "Workflow not found"}, status=404)

        except Exception as e:
            logger.error(f"Error in get_workflow_info: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def send_to_comfy(self, request: web.Request) -> web.Response:
        """Load a library workflow into the running ComfyUI graph.

        Reads the workflow JSON and broadcasts it over the ``lm_load_workflow``
        websocket channel; the ComfyUI-side extension picks it up and calls
        ``loadGraphData`` (same channel as recipe send-workflow).
        """
        try:
            if os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1":
                return web.json_response(
                    {"success": False, "error": "Standalone Mode Active"}, status=400
                )

            if not self._settings.is_workflows_enabled():
                return web.json_response(
                    {"success": False, "error": "Workflow management is disabled"},
                    status=400,
                )

            if request.method == "POST":
                payload = await self._read_json_body(request)
            else:
                payload = dict(request.query)
            file_path = (payload.get("file_path") or "").strip()
            if not file_path:
                return web.json_response(
                    {"success": False, "error": "file_path is required"}, status=400
                )

            _require_path_in_library_roots(
                file_path, self.service.scanner, label="File path"
            )

            workflow = await self._load_workflow_payload(file_path)
            if workflow is None:
                return web.json_response(
                    {
                        "success": False,
                        "error": "not_a_workflow",
                        "message": "File is missing or is not a ComfyUI workflow",
                    },
                    status=404,
                )

            # Lazy import: standalone mode replaces the ``server`` module with
            # a mock; the standalone check above already guards UX.
            from server import PromptServer  # pyright: ignore[reportMissingImports]

            PromptServer.instance.send_sync(
                "lm_load_workflow",
                {
                    "workflow": workflow,
                    "name": os.path.splitext(os.path.basename(file_path))[0],
                    # Provenance marker: the ComfyUI-side extension stamps this
                    # onto the loaded graph so its "Update LM-managed workflow"
                    # entry point can write edits back to the right document.
                    "lm_source": {
                        "file_path": file_path,
                        "sha256": await self._document_sha256(file_path),
                    },
                },
            )
            return web.json_response({"success": True, "sent": True})
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            logger.error("Error sending workflow to ComfyUI: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_workflow_content(self, request: web.Request) -> web.Response:
        """Return the extracted workflow document for a library entry.

        Used by the copy-to-clipboard flow; unlike send-to-comfy it does not
        require a running ComfyUI, so it works in standalone mode as well.
        """
        try:
            if not self._settings.is_workflows_enabled():
                return web.json_response(
                    {"success": False, "error": "Workflow management is disabled"},
                    status=400,
                )

            file_path = (request.query.get("file_path") or "").strip()
            if not file_path:
                return web.json_response(
                    {"success": False, "error": "file_path is required"}, status=400
                )

            _require_path_in_library_roots(
                file_path, self.service.scanner, label="File path"
            )

            workflow = await self._load_workflow_payload(file_path)
            if workflow is None:
                return web.json_response(
                    {
                        "success": False,
                        "error": "not_a_workflow",
                        "message": "File is missing or is not a ComfyUI workflow",
                    },
                    status=404,
                )
            return web.json_response({"success": True, "workflow": workflow})
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            logger.error("Error reading workflow content: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def _read_json_body(self, request: web.Request) -> Dict[str, Any]:
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    async def _load_workflow_payload(self, file_path: str):
        """Read the extracted workflow document off the event loop.

        ``.json`` artifacts are read directly; containers (``.zip``/image
        files) resolve to their derived ``.workflow.json`` sidecar, which is
        materialized on demand when missing.
        """

        return await asyncio.to_thread(load_artifact_workflow_document, file_path)

    async def _document_sha256(self, file_path: str) -> Optional[str]:
        """SHA256 of the extracted workflow document on disk.

        Callers must materialize the document first (``_load_workflow_payload``
        does). Returns ``None`` when the document is missing/unreadable.
        """

        document_path = get_workflow_document_path(file_path)
        try:
            if not os.path.exists(document_path):
                return None
        except OSError:
            return None
        try:
            return await calculate_sha256(document_path) or None
        except OSError:
            return None

    async def update_workflow_content(self, request: web.Request) -> web.Response:
        """Write the current ComfyUI graph back into a managed workflow.

        The ComfyUI-side extension calls this with the serialized graph when
        the user picks "Update LM-managed workflow". The write targets the
        workflow document: ``.json`` artifacts are rewritten in place, while
        container artifacts (``.zip``/images) keep their original bytes (the
        SHA256 is their CivitAI identity) and receive the edited graph in the
        derived ``.workflow.json`` sidecar.

        Optimistic concurrency: when ``base_sha256`` (the document hash the
        client saw when the workflow was opened) no longer matches the
        document on disk, the write is rejected with 409 unless ``force`` is
        set — someone else (re-download, update check) changed it meanwhile.
        """
        try:
            if not self._settings.is_workflows_enabled():
                return web.json_response(
                    {"success": False, "error": "Workflow management is disabled"},
                    status=400,
                )

            payload = await self._read_json_body(request)
            file_path = (payload.get("file_path") or "").strip()
            workflow = payload.get("workflow")
            if not file_path:
                return web.json_response(
                    {"success": False, "error": "file_path is required"}, status=400
                )
            if not isinstance(workflow, dict):
                return web.json_response(
                    {"success": False, "error": "workflow is required"}, status=400
                )

            _require_path_in_library_roots(
                file_path, self.service.scanner, label="File path"
            )

            # The provenance marker the client stamped for bookkeeping must
            # never land in the library document.
            extra = workflow.get("extra")
            if isinstance(extra, dict):
                extra.pop("lm_source", None)

            analysis = analyze_workflow(workflow)
            if analysis is None:
                return web.json_response(
                    {"success": False, "error": "workflow is not a ComfyUI graph document"},
                    status=400,
                )

            text = json.dumps(workflow, ensure_ascii=False)
            if len(text.encode("utf-8")) > MAX_WORKFLOW_JSON_BYTES:
                return web.json_response(
                    {"success": False, "error": "workflow exceeds the size limit"},
                    status=400,
                )

            document_path = get_workflow_document_path(file_path)
            base_sha256 = str(payload.get("base_sha256") or "").strip().lower()
            force = bool(payload.get("force"))
            if base_sha256 and not force and os.path.exists(document_path):
                current_sha256 = await calculate_sha256(document_path)
                if current_sha256 and current_sha256.lower() != base_sha256:
                    return web.json_response(
                        {
                            "success": False,
                            "error": "conflict",
                            "current_sha256": current_sha256,
                        },
                        status=409,
                    )

            def _write_document() -> None:
                os.makedirs(os.path.dirname(document_path), exist_ok=True)
                fd, temp_path = tempfile.mkstemp(
                    dir=os.path.dirname(document_path), suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write(text)
                    os.replace(temp_path, document_path)
                except BaseException:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                    raise

            await asyncio.to_thread(_write_document)

            new_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            await self._refresh_metadata_after_write(
                file_path, analysis, new_sha256
            )
            return web.json_response(
                {"success": True, "file_path": file_path, "sha256": new_sha256}
            )
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            logger.error("Error updating workflow content: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def _refresh_metadata_after_write(
        self, file_path: str, analysis, document_sha256: str
    ) -> None:
        """Re-sync sidecar metadata and caches after a write-back.

        Analysis fields (node classes, model refs, ...) always follow the new
        document. The CivitAI-facing artifact hash/size/modified only move for
        bare ``.json`` artifacts, whose bytes ARE the document; container
        artifacts stay byte-identical.
        """

        try:
            metadata, should_skip = await MetadataManager.load_metadata(
                file_path, WorkflowMetadata
            )
            if should_skip or metadata is None:
                return

            metadata.workflow_format = analysis.workflow_format
            metadata.node_count = analysis.node_count
            metadata.node_classes = analysis.node_classes
            metadata.model_refs = analysis.model_refs
            metadata.civitai_refs = analysis.civitai_refs

            if os.path.splitext(file_path)[1].lower() == ".json":
                metadata.sha256 = document_sha256
                real_path = os.path.realpath(file_path)
                metadata.size = os.path.getsize(real_path)
                metadata.modified = os.path.getmtime(real_path)

            await MetadataManager.save_metadata(file_path, metadata)

            scanner = getattr(self.service, "scanner", None)
            if scanner is not None:
                await scanner.sync_cache_from_metadata(
                    file_path, metadata.to_dict()
                )
        except Exception:
            logger.warning(
                "Failed to refresh workflow metadata after write-back for %s",
                file_path,
                exc_info=True,
            )
