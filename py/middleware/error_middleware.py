"""JSON error middleware for API routes.

Ensures all responses to /api/* requests return valid JSON that the
browser-extension frontend can JSON.parse() without crashing, even when
the route does not exist (404) or the handler raises an exception (500).

Extension consumers call response.json() unconditionally — an HTML error
page causes ``SyntaxError: unexpected end of data`` that leaks into the
popup UI as a toast notification.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from aiohttp import web

logger = logging.getLogger(__name__)


@web.middleware
async def api_json_error(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.Response]],
) -> web.Response:
    """Return JSON ``{"success": false, "error": "..."}`` for API errors.

    Only intercepts paths starting with ``/api/`` — all other routes
    (frontend pages, static files, WebSocket upgrades) pass through
    unchanged.
    """
    if not request.path.startswith("/api/"):
        return await handler(request)

    try:
        response = await handler(request)
        return response
    except web.HTTPException as exc:
        # Let redirects (301, 302, 307, 308) propagate — they are not errors.
        if exc.status < 400:
            raise

        logger.warning(
            "API %s %s returned HTTP %d: %s",
            request.method,
            request.path,
            exc.status,
            exc.reason,
        )

        return web.json_response(
            {"success": False, "error": f"{exc.status}: {exc.reason}"},
            status=exc.status,
        )
    except Exception as exc:
        logger.error(
            "API %s %s raised unhandled exception: %s",
            request.method,
            request.path,
            exc,
            exc_info=True,
        )

        return web.json_response(
            {
                "success": False,
                "error": f"500: Internal Server Error ({type(exc).__name__})",
            },
            status=500,
        )
