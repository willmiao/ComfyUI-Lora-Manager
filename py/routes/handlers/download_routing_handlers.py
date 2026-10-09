"""HTTP handler for download target routing decisions."""

from __future__ import annotations

import json
import logging

from aiohttp import web

from ...services.download_routing import (
    MODEL_TYPE_TO_DEFAULT_ROOT_SETTING,
    MODEL_TYPE_TO_ROOT_RULE_KEY,
    is_diffusion_model_download,
    match_download_root_rule,
    resolve_other_download_sub_type,
)
from ...utils.constants import VALID_OTHER_CIVITAI_TYPES

logger = logging.getLogger(__name__)


class DownloadRoutingHandler:
    """Expose the download-time checkpoint/diffusion-model routing decision.

    The web UI calls this when the user reaches the download location step
    so the root dropdown offers the same root set (checkpoint vs unet) that
    the download manager would pick for ``use_default_paths``.
    """

    async def get_download_routing(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"success": False, "error": "Invalid JSON payload"}, status=400
            )

        model_type = payload.get("model_type", "")
        base_model = payload.get("base_model") or ""
        file_types = payload.get("file_types") or []
        tags = payload.get("tags") or []
        selected_file_type = payload.get("selected_file_type")

        if not isinstance(model_type, str) or not model_type:
            return web.json_response(
                {"success": False, "error": "model_type is required"}, status=400
            )
        if not isinstance(base_model, str) or not isinstance(file_types, list):
            return web.json_response(
                {
                    "success": False,
                    "error": "base_model must be a string and file_types a list",
                },
                status=400,
            )
        if not isinstance(tags, list):
            tags = []
        if selected_file_type is not None and not isinstance(selected_file_type, str):
            return web.json_response(
                {"success": False, "error": "selected_file_type must be a string"},
                status=400,
            )

        # CivitAI ModelType.UNet downloads go through the checkpoint branch,
        # same as in the download manager.
        if model_type.lower() == "unet":
            model_type = "checkpoint"

        if model_type.lower() in VALID_OTHER_CIVITAI_TYPES:
            from ...services.settings_manager import get_settings_manager

            settings = get_settings_manager()
            if not settings.is_other_models_enabled():
                # Opt-in feature is off: never auto-route, the UI falls back to
                # manual folder selection and the download manager rejects it.
                return web.json_response(
                    {
                        "success": True,
                        "root_kind": "other",
                        "sub_type": None,
                        "disabled": True,
                        "reason": "other_models_disabled",
                    }
                )

            sub_type = resolve_other_download_sub_type(
                model_type,
                file_types=(str(t) for t in file_types),
                selected_file_type=selected_file_type,
            )
            if sub_type and not settings.is_other_sub_type_enabled(sub_type):
                return web.json_response(
                    {
                        "success": True,
                        "root_kind": "other",
                        "sub_type": None,
                        "disabled": True,
                        "reason": "other_sub_type_disabled",
                        "requested_sub_type": sub_type,
                    }
                )
            return web.json_response(
                {
                    "success": True,
                    "root_kind": "other",
                    "sub_type": sub_type,
                }
            )

        from ...services.settings_manager import get_settings_manager

        settings = get_settings_manager()
        is_diffusion = is_diffusion_model_download(
            model_type,
            file_types=(str(t) for t in file_types),
            base_model=base_model,
            unknown_base_model_default=settings.get(
                "unknown_base_model_routing", "diffusion_model"
            ),
        )
        root_kind = "unet" if is_diffusion else model_type

        # Apply download_root_rules against the final root kind so the
        # location-step preview matches where the download will land.
        resolved_root = ""
        matched_rule = None
        rule_key = MODEL_TYPE_TO_ROOT_RULE_KEY.get(root_kind.lower())
        default_root_setting = MODEL_TYPE_TO_DEFAULT_ROOT_SETTING.get(root_kind.lower())
        if rule_key and default_root_setting:
            default_root = settings.get(default_root_setting) or ""
            if isinstance(default_root, str) and default_root:
                rule = match_download_root_rule(
                    settings.get_download_root_rules().get(rule_key),
                    base_model,
                    tags,
                )
                if rule is not None:
                    resolved_root = rule["root"]
                    matched_rule = {
                        "match_type": rule.get("match_type"),
                        "match": list(rule.get("match") or []),
                    }
                else:
                    resolved_root = default_root
        return web.json_response(
            {
                "success": True,
                "is_diffusion_model": is_diffusion,
                "root_kind": root_kind,
                "resolved_root": resolved_root,
                "matched_rule": matched_rule,
            }
        )
