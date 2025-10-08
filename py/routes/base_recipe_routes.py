"""Base infrastructure shared across recipe routes."""
from __future__ import annotations

import logging
import os
from typing import Callable, Mapping

import jinja2
from aiohttp import web

from ..config import config
from ..recipes import RecipeParserFactory
from ..services.downloader import get_downloader
from ..services.recipes import (
    RecipeAnalysisService,
    RecipePersistenceService,
    RecipeSharingService,
)
from ..services.server_i18n import server_i18n
from ..services.service_registry import ServiceRegistry
from ..services.settings_manager import get_settings_manager
from ..utils.constants import CARD_PREVIEW_WIDTH
from ..utils.exif_utils import ExifUtils
from .handlers.recipe_handlers import (
    RecipeAnalysisHandler,
    RecipeHandlerSet,
    RecipeListingHandler,
    RecipeManagementHandler,
    RecipePageView,
    RecipeQueryHandler,
    RecipeSharingHandler,
)
from .recipe_route_registrar import ROUTE_DEFINITIONS

logger = logging.getLogger(__name__)


class BaseRecipeRoutes:
    """Common dependency and startup wiring for recipe routes."""

    _HANDLER_NAMES: tuple[str, ...] = tuple(
        definition.handler_name for definition in ROUTE_DEFINITIONS
    )

    template_name: str = "recipes.html"

    def __init__(self) -> None:
        self.recipe_scanner = None
        self.lora_scanner = None
        self.civitai_client = None
        self.settings = get_settings_manager()
        self.server_i18n = server_i18n
        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(config.templates_path),
            autoescape=True,
        )

        self._i18n_registered = False
        self._startup_hooks_registered = False
        self._handler_set: RecipeHandlerSet | None = None
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
            handler_set = self._create_handler_set()
            self._handler_set = handler_set
            self._handler_mapping = handler_set.to_route_mapping()
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

        if self._handler_set is None:
            self._handler_set = self._create_handler_set()
        return self._handler_set

    def _create_handler_set(self) -> RecipeHandlerSet:
        recipe_scanner_getter = lambda: self.recipe_scanner
        civitai_client_getter = lambda: self.civitai_client

        standalone_mode = os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1" or os.environ.get("HF_HUB_DISABLE_TELEMETRY", "0") == "0"
        if not standalone_mode:
            from ..metadata_collector import get_metadata  # type: ignore[import-not-found]
            from ..metadata_collector.metadata_processor import (  # type: ignore[import-not-found]
                MetadataProcessor,
            )
            from ..metadata_collector.metadata_registry import (  # type: ignore[import-not-found]
                MetadataRegistry,
            )
        else:  # pragma: no cover - optional dependency path
            get_metadata = None  # type: ignore[assignment]
            MetadataProcessor = None  # type: ignore[assignment]
            MetadataRegistry = None  # type: ignore[assignment]

        analysis_service = RecipeAnalysisService(
            exif_utils=ExifUtils,
            recipe_parser_factory=RecipeParserFactory,
            downloader_factory=get_downloader,
            metadata_collector=get_metadata,
            metadata_processor_cls=MetadataProcessor,
            metadata_registry_cls=MetadataRegistry,
            standalone_mode=standalone_mode,
            logger=logger,
        )
        persistence_service = RecipePersistenceService(
            exif_utils=ExifUtils,
            card_preview_width=CARD_PREVIEW_WIDTH,
            logger=logger,
        )
        sharing_service = RecipeSharingService(logger=logger)

        page_view = RecipePageView(
            ensure_dependencies_ready=self.ensure_dependencies_ready,
            settings_service=self.settings,
            server_i18n=self.server_i18n,
            template_env=self.template_env,
            template_name=self.template_name,
            recipe_scanner_getter=recipe_scanner_getter,
            logger=logger,
        )
        listing = RecipeListingHandler(
            ensure_dependencies_ready=self.ensure_dependencies_ready,
            recipe_scanner_getter=recipe_scanner_getter,
            logger=logger,
        )
        query = RecipeQueryHandler(
            ensure_dependencies_ready=self.ensure_dependencies_ready,
            recipe_scanner_getter=recipe_scanner_getter,
            format_recipe_file_url=listing.format_recipe_file_url,
            logger=logger,
        )
        management = RecipeManagementHandler(
            ensure_dependencies_ready=self.ensure_dependencies_ready,
            recipe_scanner_getter=recipe_scanner_getter,
            logger=logger,
            persistence_service=persistence_service,
            analysis_service=analysis_service,
        )
        analysis = RecipeAnalysisHandler(
            ensure_dependencies_ready=self.ensure_dependencies_ready,
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            logger=logger,
            analysis_service=analysis_service,
        )
        sharing = RecipeSharingHandler(
            ensure_dependencies_ready=self.ensure_dependencies_ready,
            recipe_scanner_getter=recipe_scanner_getter,
            logger=logger,
            sharing_service=sharing_service,
        )

        return RecipeHandlerSet(
            page_view=page_view,
            listing=listing,
            query=query,
            management=management,
            analysis=analysis,
            sharing=sharing,
        )

