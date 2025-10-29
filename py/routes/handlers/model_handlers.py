"""Handlers for base model routes."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Iterable, List, Mapping, Optional

from aiohttp import web
import jinja2

from ...config import config
from ...services.download_coordinator import DownloadCoordinator
from ...services.metadata_sync_service import MetadataSyncService
from ...services.model_file_service import ModelMoveService
from ...services.preview_asset_service import PreviewAssetService
from ...services.settings_manager import SettingsManager
from ...services.tag_update_service import TagUpdateService
from ...services.use_cases import (
    AutoOrganizeInProgressError,
    AutoOrganizeUseCase,
    BulkMetadataRefreshUseCase,
    DownloadModelEarlyAccessError,
    DownloadModelUseCase,
    DownloadModelValidationError,
    MetadataRefreshProgressReporter,
)
from ...services.websocket_manager import WebSocketManager
from ...services.websocket_progress_callback import WebSocketProgressCallback
from ...services.errors import RateLimitError, ResourceNotFoundError
from ...utils.file_utils import calculate_sha256
from ...utils.metadata_manager import MetadataManager


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

        update_available_only = request.query.get("update_available_only", "false").lower() == "true"

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
            "update_available_only": update_available_only,
            **self._parse_specific_params(request),
        }


class ModelManagementHandler:
    """Handle mutation operations on models."""

    def __init__(
        self,
        *,
        service,
        logger: logging.Logger,
        metadata_sync: MetadataSyncService,
        preview_service: PreviewAssetService,
        tag_update_service: TagUpdateService,
        lifecycle_service,
    ) -> None:
        self._service = service
        self._logger = logger
        self._metadata_sync = metadata_sync
        self._preview_service = preview_service
        self._tag_update_service = tag_update_service
        self._lifecycle_service = lifecycle_service

    async def delete_model(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_path = data.get("file_path")
            if not file_path:
                return web.Response(text="Model path is required", status=400)

            result = await self._lifecycle_service.delete_model(file_path)
            return web.json_response(result)
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error("Error deleting model: %s", exc, exc_info=True)
            return web.Response(text=str(exc), status=500)

    async def exclude_model(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_path = data.get("file_path")
            if not file_path:
                return web.Response(text="Model path is required", status=400)

            result = await self._lifecycle_service.exclude_model(file_path)
            return web.json_response(result)
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error("Error excluding model: %s", exc, exc_info=True)
            return web.Response(text=str(exc), status=500)

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

            await MetadataManager.hydrate_model_data(model_data)

            success, error = await self._metadata_sync.fetch_and_update_model(
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
        try:
            data = await request.json()
            file_path = data.get("file_path")
            model_id = data.get("model_id")
            model_version_id = data.get("model_version_id")

            if not file_path or model_id is None:
                return web.json_response(
                    {"success": False, "error": "Both file_path and model_id are required"},
                    status=400,
                )

            metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
            local_metadata = await self._metadata_sync.load_local_metadata(metadata_path)

            updated_metadata = await self._metadata_sync.relink_metadata(
                file_path=file_path,
                metadata=local_metadata,
                model_id=int(model_id),
                model_version_id=int(model_version_id) if model_version_id else None,
            )

            await self._service.scanner.update_single_model_cache(
                file_path, file_path, updated_metadata
            )

            message = (
                f"Model successfully re-linked to Civitai model {model_id}"
                + (f" version {model_version_id}" if model_version_id else "")
            )
            return web.json_response(
                {"success": True, "message": message, "hash": updated_metadata.get("sha256", "")}
            )
        except Exception as exc:
            self._logger.error("Error re-linking to CivitAI: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def replace_preview(self, request: web.Request) -> web.Response:
        try:
            reader = await request.multipart()

            field = await reader.next()
            if field is None or field.name != "preview_file":
                raise ValueError("Expected 'preview_file' field")
            content_type = field.headers.get("Content-Type", "image/png")
            content_disposition = field.headers.get("Content-Disposition", "")

            original_filename = None
            import re

            match = re.search(r'filename="(.*?)"', content_disposition)
            if match:
                original_filename = match.group(1)

            preview_data = await field.read()

            field = await reader.next()
            if field is None or field.name != "model_path":
                raise ValueError("Expected 'model_path' field")
            model_path = (await field.read()).decode()

            nsfw_level = 0
            field = await reader.next()
            if field and field.name == "nsfw_level":
                try:
                    nsfw_level = int((await field.read()).decode())
                except (ValueError, TypeError):
                    self._logger.warning("Invalid NSFW level format, using default 0")

            result = await self._preview_service.replace_preview(
                model_path=model_path,
                preview_data=preview_data,
                content_type=content_type,
                original_filename=original_filename,
                nsfw_level=nsfw_level,
                update_preview_in_cache=self._service.scanner.update_preview_in_cache,
                metadata_loader=self._metadata_sync.load_local_metadata,
            )

            return web.json_response(
                {
                    "success": True,
                    "preview_url": config.get_preview_static_url(result["preview_path"]),
                    "preview_nsfw_level": result["preview_nsfw_level"],
                }
            )
        except Exception as exc:
            self._logger.error("Error replacing preview: %s", exc, exc_info=True)
            return web.Response(text=str(exc), status=500)

    async def save_metadata(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_path = data.get("file_path")
            if not file_path:
                return web.Response(text="File path is required", status=400)

            metadata_updates = {k: v for k, v in data.items() if k != "file_path"}

            await self._metadata_sync.save_metadata_updates(
                file_path=file_path,
                updates=metadata_updates,
                metadata_loader=self._metadata_sync.load_local_metadata,
                update_cache=self._service.scanner.update_single_model_cache,
            )

            if "model_name" in metadata_updates:
                cache = await self._service.scanner.get_cached_data()
                await cache.resort()

            return web.json_response({"success": True})
        except Exception as exc:
            self._logger.error("Error saving metadata: %s", exc, exc_info=True)
            return web.Response(text=str(exc), status=500)

    async def add_tags(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_path = data.get("file_path")
            new_tags = data.get("tags", [])

            if not file_path:
                return web.Response(text="File path is required", status=400)

            if not isinstance(new_tags, list):
                return web.Response(text="Tags must be a list", status=400)

            tags = await self._tag_update_service.add_tags(
                file_path=file_path,
                new_tags=new_tags,
                metadata_loader=self._metadata_sync.load_local_metadata,
                update_cache=self._service.scanner.update_single_model_cache,
            )

            return web.json_response({"success": True, "tags": tags})
        except Exception as exc:
            self._logger.error("Error adding tags: %s", exc, exc_info=True)
            return web.Response(text=str(exc), status=500)

    async def rename_model(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_path = data.get("file_path")
            new_file_name = data.get("new_file_name")

            if not file_path or not new_file_name:
                return web.json_response(
                    {
                        "success": False,
                        "error": "File path and new file name are required",
                    },
                    status=400,
                )

            result = await self._lifecycle_service.rename_model(
                file_path=file_path, new_file_name=new_file_name
            )

            return web.json_response(
                {
                    **result,
                    "new_preview_path": config.get_preview_static_url(
                        result.get("new_preview_path")
                    ),
                }
            )
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error("Error renaming model: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def bulk_delete_models(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_paths = data.get("file_paths", [])
            if not file_paths:
                return web.json_response(
                    {
                        "success": False,
                        "error": "No file paths provided for deletion",
                    },
                    status=400,
                )

            result = await self._lifecycle_service.bulk_delete_models(file_paths)
            return web.json_response(result)
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error("Error in bulk delete: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def verify_duplicates(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_paths = data.get("file_paths", [])

            if not file_paths:
                return web.json_response(
                    {"success": False, "error": "No file paths provided for verification"},
                    status=400,
                )

            results = await self._metadata_sync.verify_duplicate_hashes(
                file_paths=file_paths,
                metadata_loader=self._metadata_sync.load_local_metadata,
                hash_calculator=calculate_sha256,
                update_cache=self._service.scanner.update_single_model_cache,
            )

            return web.json_response({"success": True, **results})
        except Exception as exc:
            self._logger.error("Error verifying duplicate models: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


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

    def __init__(
        self,
        *,
        ws_manager: WebSocketManager,
        logger: logging.Logger,
        download_use_case: DownloadModelUseCase,
        download_coordinator: DownloadCoordinator,
    ) -> None:
        self._ws_manager = ws_manager
        self._logger = logger
        self._download_use_case = download_use_case
        self._download_coordinator = download_coordinator

    async def download_model(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
            result = await self._download_use_case.execute(payload)
            if not result.get("success", False):
                return web.json_response(result, status=500)
            return web.json_response(result)
        except DownloadModelValidationError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except DownloadModelEarlyAccessError as exc:
            self._logger.warning("Early access error: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=401)
        except Exception as exc:
            error_message = str(exc)
            self._logger.error("Error downloading model: %s", error_message, exc_info=True)
            return web.json_response({"success": False, "error": error_message}, status=500)

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
            result = await self._download_use_case.execute(data)
            if not result.get("success", False):
                return web.json_response(result, status=500)
            return web.json_response(result)
        except DownloadModelValidationError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except DownloadModelEarlyAccessError as exc:
            self._logger.warning("Early access error: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=401)
        except Exception as exc:
            self._logger.error("Error downloading model via GET: %s", exc, exc_info=True)
            return web.Response(status=500, text=str(exc))

    async def cancel_download_get(self, request: web.Request) -> web.Response:
        try:
            download_id = request.query.get("download_id")
            if not download_id:
                return web.json_response({"success": False, "error": "Download ID is required"}, status=400)
            result = await self._download_coordinator.cancel_download(download_id)
            return web.json_response(result)
        except Exception as exc:
            self._logger.error("Error cancelling download via GET: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def pause_download_get(self, request: web.Request) -> web.Response:
        try:
            download_id = request.query.get("download_id")
            if not download_id:
                return web.json_response({"success": False, "error": "Download ID is required"}, status=400)
            result = await self._download_coordinator.pause_download(download_id)
            status = 200 if result.get("success") else 400
            return web.json_response(result, status=status)
        except Exception as exc:
            self._logger.error("Error pausing download via GET: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def resume_download_get(self, request: web.Request) -> web.Response:
        try:
            download_id = request.query.get("download_id")
            if not download_id:
                return web.json_response({"success": False, "error": "Download ID is required"}, status=400)
            result = await self._download_coordinator.resume_download(download_id)
            status = 200 if result.get("success") else 400
            return web.json_response(result, status=status)
        except Exception as exc:
            self._logger.error("Error resuming download via GET: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_download_progress(self, request: web.Request) -> web.Response:
        try:
            download_id = request.match_info.get("download_id")
            if not download_id:
                return web.json_response({"success": False, "error": "Download ID is required"}, status=400)
            progress_data = self._ws_manager.get_download_progress(download_id)
            if progress_data is None:
                return web.json_response({"success": False, "error": "Download ID not found"}, status=404)
            response_payload = {
                "success": True,
                "progress": progress_data.get("progress", 0),
                "bytes_downloaded": progress_data.get("bytes_downloaded"),
                "total_bytes": progress_data.get("total_bytes"),
                "bytes_per_second": progress_data.get("bytes_per_second", 0.0),
            }

            status = progress_data.get("status")
            if status and status != "progress":
                response_payload["status"] = status
                if "message" in progress_data:
                    response_payload["message"] = progress_data["message"]
            elif status is None and "message" in progress_data:
                response_payload["message"] = progress_data["message"]

            return web.json_response(response_payload)
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
        metadata_sync: MetadataSyncService,
        metadata_refresh_use_case: BulkMetadataRefreshUseCase,
        metadata_progress_callback: MetadataRefreshProgressReporter,
    ) -> None:
        self._service = service
        self._settings = settings_service
        self._ws_manager = ws_manager
        self._logger = logger
        self._metadata_provider_factory = metadata_provider_factory
        self._validate_model_type = validate_model_type
        self._expected_model_types = expected_model_types
        self._find_model_file = find_model_file
        self._metadata_sync = metadata_sync
        self._metadata_refresh_use_case = metadata_refresh_use_case
        self._metadata_progress_callback = metadata_progress_callback

    async def fetch_all_civitai(self, request: web.Request) -> web.Response:
        try:
            result = await self._metadata_refresh_use_case.execute_with_error_handling(
                progress_callback=self._metadata_progress_callback
            )
            return web.json_response(result)
        except Exception as exc:
            self._logger.error("Error in fetch_all_civitai for %ss: %s", self._service.model_type, exc)
            return web.Response(text=str(exc), status=500)

    async def get_civitai_versions(self, request: web.Request) -> web.Response:
        try:
            model_id = request.match_info["model_id"]
            metadata_provider = await self._metadata_provider_factory()
            try:
                response = await metadata_provider.get_model_versions(model_id)
            except ResourceNotFoundError:
                return web.Response(status=404, text="Model not found")
            if not response or not response.get("modelVersions"):
                return web.Response(status=404, text="Model not found")

            versions = response.get("modelVersions", [])
            model_type = response.get("type", "")
            if not self._validate_model_type(model_type):
                return web.json_response(
                    {"error": f"Model type mismatch. Expected {self._expected_model_types()}, got {model_type}"},
                    status=400,
                )

            cache = await self._service.scanner.get_cached_data()
            version_index = cache.version_index

            for version in versions:
                version_id = None
                version_id_raw = version.get("id")
                if version_id_raw is not None:
                    try:
                        version_id = int(str(version_id_raw))
                    except (TypeError, ValueError):
                        version_id = None

                cache_entry = version_index.get(version_id) if (version_id is not None and version_index) else None
                version["existsLocally"] = cache_entry is not None
                if cache_entry and isinstance(cache_entry, Mapping):
                    local_path = cache_entry.get("file_path")
                    if local_path:
                        version["localPath"] = local_path
                else:
                    version.pop("localPath", None)

                model_file = self._find_model_file(version.get("files", [])) if isinstance(version.get("files"), Iterable) else None
                if model_file and isinstance(model_file, Mapping):
                    version["modelSizeKB"] = model_file.get("sizeKB")
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
        use_case: AutoOrganizeUseCase,
        progress_callback: WebSocketProgressCallback,
        ws_manager: WebSocketManager,
        logger: logging.Logger,
    ) -> None:
        self._use_case = use_case
        self._progress_callback = progress_callback
        self._ws_manager = ws_manager
        self._logger = logger

    async def auto_organize_models(self, request: web.Request) -> web.Response:
        try:
            file_paths = None
            if request.method == "POST":
                try:
                    data = await request.json()
                    file_paths = data.get("file_paths")
                except Exception:  # pragma: no cover - permissive path
                    pass

            result = await self._use_case.execute(
                file_paths=file_paths,
                progress_callback=self._progress_callback,
            )
            return web.json_response(result.to_dict())
        except AutoOrganizeInProgressError:
            return web.json_response(
                {"success": False, "error": "Auto-organize is already running. Please wait for it to complete."},
                status=409,
            )
        except Exception as exc:
            self._logger.error("Error in auto_organize_models: %s", exc, exc_info=True)
            try:
                await self._progress_callback.on_progress(
                    {"type": "auto_organize_progress", "status": "error", "error": str(exc)}
                )
            except Exception:  # pragma: no cover - defensive reporting
                pass
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


class ModelUpdateHandler:
    """Handle update tracking requests."""

    def __init__(
        self,
        *,
        service,
        update_service,
        metadata_provider_selector,
        logger: logging.Logger,
    ) -> None:
        self._service = service
        self._update_service = update_service
        self._metadata_provider_selector = metadata_provider_selector
        self._logger = logger

    async def refresh_model_updates(self, request: web.Request) -> web.Response:
        payload = await self._read_json(request)
        force_refresh = self._parse_bool(request.query.get("force")) or self._parse_bool(
            payload.get("force")
        )

        raw_model_ids = payload.get("modelIds")
        if raw_model_ids is None:
            raw_model_ids = payload.get("model_ids")

        target_model_ids: list[int] = []
        if isinstance(raw_model_ids, (list, tuple, set)):
            for value in raw_model_ids:
                normalized = self._normalize_model_id(value)
                if normalized is not None:
                    target_model_ids.append(normalized)

        if target_model_ids:
            target_model_ids = sorted(set(target_model_ids))

        provider = await self._get_civitai_provider()
        if provider is None:
            return web.json_response(
                {"success": False, "error": "Civitai provider not available"}, status=503
            )

        try:
            records = await self._update_service.refresh_for_model_type(
                self._service.model_type,
                self._service.scanner,
                provider,
                force_refresh=force_refresh,
                target_model_ids=target_model_ids or None,
            )
        except RateLimitError as exc:
            return web.json_response(
                {"success": False, "error": str(exc) or "Rate limited"}, status=429
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.error("Failed to refresh model updates: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

        serialized_records = []
        for record in records.values():
            has_update_fn = getattr(record, "has_update", None)
            if callable(has_update_fn) and has_update_fn():
                serialized_records.append(self._serialize_record(record))

        return web.json_response(
            {
                "success": True,
                "records": serialized_records,
            }
        )

    async def set_model_update_ignore(self, request: web.Request) -> web.Response:
        payload = await self._read_json(request)
        model_id = self._normalize_model_id(payload.get("modelId"))
        if model_id is None:
            return web.json_response({"success": False, "error": "modelId is required"}, status=400)

        should_ignore = self._parse_bool(payload.get("shouldIgnore"))
        record = await self._update_service.set_should_ignore(
            self._service.model_type, model_id, should_ignore
        )
        return web.json_response({"success": True, "record": self._serialize_record(record)})

    async def set_version_update_ignore(self, request: web.Request) -> web.Response:
        payload = await self._read_json(request)
        model_id = self._normalize_model_id(payload.get("modelId"))
        version_id = self._normalize_model_id(payload.get("versionId"))
        if model_id is None or version_id is None:
            return web.json_response(
                {"success": False, "error": "modelId and versionId are required"},
                status=400,
            )

        should_ignore = self._parse_bool(payload.get("shouldIgnore"))
        record = await self._update_service.set_version_should_ignore(
            self._service.model_type,
            model_id,
            version_id,
            should_ignore,
        )
        overrides = await self._build_version_context(record)
        return web.json_response(
            {"success": True, "record": self._serialize_record(record, version_context=overrides)}
        )

    async def get_model_update_status(self, request: web.Request) -> web.Response:
        model_id = self._normalize_model_id(request.match_info.get("model_id"))
        if model_id is None:
            return web.json_response({"success": False, "error": "model_id must be an integer"}, status=400)

        refresh = self._parse_bool(request.query.get("refresh"))
        force = self._parse_bool(request.query.get("force"))

        try:
            record = await self._get_or_refresh_record(model_id, refresh=refresh, force=force)
        except RateLimitError as exc:
            return web.json_response(
                {"success": False, "error": str(exc) or "Rate limited"}, status=429
            )

        if record is None:
            return web.json_response(
                {"success": False, "error": "Model not tracked"}, status=404
            )

        return web.json_response({"success": True, "record": self._serialize_record(record)})

    async def get_model_versions(self, request: web.Request) -> web.Response:
        model_id = self._normalize_model_id(request.match_info.get("model_id"))
        if model_id is None:
            return web.json_response(
                {"success": False, "error": "model_id must be an integer"}, status=400
            )

        refresh = self._parse_bool(request.query.get("refresh"))
        force = self._parse_bool(request.query.get("force"))

        try:
            record = await self._get_or_refresh_record(model_id, refresh=refresh, force=force)
        except RateLimitError as exc:
            return web.json_response(
                {"success": False, "error": str(exc) or "Rate limited"}, status=429
            )

        if record is None:
            return web.json_response(
                {"success": False, "error": "Model not tracked"}, status=404
            )

        overrides = await self._build_version_context(record)
        return web.json_response(
            {"success": True, "record": self._serialize_record(record, version_context=overrides)}
        )

    async def _get_or_refresh_record(
        self, model_id: int, *, refresh: bool, force: bool
    ) -> Optional[object]:
        record = await self._update_service.get_record(self._service.model_type, model_id)
        if record and not refresh and not force:
            return record

        provider = await self._get_civitai_provider()
        if provider is None:
            return record

        return await self._update_service.refresh_single_model(
            self._service.model_type,
            model_id,
            self._service.scanner,
            provider,
            force_refresh=force or refresh,
        )

    async def _get_civitai_provider(self):
        try:
            return await self._metadata_provider_selector("civitai_api")
        except Exception as exc:  # pragma: no cover - defensive log
            self._logger.error("Failed to acquire civitai provider: %s", exc, exc_info=True)
            return None

    async def _read_json(self, request: web.Request) -> Dict:
        if not request.can_read_body:
            return {}
        try:
            return await request.json()
        except Exception:
            return {}

    @staticmethod
    def _parse_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes"}
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    @staticmethod
    def _normalize_model_id(value) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _serialize_record(
        self,
        record,
        *,
        version_context: Optional[Dict[int, Dict[str, Optional[str]]]] = None,
    ) -> Dict:
        context = version_context or {}
        return {
            "modelType": record.model_type,
            "modelId": record.model_id,
            "largestVersionId": record.largest_version_id,
            "versionIds": record.version_ids,
            "inLibraryVersionIds": record.in_library_version_ids,
            "lastCheckedAt": record.last_checked_at,
            "shouldIgnore": record.should_ignore_model,
            "hasUpdate": record.has_update(),
            "versions": [
                self._serialize_version(version, context.get(version.version_id))
                for version in record.versions
            ],
        }

    @staticmethod
    def _serialize_version(version, context: Optional[Dict[str, Optional[str]]]) -> Dict:
        context = context or {}
        preview_override = context.get("preview_override")
        preview_url = preview_override if preview_override is not None else version.preview_url
        return {
            "versionId": version.version_id,
            "name": version.name,
            "baseModel": version.base_model,
            "releasedAt": version.released_at,
            "sizeBytes": version.size_bytes,
            "previewUrl": preview_url,
            "isInLibrary": version.is_in_library,
            "shouldIgnore": version.should_ignore,
            "filePath": context.get("file_path"),
            "fileName": context.get("file_name"),
        }

    async def _build_version_context(self, record) -> Dict[int, Dict[str, Optional[str]]]:
        context: Dict[int, Dict[str, Optional[str]]] = {}
        try:
            cache = await self._service.scanner.get_cached_data()
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.debug("Failed to load cache while building preview overrides: %s", exc)
            return context

        version_index = getattr(cache, "version_index", None)
        if not version_index:
            return context

        for version in record.versions:
            if not version.is_in_library:
                continue
            cache_entry = version_index.get(version.version_id)
            if isinstance(cache_entry, Mapping):
                preview = cache_entry.get("preview_url")
                context_entry: Dict[str, Optional[str]] = {
                    "file_path": cache_entry.get("file_path"),
                    "file_name": cache_entry.get("file_name"),
                    "preview_override": None,
                }
                if isinstance(preview, str) and preview:
                    context_entry["preview_override"] = config.get_preview_static_url(preview)
                context[version.version_id] = context_entry
        return context


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
    updates: ModelUpdateHandler

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
            "pause_download_get": self.download.pause_download_get,
            "resume_download_get": self.download.resume_download_get,
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
            "refresh_model_updates": self.updates.refresh_model_updates,
            "set_model_update_ignore": self.updates.set_model_update_ignore,
            "set_version_update_ignore": self.updates.set_version_update_ignore,
            "get_model_update_status": self.updates.get_model_update_status,
            "get_model_versions": self.updates.get_model_versions,
        }
