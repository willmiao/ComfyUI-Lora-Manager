"""Handlers responsible for serving preview assets dynamically."""

from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path

from aiohttp import web

from ...config import config as global_config

logger = logging.getLogger(__name__)


class PreviewHandler:
    """Serve preview assets for the active library at request time."""

    def __init__(self, *, config=global_config) -> None:
        self._config = config

    async def serve_preview(self, request: web.Request) -> web.StreamResponse:
        """Return the preview file referenced by the encoded ``path`` query."""

        raw_path = request.query.get("path", "")
        if not raw_path:
            raise web.HTTPBadRequest(text="Missing 'path' query parameter")

        try:
            decoded_path = urllib.parse.unquote(raw_path)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("Failed to decode preview path %s: %s", raw_path, exc)
            raise web.HTTPBadRequest(text="Invalid preview path encoding") from exc

        normalized = decoded_path.replace("\\", "/")
        candidate = Path(normalized)
        try:
            resolved = candidate.expanduser().resolve(strict=False)
        except Exception as exc:
            logger.debug("Failed to resolve preview path %s: %s", normalized, exc)
            raise web.HTTPBadRequest(text="Unable to resolve preview path") from exc

        resolved_str = str(resolved)
        if not self._config.is_preview_path_allowed(resolved_str):
            logger.debug("Rejected preview outside allowed roots: %s", resolved_str)
            raise web.HTTPForbidden(text="Preview path is not within an allowed directory")

        if not resolved.is_file():
            logger.debug("Preview file not found at %s", resolved_str)
            raise web.HTTPNotFound(text="Preview file not found")

        # aiohttp's FileResponse handles range requests and content headers for us.
        return web.FileResponse(path=resolved, chunk_size=256 * 1024)


__all__ = ["PreviewHandler"]
