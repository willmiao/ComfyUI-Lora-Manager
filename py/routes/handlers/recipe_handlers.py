"""Dedicated handler objects for recipe-related routes."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
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
from ...utils.civitai_utils import rewrite_preview_url
from ...utils.exif_utils import ExifUtils
from ...recipes.merger import GenParamsMerger

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

    def to_route_mapping(self) -> Mapping[str, Callable[[web.Request], Awaitable[web.StreamResponse]]]:
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
            "scan_recipes": self.query.scan_recipes,
            "move_recipe": self.management.move_recipe,
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
                "lora_name": request.query.get("search_lora_name", "true").lower() == "true",
                "lora_model": request.query.get("search_lora_model", "true").lower() == "true",
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

            result = await recipe_scanner.get_paginated_data(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                search=search,
                filters=filters,
                search_options=search_options,
                lora_hash=lora_hash,
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
            self._logger.error("Error retrieving recipe details: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    def format_recipe_file_url(self, file_path: str) -> str:
        try:
            normalized_path = os.path.normpath(file_path)
            static_url = config.get_preview_static_url(normalized_path)
            if static_url:
                return static_url
        except Exception as exc:  # pragma: no cover - logging path
            self._logger.error("Error formatting recipe file URL: %s", exc, exc_info=True)
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

            sorted_tags = [{"tag": tag, "count": count} for tag, count in tag_counts.items()]
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

            cache = await recipe_scanner.get_cached_data()

            base_model_counts: Dict[str, int] = {}
            for recipe in getattr(cache, "raw_data", []):
                base_model = recipe.get("base_model")
                if base_model:
                    base_model_counts[base_model] = base_model_counts.get(base_model, 0) + 1

            sorted_models = [{"name": model, "count": count} for model, count in base_model_counts.items()]
            sorted_models.sort(key=lambda entry: entry["count"], reverse=True)
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
            self._logger.error("Error retrieving recipe folders: %s", exc, exc_info=True)
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
            self._logger.error("Error retrieving recipe folder tree: %s", exc, exc_info=True)
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
            self._logger.error("Error retrieving unified recipe folder tree: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_recipes_for_lora(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            lora_hash = request.query.get("hash")
            if not lora_hash:
                return web.json_response({"success": False, "error": "Lora hash is required"}, status=400)

            matching_recipes = await recipe_scanner.get_recipes_for_lora(lora_hash)
            return web.json_response({"success": True, "recipes": matching_recipes})
        except Exception as exc:
            self._logger.error("Error getting recipes for Lora: %s", exc)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def scan_recipes(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            self._logger.info("Manually triggering recipe cache rebuild")
            await recipe_scanner.get_cached_data(force_refresh=True)
            return web.json_response({"success": True, "message": "Recipe cache refreshed successfully"})
        except Exception as exc:
            self._logger.error("Error refreshing recipe cache: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def find_duplicates(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            duplicate_groups = await recipe_scanner.find_all_duplicate_recipes()
            response_data = []

            for fingerprint, recipe_ids in duplicate_groups.items():
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
                                or self._format_recipe_file_url(recipe.get("file_path", "")),
                                "modified": recipe.get("modified"),
                                "created_date": recipe.get("created_date"),
                                "lora_count": len(recipe.get("loras", [])),
                            }
                        )

                if len(recipes) >= 2:
                    recipes.sort(key=lambda entry: entry.get("modified", 0), reverse=True)
                    response_data.append(
                        {
                            "fingerprint": fingerprint,
                            "count": len(recipes),
                            "recipes": recipes,
                        }
                    )

            response_data.sort(key=lambda entry: entry["count"], reverse=True)
            return web.json_response({"success": True, "duplicate_groups": response_data})
        except Exception as exc:
            self._logger.error("Error finding duplicate recipes: %s", exc, exc_info=True)
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
                return web.json_response({"error": "No LoRAs found in this recipe"}, status=400)

            return web.json_response({"success": True, "syntax": " ".join(syntax_parts)})
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
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._logger = logger
        self._persistence_service = persistence_service
        self._analysis_service = analysis_service
        self._downloader_factory = downloader_factory
        self._civitai_client_getter = civitai_client_getter

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

    async def import_remote_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

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

            checkpoint_entry, lora_entries = self._parse_resources_payload(resources_raw)
            gen_params = self._parse_gen_params(params.get("gen_params"))
            metadata: Dict[str, Any] = {
                "base_model": params.get("base_model", "") or "",
                "loras": lora_entries,
            }
            source_path = params.get("source_path")
            if source_path:
                metadata["source_path"] = source_path
            if gen_params is not None:
                metadata["gen_params"] = gen_params
            if checkpoint_entry:
                metadata["checkpoint"] = checkpoint_entry
                gen_params_ref = metadata.setdefault("gen_params", {})
                if "checkpoint" not in gen_params_ref:
                    gen_params_ref["checkpoint"] = checkpoint_entry
                base_model_from_metadata = await self._resolve_base_model_from_checkpoint(checkpoint_entry)
                if base_model_from_metadata:
                    metadata["base_model"] = base_model_from_metadata

            tags = self._parse_tags(params.get("tags"))
            image_bytes, extension, civitai_meta = await self._download_remote_media(image_url)

            # Extract embedded metadata from the downloaded image
            embedded_metadata = None
            try:
                with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp_img:
                    temp_img.write(image_bytes)
                    temp_img_path = temp_img.name
                
                try:
                    raw_embedded = ExifUtils.extract_image_metadata(temp_img_path)
                    if raw_embedded:
                        # Try to parse it using standard parsers if it looks like a recipe
                        parser = self._analysis_service._recipe_parser_factory.create_parser(raw_embedded)
                        if parser:
                            parsed_embedded = await parser.parse_metadata(raw_embedded, recipe_scanner=recipe_scanner)
                            embedded_metadata = parsed_embedded
                        else:
                            # Fallback to raw string if no parser matches (might be simple params)
                            embedded_metadata = {"gen_params": {"raw_metadata": raw_embedded}}
                finally:
                    if os.path.exists(temp_img_path):
                        os.unlink(temp_img_path)
            except Exception as exc:
                self._logger.warning("Failed to extract embedded metadata during import: %s", exc)

            # Merge gen_params from all sources
            merged_gen_params = GenParamsMerger.merge(
                request_params=gen_params,
                civitai_meta=civitai_meta,
                embedded_metadata=embedded_metadata
            )

            if merged_gen_params:
                metadata["gen_params"] = merged_gen_params

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
        except RecipeValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except RecipeDownloadError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._logger.error("Error importing recipe from remote source: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

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
                    {"success": False, "error": "recipe_id and target_path are required"}, status=400
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
                    {"success": False, "error": "recipe_ids and target_path are required"}, status=400
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
            self._logger.error("Error saving recipe from widget: %s", exc, exc_info=True)
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

    def _parse_resources_payload(self, payload_raw: str) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
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

    async def _download_remote_media(self, image_url: str) -> tuple[bytes, str]:
        civitai_client = self._civitai_client_getter()
        downloader = await self._downloader_factory()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_path = temp_file.name
            download_url = image_url
            civitai_match = re.match(r"https://civitai\.com/images/(\d+)", image_url)
            if civitai_match:
                if civitai_client is None:
                    raise RecipeDownloadError("Civitai client unavailable for image download")
                image_info = await civitai_client.get_image_info(civitai_match.group(1))
                if not image_info:
                    raise RecipeDownloadError("Failed to fetch image information from Civitai")
                
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

            success, result = await downloader.download_file(download_url, temp_path, use_auth=False)
            if not success:
                raise RecipeDownloadError(f"Failed to download image: {result}")
            
            # Extract extension from URL
            url_path = download_url.split('?')[0].split('#')[0]
            extension = os.path.splitext(url_path)[1].lower()
            if not extension:
                extension = ".webp" # Default to webp if unknown

            with open(temp_path, "rb") as file_obj:
                return file_obj.read(), extension, image_info.get("meta") if civitai_match and image_info else None
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

    async def _resolve_base_model_from_checkpoint(self, checkpoint_entry: Dict[str, Any]) -> str:
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
            self._logger.warning("Failed to resolve base model from checkpoint metadata: %s", exc)

        return ""


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
            self._logger.error("Error downloading shared recipe: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)
