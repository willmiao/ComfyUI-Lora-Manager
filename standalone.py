from pathlib import Path
import os
import sys
import json

# Create mock folder_paths module BEFORE any other imports
class MockFolderPaths:
    @staticmethod
    def get_folder_paths(folder_name):
        # Load paths from settings.json
        settings_path = os.path.join(os.path.dirname(__file__), 'settings.json')
        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # For diffusion_models, combine unet and diffusers paths
                if folder_name == "diffusion_models":
                    paths = []
                    if 'folder_paths' in settings:
                        if 'unet' in settings['folder_paths']:
                            paths.extend(settings['folder_paths']['unet'])
                        if 'diffusers' in settings['folder_paths']:
                            paths.extend(settings['folder_paths']['diffusers'])
                    # Filter out paths that don't exist
                    valid_paths = [p for p in paths if os.path.exists(p)]
                    if valid_paths:
                        return valid_paths
                    else:
                        print(f"Warning: No valid paths found for {folder_name}")
                # For other folder names, return their paths directly
                elif 'folder_paths' in settings and folder_name in settings['folder_paths']:
                    paths = settings['folder_paths'][folder_name]
                    valid_paths = [p for p in paths if os.path.exists(p)]
                    if valid_paths:
                        return valid_paths
                    else:
                        print(f"Warning: No valid paths found for {folder_name}")
        except Exception as e:
            print(f"Error loading folder paths from settings: {e}")
        
        # Fallback to empty list if no paths found
        return []
    
    @staticmethod
    def get_temp_directory():
        return os.path.join(os.path.dirname(__file__), 'temp')
    
    @staticmethod
    def set_temp_directory(path):
        os.makedirs(path, exist_ok=True)
        return path

# Create mock server module with PromptServer
class MockPromptServer:
    def __init__(self):
        self.app = None
        
    def send_sync(self, *args, **kwargs):
        pass

# Create mock metadata_collector module
class MockMetadataCollector:
    def init(self):
        pass
    
    def get_metadata(self, prompt_id=None):
        return {}

# Initialize basic mocks before any imports
sys.modules['folder_paths'] = MockFolderPaths()
sys.modules['server'] = type('server', (), {'PromptServer': MockPromptServer()})
sys.modules['py.metadata_collector'] = MockMetadataCollector()

# Now we can safely import modules that depend on folder_paths and server
import argparse
import asyncio
import logging
from aiohttp import web

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("lora-manager-standalone")

# Configure aiohttp access logger to be less verbose
logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

# Now we can import the global config from our local modules
from py.config import config

