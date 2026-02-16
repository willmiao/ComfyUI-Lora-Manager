"""HTTP handlers for batch recipe import operations."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from aiohttp import web


logger = logging.getLogger(__name__)


class BatchImportHandler:
    """Handle batch recipe import requests."""

    def __init__(
        self,
        *,
        batch_import_service,
        ensure_dependencies_ready: Callable,
        recipe_scanner_getter: Callable,
        civitai_client_getter: Callable,
        logger: logging.Logger,
    ) -> None:
        self._batch_service = batch_import_service
        self._ensure_dependencies_ready = ensure_dependencies_ready
        self._recipe_scanner_getter = recipe_scanner_getter
        self._civitai_client_getter = civitai_client_getter
        self._logger = logger

    async def _get_batch_service(self):
        """Resolve the batch import service (supports callable or coroutine)."""
        service = self._batch_service
        if callable(service):
            service = service()
        if hasattr(service, "__await__"):
            service = await service
        return service

    async def import_from_directory(self, request: web.Request) -> web.Response:
        """Import and generate recipes from all images in a directory.
        
        Request body (JSON):
        {
            "directory_path": "/path/to/directory",
            "max_concurrent": 3  (optional)
        }
        """
        try:
            await self._ensure_dependencies_ready()

            data = await request.json()
            directory_path = data.get("directory_path")
            max_concurrent = data.get("max_concurrent", 3)

            if not directory_path:
                return web.json_response(
                    {"error": "Missing required field: directory_path"},
                    status=400,
                )

            recipe_scanner = self._recipe_scanner_getter()
            civitai_client = self._civitai_client_getter()

            if recipe_scanner is None:
                return web.json_response(
                    {"error": "Recipe scanner unavailable"},
                    status=500,
                )

            batch_service = await self._get_batch_service()
            result = await batch_service.import_batch_from_directory(
                directory_path=directory_path,
                recipe_scanner=recipe_scanner,
                civitai_client=civitai_client,
                max_concurrent=max_concurrent,
            )

            status = 200 if result["success"] else 400
            return web.json_response(result, status=status)

        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON in request body"},
                status=400,
            )
        except Exception as exc:
            self._logger.error(f"Error importing from directory: {exc}", exc_info=True)
            return web.json_response(
                {"error": str(exc)},
                status=500,
            )

    async def import_from_urls(self, request: web.Request) -> web.Response:
        """Import and generate recipes from a list of image URLs.
        
        Request body (JSON):
        {
            "urls": ["url1", "url2", ...],
            "max_concurrent": 3  (optional)
        }
        """
        try:
            await self._ensure_dependencies_ready()

            data = await request.json()
            urls = data.get("urls", [])
            max_concurrent = data.get("max_concurrent", 3)

            if not urls or not isinstance(urls, list):
                return web.json_response(
                    {"error": "Invalid or missing urls parameter"},
                    status=400,
                )

            recipe_scanner = self._recipe_scanner_getter()
            civitai_client = self._civitai_client_getter()

            if recipe_scanner is None:
                return web.json_response(
                    {"error": "Recipe scanner unavailable"},
                    status=500,
                )

            batch_service = await self._get_batch_service()
            result = await batch_service.import_batch_from_urls(
                urls=urls,
                recipe_scanner=recipe_scanner,
                civitai_client=civitai_client,
                max_concurrent=max_concurrent,
            )

            status = 200 if result["success"] else 400
            return web.json_response(result, status=status)

        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON in request body"},
                status=400,
            )
        except Exception as exc:
            self._logger.error(f"Error importing from URLs: {exc}", exc_info=True)
            return web.json_response(
                {"error": str(exc)},
                status=500,
            )

    async def get_batch_status(self, request: web.Request) -> web.Response:
        """Get the status of ongoing batch import operations."""
        # This endpoint can be extended to track async batch operations
        try:
            # For now, return a simple running status
            status = {
                "active": False,
                "message": "No batch operations in progress",
            }
            return web.json_response(status)
        except Exception as exc:
            self._logger.error(f"Error getting batch status: {exc}", exc_info=True)
            return web.json_response(
                {"error": str(exc)},
                status=500,
            )
