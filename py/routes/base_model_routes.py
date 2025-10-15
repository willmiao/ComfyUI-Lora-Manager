from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, Dict, Mapping

import jinja2
from aiohttp import web

from ..config import config
from ..services.download_coordinator import DownloadCoordinator
from ..services.downloader import get_downloader
from ..services.metadata_service import get_default_metadata_provider, get_metadata_provider
from ..services.metadata_sync_service import MetadataSyncService
from ..services.model_file_service import ModelFileService, ModelMoveService
from ..services.model_lifecycle_service import ModelLifecycleService
from ..services.preview_asset_service import PreviewAssetService
from ..services.server_i18n import server_i18n as default_server_i18n
from ..services.service_registry import ServiceRegistry
from ..services.settings_manager import get_settings_manager
from ..services.tag_update_service import TagUpdateService
from ..services.websocket_manager import ws_manager as default_ws_manager
from ..services.use_cases import (
    AutoOrganizeUseCase,
    BulkMetadataRefreshUseCase,
    DownloadModelUseCase,
)
from ..services.websocket_progress_callback import (
    WebSocketBroadcastCallback,
    WebSocketProgressCallback,
)
from ..utils.exif_utils import ExifUtils
from ..utils.metadata_manager import MetadataManager
from .model_route_registrar import COMMON_ROUTE_DEFINITIONS, ModelRouteRegistrar
from .handlers.model_handlers import (
    ModelAutoOrganizeHandler,
    ModelCivitaiHandler,
    ModelDownloadHandler,
    ModelHandlerSet,
    ModelListingHandler,
    ModelManagementHandler,
    ModelMoveHandler,
    ModelPageView,
    ModelQueryHandler,
    ModelUpdateHandler,
)

if TYPE_CHECKING:
    from ..services.model_update_service import ModelUpdateService

logger = logging.getLogger(__name__)


