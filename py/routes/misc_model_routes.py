import logging
from typing import Dict
from aiohttp import web

from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar
from ..services.misc_service import MiscService
from ..services.service_registry import ServiceRegistry
from ..config import config

logger = logging.getLogger(__name__)

class MiscModelRoutes(BaseModelRoutes):
    """Misc-specific route controller (VAE, Upscaler)"""

    def __init__(self):
        """Initialize Misc routes with Misc service"""
        super().__init__()
        self.template_name = "misc.html"

    async def initialize_services(self):
        """Initialize services from ServiceRegistry"""
        misc_scanner = await ServiceRegistry.get_misc_scanner()
        update_service = await ServiceRegistry.get_model_update_service()
        self.service = MiscService(misc_scanner, update_service=update_service)
        self.set_model_update_service(update_service)

        # Attach service dependencies
        self.attach_service(self.service)

    def setup_routes(self, app: web.Application):
        """Setup Misc routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())

        # Setup common routes with 'misc' prefix (includes page route)
        super().setup_routes(app, 'misc')

    def setup_specific_routes(self, registrar: ModelRouteRegistrar, prefix: str):
        """Setup Misc-specific routes"""
        # Misc info by name
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/info/{name}', prefix, self.get_misc_info)

        # VAE roots and Upscaler roots
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/vae_roots', prefix, self.get_vae_roots)
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/upscaler_roots', prefix, self.get_upscaler_roots)

    def _validate_civitai_model_type(self, model_type: str) -> bool:
        """Validate CivitAI model type for Misc (VAE or Upscaler)"""
        return model_type.lower() in ['vae', 'upscaler']

    def _get_expected_model_types(self) -> str:
        """Get expected model types string for error messages"""
        return "VAE or Upscaler"

    def _parse_specific_params(self, request: web.Request) -> Dict:
        """Parse Misc-specific parameters"""
        params: Dict = {}

        if 'misc_hash' in request.query:
            params['hash_filters'] = {'single_hash': request.query['misc_hash'].lower()}
        elif 'misc_hashes' in request.query:
            params['hash_filters'] = {
                'multiple_hashes': [h.lower() for h in request.query['misc_hashes'].split(',')]
            }

        return params

    async def get_misc_info(self, request: web.Request) -> web.Response:
        """Get detailed information for a specific misc model by name"""
        try:
            name = request.match_info.get('name', '')
            misc_info = await self.service.get_model_info_by_name(name)

            if misc_info:
                return web.json_response(misc_info)
            else:
                return web.json_response({"error": "Misc model not found"}, status=404)

        except Exception as e:
            logger.error(f"Error in get_misc_info: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def get_vae_roots(self, request: web.Request) -> web.Response:
        """Return the list of VAE roots from config"""
        try:
            roots = config.vae_roots
            return web.json_response({
                "success": True,
                "roots": roots
            })
        except Exception as e:
            logger.error(f"Error getting VAE roots: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def get_upscaler_roots(self, request: web.Request) -> web.Response:
        """Return the list of upscaler roots from config"""
        try:
            roots = config.upscaler_roots
            return web.json_response({
                "success": True,
                "roots": roots
            })
        except Exception as e:
            logger.error(f"Error getting upscaler roots: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)
