import logging
from aiohttp import web

from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar
from ..services.embedding_service import EmbeddingService
from ..services.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

class EmbeddingRoutes(BaseModelRoutes):
    """Embedding-specific route controller"""
    
    def __init__(self):
        """Initialize Embedding routes with Embedding service"""
        super().__init__()
        self.template_name = "embeddings.html"
    
    async def initialize_services(self):
        """Initialize services from ServiceRegistry"""
        embedding_scanner = await ServiceRegistry.get_embedding_scanner()
        update_service = await ServiceRegistry.get_model_update_service()
        self.service = EmbeddingService(embedding_scanner, update_service=update_service)
        self.set_model_update_service(update_service)

        # Attach service dependencies
        self.attach_service(self.service)
    
    def setup_routes(self, app: web.Application):
        """Setup Embedding routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())
        
        # Setup common routes with 'embeddings' prefix (includes page route)
        super().setup_routes(app, 'embeddings')
    
    def setup_specific_routes(self, registrar: ModelRouteRegistrar, prefix: str):
        """Setup Embedding-specific routes"""
        # Embedding info by name
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/info/{name}', prefix, self.get_embedding_info)
    
    def _validate_civitai_model_type(self, model_type: str) -> bool:
        """Validate CivitAI model type for Embedding"""
        return model_type.lower() == 'textualinversion'
    
    def _get_expected_model_types(self) -> str:
        """Get expected model types string for error messages"""
        return "TextualInversion"
    
    async def get_embedding_info(self, request: web.Request) -> web.Response:
        """Get detailed information for a specific embedding by name"""
        try:
            name = request.match_info.get('name', '')
            embedding_info = await self.service.get_model_info_by_name(name)
            
            if embedding_info:
                return web.json_response(embedding_info)
            else:
                return web.json_response({"error": "Embedding not found"}, status=404)
                
        except Exception as e:
            logger.error(f"Error in get_embedding_info: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
