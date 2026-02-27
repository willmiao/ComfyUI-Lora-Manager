import asyncio
import sys
import os
import logging
from .utils.logging_config import setup_logging

# Check if we're in standalone mode
standalone_mode = os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1" or os.environ.get("HF_HUB_DISABLE_TELEMETRY", "0") == "0"

# Only setup logging prefix if not in standalone mode
if not standalone_mode:
    setup_logging()

from server import PromptServer # type: ignore

from .config import config
from .services.model_service_factory import ModelServiceFactory, register_default_model_types
from .routes.recipe_routes import RecipeRoutes
from .routes.stats_routes import StatsRoutes
from .routes.update_routes import UpdateRoutes
from .routes.misc_routes import MiscRoutes
from .routes.preview_routes import PreviewRoutes
from .routes.example_images_routes import ExampleImagesRoutes
from .services.service_registry import ServiceRegistry
from .services.settings_manager import get_settings_manager
from .utils.example_images_migration import ExampleImagesMigration
from .services.websocket_manager import ws_manager
from .services.example_images_cleanup_service import ExampleImagesCleanupService
from .middleware.csp_middleware import relax_csp_for_remote_media

logger = logging.getLogger(__name__)

HEADER_SIZE_LIMIT = 16384


def _sanitize_size_limit(value):
    """Return a non-negative integer size for ``handler_args`` comparisons."""

    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return 0
    return coerced if coerced >= 0 else 0


class _SettingsProxy:
    def __init__(self):
        self._manager = None

    def _resolve(self):
        if self._manager is None:
            self._manager = get_settings_manager()
        return self._manager

    def get(self, *args, **kwargs):
        return self._resolve().get(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._resolve(), item)


settings = _SettingsProxy()

class LoraManager:
    """Main entry point for LoRA Manager plugin"""
    
    @classmethod
    def add_routes(cls):
        """Initialize and register all routes using the new refactored architecture"""
        app = PromptServer.instance.app

        if relax_csp_for_remote_media not in app.middlewares:
            # Ensure CSP relaxer executes after ComfyUI's block_external_middleware so it can
            # see and extend the restrictive header instead of being overwritten by it.
            block_middleware_index = next(
                (
                    idx
                    for idx, middleware in enumerate(app.middlewares)
                    if getattr(middleware, "__name__", "") == "block_external_middleware"
                ),
                None,
            )

            if block_middleware_index is None:
                app.middlewares.append(relax_csp_for_remote_media)
            else:
                app.middlewares.insert(block_middleware_index, relax_csp_for_remote_media)

        # Increase allowed header sizes so browsers with large localhost cookie
        # jars (multiple UIs on 127.0.0.1) don't trip aiohttp's 8KB default
        # limits. Cookies for unrelated apps are still sent to the plugin and
        # may otherwise raise LineTooLong errors when the request parser reads
        # them. Preserve any previously configured handler arguments while
        # ensuring our minimum sizes are applied.
        handler_args = getattr(app, "_handler_args", {}) or {}
        updated_handler_args = dict(handler_args)
        updated_handler_args["max_field_size"] = max(
            _sanitize_size_limit(handler_args.get("max_field_size", 0)),
            HEADER_SIZE_LIMIT,
        )
        updated_handler_args["max_line_size"] = max(
            _sanitize_size_limit(handler_args.get("max_line_size", 0)),
            HEADER_SIZE_LIMIT,
        )
        app._handler_args = updated_handler_args

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

        # Add static route for example images if the path exists in settings
        example_images_path = settings.get('example_images_path')
        logger.info(f"Example images path: {example_images_path}")
        if example_images_path and os.path.exists(example_images_path):
            app.router.add_static('/example_images_static', example_images_path)
            logger.info(f"Added static route for example images: /example_images_static -> {example_images_path}")

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
        ExampleImagesRoutes.setup_routes(app, ws_manager=ws_manager)
        PreviewRoutes.setup_routes(app)
        
        # Setup WebSocket routes that are shared across all model types
        app.router.add_get('/ws/fetch-progress', ws_manager.handle_connection)
        app.router.add_get('/ws/download-progress', ws_manager.handle_download_connection)
        app.router.add_get('/ws/init-progress', ws_manager.handle_init_connection)
        
        # Schedule service initialization 
        app.on_startup.append(lambda app: cls._initialize_services())
        
        # Add cleanup
        app.on_shutdown.append(cls._cleanup)
        
    @classmethod
    async def _initialize_services(cls):
        """Initialize all services using the ServiceRegistry"""
        try:
            # Apply library settings to load extra folder paths before scanning
            # Only apply if extra paths haven't been loaded yet (preserves test mocks)
            try:
                from .services.settings_manager import get_settings_manager

                settings_manager = get_settings_manager()
                library_name = settings_manager.get_active_library_name()
                libraries = settings_manager.get_libraries()
                if library_name and library_name in libraries:
                    library_config = libraries[library_name]
                    # Only apply settings if extra paths are not already configured
                    # This preserves values set by tests via monkeypatch
                    extra_paths = library_config.get("extra_folder_paths", {})
                    has_extra_paths = (
                        config.extra_loras_roots
                        or config.extra_checkpoints_roots
                        or config.extra_unet_roots
                        or config.extra_embeddings_roots
                    )
                    if not has_extra_paths and any(extra_paths.values()):
                        config.apply_library_settings(library_config)
                        logger.info(
                            "Applied library settings for '%s' with extra paths: loras=%s, checkpoints=%s, embeddings=%s",
                            library_name,
                            extra_paths.get("loras", []),
                            extra_paths.get("checkpoints", []),
                            extra_paths.get("embeddings", []),
                        )
            except Exception as exc:
                logger.warning("Failed to apply library settings during initialization: %s", exc)

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
        """Invoke the example images cleanup service for manual execution."""
        try:
            service = ExampleImagesCleanupService()
            result = await service.cleanup_example_image_folders()

            if result.get('success'):
                logger.debug(
                    "Manual example images cleanup completed: moved=%s",
                    result.get('moved_total'),
                )
            elif result.get('partial_success'):
                logger.warning(
                    "Manual example images cleanup partially succeeded: moved=%s failures=%s",
                    result.get('moved_total'),
                    result.get('move_failures'),
                )
            else:
                logger.debug(
                    "Manual example images cleanup skipped or failed: %s",
                    result.get('error', 'no changes'),
                )

            return result

        except Exception as e:  # pragma: no cover - defensive guard
            logger.error(f"Error during example images cleanup: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'error_code': 'unexpected_error',
            }

    @classmethod
    async def _cleanup(cls, app):
        """Cleanup resources using ServiceRegistry"""
        try:
            logger.info("LoRA Manager: Cleaning up services")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
