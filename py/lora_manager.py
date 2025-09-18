import asyncio
import sys
import os
import logging
from pathlib import Path
from server import PromptServer # type: ignore

from .config import config
from .services.model_service_factory import ModelServiceFactory, register_default_model_types
from .routes.recipe_routes import RecipeRoutes
from .routes.stats_routes import StatsRoutes
from .routes.update_routes import UpdateRoutes
from .routes.misc_routes import MiscRoutes
from .routes.example_images_routes import ExampleImagesRoutes
from .services.service_registry import ServiceRegistry
from .services.settings_manager import settings
from .utils.example_images_migration import ExampleImagesMigration
from .services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

# Check if we're in standalone mode
STANDALONE_MODE = 'nodes' not in sys.modules

class LoraManager:
    """Main entry point for LoRA Manager plugin"""
    
    @classmethod
    def add_routes(cls):
        """Initialize and register all routes using the new refactored architecture"""
        app = PromptServer.instance.app

        # Configure aiohttp access logger to be less verbose
        logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

        # Add specific suppression for connection reset errors
        class ConnectionResetFilter(logging.Filter):
            def filter(self, record):
                # Filter out connection reset errors that are not critical
                if "ConnectionResetError" in str(record.getMessage()):
                    return False
                if "_call_connection_lost" in str(record.getMessage()):
                    return False
                if "WinError 10054" in str(record.getMessage()):
                    return False
                return True

        # Apply the filter to asyncio logger
        asyncio_logger = logging.getLogger("asyncio")
        asyncio_logger.addFilter(ConnectionResetFilter())

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
        for idx, root in enumerate(config.base_models_roots, start=1):
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
        
        # Add static routes for each embedding root
        for idx, root in enumerate(config.embeddings_roots, start=1):
            preview_path = f'/embeddings_static/root{idx}/preview'
            
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
            'checkpoint': 1,
            'embedding': 1
        }
        
        for target_path, link_path in config._path_mappings.items():
            if target_path not in added_targets:
                # Determine if this is a checkpoint, lora, or embedding link based on path
                is_checkpoint = any(cp_root in link_path for cp_root in config.base_models_roots)
                is_checkpoint = is_checkpoint or any(cp_root in target_path for cp_root in config.base_models_roots)
                is_embedding = any(emb_root in link_path for emb_root in config.embeddings_roots)
                is_embedding = is_embedding or any(emb_root in target_path for emb_root in config.embeddings_roots)
                
                if is_checkpoint:
                    route_path = f'/checkpoints_static/link_{link_idx["checkpoint"]}/preview'
                    link_idx["checkpoint"] += 1
                elif is_embedding:
                    route_path = f'/embeddings_static/link_{link_idx["embedding"]}/preview'
                    link_idx["embedding"] += 1
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

        # Add static route for locales JSON files
        if os.path.exists(config.i18n_path):
            app.router.add_static('/locales', config.i18n_path)
            logger.info(f"Added static route for locales: /locales -> {config.i18n_path}")

        # Add static route for plugin assets
        app.router.add_static('/loras_static', config.static_path)
        
        # Register default model types with the factory
        register_default_model_types()
        
        # Setup all model routes using the factory
        ModelServiceFactory.setup_all_routes(app)
        
        # Setup non-model-specific routes
        stats_routes = StatsRoutes()
        stats_routes.setup_routes(app)
        RecipeRoutes.setup_routes(app)
        UpdateRoutes.setup_routes(app)  
        MiscRoutes.setup_routes(app)
        ExampleImagesRoutes.setup_routes(app)
        
        # Setup WebSocket routes that are shared across all model types
        app.router.add_get('/ws/fetch-progress', ws_manager.handle_connection)
        app.router.add_get('/ws/download-progress', ws_manager.handle_download_connection)
        app.router.add_get('/ws/init-progress', ws_manager.handle_init_connection)
        
        # Schedule service initialization 
        app.on_startup.append(lambda app: cls._initialize_services())
        
        # Add cleanup
        app.on_shutdown.append(cls._cleanup)
        
        logger.info(f"LoRA Manager: Set up routes for {len(ModelServiceFactory.get_registered_types())} model types: {', '.join(ModelServiceFactory.get_registered_types())}")
    
    @classmethod
    async def _initialize_services(cls):
        """Initialize all services using the ServiceRegistry"""
        try:
            # Initialize CivitaiClient first to ensure it's ready for other services
            await ServiceRegistry.get_civitai_client()

            # Register DownloadManager with ServiceRegistry
            await ServiceRegistry.get_download_manager()

            from .services.metadata_service import initialize_metadata_providers
            await initialize_metadata_providers()
            
            # Initialize WebSocket manager
            await ServiceRegistry.get_websocket_manager()
            
            # Initialize scanners in background
            lora_scanner = await ServiceRegistry.get_lora_scanner()
            checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
            embedding_scanner = await ServiceRegistry.get_embedding_scanner()
            
            # Initialize recipe scanner if needed
            recipe_scanner = await ServiceRegistry.get_recipe_scanner()
            
            # Create low-priority initialization tasks
            init_tasks = [
                asyncio.create_task(lora_scanner.initialize_in_background(), name='lora_cache_init'),
                asyncio.create_task(checkpoint_scanner.initialize_in_background(), name='checkpoint_cache_init'),
                asyncio.create_task(embedding_scanner.initialize_in_background(), name='embedding_cache_init'),
                asyncio.create_task(recipe_scanner.initialize_in_background(), name='recipe_cache_init')
            ]

            await ExampleImagesMigration.check_and_run_migrations()
            
            # Schedule post-initialization tasks to run after scanners complete
            asyncio.create_task(
                cls._run_post_initialization_tasks(init_tasks), 
                name='post_init_tasks'
            )
            
            logger.debug("LoRA Manager: All services initialized and background tasks scheduled")
                
        except Exception as e:
            logger.error(f"LoRA Manager: Error initializing services: {e}", exc_info=True)
    
    @classmethod
    async def _run_post_initialization_tasks(cls, init_tasks):
        """Run post-initialization tasks after all scanners complete"""
        try:
            logger.debug("LoRA Manager: Waiting for scanner initialization to complete...")
            
            # Wait for all scanner initialization tasks to complete
            await asyncio.gather(*init_tasks, return_exceptions=True)

            logger.debug("LoRA Manager: Scanner initialization completed, starting post-initialization tasks...")
            
            # Run post-initialization tasks
            post_tasks = [
                asyncio.create_task(cls._cleanup_backup_files(), name='cleanup_bak_files'),
                asyncio.create_task(cls._cleanup_example_images_folders(), name='cleanup_example_images'),
                # Add more post-initialization tasks here as needed
                # asyncio.create_task(cls._another_post_task(), name='another_task'),
            ]
            
            # Run all post-initialization tasks
            results = await asyncio.gather(*post_tasks, return_exceptions=True)
            
            # Log results
            for i, result in enumerate(results):
                task_name = post_tasks[i].get_name()
                if isinstance(result, Exception):
                    logger.error(f"Post-initialization task '{task_name}' failed: {result}")
                else:
                    logger.debug(f"Post-initialization task '{task_name}' completed successfully")
                    
            logger.debug("LoRA Manager: All post-initialization tasks completed")
            
        except Exception as e:
            logger.error(f"LoRA Manager: Error in post-initialization tasks: {e}", exc_info=True)
    
    @classmethod
    async def _cleanup_backup_files(cls):
        """Clean up .bak files in all model roots"""
        try:
            logger.debug("Starting cleanup of .bak files in model directories...")
            
            # Collect all model roots
            all_roots = set()
            all_roots.update(config.loras_roots)
            all_roots.update(config.base_models_roots) 
            all_roots.update(config.embeddings_roots)
            
            total_deleted = 0
            total_size_freed = 0
            
            for root_path in all_roots:
                if not os.path.exists(root_path):
                    continue
                    
                try:
                    deleted_count, size_freed = await cls._cleanup_backup_files_in_directory(root_path)
                    total_deleted += deleted_count
                    total_size_freed += size_freed
                    
                    if deleted_count > 0:
                        logger.debug(f"Cleaned up {deleted_count} .bak files in {root_path} (freed {size_freed / (1024*1024):.2f} MB)")
                        
                except Exception as e:
                    logger.error(f"Error cleaning up .bak files in {root_path}: {e}")
                    
                # Yield control periodically
                await asyncio.sleep(0.01)
            
            if total_deleted > 0:
                logger.debug(f"Backup cleanup completed: removed {total_deleted} .bak files, freed {total_size_freed / (1024*1024):.2f} MB total")
            else:
                logger.debug("Backup cleanup completed: no .bak files found")

        except Exception as e:
            logger.error(f"Error during backup file cleanup: {e}", exc_info=True)
    
    @classmethod
    async def _cleanup_backup_files_in_directory(cls, directory_path: str):
        """Clean up .bak files in a specific directory recursively
        
        Args:
            directory_path: Path to the directory to clean
            
        Returns:
            Tuple[int, int]: (number of files deleted, total size freed in bytes)
        """
        deleted_count = 0
        size_freed = 0
        visited_paths = set()
        
        def cleanup_recursive(path):
            nonlocal deleted_count, size_freed
            
            try:
                real_path = os.path.realpath(path)
                if real_path in visited_paths:
                    return
                visited_paths.add(real_path)
                
                with os.scandir(path) as it:
                    for entry in it:
                        try:
                            if entry.is_file(follow_symlinks=True) and entry.name.endswith('.bak'):
                                file_size = entry.stat().st_size
                                os.remove(entry.path)
                                deleted_count += 1
                                size_freed += file_size
                                logger.debug(f"Deleted .bak file: {entry.path}")
                                
                            elif entry.is_dir(follow_symlinks=True):
                                cleanup_recursive(entry.path)
                                
                        except Exception as e:
                            logger.warning(f"Could not delete .bak file {entry.path}: {e}")
                            
            except Exception as e:
                logger.error(f"Error scanning directory {path} for .bak files: {e}")
        
        # Run the recursive cleanup in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, cleanup_recursive, directory_path)
        
        return deleted_count, size_freed
    
    @classmethod
    async def _cleanup_example_images_folders(cls):
        """Clean up invalid or empty folders in example images directory"""
        try:
            example_images_path = settings.get('example_images_path')
            if not example_images_path or not os.path.exists(example_images_path):
                logger.debug("Example images path not configured or doesn't exist, skipping cleanup")
                return
            
            logger.debug(f"Starting cleanup of example images folders in: {example_images_path}")
            
            # Get all scanner instances to check hash validity
            lora_scanner = await ServiceRegistry.get_lora_scanner()
            checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
            embedding_scanner = await ServiceRegistry.get_embedding_scanner()
            
            total_folders_checked = 0
            empty_folders_removed = 0
            orphaned_folders_removed = 0
            
            # Scan the example images directory
            try:
                with os.scandir(example_images_path) as it:
                    for entry in it:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                            
                        folder_name = entry.name
                        folder_path = entry.path
                        total_folders_checked += 1
                        
                        try:
                            # Check if folder is empty
                            is_empty = cls._is_folder_empty(folder_path)
                            if is_empty:
                                logger.debug(f"Removing empty example images folder: {folder_name}")
                                await cls._remove_folder_safely(folder_path)
                                empty_folders_removed += 1
                                continue
                            
                            # Check if folder name is a valid SHA256 hash (64 hex characters)
                            if len(folder_name) != 64 or not all(c in '0123456789abcdefABCDEF' for c in folder_name):
                                # Skip non-hash folders to avoid deleting other content
                                logger.debug(f"Skipping non-hash folder: {folder_name}")
                                continue
                            
                            # Check if hash exists in any of the scanners
                            hash_exists = (
                                lora_scanner.has_hash(folder_name) or 
                                checkpoint_scanner.has_hash(folder_name) or 
                                embedding_scanner.has_hash(folder_name)
                            )
                            
                            if not hash_exists:
                                logger.debug(f"Removing example images folder for deleted model: {folder_name}")
                                await cls._remove_folder_safely(folder_path)
                                orphaned_folders_removed += 1
                                continue

                        except Exception as e:
                            logger.error(f"Error processing example images folder {folder_name}: {e}")
                        
                        # Yield control periodically
                        await asyncio.sleep(0.01)
                        
            except Exception as e:
                logger.error(f"Error scanning example images directory: {e}")
                return
            
            # Log final cleanup report
            total_removed = empty_folders_removed + orphaned_folders_removed
            if total_removed > 0:
                logger.info(f"Example images cleanup completed: checked {total_folders_checked} folders, "
                           f"removed {empty_folders_removed} empty folders and {orphaned_folders_removed} "
                           f"folders for deleted models (total: {total_removed} removed)")
            else:
                logger.debug(f"Example images cleanup completed: checked {total_folders_checked} folders, "
                           f"no cleanup needed")
                
        except Exception as e:
            logger.error(f"Error during example images cleanup: {e}", exc_info=True)
    
    @classmethod
    def _is_folder_empty(cls, folder_path: str) -> bool:
        """Check if a folder is empty
        
        Args:
            folder_path: Path to the folder to check
            
        Returns:
            bool: True if folder is empty, False otherwise
        """
        try:
            with os.scandir(folder_path) as it:
                return not any(it)
        except Exception as e:
            logger.debug(f"Error checking if folder is empty {folder_path}: {e}")
            return False
    
    @classmethod
    async def _remove_folder_safely(cls, folder_path: str):
        """Safely remove a folder and all its contents
        
        Args:
            folder_path: Path to the folder to remove
        """
        try:
            import shutil
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.rmtree, folder_path)
        except Exception as e:
            logger.warning(f"Failed to remove folder {folder_path}: {e}")

    @classmethod
    async def _cleanup(cls, app):
        """Cleanup resources using ServiceRegistry"""
        try:
            logger.info("LoRA Manager: Cleaning up services")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
