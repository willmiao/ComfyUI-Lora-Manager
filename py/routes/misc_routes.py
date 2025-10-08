"""Route controller for miscellaneous endpoints."""

from __future__ import annotations

import logging
import os
from typing import Awaitable, Callable, Mapping

from aiohttp import web
from server import PromptServer  # type: ignore

from ..services.metadata_service import (
    get_metadata_archive_manager,
    get_metadata_provider,
    update_metadata_providers,
)
from ..services.settings_manager import get_settings_manager
from ..services.downloader import get_downloader
from ..utils.usage_stats import UsageStats
from .handlers.misc_handlers import (
    FileSystemHandler,
    HealthCheckHandler,
    LoraCodeHandler,
    MetadataArchiveHandler,
    MiscHandlerSet,
    ModelExampleFilesHandler,
    ModelLibraryHandler,
    NodeRegistry,
    NodeRegistryHandler,
    SettingsHandler,
    TrainedWordsHandler,
    UsageStatsHandler,
    build_service_registry_adapter,
)
from .misc_route_registrar import MiscRouteRegistrar

logger = logging.getLogger(__name__)

standalone_mode = os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1" or os.environ.get(
    "HF_HUB_DISABLE_TELEMETRY", "0"
) == "0"


class MiscRoutes:
    """Route controller that mirrors the model route architecture."""

    def __init__(
        self,
        *,
        settings_service=None,
        usage_stats_factory: Callable[[], UsageStats] = UsageStats,
        prompt_server: type[PromptServer] = PromptServer,
        service_registry_adapter=build_service_registry_adapter(),
        metadata_provider_factory=get_metadata_provider,
        metadata_archive_manager_factory=get_metadata_archive_manager,
        metadata_provider_updater=update_metadata_providers,
        downloader_factory=get_downloader,
        registrar_factory=MiscRouteRegistrar,
        handler_set_factory=MiscHandlerSet,
        node_registry: NodeRegistry | None = None,
        standalone_mode_flag: bool = standalone_mode,
    ) -> None:
        self._settings = settings_service or get_settings_manager()
        self._usage_stats_factory = usage_stats_factory
        self._prompt_server = prompt_server
        self._service_registry_adapter = service_registry_adapter
        self._metadata_provider_factory = metadata_provider_factory
        self._metadata_archive_manager_factory = metadata_archive_manager_factory
        self._metadata_provider_updater = metadata_provider_updater
        self._downloader_factory = downloader_factory
        self._registrar_factory = registrar_factory
        self._handler_set_factory = handler_set_factory
        self._node_registry = node_registry or NodeRegistry()
        self._standalone_mode = standalone_mode_flag

        self._handler_mapping: Mapping[str, Callable[[web.Request], Awaitable[web.StreamResponse]]] | None = None

    @staticmethod
    def setup_routes(app: web.Application) -> None:
        """Entry point used by the application bootstrap."""
        controller = MiscRoutes()
        controller.bind(app)

    def bind(self, app: web.Application) -> None:
        registrar = self._registrar_factory(app)
        registrar.register_routes(self._ensure_handler_mapping())

    def _ensure_handler_mapping(self) -> Mapping[str, Callable[[web.Request], Awaitable[web.StreamResponse]]]:
        if self._handler_mapping is None:
            handler_set = self._create_handler_set()
            self._handler_mapping = handler_set.to_route_mapping()
        return self._handler_mapping

    def _create_handler_set(self) -> MiscHandlerSet:
        health = HealthCheckHandler()
        settings_handler = SettingsHandler(
            settings_service=self._settings,
            metadata_provider_updater=self._metadata_provider_updater,
            downloader_factory=self._downloader_factory,
        )
        usage_stats = UsageStatsHandler(usage_stats_factory=self._usage_stats_factory)
        lora_code = LoraCodeHandler(prompt_server=self._prompt_server)
        trained_words = TrainedWordsHandler()
        model_examples = ModelExampleFilesHandler()
        metadata_archive = MetadataArchiveHandler(
            metadata_archive_manager_factory=self._metadata_archive_manager_factory,
            settings_service=self._settings,
            metadata_provider_updater=self._metadata_provider_updater,
        )
        filesystem = FileSystemHandler()
        node_registry_handler = NodeRegistryHandler(
            node_registry=self._node_registry,
            prompt_server=self._prompt_server,
            standalone_mode=self._standalone_mode,
        )
        model_library = ModelLibraryHandler(
            service_registry=self._service_registry_adapter,
            metadata_provider_factory=self._metadata_provider_factory,
        )

        return self._handler_set_factory(
            health=health,
            settings=settings_handler,
            usage_stats=usage_stats,
            lora_code=lora_code,
            trained_words=trained_words,
            model_examples=model_examples,
            node_registry=node_registry_handler,
            model_library=model_library,
            metadata_archive=metadata_archive,
            filesystem=filesystem,
        )


__all__ = ["MiscRoutes"]
