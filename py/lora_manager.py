import asyncio
import os
from server import PromptServer # type: ignore
from .config import config
from .routes.lora_routes import LoraRoutes
from .routes.api_routes import ApiRoutes
from .routes.recipe_routes import RecipeRoutes
from .routes.checkpoints_routes import CheckpointsRoutes
from .services.lora_scanner import LoraScanner
from .services.recipe_scanner import RecipeScanner
from .services.file_monitor import LoraFileMonitor
from .services.lora_cache import LoraCache
from .services.recipe_cache import RecipeCache
import logging

logger = logging.getLogger(__name__)

class LoraManager:
    """Main entry point for LoRA Manager plugin"""
    
    @classmethod
    def add_routes(cls):
        """Initialize and register all routes"""
        app = PromptServer.instance.app

        added_targets = set()  # 用于跟踪已添加的目标路径
        
        # Add static routes for each lora root
        for idx, root in enumerate(config.loras_roots, start=1):
            preview_path = f'/loras_static/root{idx}/preview'
            
            real_root = root
            if root in config._path_mappings.values():
                for target, link in config._path_mappings.items():
                    if link == root:
                        real_root = target
                        break
            # 为原始路径添加静态路由
            app.router.add_static(preview_path, real_root)
            logger.info(f"Added static route {preview_path} -> {real_root}")
            
            # 记录路由映射
            config.add_route_mapping(real_root, preview_path)
            added_targets.add(real_root)
        
        # 为符号链接的目标路径添加额外的静态路由
        link_idx = 1
        
        for target_path, link_path in config._path_mappings.items():
            if target_path not in added_targets:
                route_path = f'/loras_static/link_{link_idx}/preview'
                app.router.add_static(route_path, target_path)
                logger.info(f"Added static route for link target {route_path} -> {target_path}")
                config.add_route_mapping(target_path, route_path)
                added_targets.add(target_path)
                link_idx += 1
        
        # Add static route for plugin assets
        app.router.add_static('/loras_static', config.static_path)
        
        # Setup feature routes
        routes = LoraRoutes()
        checkpoints_routes = CheckpointsRoutes()
        
        # Setup file monitoring
        monitor = LoraFileMonitor(routes.scanner, config.loras_roots)
        monitor.start()
        
        routes.setup_routes(app)
        checkpoints_routes.setup_routes(app)
        ApiRoutes.setup_routes(app, monitor)
        RecipeRoutes.setup_routes(app)
        
        # Store monitor in app for cleanup
        app['lora_monitor'] = monitor
        
        # Schedule cache initialization using the application's startup handler
        app.on_startup.append(lambda app: cls._schedule_cache_init(routes.scanner, routes.recipe_scanner))
        
        # Add cleanup
        app.on_shutdown.append(cls._cleanup)
        app.on_shutdown.append(ApiRoutes.cleanup)
    
    @classmethod
    async def _schedule_cache_init(cls, scanner: LoraScanner, recipe_scanner: RecipeScanner):
        """Schedule cache initialization in the running event loop"""
        try:
            # 创建低优先级的初始化任务
            lora_task = asyncio.create_task(cls._initialize_lora_cache(scanner), name='lora_cache_init')
            
            # Schedule recipe cache initialization with a delay to let lora scanner initialize first
            recipe_task = asyncio.create_task(cls._initialize_recipe_cache(recipe_scanner, delay=2), name='recipe_cache_init')
        except Exception as e:
            logger.error(f"LoRA Manager: Error scheduling cache initialization: {e}")
    
    @classmethod
    async def _initialize_lora_cache(cls, scanner: LoraScanner):
        """Initialize lora cache in background"""
        try:
            # 设置初始缓存占位
            scanner._cache = LoraCache(
                raw_data=[],
                sorted_by_name=[],
                sorted_by_date=[],
                folders=[]
            )
            
            # 分阶段加载缓存
            await scanner.get_cached_data(force_refresh=True)
        except Exception as e:
            logger.error(f"LoRA Manager: Error initializing lora cache: {e}")
    
    @classmethod
    async def _initialize_recipe_cache(cls, scanner: RecipeScanner, delay: float = 2.0):
        """Initialize recipe cache in background with a delay"""
        try:
            # Wait for the specified delay to let lora scanner initialize first
            await asyncio.sleep(delay)
            
            # Set initial empty cache
            scanner._cache = RecipeCache(
                raw_data=[],
                sorted_by_name=[],
                sorted_by_date=[]
            )
            
            # Force refresh to load the actual data
            await scanner.get_cached_data(force_refresh=True)
        except Exception as e:
            logger.error(f"LoRA Manager: Error initializing recipe cache: {e}")
    
    @classmethod
    async def _cleanup(cls, app):
        """Cleanup resources"""
        if 'lora_monitor' in app:
            app['lora_monitor'].stop()
