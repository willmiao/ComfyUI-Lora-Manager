"""Handlers for base model related endpoints."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiohttp import web

from ...services.civitai_base_model_service import get_civitai_base_model_service

logger = logging.getLogger(__name__)


class BaseModelHandlerSet:
    """Collection of handlers for base model operations."""

    def __init__(
        self,
        base_model_service_factory: Callable[[], Any] = get_civitai_base_model_service,
    ) -> None:
        self._base_model_service_factory = base_model_service_factory

    def to_route_mapping(
        self,
    ) -> Dict[str, Callable[[web.Request], Awaitable[web.StreamResponse]]]:
        """Return mapping of route names to handler methods."""
        return {
            "get_base_models": self.get_base_models,
            "refresh_base_models": self.refresh_base_models,
            "get_base_model_categories": self.get_base_model_categories,
            "get_base_model_cache_status": self.get_base_model_cache_status,
        }

    async def get_base_models(self, request: web.Request) -> web.Response:
        """Get merged base models (hardcoded + remote from Civitai).

        Query Parameters:
            refresh: If 'true', force refresh from API

        Returns:
            JSON response with:
            - models: List of base model names
            - source: 'cache', 'api', or 'fallback'
            - last_updated: ISO timestamp
            - counts: hardcoded_count, remote_count, merged_count
        """
        try:
            service = await self._base_model_service_factory()

            # Check for refresh parameter
            force_refresh = request.query.get("refresh", "").lower() == "true"

            result = await service.get_base_models(force_refresh=force_refresh)

            return web.json_response(
                {
                    "success": True,
                    "data": result,
                }
            )

        except Exception as e:
            logger.error(f"Error in get_base_models: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
            )

    async def refresh_base_models(self, request: web.Request) -> web.Response:
        """Force refresh base models from Civitai API.

        Returns:
            JSON response with refreshed data
        """
        try:
            service = await self._base_model_service_factory()
            result = await service.refresh_cache()

            return web.json_response(
                {
                    "success": True,
                    "data": result,
                    "message": "Base models cache refreshed successfully",
                }
            )

        except Exception as e:
            logger.error(f"Error in refresh_base_models: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
            )

    async def get_base_model_categories(self, request: web.Request) -> web.Response:
        """Get categorized base models.

        Returns:
            JSON response with categorized models
        """
        try:
            service = await self._base_model_service_factory()
            categories = service.get_model_categories()

            return web.json_response(
                {
                    "success": True,
                    "data": categories,
                }
            )

        except Exception as e:
            logger.error(f"Error in get_base_model_categories: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
            )

    async def get_base_model_cache_status(self, request: web.Request) -> web.Response:
        """Get cache status for base models.

        Returns:
            JSON response with cache status
        """
        try:
            service = await self._base_model_service_factory()
            status = service.get_cache_status()

            return web.json_response(
                {
                    "success": True,
                    "data": status,
                }
            )

        except Exception as e:
            logger.error(f"Error in get_base_model_cache_status: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
            )
