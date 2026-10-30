import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import web

from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar
from ..config import config
from ..services.model_lifecycle_service import _require_path_in_library_roots
from ..services.service_registry import ServiceRegistry
from ..services.workflow_link_registry import WorkflowLinkRegistry
from ..services.workflow_service import WorkflowService
from ..utils.constants import WORKFLOW_CIVITAI_TYPES
from ..utils.file_utils import calculate_sha256, normalize_path
from ..utils.metadata_manager import MetadataManager
from ..utils.models import WorkflowMetadata
from ..utils.workflow_analysis import (
    MAX_WORKFLOW_JSON_BYTES,
    analyze_workflow,
    load_workflow_file,
)
from ..utils.workflow_extraction import (
    get_workflow_document_path,
    load_artifact_workflow_document,
)

logger = logging.getLogger(__name__)

# Windows refuses these file names regardless of extension.
_RESERVED_WORKFLOW_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _sanitize_workflow_name(raw: Any) -> str:
    """Turn a ComfyUI workflow title into a safe library file name.

    Keeps unicode (non-Latin workflow names are common) but strips path
    separators and characters Windows rejects. The caller never supplies a
    directory: the file always lands in the configured workflow library root.
    """

    name = raw.strip() if isinstance(raw, str) else ""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = name.strip().strip(".").strip()
    if not name:
        return "Untitled"
    if name.upper() in _RESERVED_WORKFLOW_NAMES or (
        name.split(".")[0].upper() in _RESERVED_WORKFLOW_NAMES
    ):
        name = f"_{name}"
    return name[:120]


def _write_text_atomic(path: str, text: str) -> None:
    """Write ``text`` to ``path`` through a sibling temp file."""

    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _remove_file_quietly(path: str) -> None:
    """Best-effort unlink used to roll back a failed create."""

    try:
        os.unlink(path)
    except OSError:
        pass


def _resolve_workflow_preview(
    prompt_id: str, *, registry_cls: Any = None
) -> Optional[bytes]:
    """Return PNG bytes for the decode image of ``prompt_id``, or None.

    The metadata registry is server-global, so the prompt id is the ownership
    token: only the client that queued that exact prompt can attach its image.
    This keeps a create in one tab from borrowing another tab's output.

    ``registry_cls`` is an injection point for unit tests; production callers
    use the ComfyUI metadata registry singleton.
    """

    try:
        if registry_cls is None:
            from ..metadata_collector.metadata_registry import MetadataRegistry

            registry_cls = MetadataRegistry

        registry = registry_cls()
        if registry.current_prompt_id != prompt_id:
            return None
        image = registry.get_first_decoded_image(prompt_id)
        if image is None:
            return None
        from ..utils.image_tensor import tensor_to_png_bytes

        return tensor_to_png_bytes(image)
    except Exception:
        logger.warning("Failed to resolve workflow preview image", exc_info=True)
        return None


def _write_workflow_preview(file_path: str, image_bytes: bytes) -> Optional[str]:
    """Optimize and store the preview sidecar next to a workflow document."""

    try:
        from ..utils.constants import CARD_PREVIEW_WIDTH
        from ..utils.exif_utils import ExifUtils
        from ..utils.sidecar_paths import get_preview_dir

        optimized, _extension = ExifUtils.optimize_image(
            image_data=image_bytes,
            target_width=CARD_PREVIEW_WIDTH,
            format="webp",
            quality=85,
            preserve_metadata=False,
        )
        if not optimized:
            return None

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        preview_dir = get_preview_dir(file_path)
        os.makedirs(preview_dir, exist_ok=True)
        preview_path = normalize_path(
            os.path.join(preview_dir, f"{base_name}.preview.webp")
        )
        with open(preview_path, "wb") as handle:
            handle.write(optimized)
        return preview_path
    except Exception:
        logger.warning("Failed to write workflow preview", exc_info=True)
        return None


