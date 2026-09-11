"""HTTP handler for download target routing decisions."""

from __future__ import annotations

import json
import logging

from aiohttp import web

from ...services.download_routing import is_diffusion_model_download

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

        is_diffusion = is_diffusion_model_download(
            model_type,
            file_types=(str(t) for t in file_types),
            base_model=base_model,
        )
        return web.json_response(
            {
                "success": True,
                "is_diffusion_model": is_diffusion,
                "root_kind": "unet" if is_diffusion else model_type,
            }
        )
