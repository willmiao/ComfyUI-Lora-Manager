from __future__ import annotations

import logging
from typing import Callable, Mapping

from aiohttp import web

from .example_images_route_registrar import ExampleImagesRouteRegistrar
from .handlers.example_images_handlers import (
    ExampleImagesDownloadHandler,
    ExampleImagesFileHandler,
    ExampleImagesHandlerSet,
    ExampleImagesManagementHandler,
)
from ..services.use_cases.example_images import (
    DownloadExampleImagesUseCase,
    ImportExampleImagesUseCase,
)
from ..utils.example_images_download_manager import (
    DownloadManager,
    get_default_download_manager,
)
from ..utils.example_images_file_manager import ExampleImagesFileManager
from ..utils.example_images_processor import ExampleImagesProcessor
from ..services.example_images_cleanup_service import ExampleImagesCleanupService

logger = logging.getLogger(__name__)


class ExampleImagesRoutes:
    """Route controller for example image endpoints."""

    def __init__(
        self,
        *,
        ws_manager,
        download_manager: DownloadManager | None = None,
        processor=ExampleImagesProcessor,
        file_manager=ExampleImagesFileManager,
        cleanup_service: ExampleImagesCleanupService | None = None,
    ) -> None:
        if ws_manager is None:
            raise ValueError("ws_manager is required")
        self._download_manager = download_manager or get_default_download_manager(ws_manager)
        self._processor = processor
        self._file_manager = file_manager
        self._cleanup_service = cleanup_service or ExampleImagesCleanupService()
        self._handler_set: ExampleImagesHandlerSet | None = None
        self._handler_mapping: Mapping[str, Callable[[web.Request], web.StreamResponse]] | None = None

    @classmethod
    def setup_routes(cls, app: web.Application, *, ws_manager) -> None:
        """Register routes on the given aiohttp application using default wiring."""

        controller = cls(ws_manager=ws_manager)
        controller.register(app)

    def register(self, app: web.Application) -> None:
        """Bind the controller's handlers to the aiohttp router."""

        registrar = ExampleImagesRouteRegistrar(app)
        registrar.register_routes(self.to_route_mapping())

    def to_route_mapping(self) -> Mapping[str, Callable[[web.Request], web.StreamResponse]]:
        """Return the registrar-compatible mapping of handler names to callables."""

        if self._handler_mapping is None:
            handler_set = self._build_handler_set()
            self._handler_set = handler_set
            self._handler_mapping = handler_set.to_route_mapping()
        return self._handler_mapping

    def _build_handler_set(self) -> ExampleImagesHandlerSet:
        logger.debug("Building ExampleImagesHandlerSet with %s, %s, %s", self._download_manager, self._processor, self._file_manager)
        download_use_case = DownloadExampleImagesUseCase(download_manager=self._download_manager)
        download_handler = ExampleImagesDownloadHandler(download_use_case, self._download_manager)
        import_use_case = ImportExampleImagesUseCase(processor=self._processor)
        management_handler = ExampleImagesManagementHandler(
            import_use_case,
            self._processor,
            self._cleanup_service,
        )
        file_handler = ExampleImagesFileHandler(self._file_manager)
        return ExampleImagesHandlerSet(
            download=download_handler,
            management=management_handler,
            files=file_handler,
        )