class WorkflowRestoreDownloadError(RuntimeError):
    """Raised when a restore re-download fails before the file is replaced."""


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
        # Create a new library workflow from the current ComfyUI graph
        # ("Create LM-managed workflow" entry point).
        registrar.add_prefixed_route(
            'POST', '/api/lm/{prefix}/create', prefix, self.create_workflow
        )
        # Validate that a graph's provenance marker still points at a library
        # document (the entry may have been deleted/renamed from the LM page).
        registrar.add_prefixed_route(
            'GET', '/api/lm/{prefix}/link-status', prefix, self.get_workflow_link_status
        )
        # Write the current ComfyUI graph back into the managed workflow
        # document (ComfyUI-side "Update LM-managed workflow" entry point).
        registrar.add_prefixed_route(
            'PUT', '/api/lm/{prefix}/content', prefix, self.update_workflow_content
        )
        # ComfyUI-side link-state reporting (which managed workflow is open
        # and dirty in which client tab) and the LM-page-triggered write-back
        # request/response pair ("Update from ComfyUI" card menu entry).
        registrar.add_prefixed_route(
            'POST', '/api/lm/{prefix}/comfyui-state', prefix, self.report_comfyui_state
        )
        registrar.add_prefixed_route(
            'GET', '/api/lm/{prefix}/comfyui-state', prefix, self.get_comfyui_state
        )
        registrar.add_prefixed_route(
            'POST', '/api/lm/{prefix}/update-from-comfy', prefix, self.update_from_comfy
        )
        registrar.add_prefixed_route(
            'POST', '/api/lm/{prefix}/collect-result', prefix, self.collect_result
        )
        # Restore a workflow to its downloaded state (discard local edits).
        registrar.add_prefixed_route(
            'POST', '/api/lm/{prefix}/restore', prefix, self.restore_workflow
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
            # A configured-but-unavailable folder is a scanning problem, not a
            # configuration problem: report "no paths" only when unset.
            "workflows_no_paths": not bool(self._settings.get_workflow_path()),
            "standalone_mode": standalone_mode,
        }
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

    async def get_workflow_link_status(self, request: web.Request) -> web.Response:
        """Report whether a ComfyUI graph's linked library document exists.

        The ComfyUI extension calls this when a graph carries a provenance
        marker. Deleting or renaming the entry from the LM page leaves a stale
        marker client-side; the extension clears it so "Update" reverts to
        "Create" instead of writing to a path that is no longer managed.
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

            scanner = getattr(self.service, "scanner", None)
            if scanner is None:
                return web.json_response(
                    {"success": False, "error": "Workflow scanner unavailable"},
                    status=500,
                )

            # A path outside the current library roots can no longer be
            # managed by definition; report it as gone rather than an error so
            # the client can clear the marker.
            try:
                _require_path_in_library_roots(
                    file_path, scanner, label="File path"
                )
            except ValueError:
                return web.json_response({"success": True, "exists": False})

            exists = await asyncio.to_thread(os.path.exists, file_path)
            return web.json_response({"success": True, "exists": bool(exists)})
        except Exception as exc:
            logger.error(
                "Error checking workflow link status: %s", exc, exc_info=True
            )
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

    async def create_workflow(self, request: web.Request) -> web.Response:
        """Create a new library workflow from the current ComfyUI graph.

        The ComfyUI-side extension calls this for "Create LM-managed
        workflow". Unlike ``update_workflow_content`` the target document does
        not exist yet: the file is written into the single configured
        ``workflow_path`` folder, registered in the scanner cache, and returned
        together with its SHA256 so the client can stamp the provenance marker
        and keep the graph linked for subsequent write-backs.
        """
        try:
            if self._settings is None or not self._settings.is_workflows_enabled():
                return web.json_response(
                    {"success": False, "error": "Workflow management is disabled"},
                    status=400,
                )
            if self._is_standalone():
                return web.json_response(
                    {"success": False, "error": "Standalone Mode Active"}, status=400
                )

            payload = await self._read_json_body(request)
            workflow = payload.get("workflow")
            if not isinstance(workflow, dict):
                return web.json_response(
                    {"success": False, "error": "workflow is required"}, status=400
                )

            # Client-side bookkeeping must never land in the library document.
            extra = workflow.get("extra")
            if isinstance(extra, dict):
                extra.pop("lm_source", None)

            if analyze_workflow(workflow) is None:
                return web.json_response(
                    {"success": False, "error": "workflow is not a ComfyUI graph document"},
                    status=400,
                )

            text = json.dumps(workflow, ensure_ascii=False)
            encoded = text.encode("utf-8")
            if len(encoded) > MAX_WORKFLOW_JSON_BYTES:
                return web.json_response(
                    {"success": False, "error": "workflow exceeds the size limit"},
                    status=400,
                )

            # The ComfyUI extension sends the prompt id it last executed; the
            # backend only honors it while it is still the registry's current
            # prompt, so the image belongs to this client's run.
            preview_bytes: Optional[bytes] = None
            preview_prompt_id = payload.get("preview_prompt_id")
            if isinstance(preview_prompt_id, str) and preview_prompt_id.strip():
                preview_bytes = await asyncio.to_thread(
                    _resolve_workflow_preview, preview_prompt_id.strip()
                )

            library_dir = self._settings.get_workflow_path()
            if not library_dir:
                return web.json_response(
                    {
                        "success": False,
                        "error": (
                            "The workflow library folder is not configured in "
                            "LoRA Manager settings"
                        ),
                    },
                    status=400,
                )

            try:
                await asyncio.to_thread(os.makedirs, library_dir, exist_ok=True)
            except OSError as exc:
                return web.json_response(
                    {
                        "success": False,
                        "error": f"Workflow library folder is unavailable: {exc}",
                    },
                    status=400,
                )

            # The folder may have been created just now (or re-mounted since
            # startup): refresh the live roots so send-to-comfy/update can
            # resolve the new file (and its previews) immediately.
            try:
                config.refresh_workflow_roots()
            except Exception:
                logger.debug("Failed to refresh workflow roots", exc_info=True)

            sha256 = hashlib.sha256(encoded).hexdigest()
            name = _sanitize_workflow_name(payload.get("name"))
            file_name = WorkflowMetadata.generate_unique_filename(
                library_dir, name, ".json", lambda: sha256
            )
            file_path = normalize_path(os.path.join(library_dir, file_name))

            await asyncio.to_thread(_write_text_atomic, file_path, text)

            preview_path: Optional[str] = None
            if preview_bytes:
                preview_path = await asyncio.to_thread(
                    _write_workflow_preview, file_path, preview_bytes
                )
            preview_written = preview_path is not None

            scanner = getattr(self.service, "scanner", None)
            if scanner is None:
                await asyncio.to_thread(_remove_file_quietly, file_path)
                if preview_path:
                    await asyncio.to_thread(_remove_file_quietly, preview_path)
                return web.json_response(
                    {"success": False, "error": "Workflow scanner unavailable"},
                    status=500,
                )

            metadata = await scanner.register_local_artifact(file_path)
            if metadata is None:
                await asyncio.to_thread(_remove_file_quietly, file_path)
                if preview_path:
                    await asyncio.to_thread(_remove_file_quietly, preview_path)
                return web.json_response(
                    {
                        "success": False,
                        "error": "Workflow could not be registered in the library",
                    },
                    status=500,
                )

            # Let other clients refresh their cached library views; failures
            # are non-fatal for the create itself.
            try:
                from .handlers.model_handlers import _broadcast_models_changed

                _broadcast_models_changed()
            except Exception:
                logger.debug("Failed to broadcast models_changed", exc_info=True)

            return web.json_response(
                {
                    "success": True,
                    "file_path": metadata.file_path or file_path,
                    "name": os.path.splitext(file_name)[0],
                    "sha256": sha256,
                    "preview": preview_written
                    or bool(getattr(metadata, "preview_url", "")),
                }
            )
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            logger.error("Error creating workflow: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

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

            # A deleted library entry must not be resurrected by a stale
            # ComfyUI provenance marker; the client clears the marker on 404.
            if not await asyncio.to_thread(os.path.exists, file_path):
                return web.json_response(
                    {
                        "success": False,
                        "error": "not_found",
                        "message": "Workflow no longer exists in the library",
                    },
                    status=404,
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

    # ------------------------------------------------------------------
    # ComfyUI link-state reporting + LM-page-triggered write-back
    # ------------------------------------------------------------------

    @staticmethod
    def _is_standalone() -> bool:
        return os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"

    @staticmethod
    def _active_client_ids() -> set:
        """Live ComfyUI websocket client ids; empty when unavailable."""
        try:
            from server import PromptServer  # pyright: ignore[reportMissingImports]

            return set(PromptServer.instance.sockets.keys())
        except Exception:
            return set()

    async def report_comfyui_state(self, request: web.Request) -> web.Response:
        """ComfyUI client reports its active graph's LM link state.

        Body: ``{client_id, state}`` where ``state`` is
        ``{file_path, sha256, dirty, name}`` or ``null`` (active graph is not
        LM-linked). In standalone mode there are no ComfyUI clients; the
        report is accepted and dropped.
        """
        if self._is_standalone():
            return web.json_response({"success": True})

        payload = await self._read_json_body(request)
        client_id = payload.get("client_id")
        if not isinstance(client_id, str) or not client_id:
            return web.json_response(
                {"success": False, "error": "client_id is required"}, status=400
            )
        state = payload.get("state")
        registry = await WorkflowLinkRegistry.get_instance()
        await registry.report_state(
            client_id, state if isinstance(state, dict) else None
        )
        return web.json_response({"success": True})

    async def get_comfyui_state(self, request: web.Request) -> web.Response:
        """List LM-linked workflows currently open in live ComfyUI tabs."""
        if self._is_standalone():
            return web.json_response({"success": True, "states": []})

        registry = await WorkflowLinkRegistry.get_instance()
        states = await registry.get_states(self._active_client_ids())
        return web.json_response({"success": True, "states": states})

    async def update_from_comfy(self, request: web.Request) -> web.Response:
        """Ask the ComfyUI tab holding *file_path* to write its graph back.

        The LM web UI's "Update from ComfyUI" card menu entry calls this; the
        request blocks until the ComfyUI client performs the write-back (via
        the regular ``PUT .../content`` endpoint) and reports the outcome, or
        a timeout elapses.
        """
        try:
            if self._is_standalone():
                return web.json_response(
                    {"success": False, "error": "Standalone Mode Active"}, status=400
                )
            if not self._settings.is_workflows_enabled():
                return web.json_response(
                    {"success": False, "error": "Workflow management is disabled"},
                    status=400,
                )

            payload = await self._read_json_body(request)
            file_path = (payload.get("file_path") or "").strip()
            if not file_path:
                return web.json_response(
                    {"success": False, "error": "file_path is required"}, status=400
                )
            _require_path_in_library_roots(
                file_path, self.service.scanner, label="File path"
            )

            registry = await WorkflowLinkRegistry.get_instance()
            sid = await registry.find_client_for(file_path, self._active_client_ids())
            if sid is None:
                return web.json_response(
                    {
                        "success": False,
                        "error": "not_open",
                        "message": "Workflow is not open in any connected ComfyUI tab",
                    },
                    status=404,
                )

            request_id, future = registry.begin_collect()
            from server import PromptServer  # pyright: ignore[reportMissingImports]

            PromptServer.instance.send_sync(
                "lm_collect_workflow",
                {"request_id": request_id, "file_path": file_path},
                sid=sid,
            )
            result = await registry.await_collect(request_id, future, timeout=20.0)
            status = 200 if result.get("success") else 500
            if result.get("error") in ("no_changes", "cancelled"):
                status = 200
            elif result.get("error") == "timeout":
                status = 504
            return web.json_response(result, status=status)
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            logger.error("Error collecting workflow from ComfyUI: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def collect_result(self, request: web.Request) -> web.Response:
        """ComfyUI client reports the outcome of a collect request."""
        if self._is_standalone():
            return web.json_response({"success": False, "error": "Standalone Mode Active"}, status=400)

        payload = await self._read_json_body(request)
        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            return web.json_response(
                {"success": False, "error": "request_id is required"}, status=400
            )
        result = {
            key: payload[key]
            for key in ("success", "error", "sha256", "file_path")
            if key in payload
        }
        registry = await WorkflowLinkRegistry.get_instance()
        resolved = await registry.resolve_collect(request_id, result)
        return web.json_response({"success": True, "resolved": resolved})

    # ------------------------------------------------------------------
    # Restore to downloaded state
    # ------------------------------------------------------------------

    async def restore_workflow(self, request: web.Request) -> web.Response:
        """Restore a workflow to its downloaded state, discarding local edits.

        Container artifacts (``.zip``/images) were never modified — write-backs
        only touch the derived ``.workflow.json`` sidecar — so restore discards
        the sidecar and re-extracts from the pristine archive. Bare ``.json``
        artifacts are rewritten in place by write-backs, so restore
        re-downloads the recorded CivitAI version file and replaces the local
        copy (after validating the download and verifying its hash).
        """
        try:
            if not self._settings.is_workflows_enabled():
                return web.json_response(
                    {"success": False, "error": "Workflow management is disabled"},
                    status=400,
                )

            payload = await self._read_json_body(request)
            file_path = (payload.get("file_path") or "").strip()
            if not file_path:
                return web.json_response(
                    {"success": False, "error": "file_path is required"}, status=400
                )
            _require_path_in_library_roots(
                file_path, self.service.scanner, label="File path"
            )

            if not os.path.exists(file_path):
                return web.json_response(
                    {"success": False, "error": "Workflow file not found"}, status=404
                )

            if os.path.splitext(file_path)[1].lower() == ".json":
                return await self._restore_json_artifact(file_path)
            return await self._restore_container_artifact(file_path)
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            logger.error("Error restoring workflow: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def _restore_container_artifact(self, file_path: str) -> web.Response:
        """Discard the derived document and re-extract from the archive."""

        document_path = get_workflow_document_path(file_path)

        def _discard_derived() -> None:
            try:
                os.unlink(document_path)
            except FileNotFoundError:
                pass

        await asyncio.to_thread(_discard_derived)

        document = await asyncio.to_thread(load_artifact_workflow_document, file_path)
        if document is None:
            return web.json_response(
                {
                    "success": False,
                    "error": "not_a_workflow",
                    "message": "Archive does not contain a ComfyUI workflow",
                },
                status=404,
            )

        analysis = analyze_workflow(document)
        doc_sha = hashlib.sha256(
            json.dumps(document, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        await self._refresh_metadata_after_write(file_path, analysis, doc_sha)
        return web.json_response(
            {"success": True, "file_path": file_path, "restored": "extracted"}
        )

    async def _restore_json_artifact(self, file_path: str) -> web.Response:
        """Re-download the recorded CivitAI file over the local copy."""

        metadata, should_skip = await MetadataManager.load_metadata(
            file_path, WorkflowMetadata
        )
        version_info = (
            metadata.civitai
            if metadata is not None and not should_skip and metadata.from_civitai
            else None
        )
        if not isinstance(version_info, dict) or not version_info:
            return web.json_response(
                {
                    "success": False,
                    "error": "no_source",
                    "message": "Workflow has no recorded CivitAI source to restore from",
                },
                status=400,
            )

        file_info = self._find_downloaded_file_info(version_info, file_path)
        download_url = (file_info or {}).get("downloadUrl") or version_info.get(
            "downloadUrl"
        )
        if not download_url:
            return web.json_response(
                {
                    "success": False,
                    "error": "no_source",
                    "message": "Recorded CivitAI version has no download URL",
                },
                status=400,
            )
        expected_sha256 = (
            (((file_info or {}).get("hashes") or {}).get("SHA256") or "").lower()
            or None
        )

        try:
            new_sha256 = await self._download_and_replace(
                download_url, file_path, expected_sha256=expected_sha256
            )
        except WorkflowRestoreDownloadError as exc:
            return web.json_response(
                {
                    "success": False,
                    "error": "download_failed",
                    "message": str(exc),
                },
                status=502,
            )

        document = await asyncio.to_thread(load_workflow_file, file_path)
        if document is None:
            # Defensive: the temp file was validated before the replace, so
            # this can only fail on a race with an external writer.
            return web.json_response(
                {
                    "success": False,
                    "error": "not_a_workflow",
                    "message": "Restored file is not a ComfyUI workflow",
                },
                status=422,
            )

        analysis = analyze_workflow(document)
        await self._refresh_metadata_after_write(file_path, analysis, new_sha256)
        return web.json_response(
            {
                "success": True,
                "file_path": file_path,
                "restored": "downloaded",
                "sha256": new_sha256,
            }
        )

    @staticmethod
    def _find_downloaded_file_info(
        version_info: Dict[str, Any], file_path: str
    ) -> Optional[Dict[str, Any]]:
        """Match the stored version's file entry to the local artifact."""

        files = [f for f in version_info.get("files") or [] if isinstance(f, dict)]
        if not files:
            return None
        basename = os.path.basename(file_path)
        for file_info in files:
            if file_info.get("name") == basename:
                return file_info
        return files[0] if len(files) == 1 else None

    async def _download_and_replace(
        self,
        download_url: str,
        file_path: str,
        *,
        expected_sha256: Optional[str] = None,
    ) -> str:
        """Download *download_url* and atomically replace *file_path*.

        The download lands in a temp file next to the target and is only
        swapped in after it parses as a workflow and (when known) matches the
        recorded SHA256. Returns the downloaded file's SHA256.
        """

        api_key = (self._settings.get("civitai_api_key", "") or "").strip()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        timeout = aiohttp.ClientTimeout(total=600)

        fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(file_path), suffix=".download"
        )
        os.close(fd)
        try:
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(download_url) as response:
                    if response.status != 200:
                        raise WorkflowRestoreDownloadError(
                            f"Download failed with HTTP {response.status}"
                        )
                    written = 0
                    with open(temp_path, "wb") as handle:
                        async for chunk in response.content.iter_chunked(1 << 20):
                            written += len(chunk)
                            if written > MAX_WORKFLOW_JSON_BYTES:
                                raise WorkflowRestoreDownloadError(
                                    "Downloaded file exceeds the workflow size limit"
                                )
                            handle.write(chunk)

            if load_workflow_file(temp_path) is None:
                raise WorkflowRestoreDownloadError(
                    "Downloaded file is not a ComfyUI workflow"
                )

            new_sha256 = await calculate_sha256(temp_path)
            if expected_sha256 and new_sha256.lower() != expected_sha256:
                raise WorkflowRestoreDownloadError(
                    "Downloaded file does not match the recorded SHA256"
                )

            await asyncio.to_thread(os.replace, temp_path, file_path)
            return new_sha256
        except WorkflowRestoreDownloadError:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
        except Exception as exc:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise WorkflowRestoreDownloadError(str(exc)) from exc
