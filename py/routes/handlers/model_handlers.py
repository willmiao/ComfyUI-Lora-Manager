"""Handlers for base model routes."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Iterable, Mapping, Optional

from aiohttp import web
import jinja2

from ...services.model_file_service import ModelFileService, ModelMoveService
from ...services.websocket_progress_callback import WebSocketProgressCallback
from ...services.websocket_manager import WebSocketManager
from ...services.settings_manager import SettingsManager
from ...utils.routes_common import ModelRouteUtils


class ModelPageView:
    """Render the HTML view for model listings."""

    def __init__(
        self,
        *,
        template_env: jinja2.Environment,
        template_name: str,
        service,
        settings_service: SettingsManager,
        server_i18n,
        logger: logging.Logger,
    ) -> None:
        self._template_env = template_env
        self._template_name = template_name
        self._service = service
        self._settings = settings_service
        self._server_i18n = server_i18n
        self._logger = logger

    async def handle(self, request: web.Request) -> web.Response:
        try:
            is_initializing = (
                self._service.scanner._cache is None
                or (
                    hasattr(self._service.scanner, "is_initializing")
                    and callable(self._service.scanner.is_initializing)
                    and self._service.scanner.is_initializing()
                )
                or (
                    hasattr(self._service.scanner, "_is_initializing")
                    and self._service.scanner._is_initializing
                )
            )

            if not self._template_env or not self._template_name:
                return web.Response(
                    text="Template environment or template name not set",
                    status=500,
                )

            user_language = self._settings.get("language", "en")
            self._server_i18n.set_locale(user_language)

            if not hasattr(self._template_env, "_i18n_filter_added"):
                self._template_env.filters["t"] = self._server_i18n.create_template_filter()
                self._template_env._i18n_filter_added = True  # type: ignore[attr-defined]

            template_context = {
                "is_initializing": is_initializing,
                "settings": self._settings,
                "request": request,
                "folders": [],
                "t": self._server_i18n.get_translation,
            }

            if not is_initializing:
                try:
                    cache = await self._service.scanner.get_cached_data(force_refresh=False)
                    template_context["folders"] = getattr(cache, "folders", [])
                except Exception as cache_error:  # pragma: no cover - logging path
                    self._logger.error("Error loading cache data: %s", cache_error)
                    template_context["is_initializing"] = True

            rendered = self._template_env.get_template(self._template_name).render(**template_context)
            return web.Response(text=rendered, content_type="text/html")
        except Exception as exc:  # pragma: no cover - logging path
            self._logger.error("Error handling models page: %s", exc, exc_info=True)
            return web.Response(text="Error loading models page", status=500)


class ModelListingHandler:
    """Provide paginated model listings."""

    def __init__(
        self,
        *,
        service,
        parse_specific_params: Callable[[web.Request], Dict],
        logger: logging.Logger,
    ) -> None:
        self._service = service
        self._parse_specific_params = parse_specific_params
        self._logger = logger

    async def get_models(self, request: web.Request) -> web.Response:
        try:
            params = self._parse_common_params(request)
            result = await self._service.get_paginated_data(**params)
            formatted_result = {
                "items": [await self._service.format_response(item) for item in result["items"]],
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "total_pages": result["total_pages"],
            }
            return web.json_response(formatted_result)
        except Exception as exc:
            self._logger.error("Error retrieving %ss: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    def _parse_common_params(self, request: web.Request) -> Dict:
        page = int(request.query.get("page", "1"))
        page_size = min(int(request.query.get("page_size", "20")), 100)
        sort_by = request.query.get("sort_by", "name")
        folder = request.query.get("folder")
        search = request.query.get("search")
        fuzzy_search = request.query.get("fuzzy_search", "false").lower() == "true"

        base_models = request.query.getall("base_model", [])
        tags = request.query.getall("tag", [])
        favorites_only = request.query.get("favorites_only", "false").lower() == "true"

        search_options = {
            "filename": request.query.get("search_filename", "true").lower() == "true",
            "modelname": request.query.get("search_modelname", "true").lower() == "true",
            "tags": request.query.get("search_tags", "false").lower() == "true",
            "creator": request.query.get("search_creator", "false").lower() == "true",
            "recursive": request.query.get("recursive", "true").lower() == "true",
        }

        hash_filters: Dict[str, object] = {}
        if "hash" in request.query:
            hash_filters["single_hash"] = request.query["hash"]
        elif "hashes" in request.query:
            try:
                hash_list = json.loads(request.query["hashes"])
                if isinstance(hash_list, list):
                    hash_filters["multiple_hashes"] = hash_list
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "folder": folder,
            "search": search,
            "fuzzy_search": fuzzy_search,
            "base_models": base_models,
            "tags": tags,
            "search_options": search_options,
            "hash_filters": hash_filters,
            "favorites_only": favorites_only,
            **self._parse_specific_params(request),
        }


class ModelManagementHandler:
    """Handle mutation operations on models."""

    def __init__(self, *, service, logger: logging.Logger) -> None:
        self._service = service
        self._logger = logger

    async def delete_model(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_delete_model(request, self._service.scanner)

    async def exclude_model(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_exclude_model(request, self._service.scanner)

    async def fetch_civitai(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_path = data.get("file_path")
            if not file_path:
                return web.json_response({"success": False, "error": "File path is required"}, status=400)

            cache = await self._service.scanner.get_cached_data()
            model_data = next((item for item in cache.raw_data if item["file_path"] == file_path), None)
            if not model_data:
                return web.json_response({"success": False, "error": "Model not found in cache"}, status=404)
            if not model_data.get("sha256"):
                return web.json_response({"success": False, "error": "No SHA256 hash found"}, status=400)

            success, error = await ModelRouteUtils.fetch_and_update_model(
                sha256=model_data["sha256"],
                file_path=file_path,
                model_data=model_data,
                update_cache_func=self._service.scanner.update_single_model_cache,
            )
            if not success:
                return web.json_response({"success": False, "error": error})

            formatted_metadata = await self._service.format_response(model_data)
            return web.json_response({"success": True, "metadata": formatted_metadata})
        except Exception as exc:
            self._logger.error("Error fetching from CivitAI: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def relink_civitai(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_relink_civitai(request, self._service.scanner)

    async def replace_preview(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_replace_preview(request, self._service.scanner)

    async def save_metadata(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_save_metadata(request, self._service.scanner)

    async def add_tags(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_add_tags(request, self._service.scanner)

    async def rename_model(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_rename_model(request, self._service.scanner)

    async def bulk_delete_models(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_bulk_delete_models(request, self._service.scanner)

    async def verify_duplicates(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_verify_duplicates(request, self._service.scanner)


class ModelQueryHandler:
    """Serve read-only model queries."""

    def __init__(self, *, service, logger: logging.Logger) -> None:
        self._service = service
        self._logger = logger

    async def get_top_tags(self, request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "20"))
            if limit < 1 or limit > 100:
                limit = 20
            top_tags = await self._service.get_top_tags(limit)
            return web.json_response({"success": True, "tags": top_tags})
        except Exception as exc:
            self._logger.error("Error getting top tags: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": "Internal server error"}, status=500)

    async def get_base_models(self, request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "20"))
            if limit < 1 or limit > 100:
                limit = 20
            base_models = await self._service.get_base_models(limit)
            return web.json_response({"success": True, "base_models": base_models})
        except Exception as exc:
            self._logger.error("Error retrieving base models: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def scan_models(self, request: web.Request) -> web.Response:
        try:
            full_rebuild = request.query.get("full_rebuild", "false").lower() == "true"
            await self._service.scan_models(force_refresh=True, rebuild_cache=full_rebuild)
            return web.json_response({"status": "success", "message": f"{self._service.model_type.capitalize()} scan completed"})
        except Exception as exc:
            self._logger.error("Error scanning %ss: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def get_model_roots(self, request: web.Request) -> web.Response:
        try:
            roots = self._service.get_model_roots()
            return web.json_response({"success": True, "roots": roots})
        except Exception as exc:
            self._logger.error("Error getting %s roots: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_folders(self, request: web.Request) -> web.Response:
        try:
            cache = await self._service.scanner.get_cached_data()
            return web.json_response({"folders": cache.folders})
        except Exception as exc:
            self._logger.error("Error getting folders: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_folder_tree(self, request: web.Request) -> web.Response:
        try:
            model_root = request.query.get("model_root")
            if not model_root:
                return web.json_response({"success": False, "error": "model_root parameter is required"}, status=400)
            folder_tree = await self._service.get_folder_tree(model_root)
            return web.json_response({"success": True, "tree": folder_tree})
        except Exception as exc:
            self._logger.error("Error getting folder tree: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_unified_folder_tree(self, request: web.Request) -> web.Response:
        try:
            unified_tree = await self._service.get_unified_folder_tree()
            return web.json_response({"success": True, "tree": unified_tree})
        except Exception as exc:
            self._logger.error("Error getting unified folder tree: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def find_duplicate_models(self, request: web.Request) -> web.Response:
        try:
            duplicates = self._service.find_duplicate_hashes()
            result = []
            cache = await self._service.scanner.get_cached_data()
            for sha256, paths in duplicates.items():
                group = {"hash": sha256, "models": []}
                for path in paths:
                    model = next((m for m in cache.raw_data if m["file_path"] == path), None)
                    if model:
                        group["models"].append(await self._service.format_response(model))
                primary_path = self._service.get_path_by_hash(sha256)
                if primary_path and primary_path not in paths:
                    primary_model = next((m for m in cache.raw_data if m["file_path"] == primary_path), None)
                    if primary_model:
                        group["models"].insert(0, await self._service.format_response(primary_model))
                if len(group["models"]) > 1:
                    result.append(group)
            return web.json_response({"success": True, "duplicates": result, "count": len(result)})
        except Exception as exc:
            self._logger.error("Error finding duplicate %ss: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def find_filename_conflicts(self, request: web.Request) -> web.Response:
        try:
            duplicates = self._service.find_duplicate_filenames()
            result = []
            cache = await self._service.scanner.get_cached_data()
            for filename, paths in duplicates.items():
                group = {"filename": filename, "models": []}
                for path in paths:
                    model = next((m for m in cache.raw_data if m["file_path"] == path), None)
                    if model:
                        group["models"].append(await self._service.format_response(model))
                hash_val = self._service.scanner.get_hash_by_filename(filename)
                if hash_val:
                    main_path = self._service.get_path_by_hash(hash_val)
                    if main_path and main_path not in paths:
                        main_model = next((m for m in cache.raw_data if m["file_path"] == main_path), None)
                        if main_model:
                            group["models"].insert(0, await self._service.format_response(main_model))
                if group["models"]:
                    result.append(group)
            return web.json_response({"success": True, "conflicts": result, "count": len(result)})
        except Exception as exc:
            self._logger.error("Error finding filename conflicts for %ss: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_model_notes(self, request: web.Request) -> web.Response:
        try:
            model_name = request.query.get("name")
            if not model_name:
                return web.Response(text=f"{self._service.model_type.capitalize()} file name is required", status=400)
            notes = await self._service.get_model_notes(model_name)
            if notes is not None:
                return web.json_response({"success": True, "notes": notes})
            return web.json_response({"success": False, "error": f"{self._service.model_type.capitalize()} not found in cache"}, status=404)
        except Exception as exc:
            self._logger.error("Error getting %s notes: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_model_preview_url(self, request: web.Request) -> web.Response:
        try:
            model_name = request.query.get("name")
            if not model_name:
                return web.Response(text=f"{self._service.model_type.capitalize()} file name is required", status=400)
            preview_url = await self._service.get_model_preview_url(model_name)
            if preview_url:
                return web.json_response({"success": True, "preview_url": preview_url})
            return web.json_response({"success": False, "error": f"No preview URL found for the specified {self._service.model_type}"}, status=404)
        except Exception as exc:
            self._logger.error("Error getting %s preview URL: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_model_civitai_url(self, request: web.Request) -> web.Response:
        try:
            model_name = request.query.get("name")
            if not model_name:
                return web.Response(text=f"{self._service.model_type.capitalize()} file name is required", status=400)
            result = await self._service.get_model_civitai_url(model_name)
            if result["civitai_url"]:
                return web.json_response({"success": True, **result})
            return web.json_response({"success": False, "error": f"No Civitai data found for the specified {self._service.model_type}"}, status=404)
        except Exception as exc:
            self._logger.error("Error getting %s Civitai URL: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_model_metadata(self, request: web.Request) -> web.Response:
        try:
            file_path = request.query.get("file_path")
            if not file_path:
                return web.Response(text="File path is required", status=400)
            metadata = await self._service.get_model_metadata(file_path)
            if metadata is not None:
                return web.json_response({"success": True, "metadata": metadata})
            return web.json_response({"success": False, "error": f"{self._service.model_type.capitalize()} not found or no CivitAI metadata available"}, status=404)
        except Exception as exc:
            self._logger.error("Error getting %s metadata: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_model_description(self, request: web.Request) -> web.Response:
        try:
            file_path = request.query.get("file_path")
            if not file_path:
                return web.Response(text="File path is required", status=400)
            description = await self._service.get_model_description(file_path)
            if description is not None:
                return web.json_response({"success": True, "description": description})
            return web.json_response({"success": False, "error": f"{self._service.model_type.capitalize()} not found or no description available"}, status=404)
        except Exception as exc:
            self._logger.error("Error getting %s description: %s", self._service.model_type, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_relative_paths(self, request: web.Request) -> web.Response:
        try:
            search = request.query.get("search", "").strip()
            limit = min(int(request.query.get("limit", "15")), 50)
            matching_paths = await self._service.search_relative_paths(search, limit)
            return web.json_response({"success": True, "relative_paths": matching_paths})
        except Exception as exc:
            self._logger.error("Error getting relative paths for autocomplete: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class ModelDownloadHandler:
    """Coordinate downloads and progress reporting."""

    def __init__(self, *, ws_manager: WebSocketManager, logger: logging.Logger) -> None:
        self._ws_manager = ws_manager
        self._logger = logger

    async def download_model(self, request: web.Request) -> web.Response:
        return await ModelRouteUtils.handle_download_model(request)

    async def download_model_get(self, request: web.Request) -> web.Response:
        try:
            model_id = request.query.get("model_id")
            if not model_id:
                return web.Response(status=400, text="Missing required parameter: Please provide 'model_id'")

            model_version_id = request.query.get("model_version_id")
            download_id = request.query.get("download_id")
            use_default_paths = request.query.get("use_default_paths", "false").lower() == "true"
            source = request.query.get("source")

            data = {"model_id": model_id, "use_default_paths": use_default_paths}
            if model_version_id:
                data["model_version_id"] = model_version_id
            if download_id:
                data["download_id"] = download_id
            if source:
                data["source"] = source

            loop = asyncio.get_event_loop()
            future = loop.create_future()
            future.set_result(data)

            mock_request = type("MockRequest", (), {"json": lambda self=None: future})()
            return await ModelRouteUtils.handle_download_model(mock_request)
        except Exception as exc:
            self._logger.error("Error downloading model via GET: %s", exc, exc_info=True)
            return web.Response(status=500, text=str(exc))

    async def cancel_download_get(self, request: web.Request) -> web.Response:
        try:
            download_id = request.query.get("download_id")
            if not download_id:
                return web.json_response({"success": False, "error": "Download ID is required"}, status=400)
            mock_request = type("MockRequest", (), {"match_info": {"download_id": download_id}})()
            return await ModelRouteUtils.handle_cancel_download(mock_request)
        except Exception as exc:
            self._logger.error("Error cancelling download via GET: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_download_progress(self, request: web.Request) -> web.Response:
        try:
            download_id = request.match_info.get("download_id")
            if not download_id:
                return web.json_response({"success": False, "error": "Download ID is required"}, status=400)
            progress_data = self._ws_manager.get_download_progress(download_id)
            if progress_data is None:
                return web.json_response({"success": False, "error": "Download ID not found"}, status=404)
            return web.json_response({"success": True, "progress": progress_data.get("progress", 0)})
        except Exception as exc:
            self._logger.error("Error getting download progress: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class ModelCivitaiHandler:
    """CivitAI integration endpoints."""

    def __init__(
        self,
        *,
        service,
        settings_service: SettingsManager,
        ws_manager: WebSocketManager,
        logger: logging.Logger,
        metadata_provider_factory: Callable[[], Awaitable],
        validate_model_type: Callable[[str], bool],
        expected_model_types: Callable[[], str],
        find_model_file: Callable[[Iterable[Mapping[str, object]]], Optional[Mapping[str, object]]],
    ) -> None:
        self._service = service
        self._settings = settings_service
        self._ws_manager = ws_manager
        self._logger = logger
        self._metadata_provider_factory = metadata_provider_factory
        self._validate_model_type = validate_model_type
        self._expected_model_types = expected_model_types
        self._find_model_file = find_model_file

    async def fetch_all_civitai(self, request: web.Request) -> web.Response:
        try:
            cache = await self._service.scanner.get_cached_data()
            total = len(cache.raw_data)
            processed = 0
            success = 0
            needs_resort = False

            enable_metadata_archive_db = self._settings.get("enable_metadata_archive_db", False)
            to_process = [
                model
                for model in cache.raw_data
                if model.get("sha256")
                and (not model.get("civitai") or not model["civitai"].get("id"))
                and (
                    (enable_metadata_archive_db and not model.get("db_checked", False))
                    or (not enable_metadata_archive_db and model.get("from_civitai") is True)
                )
            ]
            total_to_process = len(to_process)

            await self._ws_manager.broadcast({
                "status": "started",
                "total": total_to_process,
                "processed": 0,
                "success": 0,
            })

            for model in to_process:
                try:
                    original_name = model.get("model_name")
                    result, error = await ModelRouteUtils.fetch_and_update_model(
                        sha256=model["sha256"],
                        file_path=model["file_path"],
                        model_data=model,
                        update_cache_func=self._service.scanner.update_single_model_cache,
                    )
                    if result:
                        success += 1
                        if original_name != model.get("model_name"):
                            needs_resort = True
                    processed += 1
                    await self._ws_manager.broadcast({
                        "status": "processing",
                        "total": total_to_process,
                        "processed": processed,
                        "success": success,
                        "current_name": model.get("model_name", "Unknown"),
                    })
                except Exception as exc:  # pragma: no cover - logging path
                    self._logger.error("Error fetching CivitAI data for %s: %s", model["file_path"], exc)

            if needs_resort:
                await cache.resort()

            await self._ws_manager.broadcast({
                "status": "completed",
                "total": total_to_process,
                "processed": processed,
                "success": success,
            })

            return web.json_response({
                "success": True,
                "message": f"Successfully updated {success} of {processed} processed {self._service.model_type}s (total: {total})",
            })
        except Exception as exc:
            await self._ws_manager.broadcast({"status": "error", "error": str(exc)})
            self._logger.error("Error in fetch_all_civitai for %ss: %s", self._service.model_type, exc)
            return web.Response(text=str(exc), status=500)

    async def get_civitai_versions(self, request: web.Request) -> web.Response:
        try:
            model_id = request.match_info["model_id"]
            metadata_provider = await self._metadata_provider_factory()
            response = await metadata_provider.get_model_versions(model_id)
            if not response or not response.get("modelVersions"):
                return web.Response(status=404, text="Model not found")

            versions = response.get("modelVersions", [])
            model_type = response.get("type", "")
            if not self._validate_model_type(model_type):
                return web.json_response(
                    {"error": f"Model type mismatch. Expected {self._expected_model_types()}, got {model_type}"},
                    status=400,
                )

            for version in versions:
                model_file = self._find_model_file(version.get("files", [])) if isinstance(version.get("files"), Iterable) else None
                if model_file:
                    hashes = model_file.get("hashes", {}) if isinstance(model_file, Mapping) else {}
                    sha256 = hashes.get("SHA256") if isinstance(hashes, Mapping) else None
                    if sha256:
                        version["existsLocally"] = self._service.has_hash(sha256)
                        if version["existsLocally"]:
                            version["localPath"] = self._service.get_path_by_hash(sha256)
                        version["modelSizeKB"] = model_file.get("sizeKB") if isinstance(model_file, Mapping) else None
                else:
                    version["existsLocally"] = False
            return web.json_response(versions)
        except Exception as exc:
            self._logger.error("Error fetching %s model versions: %s", self._service.model_type, exc)
            return web.Response(status=500, text=str(exc))

    async def get_civitai_model_by_version(self, request: web.Request) -> web.Response:
        try:
            model_version_id = request.match_info.get("modelVersionId")
            metadata_provider = await self._metadata_provider_factory()
            model, error_msg = await metadata_provider.get_model_version_info(model_version_id)
            if not model:
                self._logger.warning("Failed to fetch model version %s: %s", model_version_id, error_msg)
                status_code = 404 if error_msg and "not found" in error_msg.lower() else 500
                return web.json_response({"success": False, "error": error_msg or "Failed to fetch model information"}, status=status_code)
            return web.json_response(model)
        except Exception as exc:
            self._logger.error("Error fetching model details: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_civitai_model_by_hash(self, request: web.Request) -> web.Response:
        try:
            hash_value = request.match_info.get("hash")
            metadata_provider = await self._metadata_provider_factory()
            model, error = await metadata_provider.get_model_by_hash(hash_value)
            if error:
                self._logger.warning("Error getting model by hash: %s", error)
                return web.json_response({"success": False, "error": error}, status=404)
            return web.json_response(model)
        except Exception as exc:
            self._logger.error("Error fetching model details by hash: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class ModelMoveHandler:
    """Move model files between folders."""

    def __init__(self, *, move_service: ModelMoveService, logger: logging.Logger) -> None:
        self._move_service = move_service
        self._logger = logger

    async def move_model(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_path = data.get("file_path")
            target_path = data.get("target_path")
            if not file_path or not target_path:
                return web.Response(text="File path and target path are required", status=400)
            result = await self._move_service.move_model(file_path, target_path)
            status = 200 if result.get("success") else 500
            return web.json_response(result, status=status)
        except Exception as exc:
            self._logger.error("Error moving model: %s", exc, exc_info=True)
            return web.Response(text=str(exc), status=500)

    async def move_models_bulk(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_paths = data.get("file_paths", [])
            target_path = data.get("target_path")
            if not file_paths or not target_path:
                return web.Response(text="File paths and target path are required", status=400)
            result = await self._move_service.move_models_bulk(file_paths, target_path)
            return web.json_response(result)
        except Exception as exc:
            self._logger.error("Error moving models in bulk: %s", exc, exc_info=True)
            return web.Response(text=str(exc), status=500)


class ModelAutoOrganizeHandler:
    """Manage auto-organize operations."""

    def __init__(
        self,
        *,
        file_service: ModelFileService,
        progress_callback: WebSocketProgressCallback,
        ws_manager: WebSocketManager,
        logger: logging.Logger,
    ) -> None:
        self._file_service = file_service
        self._progress_callback = progress_callback
        self._ws_manager = ws_manager
        self._logger = logger

    async def auto_organize_models(self, request: web.Request) -> web.Response:
        try:
            if self._ws_manager.is_auto_organize_running():
                return web.json_response(
                    {"success": False, "error": "Auto-organize is already running. Please wait for it to complete."},
                    status=409,
                )

            auto_organize_lock = await self._ws_manager.get_auto_organize_lock()
            if auto_organize_lock.locked():
                return web.json_response(
                    {"success": False, "error": "Auto-organize is already running. Please wait for it to complete."},
                    status=409,
                )

            file_paths = None
            if request.method == "POST":
                try:
                    data = await request.json()
                    file_paths = data.get("file_paths")
                except Exception:  # pragma: no cover - permissive path
                    pass

            async with auto_organize_lock:
                result = await self._file_service.auto_organize_models(
                    file_paths=file_paths,
                    progress_callback=self._progress_callback,
                )
                return web.json_response(result.to_dict())
        except Exception as exc:
            self._logger.error("Error in auto_organize_models: %s", exc, exc_info=True)
            await self._ws_manager.broadcast_auto_organize_progress(
                {"type": "auto_organize_progress", "status": "error", "error": str(exc)}
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_auto_organize_progress(self, request: web.Request) -> web.Response:
        try:
            progress_data = self._ws_manager.get_auto_organize_progress()
            if progress_data is None:
                return web.json_response({"success": False, "error": "No auto-organize operation in progress"}, status=404)
            return web.json_response({"success": True, "progress": progress_data})
        except Exception as exc:
            self._logger.error("Error getting auto-organize progress: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


@dataclass
class ModelHandlerSet:
    """Aggregate concrete handlers into a flat mapping."""

    page_view: ModelPageView
    listing: ModelListingHandler
    management: ModelManagementHandler
    query: ModelQueryHandler
    download: ModelDownloadHandler
    civitai: ModelCivitaiHandler
    move: ModelMoveHandler
    auto_organize: ModelAutoOrganizeHandler

    def to_route_mapping(self) -> Dict[str, Callable[[web.Request], Awaitable[web.Response]]]:
        return {
            "handle_models_page": self.page_view.handle,
            "get_models": self.listing.get_models,
            "delete_model": self.management.delete_model,
            "exclude_model": self.management.exclude_model,
            "fetch_civitai": self.management.fetch_civitai,
            "fetch_all_civitai": self.civitai.fetch_all_civitai,
            "relink_civitai": self.management.relink_civitai,
            "replace_preview": self.management.replace_preview,
            "save_metadata": self.management.save_metadata,
            "add_tags": self.management.add_tags,
            "rename_model": self.management.rename_model,
            "bulk_delete_models": self.management.bulk_delete_models,
            "verify_duplicates": self.management.verify_duplicates,
            "get_top_tags": self.query.get_top_tags,
            "get_base_models": self.query.get_base_models,
            "scan_models": self.query.scan_models,
            "get_model_roots": self.query.get_model_roots,
            "get_folders": self.query.get_folders,
            "get_folder_tree": self.query.get_folder_tree,
            "get_unified_folder_tree": self.query.get_unified_folder_tree,
            "find_duplicate_models": self.query.find_duplicate_models,
            "find_filename_conflicts": self.query.find_filename_conflicts,
            "download_model": self.download.download_model,
            "download_model_get": self.download.download_model_get,
            "cancel_download_get": self.download.cancel_download_get,
            "get_download_progress": self.download.get_download_progress,
            "get_civitai_versions": self.civitai.get_civitai_versions,
            "get_civitai_model_by_version": self.civitai.get_civitai_model_by_version,
            "get_civitai_model_by_hash": self.civitai.get_civitai_model_by_hash,
            "move_model": self.move.move_model,
            "move_models_bulk": self.move.move_models_bulk,
            "auto_organize_models": self.auto_organize.auto_organize_models,
            "get_auto_organize_progress": self.auto_organize.get_auto_organize_progress,
            "get_model_notes": self.query.get_model_notes,
            "get_model_preview_url": self.query.get_model_preview_url,
            "get_model_civitai_url": self.query.get_model_civitai_url,
            "get_model_metadata": self.query.get_model_metadata,
            "get_model_description": self.query.get_model_description,
            "get_relative_paths": self.query.get_relative_paths,
        }

