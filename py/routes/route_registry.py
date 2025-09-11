"""
New route registration system using the refactored controller architecture
"""
import logging
from aiohttp import web

from ..controllers.lora_controller import LoraController
from ..controllers.health_controller import HealthController
from ..controllers.checkpoint_controller import CheckpointController
from ..controllers.embedding_controller import EmbeddingController

logger = logging.getLogger(__name__)


class RouteRegistry:
    """Central registry for setting up all application routes"""
    
    def __init__(self):
        """Initialize the route registry"""
        self.controllers = {}
    
    def setup_routes(self, app: web.Application):
        """Setup all application routes using the new controller architecture
        
        Args:
            app: aiohttp application instance
        """
        try:
            # Initialize controllers
            self._initialize_controllers()
            
            # Setup routes for each controller
            self._setup_lora_routes(app)
            self._setup_health_routes(app)
            self._setup_checkpoint_routes(app)
            self._setup_embedding_routes(app)
            
            logger.info("Successfully set up all routes using new controller architecture")
            
        except Exception as e:
            logger.error(f"Error setting up routes: {e}", exc_info=True)
            raise
    
    def _initialize_controllers(self):
        """Initialize all controllers"""
        try:
            # Initialize LoRA controller
            self.controllers['lora'] = LoraController()
            
            # Initialize health controller
            self.controllers['health'] = HealthController()
            
            # Initialize checkpoint controller
            self.controllers['checkpoint'] = CheckpointController()
            
            # Initialize embedding controller
            self.controllers['embedding'] = EmbeddingController()
            
            logger.info("Initialized all controllers")
            
        except Exception as e:
            logger.error(f"Error initializing controllers: {e}", exc_info=True)
            raise
    
    def _setup_lora_routes(self, app: web.Application):
        """Setup LoRA routes using the new controller
        
        Args:
            app: aiohttp application instance
        """
        try:
            lora_controller = self.controllers['lora']
            lora_controller.setup_routes(app)
            logger.info("Set up LoRA routes using new controller")
            
        except Exception as e:
            logger.error(f"Error setting up LoRA routes: {e}", exc_info=True)
            raise
    
    def _setup_health_routes(self, app: web.Application):
        """Setup health check routes
        
        Args:
            app: aiohttp application instance
        """
        try:
            health_controller = self.controllers['health']
            health_controller.setup_routes(app)
            logger.info("Set up health check routes using new controller")
            
        except Exception as e:
            logger.error(f"Error setting up health routes: {e}", exc_info=True)
            raise
    
    def _setup_checkpoint_routes(self, app: web.Application):
        """Setup Checkpoint routes using the new controller
        
        Args:
            app: aiohttp application instance
        """
        try:
            checkpoint_controller = self.controllers['checkpoint']
            checkpoint_controller.setup_routes(app)
            logger.info("Set up Checkpoint routes using new controller")
            
        except Exception as e:
            logger.error(f"Error setting up Checkpoint routes: {e}", exc_info=True)
            raise
    
    def _setup_embedding_routes(self, app: web.Application):
        """Setup Embedding routes using the new controller
        
        Args:
            app: aiohttp application instance
        """
        try:
            embedding_controller = self.controllers['embedding']
            embedding_controller.setup_routes(app)
            logger.info("Set up Embedding routes using new controller")
            
        except Exception as e:
            logger.error(f"Error setting up Embedding routes: {e}", exc_info=True)
            raise
    
    def get_controller(self, controller_name: str):
        """Get a controller instance by name
        
        Args:
            controller_name: Name of the controller to retrieve
            
        Returns:
            Controller instance or None if not found
        """
        return self.controllers.get(controller_name)


# Global route registry instance
route_registry = RouteRegistry()


def setup_new_routes(app: web.Application):
    """Setup all routes using the new architecture
    
    This function can be called to use the new controller-based routing system
    instead of the old BaseModelRoutes system.
    
    Args:
        app: aiohttp application instance
    """
    route_registry.setup_routes(app)