class BaseModelRoutes(ABC):
    """Base route controller for all model types."""

    template_name: str | None = None

    def __init__(
        self,
        service=None,
        *,
        settings_service=None,
        ws_manager=default_ws_manager,
        server_i18n=default_server_i18n,
        metadata_provider_factory=get_default_metadata_provider,
    ) -> None:
        self.service = None
        self.model_type = ""
        self._settings = settings_service or get_settings_manager()
        self._ws_manager = ws_manager
        self._server_i18n = server_i18n
        self._metadata_provider_factory = metadata_provider_factory

        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(config.templates_path),
            autoescape=True,
        )

        self.model_file_service: ModelFileService | None = None
        self.model_move_service: ModelMoveService | None = None
        self.model_lifecycle_service: ModelLifecycleService | None = None
        self.websocket_progress_callback = WebSocketProgressCallback()
        self.metadata_progress_callback = WebSocketBroadcastCallback()

        self._handler_set: ModelHandlerSet | None = None
        self._handler_mapping: Dict[str, Callable[[web.Request], web.StreamResponse]] | None = None

        self._preview_service = PreviewAssetService(
            metadata_manager=MetadataManager,
            downloader_factory=get_downloader,
            exif_utils=ExifUtils,
        )
        self._metadata_sync_service = MetadataSyncService(
            metadata_manager=MetadataManager,
            preview_service=self._preview_service,
            settings=self._settings,
            default_metadata_provider_factory=metadata_provider_factory,
            metadata_provider_selector=get_metadata_provider,
        )
        self._tag_update_service = TagUpdateService(metadata_manager=MetadataManager)
        self._download_coordinator = DownloadCoordinator(
            ws_manager=self._ws_manager,
            download_manager_factory=ServiceRegistry.get_download_manager,
        )
        self._model_update_service: ModelUpdateService | None = None

        if service is not None:
            self.attach_service(service)

    def set_model_update_service(self, service: "ModelUpdateService") -> None:
        """Attach the model update tracking service."""

        self._model_update_service = service
        self._handler_set = None
        self._handler_mapping = None

    def attach_service(self, service) -> None:
        """Attach a model service and rebuild handler dependencies."""
        self.service = service
        self.model_type = service.model_type
        self.model_file_service = ModelFileService(service.scanner, service.model_type)
        self.model_move_service = ModelMoveService(service.scanner)
        self.model_lifecycle_service = ModelLifecycleService(
            scanner=service.scanner,
            metadata_manager=MetadataManager,
            metadata_loader=self._metadata_sync_service.load_local_metadata,
            recipe_scanner_factory=ServiceRegistry.get_recipe_scanner,
        )
        self._handler_set = None
        self._handler_mapping = None

    def _ensure_handler_mapping(self) -> Mapping[str, Callable[[web.Request], web.StreamResponse]]:
        if self._handler_mapping is None:
            handler_set = self._create_handler_set()
            self._handler_set = handler_set
            self._handler_mapping = handler_set.to_route_mapping()
        return self._handler_mapping

    def _create_handler_set(self) -> ModelHandlerSet:
        service = self._ensure_service()
        update_service = self._ensure_model_update_service()
        page_view = ModelPageView(
            template_env=self.template_env,
            template_name=self.template_name or "",
            service=service,
            settings_service=self._settings,
            server_i18n=self._server_i18n,
            logger=logger,
        )
        listing = ModelListingHandler(
            service=service,
            parse_specific_params=self._parse_specific_params,
            logger=logger,
        )
        management = ModelManagementHandler(
            service=service,
            logger=logger,
            metadata_sync=self._metadata_sync_service,
            preview_service=self._preview_service,
            tag_update_service=self._tag_update_service,
            lifecycle_service=self._ensure_lifecycle_service(),
        )
        query = ModelQueryHandler(service=service, logger=logger)
        download_use_case = DownloadModelUseCase(download_coordinator=self._download_coordinator)
        download = ModelDownloadHandler(
            ws_manager=self._ws_manager,
            logger=logger,
            download_use_case=download_use_case,
            download_coordinator=self._download_coordinator,
        )
        metadata_refresh_use_case = BulkMetadataRefreshUseCase(
            service=service,
            metadata_sync=self._metadata_sync_service,
            settings_service=self._settings,
            logger=logger,
        )
        civitai = ModelCivitaiHandler(
            service=service,
            settings_service=self._settings,
            ws_manager=self._ws_manager,
            logger=logger,
            metadata_provider_factory=self._metadata_provider_factory,
            validate_model_type=self._validate_civitai_model_type,
            expected_model_types=self._get_expected_model_types,
            find_model_file=self._find_model_file,
            metadata_sync=self._metadata_sync_service,
            metadata_refresh_use_case=metadata_refresh_use_case,
            metadata_progress_callback=self.metadata_progress_callback,
        )
        move = ModelMoveHandler(move_service=self._ensure_move_service(), logger=logger)
        auto_organize_use_case = AutoOrganizeUseCase(
            file_service=self._ensure_file_service(),
            lock_provider=self._ws_manager,
        )
        auto_organize = ModelAutoOrganizeHandler(
            use_case=auto_organize_use_case,
            progress_callback=self.websocket_progress_callback,
            ws_manager=self._ws_manager,
            logger=logger,
        )
        updates = ModelUpdateHandler(
            service=service,
            update_service=update_service,
            metadata_provider_selector=get_metadata_provider,
            logger=logger,
        )
        return ModelHandlerSet(
            page_view=page_view,
            listing=listing,
            management=management,
            query=query,
            download=download,
            civitai=civitai,
            move=move,
            auto_organize=auto_organize,
            updates=updates,
        )

    @property
    def route_handlers(self) -> Mapping[str, Callable[[web.Request], web.StreamResponse]]:
        return self._ensure_handler_mapping()

    def setup_routes(self, app: web.Application, prefix: str) -> None:
        registrar = ModelRouteRegistrar(app)
        handler_lookup = {
            definition.handler_name: self._make_handler_proxy(definition.handler_name)
            for definition in COMMON_ROUTE_DEFINITIONS
        }
        registrar.register_common_routes(prefix, handler_lookup)
        self.setup_specific_routes(registrar, prefix)

    @abstractmethod
    def setup_specific_routes(self, registrar: ModelRouteRegistrar, prefix: str) -> None:
        """Setup model-specific routes."""
        raise NotImplementedError

    def _parse_specific_params(self, request: web.Request) -> Dict:
        """Parse model-specific parameters - to be overridden by subclasses."""
        return {}

    def _validate_civitai_model_type(self, model_type: str) -> bool:
        """Validate CivitAI model type - to be overridden by subclasses."""
        return True

    def _get_expected_model_types(self) -> str:
        """Get expected model types string for error messages - to be overridden by subclasses."""
        return "any model type"

    def _find_model_file(self, files):
        """Find the appropriate model file from the files list - can be overridden by subclasses."""
        return next((file for file in files if file.get("type") == "Model" and file.get("primary") is True), None)

    def get_handler(self, name: str) -> Callable[[web.Request], web.StreamResponse]:
        """Expose handlers for subclasses or tests."""
        return self._ensure_handler_mapping()[name]

    def _ensure_service(self):
        if self.service is None:
            raise RuntimeError("Model service has not been attached")
        return self.service

    def _ensure_file_service(self) -> ModelFileService:
        if self.model_file_service is None:
            service = self._ensure_service()
            self.model_file_service = ModelFileService(service.scanner, service.model_type)
        return self.model_file_service

    def _ensure_move_service(self) -> ModelMoveService:
        if self.model_move_service is None:
            service = self._ensure_service()
            self.model_move_service = ModelMoveService(service.scanner)
        return self.model_move_service

    def _ensure_lifecycle_service(self) -> ModelLifecycleService:
        if self.model_lifecycle_service is None:
            service = self._ensure_service()
            self.model_lifecycle_service = ModelLifecycleService(
                scanner=service.scanner,
                metadata_manager=MetadataManager,
                metadata_loader=self._metadata_sync_service.load_local_metadata,
                recipe_scanner_factory=ServiceRegistry.get_recipe_scanner,
            )
        return self.model_lifecycle_service

    def _make_handler_proxy(self, name: str) -> Callable[[web.Request], web.StreamResponse]:
        async def proxy(request: web.Request) -> web.StreamResponse:
            try:
                handler = self.get_handler(name)
            except RuntimeError:
                return web.json_response({"success": False, "error": "Service not ready"}, status=503)
            return await handler(request)

        return proxy

    def _ensure_model_update_service(self) -> "ModelUpdateService":
        if self._model_update_service is None:
            raise RuntimeError("Model update service has not been attached")
        return self._model_update_service

