"""Base infrastructure shared across recipe routes."""
from __future__ import annotations

import logging
from typing import Callable, Mapping

import jinja2
from aiohttp import web

from ..config import config
from ..services.server_i18n import server_i18n
from ..services.service_registry import ServiceRegistry
from ..services.settings_manager import settings
from .recipe_route_registrar import ROUTE_DEFINITIONS

logger = logging.getLogger(__name__)


class BaseRecipeRoutes:
    """Common dependency and startup wiring for recipe routes."""

    _HANDLER_NAMES: tuple[str, ...] = tuple(
        definition.handler_name for definition in ROUTE_DEFINITIONS
    )

    def __init__(self) -> None:
        self.recipe_scanner = None
        self.lora_scanner = None
        self.civitai_client = None
        self.settings = settings
        self.server_i18n = server_i18n
        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(config.templates_path),
            autoescape=True,
        )

        self._i18n_registered = False
        self._startup_hooks_registered = False
        self._handler_mapping: dict[str, Callable] | None = None

    async def attach_dependencies(self, app: web.Application | None = None) -> None:
        """Resolve shared services from the registry."""

        await self._ensure_services()
        self._ensure_i18n_filter()

    async def ensure_dependencies_ready(self) -> None:
        """Ensure dependencies are available for request handlers."""

        if self.recipe_scanner is None or self.civitai_client is None:
            await self.attach_dependencies()

    def register_startup_hooks(self, app: web.Application) -> None:
        """Register startup hooks once for dependency wiring."""

        if self._startup_hooks_registered:
            return

        app.on_startup.append(self.attach_dependencies)
        app.on_startup.append(self.prewarm_cache)
        self._startup_hooks_registered = True

    async def prewarm_cache(self, app: web.Application | None = None) -> None:
        """Pre-load recipe and LoRA caches on startup."""

        try:
            await self.attach_dependencies(app)

            if self.lora_scanner is not None:
                await self.lora_scanner.get_cached_data()
                hash_index = getattr(self.lora_scanner, "_hash_index", None)
                if hash_index is not None and hasattr(hash_index, "_hash_to_path"):
                    _ = len(hash_index._hash_to_path)

            if self.recipe_scanner is not None:
                await self.recipe_scanner.get_cached_data(force_refresh=True)
        except Exception as exc:
            logger.error("Error pre-warming recipe cache: %s", exc, exc_info=True)

    def to_route_mapping(self) -> Mapping[str, Callable]:
        """Return a mapping of handler name to coroutine for registrar binding."""

        if self._handler_mapping is None:
            owner = self.get_handler_owner()
            self._handler_mapping = {
                name: getattr(owner, name) for name in self._HANDLER_NAMES
            }
        return self._handler_mapping

    # Internal helpers -------------------------------------------------

    async def _ensure_services(self) -> None:
        if self.recipe_scanner is None:
            self.recipe_scanner = await ServiceRegistry.get_recipe_scanner()
            self.lora_scanner = getattr(self.recipe_scanner, "_lora_scanner", None)

        if self.civitai_client is None:
            self.civitai_client = await ServiceRegistry.get_civitai_client()

    def _ensure_i18n_filter(self) -> None:
        if not self._i18n_registered:
            self.template_env.filters["t"] = self.server_i18n.create_template_filter()
            self._i18n_registered = True

    def get_handler_owner(self):
        """Return the object supplying bound handler coroutines."""

        return self

