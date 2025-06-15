import asyncio
from server import PromptServer # type: ignore
from .config import config
from .routes.lora_routes import LoraRoutes
from .routes.api_routes import ApiRoutes
from .routes.recipe_routes import RecipeRoutes
from .routes.checkpoints_routes import CheckpointsRoutes
from .routes.update_routes import UpdateRoutes
from .routes.misc_routes import MiscRoutes
from .routes.example_images_routes import ExampleImagesRoutes
from .services.service_registry import ServiceRegistry
from .services.settings_manager import settings
from pathlib import Path
import logging
import sys
import os

logger = logging.getLogger(__name__)

# Check if we're in standalone mode
STANDALONE_MODE = 'nodes' not in sys.modules

class LoraManager:
    """Main entry point for LoRA Manager plugin"""
    
    @classmethod
    def add_routes(cls):
        """Initialize and register all routes"""
        app = PromptServer.instance.app

        # Configure aiohttp access logger to be less verbose
        logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

        added_targets = set()  # Track already added target paths
        
        # Add static route for example images if the path exists in settings
        example_images_path = settings.get('example_images_path')
        logger.info(f"Example images path: {example_images_path}")
        if example_images_path and os.path.exists(example_images_path):
            app.router.add_static('/example_images_static', example_images_path)
            logger.info(f"Added static route for example images: /example_images_static -> {example_images_path}")
        
        # Add static routes for each lora root
        for idx, root in enumerate(config.loras_roots, start=1):
            preview_path = f'/loras_static/root{idx}/preview'
            
            real_root = root
            if root in config._path_mappings.values():
                for target, link in config._path_mappings.items():
                    if link == root:
                        real_root = target
                        break
            # Add static route for original path
            app.router.add_static(preview_path, real_root)
            logger.info(f"Added static route {preview_path} -> {real_root}")
            
            # Record route mapping
            config.add_route_mapping(real_root, preview_path)
            added_targets.add(real_root)
        
        # Add static routes for each checkpoint root
        for idx, root in enumerate(config.checkpoints_roots, start=1):
            preview_path = f'/checkpoints_static/root{idx}/preview'
            
            real_root = root
            if root in config._path_mappings.values():
                for target, link in config._path_mappings.items():
                    if link == root:
                        real_root = target
                        break
            # Add static route for original path
            app.router.add_static(preview_path, real_root)
            logger.info(f"Added static route {preview_path} -> {real_root}")
            
            # Record route mapping
            config.add_route_mapping(real_root, preview_path)
            added_targets.add(real_root)
        
        # Add static routes for symlink target paths
        link_idx = {
            'lora': 1,
            'checkpoint': 1
        }
        
        for target_path, link_path in config._path_mappings.items():
            if target_path not in added_targets:
                # Determine if this is a checkpoint or lora link based on path
                is_checkpoint = any(cp_root in link_path for cp_root in config.checkpoints_roots)
                is_checkpoint = is_checkpoint or any(cp_root in target_path for cp_root in config.checkpoints_roots)
                
                if is_checkpoint:
                    route_path = f'/checkpoints_static/link_{link_idx["checkpoint"]}/preview'
                    link_idx["checkpoint"] += 1
                else:
                    route_path = f'/loras_static/link_{link_idx["lora"]}/preview'
                    link_idx["lora"] += 1
                
                try:
                    app.router.add_static(route_path, Path(target_path).resolve(strict=False))
                    logger.info(f"Added static route for link target {route_path} -> {target_path}")
                    config.add_route_mapping(target_path, route_path)
                    added_targets.add(target_path)
                except Exception as e:
                    logger.warning(f"Failed to add static route on initialization for {target_path}: {e}")
                    continue
        
        # Add static route for plugin assets
        app.router.add_static('/loras_static', config.static_path)
        
        # Setup feature routes
        lora_routes = LoraRoutes()
        checkpoints_routes = CheckpointsRoutes()
        
        # Initialize routes
        lora_routes.setup_routes(app)
        checkpoints_routes.setup_routes(app)
        ApiRoutes.setup_routes(app)
        RecipeRoutes.setup_routes(app)
        UpdateRoutes.setup_routes(app)  
        MiscRoutes.setup_routes(app)  # Register miscellaneous routes
        ExampleImagesRoutes.setup_routes(app)  # Register example images routes
        
        # Schedule service initialization 
        app.on_startup.append(lambda app: cls._initialize_services())
        
        # Add cleanup
        app.on_shutdown.append(cls._cleanup)
        app.on_shutdown.append(ApiRoutes.cleanup)
    
    @classmethod
    async def _initialize_services(cls):
        """Initialize all services using the ServiceRegistry"""
        try:
            # Ensure aiohttp access logger is configured with reduced verbosity
            logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
            
            # Initialize CivitaiClient first to ensure it's ready for other services
            civitai_client = await ServiceRegistry.get_civitai_client()

            # Register DownloadManager with ServiceRegistry
            download_manager = await ServiceRegistry.get_download_manager()
            
            # Initialize WebSocket manager
            ws_manager = await ServiceRegistry.get_websocket_manager()
            
            # Initialize scanners in background
            lora_scanner = await ServiceRegistry.get_lora_scanner()
            checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
            
            # Initialize recipe scanner if needed
            recipe_scanner = await ServiceRegistry.get_recipe_scanner()
            
            # Initialize metadata collector if not in standalone mode
            if not STANDALONE_MODE:
                from .metadata_collector import init as init_metadata
                init_metadata()
                logger.debug("Metadata collector initialized")
            
            # Create low-priority initialization tasks
            asyncio.create_task(lora_scanner.initialize_in_background(), name='lora_cache_init')
            asyncio.create_task(checkpoint_scanner.initialize_in_background(), name='checkpoint_cache_init')
            asyncio.create_task(recipe_scanner.initialize_in_background(), name='recipe_cache_init')
            
            logger.info("LoRA Manager: All services initialized and background tasks scheduled")
                
        except Exception as e:
            logger.error(f"LoRA Manager: Error initializing services: {e}", exc_info=True)
    
    @classmethod
    async def _cleanup(cls, app):
        """Cleanup resources using ServiceRegistry"""
        try:
            logger.info("LoRA Manager: Cleaning up services")
                
            # Close CivitaiClient gracefully
            civitai_client = await ServiceRegistry.get_service("civitai_client")
            if civitai_client:
                await civitai_client.close()
                logger.info("Closed CivitaiClient connection")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
