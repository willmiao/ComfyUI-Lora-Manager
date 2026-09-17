import logging
import os
from typing import Any, Dict, List
from aiohttp import web

from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar
from ..config import config
from ..services.other_model_service import OtherModelService
from ..services.service_registry import ServiceRegistry
from ..utils.constants import (
    CIVITAI_TYPE_TO_OTHER_SUB_TYPE,
    OTHER_MODEL_FOLDER_SUBTYPES,
    VALID_OTHER_CIVITAI_TYPES,
)

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
        # Other-model roots grouped by sub_type (text_encoders + legacy clip
        # are aggregated under text_encoder)
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/roots_by_subtype', prefix, self.get_roots_by_subtype)

    def _validate_civitai_model_type(self, model_type: str) -> bool:
        """Validate CivitAI model type for other models.

        Accepts retired CivitAI types (CLIP, CLIPVision) as well — grandfathered
        models on CivitAI still carry them. Types whose sub_type is currently
        disabled (or every type while the opt-in feature is off) are rejected.
        """
        normalized = (model_type or "").strip().lower()
        if normalized not in VALID_OTHER_CIVITAI_TYPES:
            return False
        if not self._settings.is_other_models_enabled():
            return False

        sub_type = CIVITAI_TYPE_TO_OTHER_SUB_TYPE.get(normalized)
        if sub_type is None:
            # CivitAI "Other" has no sub_type of its own; it is only usable
            # while at least one sub_type is enabled.
            return bool(self._settings.get_enabled_other_sub_types())
        return self._settings.is_other_sub_type_enabled(sub_type)

    def _get_page_context_provider(self):
        """Expose the opt-in feature state to the Other Models page template."""
        return self._page_context_for_other

    def _page_context_for_other(self, request: web.Request) -> Dict[str, Any]:
        if not self._settings.is_other_models_enabled():
            return {"other_disabled": True, "other_no_paths": False}

        # Enabled but nothing to scan: folder paths for the managed sub_types
        # resolved to no existing folder. Render an actionable empty state
        # instead of an apparently broken empty grid.
        standalone_mode = os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"
        context = {
            "other_disabled": False,
            "other_no_paths": not bool(config.other_roots),
            "standalone_mode": standalone_mode,
        }
        if standalone_mode:
            # The settings UI cannot edit primary folder_paths, so the empty
            # state must point at the actual file the user has to edit.
            context["settings_file"] = getattr(self._settings, "settings_file", "") or ""
        return context

    def _get_expected_model_types(self) -> str:
        """Get expected model types string for error messages"""
        return "VAE, Upscaler, TextEncoder, CLIPVision, Controlnet, or Other"

    def _parse_specific_params(self, request: web.Request) -> Dict[str, Any]:
        """Parse other-model-specific parameters (none in Phase 1)."""
        return {}

    async def get_roots_by_subtype(self, request: web.Request) -> web.Response:
        """Return other-model roots grouped by sub_type.

        Aggregates the per-folder_paths-key roots from config
        (``text_encoders`` and the legacy ``clip`` key both land under
        ``text_encoder``).
        """
        try:
            roots_by_subtype: Dict[str, List[str]] = {}
            for key, roots in (config.other_folder_roots or {}).items():
                sub_type = OTHER_MODEL_FOLDER_SUBTYPES.get(key)
                if not sub_type:
                    continue
                bucket = roots_by_subtype.setdefault(sub_type, [])
                for root in roots:
                    if root and root not in bucket:
                        bucket.append(root)
            return web.json_response(
                {"success": True, "roots_by_subtype": roots_by_subtype}
            )
        except Exception as e:
            logger.error(f"Error getting other roots by sub_type: {e}", exc_info=True)
            return web.json_response(
                {"success": False, "error": str(e)}, status=500
            )

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
