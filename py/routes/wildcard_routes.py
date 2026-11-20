"""Wildcard routes: shared model management plus activation endpoints."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from typing import Any

from aiohttp import web

from ..services.model_lifecycle_service import _require_path_in_library_roots
from ..services.service_registry import ServiceRegistry
from ..services.wildcard_activation_service import (
    WildcardConflictError,
    WildcardLibraryError,
    get_wildcard_activation_service,
)
from ..services.wildcard_model_service import WildcardModelService
from ..services.wildcard_parser import (
    MAX_ARTIFACT_BYTES,
    SUPPORTED_ARTIFACT_EXTENSIONS,
)
from ..services.wildcard_service import get_wildcard_service
from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar

logger = logging.getLogger(__name__)


class WildcardRoutes(BaseModelRoutes):
    def __init__(self, *, activation_service=None, **kwargs):
        super().__init__(**kwargs)
        self.template_name = "wildcards.html"
        self.activation_service = activation_service or get_wildcard_activation_service()

    async def initialize_services(self):
        scanner = await ServiceRegistry.get_wildcard_scanner()
        update_service = await ServiceRegistry.get_model_update_service()
        self.service = WildcardModelService(
            scanner, update_service=update_service, activation_service=self.activation_service
        )
        self.set_model_update_service(update_service)
        self.attach_service(self.service)

    def setup_routes(self, app: web.Application, prefix: str = "wildcards"):
        app.on_startup.append(lambda _: self.initialize_services())
        super().setup_routes(app, prefix)

    def setup_specific_routes(self, registrar: ModelRouteRegistrar, prefix: str):
        for method, path, handler in (
            ("GET", "/content", self.get_content),
            ("GET", "/entries", self.get_entries),
            ("GET", "/active", self.get_active),
            ("POST", "/activate", self.activate),
            ("POST", "/deactivate", self.deactivate),
            ("POST", "/bulk-activate", self.bulk_activate),
            ("POST", "/bulk-deactivate", self.bulk_deactivate),
            ("POST", "/import", self.import_files),
        ):
            registrar.add_prefixed_route(
                method, f"/api/lm/{{prefix}}{path}", prefix, handler
            )

    def _validate_civitai_model_type(self, model_type: str) -> bool:
        return self._settings.is_wildcards_enabled() and (
            model_type or ""
        ).strip().lower() == "wildcards"

    def _get_expected_model_types(self) -> str:
        return "Wildcards"

    def _find_model_file(self, files):
        candidates = [
            item
            for item in files
            if str(item.get("name", "")).lower().endswith(SUPPORTED_ARTIFACT_EXTENSIONS)
        ]
        candidates.sort(key=lambda item: (not bool(item.get("primary")), item.get("id", 0)))
        return candidates[0] if candidates else None

    def _get_page_context_provider(self):
        return self._page_context

    def _page_context(self, request: web.Request) -> dict[str, Any]:
        if not self._settings.is_wildcards_enabled():
            return {"wildcards_disabled": True, "wildcards_no_paths": False}
        return {
            "wildcards_disabled": False,
            "wildcards_no_paths": not bool(self._settings.get_wildcard_path()),
            "standalone_mode": os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1",
        }

    @staticmethod
    async def _json_body(request: web.Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except Exception as exc:
            raise WildcardLibraryError("A JSON request body is required") from exc
        if not isinstance(payload, dict):
            raise WildcardLibraryError("A JSON object is required")
        return payload

    @staticmethod
    def _error(exc: Exception) -> web.Response:
        if isinstance(exc, FileNotFoundError):
            return web.json_response({"success": False, "error": "Wildcard resource not found"}, status=404)
        if isinstance(exc, WildcardConflictError):
            return web.json_response(
                {"success": False, "error": str(exc), "conflicts": exc.conflicts}, status=409
            )
        if isinstance(exc, (WildcardLibraryError, ValueError, OSError, KeyError)):
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        logger.error("Wildcard request failed", exc_info=True)
        return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def _resource(self, file_path: str) -> dict[str, Any]:
        scanner = self.service.scanner
        _require_path_in_library_roots(file_path, scanner, label="File path")
        cache = await scanner.get_cached_data()
        normalized = os.path.normcase(os.path.abspath(file_path))
        resource = next(
            (
                item
                for item in cache.raw_data
                if os.path.normcase(os.path.abspath(item.get("file_path", ""))) == normalized
            ),
            None,
        )
        if resource is None:
            raise FileNotFoundError(file_path)
        return resource

    async def _formatted_resource(self, file_path: str) -> dict[str, Any]:
        return await self.service.format_response(await self._resource(file_path))

    async def _broadcast_changed(self, file_path: str, active: bool) -> None:
        payload = {"file_path": file_path, "active": active}
        try:
            await self._ws_manager.broadcast({"type": "wildcard_activation_changed", **payload})
        except Exception:
            logger.debug("Unable to broadcast wildcard activation", exc_info=True)
        if os.environ.get("LORA_MANAGER_STANDALONE", "0") != "1":
            try:
                from server import PromptServer

                PromptServer.instance.send_sync("lm_wildcards_changed", payload)
            except Exception:
                logger.debug("Unable to notify ComfyUI wildcard panels", exc_info=True)

    async def get_content(self, request: web.Request) -> web.Response:
        try:
            file_path = request.query["file_path"]
            await self._resource(file_path)
            result = await asyncio.to_thread(
                self.activation_service.read_source, file_path, request.query["source_path"]
            )
            return web.json_response({"success": True, **result})
        except Exception as exc:
            return self._error(exc)

    async def get_entries(self, request: web.Request) -> web.Response:
        try:
            file_path = request.query["file_path"]
            await self._resource(file_path)
            result = await asyncio.to_thread(
                self.activation_service.get_entry_values,
                file_path,
                request.query["key"],
                max(0, int(request.query.get("offset", "0"))),
                min(500, max(1, int(request.query.get("limit", "200")))),
            )
            return web.json_response({"success": True, **result})
        except Exception as exc:
            return self._error(exc)

    async def get_active(self, request: web.Request) -> web.Response:
        try:
            cache = await self.service.scanner.get_cached_data()
            search = request.query.get("search", "").strip().lower()
            resources = []
            for raw in cache.raw_data:
                if raw.get("exclude"):
                    continue
                formatted = await self.service.format_response(raw)
                if not formatted:
                    continue
                haystack = " ".join(
                    [formatted["model_name"], formatted["file_name"]]
                    + [entry["effective_key"] for entry in formatted.get("entries", [])]
                ).lower()
                if search and search not in haystack:
                    continue
                resources.append(
                    {
                        key: formatted.get(key)
                        for key in (
                            "file_path", "model_name", "file_name", "preview_url", "active",
                            "activation_namespace", "activation_aliases", "activated_at",
                            "wildcard_format", "base_model", "folder",
                            "entries", "entry_count", "value_count",
                            "civitai", "errors",
                        )
                    }
                )
            resources.sort(key=lambda item: (not item["active"], item["model_name"].lower()))
            runtime = get_wildcard_service()
            return web.json_response(
                {
                    "success": True,
                    "resources": resources[:200],
                    "manual": {
                        "entries": runtime.get_manual_entries(sample_limit=3)
                    },
                    "runtime_conflicts": runtime.get_runtime_conflicts(),
                }
            )
        except Exception as exc:
            return self._error(exc)

    async def activate(self, request: web.Request) -> web.Response:
        try:
            payload = await self._json_body(request)
            file_path = str(payload["file_path"])
            resource = await self._resource(file_path)
            result = await asyncio.to_thread(
                self.activation_service.activate,
                resource,
                payload.get("namespace", ""),
                payload.get("aliases") or {},
            )
            await self._broadcast_changed(file_path, True)
            return web.json_response(
                {"success": True, **result, "resource": await self._formatted_resource(file_path)}
            )
        except Exception as exc:
            return self._error(exc)

    async def deactivate(self, request: web.Request) -> web.Response:
        try:
            payload = await self._json_body(request)
            file_path = str(payload["file_path"])
            await self._resource(file_path)
            await asyncio.to_thread(self.activation_service.deactivate, file_path)
            await self._broadcast_changed(file_path, False)
            return web.json_response(
                {"success": True, "resource": await self._formatted_resource(file_path)}
            )
        except Exception as exc:
            return self._error(exc)

    async def bulk_activate(self, request: web.Request) -> web.Response:
        return await self._bulk_set_activation(request, True)

    async def bulk_deactivate(self, request: web.Request) -> web.Response:
        return await self._bulk_set_activation(request, False)

    async def _bulk_set_activation(self, request: web.Request, active: bool) -> web.Response:
        try:
            payload = await self._json_body(request)
            raw_paths = payload.get("file_paths")
            if not isinstance(raw_paths, list) or not raw_paths:
                raise WildcardLibraryError("file_paths must be a non-empty array")
            file_paths: list[str] = []
            seen: set[str] = set()
            for value in raw_paths:
                if not isinstance(value, str) or not value.strip():
                    raise WildcardLibraryError("Every file path must be a non-empty string")
                normalized = os.path.normcase(os.path.abspath(value))
                if normalized in seen:
                    continue
                seen.add(normalized)
                file_paths.append(value)

            results: list[dict[str, Any]] = []
            for file_path in file_paths:
                try:
                    resource = await self._resource(file_path)
                    current = self.activation_service.activation_for(file_path)
                    if (current is not None) == active:
                        results.append({"file_path": file_path, "success": True, "active": active})
                        continue
                    if active:
                        await asyncio.to_thread(self.activation_service.activate, resource)
                    else:
                        await asyncio.to_thread(self.activation_service.deactivate, file_path)
                    await self._broadcast_changed(file_path, active)
                    results.append({"file_path": file_path, "success": True, "active": active})
                except WildcardConflictError as exc:
                    results.append({
                        "file_path": file_path,
                        "success": False,
                        "error": str(exc),
                        "conflicts": exc.conflicts,
                    })
                except Exception as exc:
                    results.append({
                        "file_path": file_path,
                        "success": False,
                        "error": str(exc) or "Wildcard resource not found",
                    })

            success_count = sum(1 for result in results if result["success"])
            return web.json_response({
                "success": True,
                "action": "activate" if active else "deactivate",
                "total": len(results),
                "success_count": success_count,
                "failure_count": len(results) - success_count,
                "results": results,
            })
        except Exception as exc:
            return self._error(exc)

    async def import_files(self, request: web.Request) -> web.Response:
        try:
            roots = self.service.scanner.get_model_roots()
            if not roots:
                raise WildcardLibraryError("Configure the wildcard library folder first")
            reader = await request.multipart()
            resources = []
            async for part in reader:
                if part.name != "file" or not part.filename:
                    continue
                file_name = os.path.basename(part.filename.replace("\\", "/"))
                file_name = re.sub(r'[:*?"<>|\x00-\x1f]', "_", file_name).strip(". ")
                if not file_name.lower().endswith(SUPPORTED_ARTIFACT_EXTENSIONS):
                    raise WildcardLibraryError("Supported formats are ZIP, TXT, YAML and JSON")
                data = bytearray()
                while True:
                    chunk = await part.read_chunk(1024 * 1024)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_ARTIFACT_BYTES:
                        raise WildcardLibraryError("Wildcard artifact exceeds the 256 MiB limit")
                target_dir = roots[0]
                os.makedirs(target_dir, exist_ok=True)
                stem, extension = os.path.splitext(file_name)
                target = os.path.join(target_dir, file_name)
                if os.path.exists(target):
                    target = os.path.join(target_dir, f"{stem}-{uuid.uuid4().hex[:8]}{extension}")
                with open(target, "wb") as handle:
                    handle.write(data)
                metadata = await self.service.scanner.register_local_artifact(target)
                if metadata is None:
                    raise WildcardLibraryError(f"Unable to register {file_name}")
                resources.append(await self.service.format_response(metadata.to_dict()))
            if not resources:
                raise WildcardLibraryError("Choose at least one wildcard file")
            return web.json_response({"success": True, "resources": resources})
        except Exception as exc:
            return self._error(exc)


__all__ = ["WildcardRoutes"]