class StandaloneServer:
    """Server implementation for standalone mode"""
    
    def __init__(self):
        self.app = web.Application(logger=logger)
        self.instance = self  # Make it compatible with PromptServer.instance pattern
        
        # Ensure the app's access logger is configured to reduce verbosity
        self.app._subapps = []  # Ensure this exists to avoid AttributeError
        
        # Configure access logging for the app
        self.app.on_startup.append(self._configure_access_logger)
    
    async def _configure_access_logger(self, app):
        """Configure access logger to reduce verbosity"""
        logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
        
        # If using aiohttp>=3.8.0, configure access logger through app directly
        if hasattr(app, 'access_logger'):
            app.access_logger.setLevel(logging.WARNING)
    
    async def setup(self):
        """Set up the standalone server"""
        # Create placeholders for compatibility with ComfyUI's implementation
        self.last_prompt_id = None
        self.last_node_id = None
        self.client_id = None
        
        # Set up routes
        self.setup_routes()
        
        # Add startup and shutdown handlers
        self.app.on_startup.append(self.on_startup)
        self.app.on_shutdown.append(self.on_shutdown)
    
    def setup_routes(self):
        """Set up basic routes"""
        # Add a simple status endpoint
        self.app.router.add_get('/', self.handle_status)
        
        # Add static route for example images if the path exists in settings
        settings_path = os.path.join(os.path.dirname(__file__), 'settings.json')
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            example_images_path = settings.get('example_images_path')
            logger.info(f"Example images path: {example_images_path}")
            if example_images_path and os.path.exists(example_images_path):
                self.app.router.add_static('/example_images_static', example_images_path)
                logger.info(f"Added static route for example images: /example_images_static -> {example_images_path}")
    
    async def handle_status(self, request):
        """Handle status request by redirecting to loras page"""
        # Redirect to loras page instead of showing status
        raise web.HTTPFound('/loras')
        
        # Original JSON response (commented out)
        # return web.json_response({
        #     "status": "running",
        #     "mode": "standalone",
        #     "loras_roots": config.loras_roots,
        #     "checkpoints_roots": config.checkpoints_roots
        # })
    
    async def on_startup(self, app):
        """Startup handler"""
        logger.info("LoRA Manager standalone server starting...")
    
    async def on_shutdown(self, app):
        """Shutdown handler"""
        logger.info("LoRA Manager standalone server shutting down...")
    
    def send_sync(self, event_type, data, sid=None):
        """Stub for compatibility with PromptServer"""
        # In standalone mode, we don't have the same websocket system
        pass
    
    async def start(self, host='127.0.0.1', port=8188):
        """Start the server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        # Log the server address with a clickable localhost URL regardless of the actual binding
        logger.info(f"Server started at http://127.0.0.1:{port}")
        
        # Keep the server running
        while True:
            await asyncio.sleep(3600)  # Sleep for a long time
    
    async def publish_loop(self):
        """Stub for compatibility with PromptServer"""
        # This method exists in ComfyUI's server but we don't need it
        pass

# After all mocks are in place, import LoraManager
from py.lora_manager import LoraManager

class StandaloneLoraManager(LoraManager):
    """Extended LoraManager for standalone mode"""
    
    @classmethod
    def add_routes(cls, server_instance):
        """Initialize and register all routes for standalone mode"""
        app = server_instance.app
        
        # Store app in a global-like location for compatibility
        sys.modules['server'].PromptServer.instance = server_instance

        # Configure aiohttp access logger to be less verbose
        logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
        
        added_targets = set()  # Track already added target paths
        
        # Add static routes for each lora root
        for idx, root in enumerate(config.loras_roots, start=1):
            if not os.path.exists(root):
                logger.warning(f"Lora root path does not exist: {root}")
                continue
                
            preview_path = f'/loras_static/root{idx}/preview'
            
            # Check if this root is a link path in the mappings
            real_root = root
            for target, link in config._path_mappings.items():
                if os.path.normpath(link) == os.path.normpath(root):
                    # If so, route should point to the target (real path)
                    real_root = target
                    break
            
            # Normalize and standardize path display for consistency
            display_root = real_root.replace('\\', '/')
            
            # Add static route for original path - use the normalized path
            app.router.add_static(preview_path, real_root)
            logger.info(f"Added static route {preview_path} -> {display_root}")
            
            # Record route mapping with normalized path
            config.add_route_mapping(real_root, preview_path)
            added_targets.add(os.path.normpath(real_root))
        
        # Add static routes for each checkpoint root
        for idx, root in enumerate(config.checkpoints_roots, start=1):
            if not os.path.exists(root):
                logger.warning(f"Checkpoint root path does not exist: {root}")
                continue
                
            preview_path = f'/checkpoints_static/root{idx}/preview'
            
            # Check if this root is a link path in the mappings
            real_root = root
            for target, link in config._path_mappings.items():
                if os.path.normpath(link) == os.path.normpath(root):
                    # If so, route should point to the target (real path)
                    real_root = target
                    break
            
            # Normalize and standardize path display for consistency
            display_root = real_root.replace('\\', '/')
            
            # Add static route for original path
            app.router.add_static(preview_path, real_root)
            logger.info(f"Added static route {preview_path} -> {display_root}")
            
            # Record route mapping
            config.add_route_mapping(real_root, preview_path)
            added_targets.add(os.path.normpath(real_root))
        
        # Add static routes for symlink target paths that aren't already covered
        link_idx = {
            'lora': 1,
            'checkpoint': 1
        }
        
        for target_path, link_path in config._path_mappings.items():
            norm_target = os.path.normpath(target_path)
            if norm_target not in added_targets:
                # Determine if this is a checkpoint or lora link based on path
                is_checkpoint = any(os.path.normpath(cp_root) in os.path.normpath(link_path) for cp_root in config.checkpoints_roots)
                is_checkpoint = is_checkpoint or any(os.path.normpath(cp_root) in norm_target for cp_root in config.checkpoints_roots)
                
                if is_checkpoint:
                    route_path = f'/checkpoints_static/link_{link_idx["checkpoint"]}/preview'
                    link_idx["checkpoint"] += 1
                else:
                    route_path = f'/loras_static/link_{link_idx["lora"]}/preview'
                    link_idx["lora"] += 1
                
                # Display path with forward slashes for consistency
                display_target = target_path.replace('\\', '/')
                
                try:
                    app.router.add_static(route_path, Path(target_path).resolve(strict=False))
                    logger.info(f"Added static route for link target {route_path} -> {display_target}")
                    config.add_route_mapping(target_path, route_path)
                    added_targets.add(norm_target)
                except Exception as e:
                    logger.warning(f"Failed to add static route on initialization for {target_path}: {e}")
                    continue
        
        # Add static route for plugin assets
        app.router.add_static('/loras_static', config.static_path)
        
        # Setup feature routes
        from py.routes.lora_routes import LoraRoutes
        from py.routes.api_routes import ApiRoutes
        from py.routes.recipe_routes import RecipeRoutes
        from py.routes.checkpoints_routes import CheckpointsRoutes
        from py.routes.update_routes import UpdateRoutes
        from py.routes.misc_routes import MiscRoutes
        from py.routes.example_images_routes import ExampleImagesRoutes
        
        lora_routes = LoraRoutes()
        checkpoints_routes = CheckpointsRoutes()
        
        # Initialize routes
        lora_routes.setup_routes(app)
        checkpoints_routes.setup_routes(app)
        ApiRoutes.setup_routes(app)
        RecipeRoutes.setup_routes(app)
        UpdateRoutes.setup_routes(app)
        MiscRoutes.setup_routes(app)
        ExampleImagesRoutes.setup_routes(app)
        
        # Schedule service initialization
        app.on_startup.append(lambda app: cls._initialize_services())
        
        # Add cleanup
        app.on_shutdown.append(cls._cleanup)
        app.on_shutdown.append(ApiRoutes.cleanup)

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="LoRA Manager Standalone Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", 
                        help="Host address to bind the server to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8188,
                        help="Port to bind the server to (default: 8188, access via http://localhost:8188/loras)")
    # parser.add_argument("--loras", type=str, nargs="+", 
    #                     help="Additional paths to LoRA model directories (optional if settings.json has paths)")
    # parser.add_argument("--checkpoints", type=str, nargs="+",
    #                     help="Additional paths to checkpoint model directories (optional if settings.json has paths)")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Logging level")
    return parser.parse_args()

async def main():
    """Main entry point for standalone mode"""
    args = parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Explicitly configure aiohttp access logger regardless of selected log level
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    
    # Create the server instance
    server = StandaloneServer()
    
    # Initialize routes via the standalone lora manager
    StandaloneLoraManager.add_routes(server)
    
    # Set up and start the server
    await server.setup()
    await server.start(host=args.host, port=args.port)

if __name__ == "__main__":
    try:
        # Run the main function
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
