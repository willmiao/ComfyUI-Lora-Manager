import logging
from aiohttp import web
from typing import Dict, Any

from .base_model_controller import BaseModelController
from ..services.embedding_service import EmbeddingService
from ..services.service_registry import ServiceRegistry
from ..services.metadata_service import get_default_metadata_provider
from ..services.server_i18n import server_i18n

logger = logging.getLogger(__name__)


class EmbeddingController(BaseModelController):
    """Embedding-specific controller"""
    
    def __init__(self, service_container=None):
        """Initialize Embedding controller"""
        # Service will be initialized later via setup_routes
        self.service = None
        super().__init__(None, 'embedding', service_container)
    
    async def initialize_services(self):
        """Initialize services from ServiceRegistry"""
        embedding_scanner = await ServiceRegistry.get_embedding_scanner()
        self.service = EmbeddingService(embedding_scanner)
        
        # Update the model_service reference in parent
        self.model_service = self.service
    
    def setup_routes(self, app: web.Application):
        """Setup Embedding routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())
        
        # Setup common routes with 'embeddings' prefix
        super().setup_routes(app, 'embeddings')
    
    def setup_specific_routes(self, app: web.Application, prefix: str):
        """Setup Embedding-specific routes"""
        # Embedding-specific query routes (if any)
        # app.router.add_get(f'/api/{prefix}/embedding-info', self.get_embedding_info)
        pass
    
    async def handle_models_page(self, request: web.Request) -> web.Response:
        """Handle the Embeddings page"""
        try:
            template = self.template_env.get_template(self.template_name)
            content = template.render(
                title=server_i18n.get('embeddings.title', 'Embeddings'),
                model_type='embedding'
            )
            return web.Response(text=content, content_type='text/html')
        except Exception as e:
            logger.error(f"Error rendering Embeddings page: {e}", exc_info=True)
            return web.Response(text="Error loading page", status=500)
    
    def _parse_specific_params(self, request: web.Request) -> Dict[str, Any]:
        """Parse Embedding-specific parameters"""
        params = {}
        
        # Embedding-specific parameters can be added here
        # For example, vector dimension, format filters, etc.
        
        return params
