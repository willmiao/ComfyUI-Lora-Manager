"""Concrete batch import route configuration."""

from aiohttp import web

from .recipe_route_registrar import RecipeRouteRegistrar
from .base_recipe_routes import BaseRecipeRoutes
from .batch_import_route_registrar import (
    register_batch_import_routes,
    BatchImportHandlerSet,
)
from .handlers.batch_import_handler import BatchImportHandler
from ..services.recipes.batch_import_service import BatchImportService


logger = __import__("logging").getLogger(__name__)


class BatchImportRoutes(BaseRecipeRoutes):
    """API route handlers for batch recipe import management."""

    @classmethod
    def setup_routes(cls, app: web.Application):
        """Register batch import API routes."""

        routes = cls()
        routes.register_startup_hooks(app)
        
        # Create batch import service
        async def create_batch_service():
            await routes.ensure_dependencies_ready()
            
            # Import here to avoid circular imports
            from ..services.recipes import RecipeAnalysisService, RecipePersistenceService
            from ..utils.exif_utils import ExifUtils
            from ..recipes import RecipeParserFactory
            from ..services.downloader import get_downloader
            from ..utils.constants import CARD_PREVIEW_WIDTH
            
            # Initialize services if not already done
            if not hasattr(routes, '_batch_analysis_service'):
                standalone_mode = app.get('standalone_mode', False)
                if not standalone_mode:
                    try:
                        from ..metadata_collector import get_metadata
                        from ..metadata_collector.metadata_processor import MetadataProcessor
                        from ..metadata_collector.metadata_registry import MetadataRegistry
                    except (ImportError, Exception):
                        get_metadata = None
                        MetadataProcessor = None
                        MetadataRegistry = None
                else:
                    get_metadata = None
                    MetadataProcessor = None
                    MetadataRegistry = None
                
                routes._batch_analysis_service = RecipeAnalysisService(
                    exif_utils=ExifUtils,
                    recipe_parser_factory=RecipeParserFactory,
                    downloader_factory=get_downloader,
                    metadata_collector=get_metadata,
                    metadata_processor_cls=MetadataProcessor,
                    metadata_registry_cls=MetadataRegistry,
                    standalone_mode=standalone_mode,
                    logger=logger,
                )
                routes._batch_persistence_service = RecipePersistenceService(
                    exif_utils=ExifUtils,
                    card_preview_width=CARD_PREVIEW_WIDTH,
                    logger=logger,
                )
            
            batch_service = BatchImportService(
                analysis_service=routes._batch_analysis_service,
                persistence_service=routes._batch_persistence_service,
            )
            return batch_service

        # Create handler
        recipe_scanner_getter = lambda: routes.recipe_scanner
        civitai_client_getter = lambda: routes.civitai_client

        # Make sure to pass a callable that returns the service
        async def get_batch_service():
            if not hasattr(routes, '_batch_service'):
                routes._batch_service = await create_batch_service()
            return routes._batch_service

        batch_import_handler = BatchImportHandler(
            batch_import_service=get_batch_service,
            ensure_dependencies_ready=routes.ensure_dependencies_ready,
            recipe_scanner_getter=recipe_scanner_getter,
            civitai_client_getter=civitai_client_getter,
            logger=logger,
        )

        # Register routes
        handler_set = BatchImportHandlerSet(handler=batch_import_handler)
        register_batch_import_routes(app, handler_set)
