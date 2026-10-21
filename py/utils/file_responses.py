"""File response helpers with a Windows-safe chunked transport."""

from __future__ import annotations

import sys

from aiohttp import web


class ChunkedFileResponse(web.FileResponse):
    """FileResponse that skips loop.sendfile and always sends in chunks.

    On Windows, aiohttp's native sendfile (TransmitFile over IOCP) is suspected
    of wedging the event loop and leaving an unkillable process when clients
    abort transfers while scrolling through previews. Range, ETag and header
    handling stay with FileResponse.
    """

    async def _sendfile(self, request, fobj, offset, count):
        writer = await web.StreamResponse.prepare(self, request)
        try:
            return await self._sendfile_fallback(writer, fobj, offset, count)
        except ConnectionError:
            # Client went away mid-transfer, which is routine when scrolling fast.
            return writer


def platform_file_response_class():
    """Return the FileResponse class appropriate for the current platform.

    Windows gets ChunkedFileResponse (no native sendfile); Linux and macOS
    keep kernel sendfile. Routes registered via ``add_static`` build plain
    ``FileResponse`` internally, so swapping them over requires replacing the
    static resource's handler rather than just passing this class.
    """
    if sys.platform == "win32":
        return ChunkedFileResponse
    return web.FileResponse


__all__ = ["ChunkedFileResponse", "platform_file_response_class"]
