"""Handlers responsible for serving preview assets dynamically."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import urllib.parse
from pathlib import Path

from aiohttp import web

from ...config import config as global_config

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024  # 1 MB — balance between streaming iteration overhead and per-chunk memory

# Video file extensions that bypass native sendfile on Windows
# to avoid IOCP/ProactorEventLoop crashes during client disconnect.
_VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov", ".avi", ".mkv"})


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
            asyncio.create_task(self._cleanup_stale_preview_url(normalized))
            raise web.HTTPNotFound(text="Preview file not found")

        # aiohttp's FileResponse handles range requests, content headers, and
        # uses kernel sendfile (zero-copy DMA) on Linux/macOS. On Windows it
        # uses IOCP-based _sendfile_native which can crash when the client
        # disconnects mid-transfer during fast scrolling. The _stream_file()
        # fallback is kept for a future compat toggle.
        #
        # Set explicit Cache-Control so the browser can cache video (and image)
        # previews across VirtualScroller recycling cycles. Without this,
        # Chrome does not cache 206 Partial Content responses for <video>
        # elements, causing the same video to be re-downloaded on every scroll.
        resp = web.FileResponse(path=resolved, chunk_size=_CHUNK_SIZE)
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

    async def _stream_file(
        self, request: web.Request, path: Path
    ) -> web.StreamResponse:
        """Stream a file chunk-by-chunk, bypassing native sendfile.

        This avoids the Windows IOCP ``_sendfile_native`` crash that occurs
        when the client disconnects during a large file transfer.
        """
        content_type, _ = mimetypes.guess_type(str(path))
        if content_type is None:
            content_type = "application/octet-stream"

        file_size = path.stat().st_size
        resp = web.StreamResponse()
        resp.content_type = content_type
        resp.content_length = file_size

        # Allow browser caching: video previews rarely change during a session.
        # The frontend already appends ?t={version} to bust cache on update.
        resp.headers["Cache-Control"] = "public, max-age=86400"

        await resp.prepare(request)

        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    await resp.write(chunk)
        except (ConnectionResetError, ConnectionAbortedError):
            # Client disconnected during streaming — expected when scrolling
            # rapidly through a library with animated previews.
            pass
        except OSError as exc:
            logger.debug("I/O error streaming preview %s: %s", path, exc)

        return resp


__all__ = ["PreviewHandler"]
