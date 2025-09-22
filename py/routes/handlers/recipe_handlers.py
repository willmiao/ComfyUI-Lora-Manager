"""Dedicated handler objects for recipe-related routes."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional

import numpy as np
from aiohttp import web
from PIL import Image

from ...config import config
from ...recipes import RecipeParserFactory
from ...services.downloader import get_downloader
from ...services.server_i18n import server_i18n as default_server_i18n
from ...services.settings_manager import SettingsManager
from ...utils.constants import CARD_PREVIEW_WIDTH
from ...utils.exif_utils import ExifUtils

# Check if running in standalone mode
standalone_mode = os.environ.get("HF_HUB_DISABLE_TELEMETRY", "0") == "0"

if not standalone_mode:
    from ...metadata_collector import get_metadata
    from ...metadata_collector.metadata_processor import MetadataProcessor
    from ...metadata_collector.metadata_registry import MetadataRegistry
else:  # pragma: no cover - optional dependency path
    get_metadata = None  # type: ignore[assignment]
    MetadataProcessor = None  # type: ignore[assignment]
    MetadataRegistry = None  # type: ignore[assignment]

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
            "analyze_uploaded_image": self.analysis.analyze_uploaded_image,
            "analyze_local_image": self.analysis.analyze_local_image,
            "save_recipe": self.management.save_recipe,
            "delete_recipe": self.management.delete_recipe,
            "get_top_tags": self.query.get_top_tags,
            "get_base_models": self.query.get_base_models,
            "share_recipe": self.sharing.share_recipe,
            "download_shared_recipe": self.sharing.download_shared_recipe,
            "get_recipe_syntax": self.query.get_recipe_syntax,
            "update_recipe": self.management.update_recipe,
            "reconnect_lora": self.management.reconnect_lora,
            "find_duplicates": self.query.find_duplicates,
            "bulk_delete": self.management.bulk_delete,
            "save_recipe_from_widget": self.management.save_recipe_from_widget,
            "get_recipes_for_lora": self.query.get_recipes_for_lora,
            "scan_recipes": self.query.scan_recipes,
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

            search_options = {
                "title": request.query.get("search_title", "true").lower() == "true",
                "tags": request.query.get("search_tags", "true").lower() == "true",
                "lora_name": request.query.get("search_lora_name", "true").lower() == "true",
                "lora_model": request.query.get("search_lora_model", "true").lower() == "true",
            }

            filters: Dict[str, list[str]] = {}
            base_models = request.query.get("base_models")
            if base_models:
                filters["base_model"] = base_models.split(",")

            tags = request.query.get("tags")
            if tags:
                filters["tags"] = tags.split(",")

            lora_hash = request.query.get("lora_hash")

            result = await recipe_scanner.get_paginated_data(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                search=search,
                filters=filters,
                search_options=search_options,
                lora_hash=lora_hash,
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
            recipes_dir = os.path.join(config.loras_roots[0], "recipes").replace(os.sep, "/")
            normalized_path = file_path.replace(os.sep, "/")
            if normalized_path.startswith(recipes_dir):
                relative_path = os.path.relpath(file_path, config.loras_roots[0]).replace(os.sep, "/")
                return f"/loras_static/root1/preview/{relative_path}"

            file_name = os.path.basename(file_path)
            return f"/loras_static/root1/preview/recipes/{file_name}"
        except Exception as exc:  # pragma: no cover - logging path
            self._logger.error("Error formatting recipe file URL: %s", exc, exc_info=True)
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

    async def get_recipes_for_lora(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            lora_hash = request.query.get("hash")
            if not lora_hash:
                return web.json_response({"success": False, "error": "Lora hash is required"}, status=400)

            cache = await recipe_scanner.get_cached_data()
            matching_recipes = []
            for recipe in getattr(cache, "raw_data", []):
                for lora in recipe.get("loras", []):
                    if lora.get("hash", "").lower() == lora_hash.lower():
                        matching_recipes.append(recipe)
                        break

            lora_scanner = getattr(recipe_scanner, "_lora_scanner", None)
            for recipe in matching_recipes:
                for lora in recipe.get("loras", []):
                    hash_value = (lora.get("hash") or "").lower()
                    if hash_value and lora_scanner is not None:
                        lora["inLibrary"] = lora_scanner.has_hash(hash_value)
                        lora["preview_url"] = lora_scanner.get_preview_url_by_hash(hash_value)
                        lora["localPath"] = lora_scanner.get_path_by_hash(hash_value)
                if recipe.get("file_path"):
                    recipe["file_url"] = self._format_recipe_file_url(recipe["file_path"])
                else:
                    recipe["file_url"] = "/loras_static/images/no-preview.png"

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
            cache = await recipe_scanner.get_cached_data()
            recipe = next(
                (r for r in getattr(cache, "raw_data", []) if str(r.get("id", "")) == recipe_id),
                None,
            )
            if not recipe:
                return web.json_response({"error": "Recipe not found"}, status=404)

            loras = recipe.get("loras", [])
            if not loras:
                return web.json_response({"error": "No LoRAs found in this recipe"}, status=400)

            lora_scanner = getattr(recipe_scanner, "_lora_scanner", None)
            hash_index = getattr(lora_scanner, "_hash_index", None)

            lora_syntax_parts = []
            for lora in loras:
                if lora.get("isDeleted", False):
                    continue
                hash_value = (lora.get("hash") or "").lower()
                if not hash_value or lora_scanner is None or not lora_scanner.has_hash(hash_value):
                    continue

                file_name = None
                if hash_value and hash_index is not None and hasattr(hash_index, "_hash_to_path"):
                    file_path = hash_index._hash_to_path.get(hash_value)
                    if file_path:
                        file_name = os.path.splitext(os.path.basename(file_path))[0]

                if not file_name and lora.get("modelVersionId") and lora_scanner is not None:
                    all_loras = await lora_scanner.get_cached_data()
                    for cached_lora in getattr(all_loras, "raw_data", []):
                        civitai_info = cached_lora.get("civitai")
                        if civitai_info and civitai_info.get("id") == lora.get("modelVersionId"):
                            file_name = os.path.splitext(os.path.basename(cached_lora["path"]))[0]
                            break

                if not file_name:
                    file_name = lora.get("file_name", "unknown-lora")

                strength = lora.get("strength", 1.0)
                lora_syntax_parts.append(f"<lora:{file_name}:{strength}>")

            return web.json_response({"success": True, "syntax": " ".join(lora_syntax_parts)})
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
        exif_utils=ExifUtils,
        card_preview_width: int = CARD_PREVIEW_WIDTH,
        metadata_collector: Optional[Callable[[], Any]] = get_metadata,
        metadata_processor_cls: Optional[type] = MetadataProcessor,
        metadata_registry_cls: Optional[type] = MetadataRegistry,
        standalone_mode: bool = standalone_mode,
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._logger = logger
        self._exif_utils = exif_utils
        self._card_preview_width = card_preview_width
        self._metadata_collector = metadata_collector
        self._metadata_processor_cls = metadata_processor_cls
        self._metadata_registry_cls = metadata_registry_cls
        self._standalone_mode = standalone_mode

    async def save_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            reader = await request.multipart()

            image: Optional[bytes] = None
            image_base64: Optional[str] = None
            name: Optional[str] = None
            tags: list[str] = []
            metadata: Dict[str, Any] | None = None

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
                    image = bytes(image_chunks)
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

            missing_fields = []
            if not name:
                missing_fields.append("name")
            if not metadata:
                missing_fields.append("metadata")
            if missing_fields:
                return web.json_response(
                    {"error": f"Missing required fields: {', '.join(missing_fields)}"},
                    status=400,
                )

            if image is None:
                if image_base64:
                    try:
                        if "," in image_base64:
                            image_base64 = image_base64.split(",", 1)[1]
                        image = base64.b64decode(image_base64)
                    except Exception as exc:
                        return web.json_response({"error": f"Invalid base64 image data: {exc}"}, status=400)
                else:
                    return web.json_response({"error": "No image data provided"}, status=400)

            recipes_dir = recipe_scanner.recipes_dir
            os.makedirs(recipes_dir, exist_ok=True)

            import uuid

            recipe_id = str(uuid.uuid4())
            optimized_image, extension = self._exif_utils.optimize_image(
                image_data=image,
                target_width=self._card_preview_width,
                format="webp",
                quality=85,
                preserve_metadata=True,
            )

            image_filename = f"{recipe_id}{extension}"
            image_path = os.path.join(recipes_dir, image_filename)
            with open(image_path, "wb") as file_obj:
                file_obj.write(optimized_image)

            current_time = time.time()
            loras_data = []
            for lora in metadata.get("loras", []):
                loras_data.append(
                    {
                        "file_name": lora.get("file_name", "")
                        or (
                            os.path.splitext(os.path.basename(lora.get("localPath", "")))[0]
                            if lora.get("localPath")
                            else ""
                        ),
                        "hash": (lora.get("hash") or "").lower(),
                        "strength": float(lora.get("weight", 1.0)),
                        "modelVersionId": lora.get("id", 0),
                        "modelName": lora.get("name", ""),
                        "modelVersionName": lora.get("version", ""),
                        "isDeleted": lora.get("isDeleted", False),
                        "exclude": lora.get("exclude", False),
                    }
                )

            gen_params = metadata.get("gen_params", {})
            if not gen_params and "raw_metadata" in metadata:
                raw_metadata = metadata.get("raw_metadata", {})
                gen_params = {
                    "prompt": raw_metadata.get("prompt", ""),
                    "negative_prompt": raw_metadata.get("negative_prompt", ""),
                    "checkpoint": raw_metadata.get("checkpoint", {}),
                    "steps": raw_metadata.get("steps", ""),
                    "sampler": raw_metadata.get("sampler", ""),
                    "cfg_scale": raw_metadata.get("cfg_scale", ""),
                    "seed": raw_metadata.get("seed", ""),
                    "size": raw_metadata.get("size", ""),
                    "clip_skip": raw_metadata.get("clip_skip", ""),
                }

            from ...utils.utils import calculate_recipe_fingerprint

            fingerprint = calculate_recipe_fingerprint(loras_data)

            recipe_data = {
                "id": recipe_id,
                "file_path": image_path,
                "title": name,
                "modified": current_time,
                "created_date": current_time,
                "base_model": metadata.get("base_model", ""),
                "loras": loras_data,
                "gen_params": gen_params,
                "fingerprint": fingerprint,
            }

            if tags:
                recipe_data["tags"] = tags

            if metadata.get("source_path"):
                recipe_data["source_path"] = metadata.get("source_path")

            json_filename = f"{recipe_id}.recipe.json"
            json_path = os.path.join(recipes_dir, json_filename)
            with open(json_path, "w", encoding="utf-8") as file_obj:
                json.dump(recipe_data, file_obj, indent=4, ensure_ascii=False)

            self._exif_utils.append_recipe_metadata(image_path, recipe_data)

            matching_recipes = []
            if fingerprint:
                matching_recipes = await recipe_scanner.find_recipes_by_fingerprint(fingerprint)
                if recipe_id in matching_recipes:
                    matching_recipes.remove(recipe_id)

            cache = getattr(recipe_scanner, "_cache", None)
            if cache is not None:
                cache.raw_data.append(recipe_data)
                asyncio.create_task(cache.resort())
                self._logger.info("Added recipe %s to cache", recipe_id)

            return web.json_response(
                {
                    "success": True,
                    "recipe_id": recipe_id,
                    "image_path": image_path,
                    "json_path": json_path,
                    "matching_recipes": matching_recipes,
                }
            )
        except Exception as exc:
            self._logger.error("Error saving recipe: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def delete_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            recipe_id = request.match_info["recipe_id"]
            recipes_dir = recipe_scanner.recipes_dir
            if not recipes_dir or not os.path.exists(recipes_dir):
                return web.json_response({"error": "Recipes directory not found"}, status=404)

            recipe_json_path = os.path.join(recipes_dir, f"{recipe_id}.recipe.json")
            if not os.path.exists(recipe_json_path):
                return web.json_response({"error": "Recipe not found"}, status=404)

            with open(recipe_json_path, "r", encoding="utf-8") as file_obj:
                recipe_data = json.load(file_obj)

            image_path = recipe_data.get("file_path")
            os.remove(recipe_json_path)
            self._logger.info("Deleted recipe JSON file: %s", recipe_json_path)

            if image_path and os.path.exists(image_path):
                os.remove(image_path)
                self._logger.info("Deleted recipe image: %s", image_path)

            cache = getattr(recipe_scanner, "_cache", None)
            if cache is not None:
                cache.raw_data = [
                    item for item in cache.raw_data if str(item.get("id", "")) != recipe_id
                ]
                asyncio.create_task(cache.resort())
                self._logger.info("Removed recipe %s from cache", recipe_id)

            return web.json_response({"success": True, "message": "Recipe deleted successfully"})
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

            if not any(
                key in data for key in ("title", "tags", "source_path", "preview_nsfw_level")
            ):
                return web.json_response(
                    {
                        "error": (
                            "At least one field to update must be provided (title or tags or "
                            "source_path or preview_nsfw_level)"
                        )
                    },
                    status=400,
                )

            success = await recipe_scanner.update_recipe_metadata(recipe_id, data)
            if not success:
                return web.json_response({"error": "Recipe not found or update failed"}, status=404)

            return web.json_response({"success": True, "recipe_id": recipe_id, "updates": data})
        except Exception as exc:
            self._logger.error("Error updating recipe: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def reconnect_lora(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            data = await request.json()
            required_fields = ["recipe_id", "lora_index", "target_name"]
            for field in required_fields:
                if field not in data:
                    return web.json_response({"error": f"Missing required field: {field}"}, status=400)

            recipe_id = data["recipe_id"]
            lora_index = int(data["lora_index"])
            target_name = data["target_name"]

            recipe_path = os.path.join(recipe_scanner.recipes_dir, f"{recipe_id}.recipe.json")
            if not os.path.exists(recipe_path):
                return web.json_response({"error": "Recipe not found"}, status=404)

            lora_scanner = getattr(recipe_scanner, "_lora_scanner", None)
            target_lora = None if lora_scanner is None else await lora_scanner.get_model_info_by_name(target_name)
            if not target_lora:
                return web.json_response({"error": f"Local LoRA not found with name: {target_name}"}, status=404)

            with open(recipe_path, "r", encoding="utf-8") as file_obj:
                recipe_data = json.load(file_obj)

            loras = recipe_data.get("loras", [])
            lora = loras[lora_index] if lora_index < len(loras) else None
            if lora is None:
                return web.json_response({"error": "LoRA index out of range in recipe"}, status=404)

            lora["isDeleted"] = False
            lora["exclude"] = False
            lora["file_name"] = target_name
            if "sha256" in target_lora:
                lora["hash"] = target_lora["sha256"].lower()
            if target_lora.get("civitai"):
                lora["modelName"] = target_lora["civitai"]["model"]["name"]
                lora["modelVersionName"] = target_lora["civitai"]["name"]
                lora["modelVersionId"] = target_lora["civitai"]["id"]

            from ...utils.utils import calculate_recipe_fingerprint

            recipe_data["fingerprint"] = calculate_recipe_fingerprint(recipe_data.get("loras", []))

            with open(recipe_path, "w", encoding="utf-8") as file_obj:
                json.dump(recipe_data, file_obj, indent=4, ensure_ascii=False)

            updated_lora = dict(lora)
            updated_lora["inLibrary"] = True
            updated_lora["preview_url"] = config.get_preview_static_url(target_lora["preview_url"])
            updated_lora["localPath"] = target_lora["file_path"]

            cache = getattr(recipe_scanner, "_cache", None)
            if cache is not None:
                for cache_item in cache.raw_data:
                    if cache_item.get("id") == recipe_id:
                        cache_item["loras"] = recipe_data["loras"]
                        cache_item["fingerprint"] = recipe_data["fingerprint"]
                        asyncio.create_task(cache.resort())
                        break

            image_path = recipe_data.get("file_path")
            if image_path and os.path.exists(image_path):
                self._exif_utils.append_recipe_metadata(image_path, recipe_data)

            matching_recipes = []
            if "fingerprint" in recipe_data:
                matching_recipes = await recipe_scanner.find_recipes_by_fingerprint(recipe_data["fingerprint"])
                if recipe_id in matching_recipes:
                    matching_recipes.remove(recipe_id)

            return web.json_response(
                {
                    "success": True,
                    "recipe_id": recipe_id,
                    "updated_lora": updated_lora,
                    "matching_recipes": matching_recipes,
                }
            )
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
            if not recipe_ids:
                return web.json_response(
                    {"success": False, "error": "No recipe IDs provided"},
                    status=400,
                )

            recipes_dir = recipe_scanner.recipes_dir
            if not recipes_dir or not os.path.exists(recipes_dir):
                return web.json_response(
                    {"success": False, "error": "Recipes directory not found"},
                    status=404,
                )

            deleted_recipes: list[str] = []
            failed_recipes: list[Dict[str, Any]] = []

            for recipe_id in recipe_ids:
                recipe_json_path = os.path.join(recipes_dir, f"{recipe_id}.recipe.json")
                if not os.path.exists(recipe_json_path):
                    failed_recipes.append({"id": recipe_id, "reason": "Recipe not found"})
                    continue

                try:
                    with open(recipe_json_path, "r", encoding="utf-8") as file_obj:
                        recipe_data = json.load(file_obj)
                    image_path = recipe_data.get("file_path")
                    os.remove(recipe_json_path)
                    if image_path and os.path.exists(image_path):
                        os.remove(image_path)
                    deleted_recipes.append(recipe_id)
                except Exception as exc:
                    failed_recipes.append({"id": recipe_id, "reason": str(exc)})

            cache = getattr(recipe_scanner, "_cache", None)
            if deleted_recipes and cache is not None:
                cache.raw_data = [item for item in cache.raw_data if item.get("id") not in deleted_recipes]
                asyncio.create_task(cache.resort())
                self._logger.info("Removed %s recipes from cache", len(deleted_recipes))

            return web.json_response(
                {
                    "success": True,
                    "deleted": deleted_recipes,
                    "failed": failed_recipes,
                    "total_deleted": len(deleted_recipes),
                    "total_failed": len(failed_recipes),
                }
            )
        except Exception as exc:
            self._logger.error("Error performing bulk delete: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def save_recipe_from_widget(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            if self._metadata_collector is None or self._metadata_processor_cls is None:
                return web.json_response({"error": "Metadata collection not available"}, status=400)

            raw_metadata = self._metadata_collector()
            metadata_dict = self._metadata_processor_cls.to_dict(raw_metadata)
            if not metadata_dict:
                return web.json_response({"error": "No generation metadata found"}, status=400)

            if not self._standalone_mode and self._metadata_registry_cls is not None:
                metadata_registry = self._metadata_registry_cls()
                latest_image = metadata_registry.get_first_decoded_image()
            else:
                latest_image = None

            if latest_image is None:
                return web.json_response(
                    {"error": "No recent images found to use for recipe. Try generating an image first."},
                    status=400,
                )

            self._logger.debug("Image type: %s", type(latest_image))

            try:
                if isinstance(latest_image, tuple):
                    tensor_image = latest_image[0] if latest_image else None
                    if tensor_image is None:
                        return web.json_response({"error": "Empty image tuple received"}, status=400)
                else:
                    tensor_image = latest_image

                if hasattr(tensor_image, "shape"):
                    shape_info = tensor_image.shape
                    self._logger.debug("Tensor shape: %s, dtype: %s", shape_info, tensor_image.dtype)

                import torch  # type: ignore[import-not-found]

                if isinstance(tensor_image, torch.Tensor):
                    image_np = tensor_image.cpu().numpy()
                else:
                    image_np = np.array(tensor_image)

                while len(image_np.shape) > 3:
                    image_np = image_np[0]

                if image_np.dtype in (np.float32, np.float64) and image_np.max() <= 1.0:
                    image_np = (image_np * 255).astype(np.uint8)

                if len(image_np.shape) == 3 and image_np.shape[2] == 3:
                    pil_image = Image.fromarray(image_np)
                    img_byte_arr = io.BytesIO()
                    pil_image.save(img_byte_arr, format="PNG")
                    image_bytes = img_byte_arr.getvalue()
                else:
                    return web.json_response(
                        {"error": f"Cannot handle this data shape: {image_np.shape}, {image_np.dtype}"},
                        status=400,
                    )
            except Exception as exc:
                self._logger.error("Error processing image data: %s", exc, exc_info=True)
                return web.json_response({"error": f"Error processing image: {exc}"}, status=400)

            lora_stack = metadata_dict.get("loras", "")
            import re

            lora_matches = re.findall(r"<lora:([^:]+):([^>]+)>", lora_stack)
            if not lora_matches:
                return web.json_response({"error": "No LoRAs found in the generation metadata"}, status=400)

            loras_for_name = lora_matches[:3]
            recipe_name_parts = []
            for name, strength in loras_for_name:
                recipe_name_parts.append(f"{name.strip()}-{float(strength):.2f}")
            recipe_name = "_".join(recipe_name_parts)

            recipe_name = recipe_name or "recipe"

            recipes_dir = recipe_scanner.recipes_dir
            os.makedirs(recipes_dir, exist_ok=True)

            import uuid

            recipe_id = str(uuid.uuid4())
            image_filename = f"{recipe_id}.png"
            image_path = os.path.join(recipes_dir, image_filename)
            with open(image_path, "wb") as file_obj:
                file_obj.write(image_bytes)

            loras_data = []
            lora_scanner = getattr(recipe_scanner, "_lora_scanner", None)
            base_model_counts: Dict[str, int] = {}

            for name, strength in lora_matches:
                lora_info = None
                if lora_scanner is not None:
                    lora_info = await lora_scanner.get_model_info_by_name(name)
                lora_data = {
                    "file_name": name,
                    "strength": float(strength),
                    "hash": (lora_info.get("sha256") or "").lower() if lora_info else "",
                    "modelVersionId": lora_info.get("civitai", {}).get("id") if lora_info else 0,
                    "modelName": lora_info.get("civitai", {}).get("model", {}).get("name") if lora_info else "",
                    "modelVersionName": lora_info.get("civitai", {}).get("name") if lora_info else "",
                    "isDeleted": False,
                    "exclude": False,
                }
                loras_data.append(lora_data)

                if lora_info and "base_model" in lora_info:
                    base_model = lora_info["base_model"]
                    base_model_counts[base_model] = base_model_counts.get(base_model, 0) + 1

            most_common_base_model = ""
            if base_model_counts:
                most_common_base_model = max(base_model_counts.items(), key=lambda item: item[1])[0]

            recipe_data = {
                "id": recipe_id,
                "file_path": image_path,
                "title": recipe_name,
                "modified": time.time(),
                "created_date": time.time(),
                "base_model": most_common_base_model,
                "loras": loras_data,
                "checkpoint": metadata_dict.get("checkpoint", ""),
                "gen_params": {
                    key: value
                    for key, value in metadata_dict.items()
                    if key not in ["checkpoint", "loras"]
                },
                "loras_stack": lora_stack,
            }

            json_filename = f"{recipe_id}.recipe.json"
            json_path = os.path.join(recipes_dir, json_filename)
            with open(json_path, "w", encoding="utf-8") as file_obj:
                json.dump(recipe_data, file_obj, indent=4, ensure_ascii=False)

            self._exif_utils.append_recipe_metadata(image_path, recipe_data)

            cache = getattr(recipe_scanner, "_cache", None)
            if cache is not None:
                cache.raw_data.append(recipe_data)
                asyncio.create_task(cache.resort())
                self._logger.info("Added recipe %s to cache", recipe_id)

            return web.json_response(
                {
                    "success": True,
                    "recipe_id": recipe_id,
                    "image_path": image_path,
                    "json_path": json_path,
                    "recipe_name": recipe_name,
                }
            )
        except Exception as exc:
            self._logger.error("Error saving recipe from widget: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)


class RecipeAnalysisHandler:
    """Analyze images to extract recipe metadata."""

    def __init__(
        self,
        *,
        ensure_dependencies_ready: EnsureDependenciesCallable,
        recipe_scanner_getter: RecipeScannerGetter,
        civitai_client_getter: CivitaiClientGetter,
        logger: Logger,
        exif_utils=ExifUtils,
        recipe_parser_factory=RecipeParserFactory,
        downloader_factory=get_downloader,
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._civitai_client_getter = civitai_client_getter
        self._logger = logger
        self._exif_utils = exif_utils
        self._recipe_parser_factory = recipe_parser_factory
        self._downloader_factory = downloader_factory

    async def analyze_uploaded_image(self, request: web.Request) -> web.Response:
        temp_path: Optional[str] = None
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            civitai_client = self._civitai_client_getter()
            if recipe_scanner is None or civitai_client is None:
                raise RuntimeError("Required services unavailable")

            content_type = request.headers.get("Content-Type", "")
            is_url_mode = False
            metadata: Optional[Dict[str, Any]] = None

            if "multipart/form-data" in content_type:
                reader = await request.multipart()
                field = await reader.next()
                if field is None or field.name != "image":
                    return web.json_response({"error": "No image field found", "loras": []}, status=400)

                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                    while True:
                        chunk = await field.read_chunk()
                        if not chunk:
                            break
                        temp_file.write(chunk)
                    temp_path = temp_file.name
            elif "application/json" in content_type:
                data = await request.json()
                url = data.get("url")
                is_url_mode = True
                if not url:
                    return web.json_response({"error": "No URL provided", "loras": []}, status=400)

                import re

                civitai_image_match = re.match(r"https://civitai\.com/images/(\d+)", url)
                if civitai_image_match:
                    image_id = civitai_image_match.group(1)
                    image_info = await civitai_client.get_image_info(image_id)
                    if not image_info:
                        return web.json_response(
                            {"error": "Failed to fetch image information from Civitai", "loras": []},
                            status=400,
                        )
                    image_url = image_info.get("url")
                    if not image_url:
                        return web.json_response(
                            {"error": "No image URL found in Civitai response", "loras": []},
                            status=400,
                        )

                    downloader = await self._downloader_factory()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                        temp_path = temp_file.name

                    success, result = await downloader.download_file(
                        image_url,
                        temp_path,
                        use_auth=False,
                    )
                    if not success:
                        return web.json_response(
                            {"error": f"Failed to download image from URL: {result}", "loras": []},
                            status=400,
                        )
                    metadata = image_info.get("meta") if "meta" in image_info else None
            else:
                return web.json_response({"error": "Unsupported content type", "loras": []}, status=400)

            if metadata is None and temp_path:
                metadata = self._exif_utils.extract_image_metadata(temp_path)

            if not metadata:
                response: Dict[str, Any] = {"error": "No metadata found in this image", "loras": []}
                if is_url_mode and temp_path:
                    with open(temp_path, "rb") as image_file:
                        response["image_base64"] = base64.b64encode(image_file.read()).decode("utf-8")
                return web.json_response(response, status=200)

            parser = self._recipe_parser_factory.create_parser(metadata)
            if parser is None:
                response = {"error": "No parser found for this image", "loras": []}
                if is_url_mode and temp_path:
                    with open(temp_path, "rb") as image_file:
                        response["image_base64"] = base64.b64encode(image_file.read()).decode("utf-8")
                return web.json_response(response, status=200)

            result = await parser.parse_metadata(metadata, recipe_scanner=recipe_scanner)

            if is_url_mode and temp_path:
                with open(temp_path, "rb") as image_file:
                    result["image_base64"] = base64.b64encode(image_file.read()).decode("utf-8")

            if "error" in result and not result.get("loras"):
                return web.json_response(result, status=200)

            from ...utils.utils import calculate_recipe_fingerprint

            fingerprint = calculate_recipe_fingerprint(result.get("loras", []))
            result["fingerprint"] = fingerprint

            matching_recipes = []
            if fingerprint:
                matching_recipes = await recipe_scanner.find_recipes_by_fingerprint(fingerprint)

            result["matching_recipes"] = matching_recipes
            return web.json_response(result)
        except Exception as exc:
            self._logger.error("Error analyzing recipe image: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc), "loras": []}, status=500)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception as cleanup_exc:  # pragma: no cover - logging path
                    self._logger.error("Error deleting temporary file: %s", cleanup_exc)

    async def analyze_local_image(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            data = await request.json()
            file_path = data.get("path")
            if not file_path:
                return web.json_response({"error": "No file path provided", "loras": []}, status=400)

            file_path = os.path.normpath(file_path.strip('"').strip("'"))
            if not os.path.isfile(file_path):
                return web.json_response({"error": "File not found", "loras": []}, status=404)

            metadata = self._exif_utils.extract_image_metadata(file_path)
            if not metadata:
                with open(file_path, "rb") as image_file:
                    image_base64 = base64.b64encode(image_file.read()).decode("utf-8")
                return web.json_response(
                    {"error": "No metadata found in this image", "loras": [], "image_base64": image_base64},
                    status=200,
                )

            parser = self._recipe_parser_factory.create_parser(metadata)
            if parser is None:
                with open(file_path, "rb") as image_file:
                    image_base64 = base64.b64encode(image_file.read()).decode("utf-8")
                return web.json_response(
                    {"error": "No parser found for this image", "loras": [], "image_base64": image_base64},
                    status=200,
                )

            result = await parser.parse_metadata(metadata, recipe_scanner=recipe_scanner)
            with open(file_path, "rb") as image_file:
                result["image_base64"] = base64.b64encode(image_file.read()).decode("utf-8")

            if "error" in result and not result.get("loras"):
                return web.json_response(result, status=200)

            from ...utils.utils import calculate_recipe_fingerprint

            fingerprint = calculate_recipe_fingerprint(result.get("loras", []))
            result["fingerprint"] = fingerprint

            matching_recipes = []
            if fingerprint:
                matching_recipes = await recipe_scanner.find_recipes_by_fingerprint(fingerprint)
            result["matching_recipes"] = matching_recipes

            return web.json_response(result)
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
    ) -> None:
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._logger = logger
        self._shared_recipes: Dict[str, Dict[str, Any]] = {}

    async def share_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            recipe_id = request.match_info["recipe_id"]
            cache = await recipe_scanner.get_cached_data()
            recipe = next(
                (r for r in getattr(cache, "raw_data", []) if str(r.get("id", "")) == recipe_id),
                None,
            )
            if not recipe:
                return web.json_response({"error": "Recipe not found"}, status=404)

            image_path = recipe.get("file_path")
            if not image_path or not os.path.exists(image_path):
                return web.json_response({"error": "Recipe image not found"}, status=404)

            import shutil

            ext = os.path.splitext(image_path)[1]
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
                temp_path = temp_file.name
            shutil.copy2(image_path, temp_path)
            processed_path = temp_path

            timestamp = int(time.time())
            url_path = f"/api/recipe/{recipe_id}/share/download?t={timestamp}"
            self._shared_recipes[recipe_id] = {
                "path": processed_path,
                "timestamp": timestamp,
                "expires": time.time() + 300,
            }
            self._cleanup_shared_recipes()

            filename = f"recipe_{recipe.get('title', '').replace(' ', '_').lower()}{ext}"
            return web.json_response({"success": True, "download_url": url_path, "filename": filename})
        except Exception as exc:
            self._logger.error("Error sharing recipe: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    async def download_shared_recipe(self, request: web.Request) -> web.Response:
        try:
            await self._ensure_dependencies_ready()
            recipe_scanner = self._recipe_scanner_getter()
            if recipe_scanner is None:
                raise RuntimeError("Recipe scanner unavailable")

            recipe_id = request.match_info["recipe_id"]
            shared_info = self._shared_recipes.get(recipe_id)
            if not shared_info:
                return web.json_response({"error": "Shared recipe not found or expired"}, status=404)

            file_path = shared_info["path"]
            if not os.path.exists(file_path):
                return web.json_response({"error": "Shared recipe file not found"}, status=404)

            cache = await recipe_scanner.get_cached_data()
            recipe = next(
                (r for r in getattr(cache, "raw_data", []) if str(r.get("id", "")) == recipe_id),
                None,
            )
            filename_base = (
                f"recipe_{recipe.get('title', '').replace(' ', '_').lower()}"
                if recipe
                else recipe_id
            )
            ext = os.path.splitext(file_path)[1]
            download_filename = f"{filename_base}{ext}"

            return web.FileResponse(
                file_path,
                headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
            )
        except Exception as exc:
            self._logger.error("Error downloading shared recipe: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    def _cleanup_shared_recipes(self) -> None:
        current_time = time.time()
        expired_ids = [
            recipe_id
            for recipe_id, info in self._shared_recipes.items()
            if current_time > info.get("expires", 0)
        ]

        for recipe_id in expired_ids:
            try:
                file_path = self._shared_recipes[recipe_id]["path"]
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception as exc:  # pragma: no cover - logging path
                self._logger.error("Error cleaning up shared recipe %s: %s", recipe_id, exc)
            finally:
                self._shared_recipes.pop(recipe_id, None)
