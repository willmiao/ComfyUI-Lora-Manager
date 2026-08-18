import logging
import os
from typing import Any, Dict, List, Set
from aiohttp import web

from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar
from ..services.checkpoint_service import CheckpointService
from ..services.service_registry import ServiceRegistry
from ..config import config
from ..utils.utils import _format_model_name_for_comfyui

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
    
    def setup_routes(self, app: web.Application, prefix: str = "checkpoints"):
        """Setup Checkpoint routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())

        # Setup common routes with 'checkpoints' prefix (includes page route)
        super().setup_routes(app, prefix)
    
    def setup_specific_routes(self, registrar: ModelRouteRegistrar, prefix: str):
        """Setup Checkpoint-specific routes"""
        # Checkpoint info by name
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/info/{name}', prefix, self.get_checkpoint_info)

        # Checkpoint roots and Unet roots
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/checkpoints_roots', prefix, self.get_checkpoints_roots)
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/unet_roots', prefix, self.get_unet_roots)

        # Name/base_model pool for the Random Checkpoint/Unet Loader nodes
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/loader-pool', prefix, self.get_loader_pool)
    
    async def get_loader_pool(self, request: web.Request) -> web.Response:
        """Return ComfyUI-formatted model names with their base_model.

        Backing data for the Random Checkpoint/Unet Loader nodes: the front-end
        filters the ckpt_name/unet_name combo options by base_model using this
        pool, so control_after_generate randomizes within the narrowed set.
        """
        try:
            sub_type = request.query.get("sub_type", "checkpoint")
            if sub_type not in ("checkpoint", "diffusion_model"):
                return web.json_response({"error": "invalid sub_type"}, status=400)
            scanner = await ServiceRegistry.get_checkpoint_scanner()
            cache = await scanner.get_cached_data()
            model_roots = scanner.get_model_roots()
            items: List[Dict[str, str]] = []
            for item in cache.raw_data:
                if item.get("sub_type") != sub_type:
                    continue
                file_path = item.get("file_path", "")
                if not file_path or not os.path.exists(file_path):
                    continue
                formatted_name = _format_model_name_for_comfyui(file_path, model_roots)
                if formatted_name:
                    items.append(
                        {
                            "name": formatted_name,
                            "base_model": item.get("base_model", "") or "",
                        }
                    )
            items.sort(key=lambda x: x["name"])
            return web.json_response({"items": items})
        except Exception as e:
            logger.error(f"Error getting loader pool: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    def _validate_civitai_model_type(self, model_type: str) -> bool:
        """Validate CivitAI model type for Checkpoint"""
        return model_type.lower() == 'checkpoint'
    
    def _get_expected_model_types(self) -> str:
        """Get expected model types string for error messages"""
        return "Checkpoint"

    def _parse_specific_params(self, request: web.Request) -> Dict[str, Any]:
        """Parse Checkpoint-specific parameters"""
        params: Dict[str, Any] = {}

        if 'checkpoint_hash' in request.query:
            params['hash_filters'] = {'single_hash': request.query['checkpoint_hash'].lower()}
        elif 'checkpoint_hashes' in request.query:
            params['hash_filters'] = {
                'multiple_hashes': [h.lower() for h in request.query['checkpoint_hashes'].split(',')]
            }

        return params
    
    async def get_checkpoint_info(self, request: web.Request) -> web.Response:
        """Get detailed information for a specific checkpoint by name"""
        try:
            name = request.match_info.get('name', '')
            checkpoint_info = await self.service.get_model_info_by_name(name)  # pyright: ignore[reportAttributeAccessIssue]
            
            if checkpoint_info:
                return web.json_response(checkpoint_info)
            else:
                return web.json_response({"error": "Checkpoint not found"}, status=404)
                
        except Exception as e:
            logger.error(f"Error in get_checkpoint_info: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def get_checkpoints_roots(self, request: web.Request) -> web.Response:
        """Return the list of checkpoint roots from config (including extra paths)"""
        try:
            # Merge checkpoints_roots with extra_checkpoints_roots, preserving order and removing duplicates
            roots: List[str] = []
            roots.extend(config.checkpoints_roots or [])
            roots.extend(config.extra_checkpoints_roots or [])
            # Remove duplicates while preserving order
            seen: set[str] = set()
            unique_roots: List[str] = []
            for root in roots:
                if root and root not in seen:
                    seen.add(root)
                    unique_roots.append(root)
            return web.json_response({
                "success": True,
                "roots": unique_roots
            })
        except Exception as e:
            logger.error(f"Error getting checkpoint roots: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def get_unet_roots(self, request: web.Request) -> web.Response:
        """Return the list of unet roots from config (including extra paths)"""
        try:
            # Merge unet_roots with extra_unet_roots, preserving order and removing duplicates
            roots: List[str] = []
            roots.extend(config.unet_roots or [])
            roots.extend(config.extra_unet_roots or [])
            # Remove duplicates while preserving order
            seen: set[str] = set()
            unique_roots: List[str] = []
            for root in roots:
                if root and root not in seen:
                    seen.add(root)
                    unique_roots.append(root)
            return web.json_response({
                "success": True,
                "roots": unique_roots
            })
        except Exception as e:
            logger.error(f"Error getting unet roots: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)
