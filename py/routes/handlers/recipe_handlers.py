"""Dedicated handler objects for recipe-related routes."""

from __future__ import annotations

import json
import logging
import os
import re
import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from aiohttp import web

from ...config import config
from ...services.server_i18n import server_i18n as default_server_i18n
from ...services.settings_manager import SettingsManager
from ...services.recipes import (
    RecipeAnalysisService,
    RecipeDownloadError,
    RecipeNotFoundError,
    RecipePersistenceService,
    RecipeSharingService,
    RecipeValidationError,
)
from ...services.metadata_service import get_default_metadata_provider
from ...utils.civitai_utils import extract_civitai_image_id, rewrite_preview_url
from ...utils.exif_utils import ExifUtils
from ...recipes.merger import GenParamsMerger
from ...recipes.enrichment import RecipeEnricher
from ...services.websocket_manager import ws_manager as default_ws_manager
from ...services.batch_import_service import BatchImportService

Logger = logging.Logger
EnsureDependenciesCallable = Callable[[], Awaitable[None]]
RecipeScannerGetter = Callable[[], Any]
CivitaiClientGetter = Callable[[], Any]


@dataclass(frozen=True)
class RecipeHandlerSet:
    """Group of handlers providing recipe route implementations."""

    page_view: "RecipePageView"
    listing: "RecipeListingHandler"
    query: "RecipeQueryHandler"
    management: "RecipeManagementHandler"
    analysis: "RecipeAnalysisHandler"
    sharing: "RecipeSharingHandler"
    batch_import: "BatchImportHandler"

    def to_route_mapping(
        self,
    ) -> Mapping[str, Callable[[web.Request], Awaitable[web.StreamResponse]]]:
        """Expose handler coroutines keyed by registrar handler names."""

        return {
            "render_page": self.page_view.render_page,
            "list_recipes": self.listing.list_recipes,
            "get_recipe": self.listing.get_recipe,
            "import_remote_recipe": self.management.import_remote_recipe,
            "analyze_uploaded_image": self.analysis.analyze_uploaded_image,
            "analyze_local_image": self.analysis.analyze_local_image,
            "save_recipe": self.management.save_recipe,
            "delete_recipe": self.management.delete_recipe,
            "get_top_tags": self.query.get_top_tags,
            "get_base_models": self.query.get_base_models,
            "get_roots": self.query.get_roots,
            "get_folders": self.query.get_folders,
            "get_folder_tree": self.query.get_folder_tree,
            "get_unified_folder_tree": self.query.get_unified_folder_tree,
            "share_recipe": self.sharing.share_recipe,
            "download_shared_recipe": self.sharing.download_shared_recipe,
            "get_recipe_syntax": self.query.get_recipe_syntax,
            "update_recipe": self.management.update_recipe,
            "reconnect_lora": self.management.reconnect_lora,
            "find_duplicates": self.query.find_duplicates,
            "move_recipes_bulk": self.management.move_recipes_bulk,
            "bulk_delete": self.management.bulk_delete,
            "save_recipe_from_widget": self.management.save_recipe_from_widget,
            "get_recipes_for_lora": self.query.get_recipes_for_lora,
            "get_recipes_for_checkpoint": self.query.get_recipes_for_checkpoint,
            "scan_recipes": self.query.scan_recipes,
            "move_recipe": self.management.move_recipe,
            "repair_recipes": self.management.repair_recipes,
            "cancel_repair": self.management.cancel_repair,
            "repair_recipe": self.management.repair_recipe,
            "get_repair_progress": self.management.get_repair_progress,
            "start_batch_import": self.batch_import.start_batch_import,
            "get_batch_import_progress": self.batch_import.get_batch_import_progress,
            "cancel_batch_import": self.batch_import.cancel_batch_import,
            "start_directory_import": self.batch_import.start_directory_import,
            "browse_directory": self.batch_import.browse_directory,
            "check_image_exists": self.management.check_image_exists,
            "import_from_url": self.management.import_from_url,
        }


