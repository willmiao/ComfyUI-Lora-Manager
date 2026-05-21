"""Handlers responsible for serving preview assets dynamically."""

from __future__ import annotations

import logging
import mimetypes
import urllib.parse
from pathlib import Path

from aiohttp import web

from ...config import config as global_config

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 256 * 1024  # 256 KB

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
            raise web.HTTPNotFound(text="Preview file not found")

        # Video files: stream manually to avoid Windows native sendfile crash.
        # aiohttp's FileResponse uses _sendfile_native on Windows (IOCP-based),
        # which breaks when the client disconnects mid-transfer — this happens
        # constantly when users scroll through a gallery of animated previews.
        suffix = resolved.suffix.lower()
        if suffix in _VIDEO_EXTENSIONS:
            return await self._stream_file(request, resolved)

        # aiohttp's FileResponse handles range requests and content headers for us.
        return web.FileResponse(path=resolved, chunk_size=_CHUNK_SIZE)

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
