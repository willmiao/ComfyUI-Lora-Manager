import logging
from typing import Any, Dict
from aiohttp import web

from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar
from ..services.other_model_service import OtherModelService
from ..services.service_registry import ServiceRegistry
from ..utils.constants import VALID_OTHER_CIVITAI_TYPES

logger = logging.getLogger(__name__)


class OtherRoutes(BaseModelRoutes):
    """Other-model-specific route controller (VAE, upscaler, text encoder, ...)"""

    def __init__(self):
        """Initialize Other-model routes with OtherModel service"""
        super().__init__()
        self.template_name = "other.html"

    async def initialize_services(self):
        """Initialize services from ServiceRegistry"""
        other_scanner = await ServiceRegistry.get_other_scanner()
        update_service = await ServiceRegistry.get_model_update_service()
        self.service = OtherModelService(other_scanner, update_service=update_service)
        self.set_model_update_service(update_service)

        # Attach service dependencies
        self.attach_service(self.service)

    def setup_routes(self, app: web.Application, prefix: str = "other"):
        """Setup Other-model routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())

        # Setup common routes with 'other' prefix (includes page route)
        super().setup_routes(app, prefix)

    def setup_specific_routes(self, registrar: ModelRouteRegistrar, prefix: str):
        """Setup Other-model-specific routes"""
        # Other-model info by name
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/info/{name}', prefix, self.get_other_model_info)

    def _validate_civitai_model_type(self, model_type: str) -> bool:
        """Validate CivitAI model type for other models.

        Accepts retired CivitAI types (CLIP, CLIPVision) as well — grandfathered
        models on CivitAI still carry them.
        """
        return model_type.lower() in VALID_OTHER_CIVITAI_TYPES

    def _get_expected_model_types(self) -> str:
        """Get expected model types string for error messages"""
        return "VAE, Upscaler, TextEncoder, CLIPVision, Controlnet, or Other"

    def _parse_specific_params(self, request: web.Request) -> Dict[str, Any]:
        """Parse other-model-specific parameters (none in Phase 1)."""
        return {}

    async def get_other_model_info(self, request: web.Request) -> web.Response:
        """Get detailed information for a specific other model by name"""
        try:
            name = request.match_info.get('name', '')
            model_info = await self.service.get_model_info_by_name(name)  # pyright: ignore[reportAttributeAccessIssue]

            if model_info:
                return web.json_response(model_info)
            else:
                return web.json_response({"error": "Model not found"}, status=404)

        except Exception as e:
            logger.error(f"Error in get_other_model_info: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
