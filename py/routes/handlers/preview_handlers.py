"""Handlers responsible for serving preview assets dynamically."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from pathlib import Path

from aiohttp import web

from ...config import config as global_config
from ...utils.file_responses import platform_file_response_class

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024  # 1 MB — balance between streaming iteration overhead and per-chunk memory

_FileResponse = platform_file_response_class()


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

        if not self._config.is_preview_path_allowed(normalized):
            raise web.HTTPForbidden(text="Preview path is not within an allowed directory")

        candidate = Path(normalized)
        try:
            resolved = candidate.expanduser().resolve(strict=False)
        except Exception as exc:
            logger.debug("Failed to resolve preview path %s: %s", normalized, exc)
            raise web.HTTPBadRequest(text="Unable to resolve preview path") from exc

        if not resolved.is_file():
            logger.debug("Preview file not found at %s", str(resolved))
            if resolved.parent.is_dir():
                # The file is really gone from a reachable directory, so the
                # cached preview_url is stale and can be cleared.
                asyncio.create_task(self._cleanup_stale_preview_url(normalized))
            else:
                # The directory itself is unreachable (drive switched off,
                # unmounted share). Nothing was deleted: keep the cached
                # preview_url so the card recovers when the drive is back.
                logger.debug(
                    "Preview directory unreachable, keeping cached preview_url: %s",
                    str(resolved.parent),
                )
            raise web.HTTPNotFound(text="Preview file not found")

        # FileResponse handles range requests and content headers, and uses
        # kernel sendfile on Linux/macOS (chunked on Windows, see above).
        #
        # Set explicit Cache-Control so the browser can cache video (and image)
        # previews across VirtualScroller recycling cycles. Without this,
        # Chrome does not cache 206 Partial Content responses for <video>
        # elements, causing the same video to be re-downloaded on every scroll.
        resp = _FileResponse(path=resolved, chunk_size=_CHUNK_SIZE)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    async def _cleanup_stale_preview_url(self, normalized_preview_path: str) -> None:
        """Fire-and-forget: clear stale preview_url from all model caches.

        When a preview file is no longer on disk, remove its reference from
        every cached entry so subsequent list API responses return an empty
        ``preview_url``, letting the frontend show the no-preview placeholder.
        """
        try:
            from ...services.service_registry import ServiceRegistry

            for service_name in ("lora_scanner", "checkpoint_scanner", "embedding_scanner"):
                scanner = ServiceRegistry.get_service_sync(service_name)
                if scanner is None or not hasattr(scanner, "_cache"):
                    continue
                cache = getattr(scanner, "_cache", None)
                if cache is None or not hasattr(cache, "clear_preview_by_path"):
                    continue
                cleared = await cache.clear_preview_by_path(normalized_preview_path)
                if cleared and hasattr(scanner, "_persist_current_cache"):
                    await scanner._persist_current_cache()
                    logger.info(
                        "Cleared stale preview_url for %d %s entries (%s)",
                        cleared,
                        service_name,
                        normalized_preview_path,
                    )
        except Exception as exc:
            logger.debug("Failed to clean up stale preview_url: %s", exc)


__all__ = ["PreviewHandler"]