class RecipePageView:
    """Render the recipe shell page."""

    def __init__(
        self,
        *,
        ensure_dependencies_ready: EnsureDependenciesCallable,
        settings_service: SettingsManager,
        server_i18n=default_server_i18n,
        template_env,
        template_name: str,
        recipe_scanner_getter: RecipeScannerGetter,
        logger: Logger,
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._settings = settings_service
        self._server_i18n = server_i18n
        self._template_env = template_env
        self._template_name = template_name
        self._recipe_scanner_getter = recipe_scanner_getter
        self._logger = logger

    async def render_page(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:  # pragma: no cover - defensive guard
                raise RuntimeError("Recipe scanner not available")

            user_language = self._settings.get("language", "en")
            self._server_i18n.set_locale(user_language)

            try:
                await recipe_scanner.get_cached_data(force_refresh=False)
                rendered = self._template_env.get_template(self._template_name).render(
                    recipes=[],
                    is_initializing=False,
                    settings=self._settings,
                    request=request,
                    t=self._server_i18n.get_translation,
                )
            except Exception as cache_error:  # pragma: no cover - logging path
                self._logger.error("Error loading recipe cache data: %s", cache_error)
                rendered = self._template_env.get_template(self._template_name).render(
                    is_initializing=True,
                    settings=self._settings,
                    request=request,
                    t=self._server_i18n.get_translation,
                )
            return web.Response(text=rendered, content_type="text/html")
        except Exception as exc:  # pragma: no cover - logging path
            self._logger.error("Error handling recipes request: %s", exc, exc_info=True)
            return web.Response(text="Error loading recipes page", status=500)


class RecipeListingHandler:
    """Provide listing and detail APIs for recipes."""

    def __init__(
        self,
        *,
        ensure_dependencies_ready: EnsureDependenciesCallable,
        recipe_scanner_getter: RecipeScannerGetter,
        logger: Logger,
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._logger = logger

    async def list_recipes(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            page = int(request.query.get("page", "1"))
            page_size = int(request.query.get("page_size", "20"))
            sort_by = request.query.get("sort_by", "date")
            search = request.query.get("search")
            folder = request.query.get("folder")
            recursive = request.query.get("recursive", "true").lower() == "true"

            search_options = {
                "title": request.query.get("search_title", "true").lower() == "true",
                "tags": request.query.get("search_tags", "true").lower() == "true",
                "lora_name": request.query.get("search_lora_name", "true").lower()
                == "true",
                "lora_model": request.query.get("search_lora_model", "true").lower()
                == "true",
                "prompt": request.query.get("search_prompt", "true").lower() == "true",
            }

            filters: Dict[str, Any] = {}
            base_models = request.query.get("base_models")
            if base_models:
                filters["base_model"] = base_models.split(",")

            if request.query.get("favorite", "false").lower() == "true":
                filters["favorite"] = True

            tag_filters: Dict[str, str] = {}
            legacy_tags = request.query.get("tags")
            if legacy_tags:
                for tag in legacy_tags.split(","):
                    tag = tag.strip()
                    if tag:
                        tag_filters[tag] = "include"

            include_tags = request.query.getall("tag_include", [])
            for tag in include_tags:
                if tag:
                    tag_filters[tag] = "include"

            exclude_tags = request.query.getall("tag_exclude", [])
            for tag in exclude_tags:
                if tag:
                    tag_filters[tag] = "exclude"

            if tag_filters:
                filters["tags"] = tag_filters

            lora_hash = request.query.get("lora_hash")
            checkpoint_hash = request.query.get("checkpoint_hash")

            result = await recipe_scanner.get_paginated_data(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                search=search,
                filters=filters,
                search_options=search_options,
                lora_hash=lora_hash,
                checkpoint_hash=checkpoint_hash,
                folder=folder,
                recursive=recursive,
            )

            for item in result.get("items", []):
                file_path = item.get("file_path")
                if file_path:
                    item["file_url"] = self.format_recipe_file_url(file_path)
                else:
                    item.setdefault("file_url", "/loras_static/images/no-preview.png")
                item.setdefault("loras", [])
                item.setdefault("base_model", "")

            return web.json_response(result)
        except Exception as exc:
            self._logger.error("Error retrieving recipes: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def get_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            recipe_id = request.match_info["recipe_id"]
            recipe = await recipe_scanner.get_recipe_by_id(recipe_id)

            if not recipe:
                return web.json_response({"error": "Recipe not found"}, status=404)
            return web.json_response(recipe)
        except Exception as exc:
            self._logger.error(
                "Error retrieving recipe details: %s", exc, exc_info=True
            )
            return web.json_response({"error": str(exc)}, status=500)

    def format_recipe_file_url(self, file_path: str) -> str:
        try:
            normalized_path = os.path.normpath(file_path)
            static_url = config.get_preview_static_url(normalized_path)
            if static_url:
                return static_url
        except Exception as exc:  # pragma: no cover - logging path
            self._logger.error(
                "Error formatting recipe file URL: %s", exc, exc_info=True
            )
            return "/loras_static/images/no-preview.png"

        return "/loras_static/images/no-preview.png"


class RecipeQueryHandler:
    """Provide read-only insights on recipe data."""

    def __init__(
        self,
        *,
        ensure_dependencies_ready: EnsureDependenciesCallable,
        recipe_scanner_getter: RecipeScannerGetter,
        format_recipe_file_url: Callable[[str], str],
        logger: Logger,
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._format_recipe_file_url = format_recipe_file_url
        self._logger = logger

    async def get_top_tags(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            limit = int(request.query.get("limit", "20"))
            cache = await recipe_scanner.get_cached_data()

            tag_counts: Dict[str, int] = {}
            for recipe in getattr(cache, "raw_data", []):
                for tag in recipe.get("tags", []) or []:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

            sorted_tags = [
                {"tag": tag, "count": count} for tag, count in tag_counts.items()
            ]
            sorted_tags.sort(key=lambda entry: entry["count"], reverse=True)
            return web.json_response({"success": True, "tags": sorted_tags[:limit]})
        except Exception as exc:
            self._logger.error("Error retrieving top tags: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_base_models(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            limit = int(request.query.get("limit", "20"))
            cache = await recipe_scanner.get_cached_data()

            base_model_counts: Dict[str, int] = {}
            for recipe in getattr(cache, "raw_data", []):
                base_model = recipe.get("base_model")
                if base_model:
                    base_model_counts[base_model] = (
                        base_model_counts.get(base_model, 0) + 1
                    )

            sorted_models = [
                {"name": model, "count": count}
                for model, count in base_model_counts.items()
            ]
            sorted_models.sort(key=lambda entry: entry["count"], reverse=True)
            if limit > 0:
                sorted_models = sorted_models[:limit]
            return web.json_response({"success": True, "base_models": sorted_models})
        except Exception as exc:
            self._logger.error("Error retrieving base models: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_roots(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            roots = [recipe_scanner.recipes_dir] if recipe_scanner.recipes_dir else []
            return web.json_response({"success": True, "roots": roots})
        except Exception as exc:
            self._logger.error("Error retrieving recipe roots: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_folders(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            folders = await recipe_scanner.get_folders()
            return web.json_response({"success": True, "folders": folders})
        except Exception as exc:
            self._logger.error(
                "Error retrieving recipe folders: %s", exc, exc_info=True
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_folder_tree(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            folder_tree = await recipe_scanner.get_folder_tree()
            return web.json_response({"success": True, "tree": folder_tree})
        except Exception as exc:
            self._logger.error(
                "Error retrieving recipe folder tree: %s", exc, exc_info=True
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_unified_folder_tree(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            folder_tree = await recipe_scanner.get_folder_tree()
            return web.json_response({"success": True, "tree": folder_tree})
        except Exception as exc:
            self._logger.error(
                "Error retrieving unified recipe folder tree: %s", exc, exc_info=True
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_recipes_for_lora(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            lora_hash = request.query.get("hash")
            if not lora_hash:
                return web.json_response(
                    {"success": False, "error": "Lora hash is required"}, status=400
                )

            matching_recipes = await recipe_scanner.get_recipes_for_lora(lora_hash)
            return web.json_response({"success": True, "recipes": matching_recipes})
        except Exception as exc:
            self._logger.error("Error getting recipes for Lora: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_recipes_for_checkpoint(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            checkpoint_hash = request.query.get("hash")
            if not checkpoint_hash:
                return web.json_response(
                    {"success": False, "error": "Checkpoint hash is required"},
                    status=400,
                )

            matching_recipes = await recipe_scanner.get_recipes_for_checkpoint(
                checkpoint_hash
            )
            return web.json_response({"success": True, "recipes": matching_recipes})
        except Exception as exc:
            self._logger.error("Error getting recipes for checkpoint: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def scan_recipes(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            self._logger.info("Manually triggering recipe cache rebuild")
            await recipe_scanner.get_cached_data(force_refresh=True)
            return web.json_response(
                {"success": True, "message": "Recipe cache refreshed successfully"}
            )
        except Exception as exc:
            self._logger.error("Error refreshing recipe cache: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def find_duplicates(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            fingerprint_groups = await recipe_scanner.find_all_duplicate_recipes()
            url_groups = await recipe_scanner.find_duplicate_recipes_by_source()
            response_data = []

            for fingerprint, recipe_ids in fingerprint_groups.items():
                if len(recipe_ids) <= 1:
                    continue

                recipes = []
                for recipe_id in recipe_ids:
                    recipe = await recipe_scanner.get_recipe_by_id(recipe_id)
                    if recipe:
                        recipes.append(
                            {
                                "id": recipe.get("id"),
                                "title": recipe.get("title"),
                                "file_url": recipe.get("file_url")
                                or self._format_recipe_file_url(
                                    recipe.get("file_path", "")
                                ),
                                "modified": recipe.get("modified"),
                                "created_date": recipe.get("created_date"),
                                "lora_count": len(recipe.get("loras", [])),
                            }
                        )

                if len(recipes) >= 2:
                    recipes.sort(
                        key=lambda entry: entry.get("modified", 0), reverse=True
                    )
                    response_data.append(
                        {
                            "type": "fingerprint",
                            "fingerprint": fingerprint,
                            "count": len(recipes),
                            "recipes": recipes,
                        }
                    )

            for url, recipe_ids in url_groups.items():
                if len(recipe_ids) <= 1:
                    continue

                recipes = []
                for recipe_id in recipe_ids:
                    recipe = await recipe_scanner.get_recipe_by_id(recipe_id)
                    if recipe:
                        recipes.append(
                            {
                                "id": recipe.get("id"),
                                "title": recipe.get("title"),
                                "file_url": recipe.get("file_url")
                                or self._format_recipe_file_url(
                                    recipe.get("file_path", "")
                                ),
                                "modified": recipe.get("modified"),
                                "created_date": recipe.get("created_date"),
                                "lora_count": len(recipe.get("loras", [])),
                            }
                        )

                if len(recipes) >= 2:
                    recipes.sort(
                        key=lambda entry: entry.get("modified", 0), reverse=True
                    )
                    response_data.append(
                        {
                            "type": "source_path",
                            "fingerprint": url,
                            "count": len(recipes),
                            "recipes": recipes,
                        }
                    )

            response_data.sort(key=lambda entry: entry["count"], reverse=True)
            return web.json_response(
                {"success": True, "duplicate_groups": response_data}
            )
        except Exception as exc:
            self._logger.error(
                "Error finding duplicate recipes: %s", exc, exc_info=True
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_recipe_syntax(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            recipe_id = request.match_info["recipe_id"]
            try:
                syntax_parts = await recipe_scanner.get_recipe_syntax_tokens(recipe_id)
            except RecipeNotFoundError:
                return web.json_response({"error": "Recipe not found"}, status=404)

            if not syntax_parts:
                return web.json_response(
                    {"error": "No LoRAs found in this recipe"}, status=400
                )

            return web.json_response(
                {"success": True, "syntax": " ".join(syntax_parts)}
            )
        except Exception as exc:
            self._logger.error("Error generating recipe syntax: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)


class RecipeManagementHandler:
    """Handle create/update/delete style recipe operations."""

    def __init__(
        self,
        *,
        ensure_dependencies_ready: EnsureDependenciesCallable,
        recipe_scanner_getter: RecipeScannerGetter,
        logger: Logger,
        persistence_service: RecipePersistenceService,
        analysis_service: RecipeAnalysisService,
        downloader_factory,
        civitai_client_getter: CivitaiClientGetter,
        ws_manager=default_ws_manager,
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._logger = logger
        self._persistence_service = persistence_service
        self._analysis_service = analysis_service
        self._downloader_factory = downloader_factory
        self._civitai_client_getter = civitai_client_getter
        self._ws_manager = ws_manager
        self._import_semaphore = asyncio.Semaphore(2)

    async def save_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            reader = await request.multipart()
            payload = await self._parse_save_payload(reader)

            result = await self._persistence_service.save_recipe(
                recipe_scanner=recipe_scanner,
                image_bytes=payload["image_bytes"],
                image_base64=payload["image_base64"],
                name=payload["name"],
                tags=payload["tags"],
                metadata=payload["metadata"],
                extension=payload.get("extension"),
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error("Error saving recipe: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def repair_recipes(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                return web.json_response(
                    {"success": False, "error": "Recipe scanner unavailable"},
                    status=503,
                )

            # Check if already running
            if self._ws_manager.is_recipe_repair_running():
                return web.json_response(
                    {"success": False, "error": "Recipe repair already in progress"},
                    status=409,
                )

            recipe_scanner.reset_cancellation()

            async def progress_callback(data):
                await self._ws_manager.broadcast_recipe_repair_progress(data)

            # Run in background to avoid timeout
            async def run_repair():
                try:
                    await recipe_scanner.repair_all_recipes(
                        progress_callback=progress_callback
                    )
                except Exception as e:
                    self._logger.error(
                        f"Error in recipe repair task: {e}", exc_info=True
                    )
                    await self._ws_manager.broadcast_recipe_repair_progress(
                        {"status": "error", "error": str(e)}
                    )
                finally:
                    # Keep the final status for a while so the UI can see it
                    await asyncio.sleep(5)
                    # Don't cleanup if it was cancelled, let the UI see the cancelled state for a bit?
                    # Actually cleanup_recipe_repair_progress is fine as long as we waited enough.
                    self._ws_manager.cleanup_recipe_repair_progress()

            asyncio.create_task(run_repair())

            return web.json_response(
                {"success": True, "message": "Recipe repair started"}
            )
        except Exception as exc:
            self._logger.error("Error starting recipe repair: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def cancel_repair(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                return web.json_response(
                    {"success": False, "error": "Recipe scanner unavailable"},
                    status=503,
                )

            recipe_scanner.cancel_task()
            return web.json_response(
                {"success": True, "message": "Cancellation requested"}
            )
        except Exception as exc:
            self._logger.error("Error cancelling recipe repair: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def repair_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                return web.json_response(
                    {"success": False, "error": "Recipe scanner unavailable"},
                    status=503,
                )

            recipe_id = request.match_info["recipe_id"]
            result = await recipe_scanner.repair_recipe_by_id(recipe_id)
            return web.json_response(result)
        except RecipeNotFoundError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=404)
        except Exception as exc:
            self._logger.error("Error repairing single recipe: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_repair_progress(self, request: web.Request) -> web.Response:
        try:
            progress = self._ws_manager.get_recipe_repair_progress()
            if progress:
                return web.json_response({"success": True, "progress": progress})
            return web.json_response(
                {"success": False, "message": "No repair in progress"}, status=404
            )
        except Exception as exc:
            self._logger.error("Error getting repair progress: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def import_remote_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            # 1. Parse Parameters
            params = request.rel_url.query
            image_url = params.get("image_url")
            name = params.get("name")
            resources_raw = params.get("resources")

            if not image_url:
                raise RecipeValidationError("Missing required field: image_url")
            if not name:
                raise RecipeValidationError("Missing required field: name")
            if not resources_raw:
                raise RecipeValidationError("Missing required field: resources")

            checkpoint_entry, lora_entries = self._parse_resources_payload(
                resources_raw
            )
            gen_params_request = self._parse_gen_params(params.get("gen_params"))

            self._logger.info(
                "Remote recipe import received: url=%s, lora_count=%d",
                image_url,
                len(lora_entries),
            )
            self._logger.debug(
                "  gen_params_keys=%s, checkpoint_keys=%s",
                sorted(gen_params_request.keys()) if gen_params_request else [],
                sorted(checkpoint_entry.keys()) if isinstance(checkpoint_entry, dict) else [],
            )

            # Throttle concurrent imports to avoid starving ComfyUI's event loop
            async with self._import_semaphore:
                return await self._do_import_remote_recipe(
                    image_url=image_url,
                    name=name,
                    lora_entries=lora_entries,
                    checkpoint_entry=checkpoint_entry,
                    gen_params_request=gen_params_request,
                    tags=self._parse_tags(params.get("tags")),
                    base_model=params.get("base_model", "") or "",
                    source_path=params.get("source_path") or image_url,
                )
        except RecipeValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except RecipeDownloadError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error(
                "Error importing recipe from remote source: %s", exc, exc_info=True
            )
            return web.json_response({"error": str(exc)}, status=500)

    async def _do_import_remote_recipe(
        self,
        *,
        image_url: str,
        name: str,
        lora_entries: list,
        checkpoint_entry: dict,
        gen_params_request: dict,
        tags: list,
        base_model: str,
        source_path: str,
    ) -> web.Response:
        recipe_scanner = self._recipe_scanner_getter()
        if recipe_scanner is None:
            raise RuntimeError("Recipe scanner unavailable")

        metadata: Dict[str, Any] = {
            "base_model": base_model,
            "loras": lora_entries,
            "gen_params": gen_params_request or {},
            "source_path": source_path,
        }

        if checkpoint_entry:
            metadata["checkpoint"] = checkpoint_entry
            if not metadata["base_model"]:
                base_model_from_metadata = (
                    await self._resolve_base_model_from_checkpoint(checkpoint_entry)
                )
                if base_model_from_metadata:
                    metadata["base_model"] = base_model_from_metadata

        # Download image
        (
            image_bytes,
            extension,
            civitai_meta_raw,
            model_version_id,
        ) = await self._download_remote_media(image_url)

        # Extract embedded EXIF metadata (offloaded to thread pool in this call)
        embedded_gen_params = {}
        parsed_embedded = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=extension, delete=False
            ) as temp_img:
                temp_img.write(image_bytes)
                temp_img_path = temp_img.name

            try:
                raw_embedded = await asyncio.to_thread(
                    ExifUtils.extract_image_metadata, temp_img_path
                )
                if raw_embedded:
                    parser = (
                        self._analysis_service._recipe_parser_factory.create_parser(
                            raw_embedded
                        )
                    )
                    if parser:
                        parsed_embedded = await parser.parse_metadata(
                            raw_embedded, recipe_scanner=recipe_scanner
                        )
                        if parsed_embedded and "gen_params" in parsed_embedded:
                            embedded_gen_params = parsed_embedded["gen_params"]
                    else:
                        embedded_gen_params = {"raw_metadata": raw_embedded}
            finally:
                if os.path.exists(temp_img_path):
                    os.unlink(temp_img_path)
        except Exception as exc:
            self._logger.warning(
                "Failed to extract embedded metadata during import: %s", exc
            )

        # Fallback: if EXIF extraction yielded nothing, parse Civitai API meta directly
        # (same approach as analyze_remote_image — downloaded Civitai images often
        # have no embedded EXIF but the API meta contains resources/hashes)
        if parsed_embedded is None and civitai_meta_raw:
            civitai_inner_meta = civitai_meta_raw
            if isinstance(civitai_meta_raw, dict) and "meta" in civitai_meta_raw:
                civitai_inner_meta = civitai_meta_raw["meta"]
            if isinstance(civitai_inner_meta, dict):
                parser = self._analysis_service._recipe_parser_factory.create_parser(
                    civitai_inner_meta
                )
                if parser:
                    parsed_embedded = await parser.parse_metadata(
                        civitai_inner_meta, recipe_scanner=recipe_scanner
                    )
                    if parsed_embedded and "gen_params" in parsed_embedded:
                        embedded_gen_params = parsed_embedded["gen_params"]

        if embedded_gen_params:
            metadata["gen_params"] = embedded_gen_params

        if parsed_embedded:
            parsed_loras = parsed_embedded.get("loras")
            if parsed_loras and not metadata.get("loras"):
                metadata["loras"] = parsed_loras
            parsed_model = parsed_embedded.get("model")
            if parsed_model and not metadata.get("checkpoint"):
                metadata["checkpoint"] = parsed_model

        civitai_client = self._civitai_client_getter()
        await RecipeEnricher.enrich_recipe(
            recipe=metadata,
            civitai_client=civitai_client,
            request_params=gen_params_request,
            prefetched_civitai_meta_raw=civitai_meta_raw,
            prefetched_model_version_id=model_version_id,
        )

        result = await self._persistence_service.save_recipe(
            recipe_scanner=recipe_scanner,
            image_bytes=image_bytes,
            image_base64=None,
            name=name,
            tags=tags,
            metadata=metadata,
            extension=extension,
        )
        return web.json_response(result.payload, status=result.status)

    async def delete_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            recipe_id = request.match_info["recipe_id"]
            result = await self._persistence_service.delete_recipe(
                recipe_scanner=recipe_scanner, recipe_id=recipe_id
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeNotFoundError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        except Exception as exc:
            self._logger.error("Error deleting recipe: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def update_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            recipe_id = request.match_info["recipe_id"]
            data = await request.json()
            result = await self._persistence_service.update_recipe(
                recipe_scanner=recipe_scanner, recipe_id=recipe_id, updates=data
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except RecipeNotFoundError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        except Exception as exc:
            self._logger.error("Error updating recipe: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def move_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            data = await request.json()
            recipe_id = data.get("recipe_id")
            target_path = data.get("target_path")
            if not recipe_id or not target_path:
                return web.json_response(
                    {
                        "success": False,
                        "error": "recipe_id and target_path are required",
                    },
                    status=400,
                )

            result = await self._persistence_service.move_recipe(
                recipe_scanner=recipe_scanner,
                recipe_id=str(recipe_id),
                target_path=str(target_path),
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeValidationError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except RecipeNotFoundError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=404)
        except Exception as exc:
            self._logger.error("Error moving recipe: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def move_recipes_bulk(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            data = await request.json()
            recipe_ids = data.get("recipe_ids") or []
            target_path = data.get("target_path")
            if not recipe_ids or not target_path:
                return web.json_response(
                    {
                        "success": False,
                        "error": "recipe_ids and target_path are required",
                    },
                    status=400,
                )

            result = await self._persistence_service.move_recipes_bulk(
                recipe_scanner=recipe_scanner,
                recipe_ids=recipe_ids,
                target_path=str(target_path),
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeValidationError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except RecipeNotFoundError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=404)
        except Exception as exc:
            self._logger.error("Error moving recipes in bulk: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def reconnect_lora(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            data = await request.json()
            for field in ("recipe_id", "lora_index", "target_name"):
                if field not in data:
                    raise RecipeValidationError(f"Missing required field: {field}")

            result = await self._persistence_service.reconnect_lora(
                recipe_scanner=recipe_scanner,
                recipe_id=data["recipe_id"],
                lora_index=int(data["lora_index"]),
                target_name=data["target_name"],
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except RecipeNotFoundError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        except Exception as exc:
            self._logger.error("Error reconnecting LoRA: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def bulk_delete(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            data = await request.json()
            recipe_ids = data.get("recipe_ids", [])
            result = await self._persistence_service.bulk_delete(
                recipe_scanner=recipe_scanner, recipe_ids=recipe_ids
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeValidationError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except RecipeNotFoundError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=404)
        except Exception as exc:
            self._logger.error("Error performing bulk delete: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def save_recipe_from_widget(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            analysis = await self._analysis_service.analyze_widget_metadata(
                recipe_scanner=recipe_scanner
            )
            metadata = analysis.payload.get("metadata")
            image_bytes = analysis.payload.get("image_bytes")
            if not metadata or image_bytes is None:
                raise RecipeValidationError("Unable to extract metadata from widget")

            result = await self._persistence_service.save_recipe_from_widget(
                recipe_scanner=recipe_scanner,
                metadata=metadata,
                image_bytes=image_bytes,
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error(
                "Error saving recipe from widget: %s", exc, exc_info=True
            )
            return web.json_response({"error": str(exc)}, status=500)

    async def _parse_save_payload(self, reader) -> dict[str, Any]:
        image_bytes: Optional[bytes] = None
        image_base64: Optional[str] = None
        name: Optional[str] = None
        tags: list[str] = []
        metadata: Optional[Dict[str, Any]] = None
        extension: Optional[str] = None

        while True:
            field = await reader.next()
            if field is None:
                break
            if field.name == "image":
                image_chunks = bytearray()
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    image_chunks.extend(chunk)
                image_bytes = bytes(image_chunks)
            elif field.name == "image_base64":
                image_base64 = await field.text()
            elif field.name == "name":
                name = await field.text()
            elif field.name == "tags":
                tags_text = await field.text()
                try:
                    parsed_tags = json.loads(tags_text)
                    tags = parsed_tags if isinstance(parsed_tags, list) else []
                except Exception:
                    tags = []
            elif field.name == "metadata":
                metadata_text = await field.text()
                try:
                    metadata = json.loads(metadata_text)
                except Exception:
                    metadata = {}
            elif field.name == "extension":
                extension = await field.text()

        return {
            "image_bytes": image_bytes,
            "image_base64": image_base64,
            "name": name,
            "tags": tags,
            "metadata": metadata,
            "extension": extension,
        }

    def _parse_tags(self, tag_text: Optional[str]) -> list[str]:
        if not tag_text:
            return []
        return [tag.strip() for tag in tag_text.split(",") if tag.strip()]

    def _parse_gen_params(self, payload: Optional[str]) -> Optional[Dict[str, Any]]:
        if payload is None:
            return None
        if payload == "":
            return {}
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RecipeValidationError(f"Invalid gen_params payload: {exc}") from exc
        if parsed is None:
            return {}
        if not isinstance(parsed, dict):
            raise RecipeValidationError("gen_params payload must be an object")
        return parsed

    def _parse_resources_payload(
        self, payload_raw: str
    ) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError as exc:
            raise RecipeValidationError(f"Invalid resources payload: {exc}") from exc

        if not isinstance(payload, list):
            raise RecipeValidationError("Resources payload must be a list")

        checkpoint_entry: Optional[Dict[str, Any]] = None
        lora_entries: List[Dict[str, Any]] = []

        for resource in payload:
            if not isinstance(resource, dict):
                continue
            resource_type = str(resource.get("type") or "").lower()
            if resource_type == "checkpoint":
                checkpoint_entry = self._build_checkpoint_entry(resource)
            elif resource_type in {"lora", "lycoris"}:
                lora_entries.append(self._build_lora_entry(resource))

        return checkpoint_entry, lora_entries

    def _build_checkpoint_entry(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": resource.get("type", "checkpoint"),
            "modelId": self._safe_int(resource.get("modelId")),
            "modelVersionId": self._safe_int(resource.get("modelVersionId")),
            "modelName": resource.get("modelName", ""),
            "modelVersionName": resource.get("modelVersionName", ""),
        }

    def _build_lora_entry(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        weight_raw = resource.get("weight", 1.0)
        try:
            weight = float(weight_raw)
        except (TypeError, ValueError):
            weight = 1.0
        return {
            "file_name": resource.get("modelName", ""),
            "weight": weight,
            "id": self._safe_int(resource.get("modelVersionId")),
            "name": resource.get("modelName", ""),
            "version": resource.get("modelVersionName", ""),
            "isDeleted": False,
            "exclude": False,
        }

    async def _download_remote_media(self, image_url: str) -> tuple[bytes, str, Any, Any]:
        civitai_client = self._civitai_client_getter()
        downloader = await self._downloader_factory()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_path = temp_file.name
            download_url = image_url
            image_info = None
            civitai_image_id = extract_civitai_image_id(image_url)
            if civitai_image_id:
                if civitai_client is None:
                    raise RecipeDownloadError(
                        "Civitai client unavailable for image download"
                    )
                image_info = await civitai_client.get_image_info(
                    civitai_image_id, source_url=image_url
                )
                if not image_info:
                    raise RecipeDownloadError(
                        "Failed to fetch image information from Civitai"
                    )

                media_url = image_info.get("url")
                if not media_url:
                    raise RecipeDownloadError("No image URL found in Civitai response")

                # Use optimized preview URLs if possible
                media_type = image_info.get("type")
                rewritten_url, _ = rewrite_preview_url(media_url, media_type=media_type)
                if rewritten_url:
                    download_url = rewritten_url
                else:
                    download_url = media_url

            success, result = await downloader.download_file(
                download_url, temp_path, use_auth=False
            )
            if not success:
                raise RecipeDownloadError(f"Failed to download image: {result}")

            # Extract extension from URL
            url_path = download_url.split("?")[0].split("#")[0]
            extension = os.path.splitext(url_path)[1].lower()
            if not extension:
                extension = ".webp"  # Default to webp if unknown

            with open(temp_path, "rb") as file_obj:
                model_ver_id = None
                if civitai_image_id and image_info:
                    model_ver_id = image_info.get("modelVersionId")
                    if not model_ver_id:
                        ids = image_info.get("modelVersionIds")
                        if isinstance(ids, list) and ids:
                            model_ver_id = ids[0]
                return (
                    file_obj.read(),
                    extension,
                    image_info.get("meta") if civitai_image_id and image_info else None,
                    model_ver_id,
                )
        except RecipeDownloadError:
            raise
        except RecipeValidationError:
            raise
        except Exception as exc:  # pragma: no cover - defensive guard
            raise RecipeValidationError(f"Unable to download image: {exc}") from exc
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    async def _resolve_base_model_from_checkpoint(
        self, checkpoint_entry: Dict[str, Any]
    ) -> str:
        version_id = self._safe_int(checkpoint_entry.get("modelVersionId"))

        if not version_id:
            return ""

        try:
            provider = await get_default_metadata_provider()
            if not provider:
                return ""

            version_info = await provider.get_model_version_info(version_id)
            if isinstance(version_info, tuple):
                version_info = version_info[0]

            if isinstance(version_info, dict):
                base_model = version_info.get("baseModel") or ""
                return str(base_model) if base_model is not None else ""
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.warning(
                "Failed to resolve base model from checkpoint metadata: %s", exc
            )

        return ""

    async def check_image_exists(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            image_ids_raw = request.query.get("image_ids", "")
            if not image_ids_raw:
                return web.json_response({"success": True, "results": {}})

            requested_ids = set()
            for raw in image_ids_raw.split(","):
                stripped = raw.strip()
                if stripped and stripped.isdigit():
                    requested_ids.add(stripped)

            if not requested_ids:
                return web.json_response({"success": True, "results": {}})

            cache = await recipe_scanner.get_cached_data()

            # Build lookup: image_id -> recipe_id from stored source_path
            image_to_recipe = {}
            for recipe in getattr(cache, "raw_data", []):
                source = recipe.get("source_path")
                if not source:
                    continue
                image_id = extract_civitai_image_id(source)
                if image_id and image_id not in image_to_recipe:
                    image_to_recipe[image_id] = recipe.get("id")

            results = {}
            for img_id in requested_ids:
                recipe_id = image_to_recipe.get(img_id)
                results[img_id] = {
                    "in_library": recipe_id is not None,
                    "recipe_id": recipe_id,
                }

            return web.json_response({"success": True, "results": results})
        except Exception as exc:
            self._logger.error(
                "Error checking image existence: %s", exc, exc_info=True
            )
            return web.json_response({"error": str(exc)}, status=500)

    async def import_from_url(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            image_url = request.query.get("image_url")
            if not image_url:
                raise RecipeValidationError("Missing required field: image_url")

            image_id = extract_civitai_image_id(image_url)
            if not image_id:
                raise RecipeValidationError(
                    "Could not extract Civitai image ID from URL"
                )

            # Check for duplicate (fast, before acquiring semaphore)
            cache = await recipe_scanner.get_cached_data()
            for recipe in getattr(cache, "raw_data", []):
                source = recipe.get("source_path")
                if source:
                    existing_id = extract_civitai_image_id(source)
                    if existing_id == image_id:
                        return web.json_response({
                            "success": True,
                            "recipe_id": recipe.get("id"),
                            "name": recipe.get("title", ""),
                            "already_exists": True,
                        })

            async with self._import_semaphore:
                return await self._do_import_from_url(image_url, recipe_scanner)
        except RecipeValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except RecipeDownloadError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error(
                "Error importing recipe from URL: %s", exc, exc_info=True
            )
            return web.json_response({"error": str(exc)}, status=500)

    async def _do_import_from_url(
        self,
        image_url: str,
        recipe_scanner: Any,
    ) -> web.Response:
        image_id = extract_civitai_image_id(image_url)
        if not image_id:
            raise RecipeValidationError(
                "Could not extract Civitai image ID from URL"
            )

        image_bytes, extension, civitai_meta_raw, model_version_id = (
            await self._download_remote_media(image_url)
        )

        # Extract embedded EXIF metadata
        embedded_gen_params = {}
        parsed_embedded = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=extension, delete=False
            ) as temp_img:
                temp_img.write(image_bytes)
                temp_img_path = temp_img.name

            try:
                raw_embedded = await asyncio.to_thread(
                    ExifUtils.extract_image_metadata, temp_img_path
                )
                if raw_embedded:
                    parser = (
                        self._analysis_service._recipe_parser_factory.create_parser(
                            raw_embedded
                        )
                    )
                    if parser:
                        parsed_embedded = await parser.parse_metadata(
                            raw_embedded, recipe_scanner=recipe_scanner
                        )
                        if parsed_embedded and "gen_params" in parsed_embedded:
                            embedded_gen_params = parsed_embedded["gen_params"]
            finally:
                if os.path.exists(temp_img_path):
                    os.unlink(temp_img_path)
        except Exception as exc:
            self._logger.warning(
                "Failed to extract embedded metadata: %s", exc
            )

        if parsed_embedded is None and civitai_meta_raw:
            civitai_inner_meta = civitai_meta_raw
            if isinstance(civitai_meta_raw, dict) and "meta" in civitai_meta_raw:
                civitai_inner_meta = civitai_meta_raw["meta"]
            if isinstance(civitai_inner_meta, dict):
                parser = self._analysis_service._recipe_parser_factory.create_parser(
                    civitai_inner_meta
                )
                if parser:
                    parsed_embedded = await parser.parse_metadata(
                        civitai_inner_meta, recipe_scanner=recipe_scanner
                    )
                    if parsed_embedded and "gen_params" in parsed_embedded:
                        embedded_gen_params = parsed_embedded["gen_params"]

        metadata: Dict[str, Any] = {
            "base_model": "",
            "loras": [],
            "gen_params": embedded_gen_params or {},
            "source_path": image_url,
        }

        if parsed_embedded:
            parsed_loras = parsed_embedded.get("loras")
            if parsed_loras and not metadata.get("loras"):
                metadata["loras"] = parsed_loras
            parsed_model = parsed_embedded.get("model")
            if parsed_model and not metadata.get("checkpoint"):
                metadata["checkpoint"] = parsed_model

        civitai_client = self._civitai_client_getter()
        await RecipeEnricher.enrich_recipe(
            recipe=metadata,
            civitai_client=civitai_client,
            request_params={},
            prefetched_civitai_meta_raw=civitai_meta_raw,
            prefetched_model_version_id=model_version_id,
        )

        prompt = (
            metadata.get("gen_params", {}).get("prompt")
            or metadata.get("gen_params", {}).get("positivePrompt")
            or ""
        )
        if prompt:
            name = " ".join(str(prompt).split()[:10])
        else:
            name = f"Civitai Image {image_id}"

        result = await self._persistence_service.save_recipe(
            recipe_scanner=recipe_scanner,
            image_bytes=image_bytes,
            image_base64=None,
            name=name,
            tags=[],
            metadata=metadata,
            extension=extension,
        )
        return web.json_response(result.payload, status=result.status)


class RecipeAnalysisHandler:
    """Analyze images to extract recipe metadata."""

    def __init__(
        self,
        *,
        ensure_dependencies_ready: EnsureDependenciesCallable,
        recipe_scanner_getter: RecipeScannerGetter,
        civitai_client_getter: CivitaiClientGetter,
        logger: Logger,
        analysis_service: RecipeAnalysisService,
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._civitai_client_getter = civitai_client_getter
        self._logger = logger
        self._analysis_service = analysis_service

    async def analyze_uploaded_image(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            civitai_client = self._civitai_client_getter()
            if recipe_scanner is None or civitai_client is None:
                raise RuntimeError("Required services unavailable")

            content_type = request.headers.get("Content-Type", "")
            if "multipart/form-data" in content_type:
                reader = await request.multipart()
                field = await reader.next()
                if field is None or field.name != "image":
                    raise RecipeValidationError("No image field found")
                image_chunks = bytearray()
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    image_chunks.extend(chunk)
                result = await self._analysis_service.analyze_uploaded_image(
                    image_bytes=bytes(image_chunks),
                    recipe_scanner=recipe_scanner,
                )
                return web.json_response(result.payload, status=result.status)

            if "application/json" in content_type:
                data = await request.json()
                result = await self._analysis_service.analyze_remote_image(
                    url=data.get("url"),
                    recipe_scanner=recipe_scanner,
                    civitai_client=civitai_client,
                )
                return web.json_response(result.payload, status=result.status)

            raise RecipeValidationError("Unsupported content type")
        except RecipeValidationError as exc:
            return web.json_response({"error": str(exc), "loras": []}, status=400)
        except RecipeDownloadError as exc:
            return web.json_response({"error": str(exc), "loras": []}, status=400)
        except RecipeNotFoundError as exc:
            return web.json_response({"error": str(exc), "loras": []}, status=404)
        except Exception as exc:
            self._logger.error("Error analyzing recipe image: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc), "loras": []}, status=500)

    async def analyze_local_image(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            data = await request.json()
            result = await self._analysis_service.analyze_local_image(
                file_path=data.get("path"),
                recipe_scanner=recipe_scanner,
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeValidationError as exc:
            return web.json_response({"error": str(exc), "loras": []}, status=400)
        except RecipeNotFoundError as exc:
            return web.json_response({"error": str(exc), "loras": []}, status=404)
        except Exception as exc:
            self._logger.error("Error analyzing local image: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc), "loras": []}, status=500)


class RecipeSharingHandler:
    """Serve endpoints related to recipe sharing."""

    def __init__(
        self,
        *,
        ensure_dependencies_ready: EnsureDependenciesCallable,
        recipe_scanner_getter: RecipeScannerGetter,
        logger: Logger,
        sharing_service: RecipeSharingService,
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._logger = logger
        self._sharing_service = sharing_service

    async def share_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            recipe_id = request.match_info["recipe_id"]
            result = await self._sharing_service.share_recipe(
                recipe_scanner=recipe_scanner, recipe_id=recipe_id
            )
            return web.json_response(result.payload, status=result.status)
        except RecipeNotFoundError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        except Exception as exc:
            self._logger.error("Error sharing recipe: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def download_shared_recipe(self, request: web.Request) -> web.StreamResponse:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            recipe_id = request.match_info["recipe_id"]
            download_info = await self._sharing_service.prepare_download(
                recipe_scanner=recipe_scanner, recipe_id=recipe_id
            )
            return web.FileResponse(
                download_info.file_path,
                headers={
                    "Content-Disposition": f'attachment; filename="{download_info.download_filename}"'
                },
            )
        except RecipeNotFoundError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        except Exception as exc:
            self._logger.error(
                "Error downloading shared recipe: %s", exc, exc_info=True
            )
            return web.json_response({"error": str(exc)}, status=500)


class BatchImportHandler:
    """Handle batch import operations for recipes."""

    def __init__(
        self,
        *,
        ensure_dependencies_ready: EnsureDependenciesCallable,
        recipe_scanner_getter: RecipeScannerGetter,
        civitai_client_getter: CivitaiClientGetter,
        logger: Logger,
        batch_import_service: BatchImportService,
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._civitai_client_getter = civitai_client_getter
        self._logger = logger
        self._batch_import_service = batch_import_service

    async def start_batch_import(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()

            if self._batch_import_service.is_import_running():
                return web.json_response(
                    {"success": False, "error": "Batch import already in progress"},
                    status=409,
                )

            data = await request.json()
            items = data.get("items", [])
            tags = data.get("tags", [])
            skip_no_metadata = data.get("skip_no_metadata", False)

            if not items:
                return web.json_response(
                    {"success": False, "error": "No items provided"},
                    status=400,
                )

            for item in items:
                if not item.get("source"):
                    return web.json_response(
                        {
                            "success": False,
                            "error": "Each item must have a 'source' field",
                        },
                        status=400,
                    )

            operation_id = await self._batch_import_service.start_batch_import(
                recipe_scanner_getter=self._recipe_scanner_getter,
                civitai_client_getter=self._civitai_client_getter,
                items=items,
                tags=tags,
                skip_no_metadata=skip_no_metadata,
            )

            return web.json_response(
                {
                    "success": True,
                    "operation_id": operation_id,
                }
            )
        except RecipeValidationError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error("Error starting batch import: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def start_directory_import(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()

            if self._batch_import_service.is_import_running():
                return web.json_response(
                    {"success": False, "error": "Batch import already in progress"},
                    status=409,
                )

            data = await request.json()
            directory = data.get("directory")
            recursive = data.get("recursive", True)
            tags = data.get("tags", [])
            skip_no_metadata = data.get("skip_no_metadata", True)

            if not directory:
                return web.json_response(
                    {"success": False, "error": "Directory path is required"},
                    status=400,
                )

            operation_id = await self._batch_import_service.start_directory_import(
                recipe_scanner_getter=self._recipe_scanner_getter,
                civitai_client_getter=self._civitai_client_getter,
                directory=directory,
                recursive=recursive,
                tags=tags,
                skip_no_metadata=skip_no_metadata,
            )

            return web.json_response(
                {
                    "success": True,
                    "operation_id": operation_id,
                }
            )
        except RecipeValidationError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error(
                "Error starting directory import: %s", exc, exc_info=True
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_batch_import_progress(self, request: web.Request) -> web.Response:
        try:
            operation_id = request.query.get("operation_id")
            if not operation_id:
                return web.json_response(
                    {"success": False, "error": "operation_id is required"},
                    status=400,
                )

            progress = self._batch_import_service.get_progress(operation_id)
            if not progress:
                return web.json_response(
                    {"success": False, "error": "Operation not found"},
                    status=404,
                )

            return web.json_response(
                {
                    "success": True,
                    "progress": progress.to_dict(),
                }
            )
        except Exception as exc:
            self._logger.error(
                "Error getting batch import progress: %s", exc, exc_info=True
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def cancel_batch_import(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            operation_id = data.get("operation_id")

            if not operation_id:
                return web.json_response(
                    {"success": False, "error": "operation_id is required"},
                    status=400,
                )

            cancelled = self._batch_import_service.cancel_import(operation_id)
            if not cancelled:
                return web.json_response(
                    {
                        "success": False,
                        "error": "Operation not found or already completed",
                    },
                    status=404,
                )

            return web.json_response(
                {"success": True, "message": "Cancellation requested"}
            )
        except Exception as exc:
            self._logger.error("Error cancelling batch import: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def browse_directory(self, request: web.Request) -> web.Response:
        """Browse a directory and return its contents (subdirectories and files)."""
        try:
            data = await request.json()
            directory_path = data.get("path", "")

            if not directory_path:
                return web.json_response(
                    {"success": False, "error": "Directory path is required"},
                    status=400,
                )

            # Normalize the path
            path = Path(directory_path).expanduser().resolve()

            # Security check: ensure path is within allowed directories
            # Allow common image/model directories
            allowed_roots = [
                Path.home(),
                Path("/"),  # Allow browsing from root for flexibility
            ]

            # Check if path is within any allowed root
            is_allowed = False
            for root in allowed_roots:
                try:
                    path.relative_to(root)
                    is_allowed = True
                    break
                except ValueError:
                    continue

            if not is_allowed:
                return web.json_response(
                    {"success": False, "error": "Access denied to this directory"},
                    status=403,
                )

            if not path.exists():
                return web.json_response(
                    {"success": False, "error": "Directory does not exist"},
                    status=404,
                )

            if not path.is_dir():
                return web.json_response(
                    {"success": False, "error": "Path is not a directory"},
                    status=400,
                )

            # List directory contents
            directories = []
            image_files = []

            image_extensions = {
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".webp",
                ".bmp",
                ".tiff",
                ".tif",
            }

            try:
                for item in path.iterdir():
                    try:
                        if item.is_dir():
                            # Skip hidden directories and common system folders
                            if not item.name.startswith(".") and item.name not in [
                                "__pycache__",
                                "node_modules",
                            ]:
                                directories.append(
                                    {
                                        "name": item.name,
                                        "path": str(item),
                                        "is_parent": False,
                                    }
                                )
                        elif item.is_file() and item.suffix.lower() in image_extensions:
                            image_files.append(
                                {
                                    "name": item.name,
                                    "path": str(item),
                                    "size": item.stat().st_size,
                                }
                            )
                    except (PermissionError, OSError):
                        # Skip files/directories we can't access
                        continue

                # Sort directories and files alphabetically
                directories.sort(key=lambda x: x["name"].lower())
                image_files.sort(key=lambda x: x["name"].lower())

                # Add parent directory if not at root
                parent_path = path.parent
                show_parent = str(path) != str(path.root)

                return web.json_response(
                    {
                        "success": True,
                        "current_path": str(path),
                        "parent_path": str(parent_path) if show_parent else None,
                        "directories": directories,
                        "image_files": image_files,
                        "image_count": len(image_files),
                        "directory_count": len(directories),
                    }
                )

            except PermissionError:
                return web.json_response(
                    {"success": False, "error": "Permission denied"},
                    status=403,
                )
            except OSError as exc:
                return web.json_response(
                    {"success": False, "error": f"Error reading directory: {str(exc)}"},
                    status=500,
                )

        except json.JSONDecodeError:
            return web.json_response(
                {"success": False, "error": "Invalid JSON"},
                status=400,
            )
        except Exception as exc:
            self._logger.error("Error browsing directory: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)
