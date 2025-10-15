import logging
from aiohttp import web

from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar
from ..services.checkpoint_service import CheckpointService
from ..services.service_registry import ServiceRegistry
from ..config import config

logger = logging.getLogger(__name__)

class CheckpointRoutes(BaseModelRoutes):
    """Checkpoint-specific route controller"""
    
    def __init__(self):
        """Initialize Checkpoint routes with Checkpoint service"""
        super().__init__()
        self.template_name = "checkpoints.html"
    
    async def initialize_services(self):
        """Initialize services from ServiceRegistry"""
        checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
        update_service = await ServiceRegistry.get_model_update_service()
        self.service = CheckpointService(checkpoint_scanner, update_service=update_service)
        self.set_model_update_service(update_service)

        # Attach service dependencies
        self.attach_service(self.service)
    
    def setup_routes(self, app: web.Application):
        """Setup Checkpoint routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())
        
        # Setup common routes with 'checkpoints' prefix (includes page route)
        super().setup_routes(app, 'checkpoints')
    
    def setup_specific_routes(self, registrar: ModelRouteRegistrar, prefix: str):
        """Setup Checkpoint-specific routes"""
        # Checkpoint info by name
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/info/{name}', prefix, self.get_checkpoint_info)

        # Checkpoint roots and Unet roots
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/checkpoints_roots', prefix, self.get_checkpoints_roots)
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/unet_roots', prefix, self.get_unet_roots)
    
    def _validate_civitai_model_type(self, model_type: str) -> bool:
        """Validate CivitAI model type for Checkpoint"""
        return model_type.lower() == 'checkpoint'
    
    def _get_expected_model_types(self) -> str:
        """Get expected model types string for error messages"""
        return "Checkpoint"
    
    async def get_checkpoint_info(self, request: web.Request) -> web.Response:
        """Get detailed information for a specific checkpoint by name"""
        try:
            name = request.match_info.get('name', '')
            checkpoint_info = await self.service.get_model_info_by_name(name)
            
            if checkpoint_info:
                return web.json_response(checkpoint_info)
            else:
                return web.json_response({"error": "Checkpoint not found"}, status=404)
                
        except Exception as e:
            logger.error(f"Error in get_checkpoint_info: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def get_checkpoints_roots(self, request: web.Request) -> web.Response:
        """Return the list of checkpoint roots from config"""
        try:
            roots = config.checkpoints_roots
            return web.json_response({
                "success": True,
                "roots": roots
            })
        except Exception as e:
            logger.error(f"Error getting checkpoint roots: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def get_unet_roots(self, request: web.Request) -> web.Response:
        """Return the list of unet roots from config"""
        try:
            roots = config.unet_roots
            return web.json_response({
                "success": True,
                "roots": roots
            })
        except Exception as e:
            logger.error(f"Error getting unet roots: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)
