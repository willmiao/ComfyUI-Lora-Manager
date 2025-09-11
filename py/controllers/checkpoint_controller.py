import logging
from aiohttp import web
from typing import Dict, Any

from .base_model_controller import BaseModelController
from ..services.checkpoint_service import CheckpointService
from ..services.service_registry import ServiceRegistry
from ..services.metadata_service import get_default_metadata_provider
from ..services.server_i18n import server_i18n

logger = logging.getLogger(__name__)


class CheckpointController(BaseModelController):
    """Checkpoint-specific controller"""
    
    def __init__(self, service_container=None):
        """Initialize Checkpoint controller"""
        # Service will be initialized later via setup_routes
        self.service = None
        super().__init__(None, 'checkpoint', service_container)
    
    async def initialize_services(self):
        """Initialize services from ServiceRegistry"""
        checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
        self.service = CheckpointService(checkpoint_scanner)
        
        # Update the model_service reference in parent
        self.model_service = self.service
    
    def setup_routes(self, app: web.Application):
        """Setup Checkpoint routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())
        
        # Setup common routes with 'checkpoints' prefix
        super().setup_routes(app, 'checkpoints')
    
    def setup_specific_routes(self, app: web.Application, prefix: str):
        """Setup Checkpoint-specific routes"""
        # Checkpoint-specific query routes (if any)
        # app.router.add_get(f'/api/{prefix}/checkpoint-info', self.get_checkpoint_info)
        pass
    
    async def handle_models_page(self, request: web.Request) -> web.Response:
        """Handle the Checkpoints page"""
        try:
            template = self.template_env.get_template(self.template_name)
            content = template.render(
                title=server_i18n.get('checkpoints.title', 'Checkpoints'),
                model_type='checkpoint'
            )
            return web.Response(text=content, content_type='text/html')
        except Exception as e:
            logger.error(f"Error rendering Checkpoints page: {e}", exc_info=True)
            return web.Response(text="Error loading page", status=500)
    
    def _parse_specific_params(self, request: web.Request) -> Dict[str, Any]:
        """Parse Checkpoint-specific parameters"""
        params = {}
        
        # Checkpoint-specific parameters can be added here
        # For example, model architecture, size filters, etc.
        
        return params
