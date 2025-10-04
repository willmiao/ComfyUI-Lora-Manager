"""Route controller for preview asset delivery."""

from __future__ import annotations

from aiohttp import web

from .handlers.preview_handlers import PreviewHandler


class PreviewRoutes:
    """Register routes that expose preview assets."""

    def __init__(self, *, handler: PreviewHandler | None = None) -> None:
        self._handler = handler or PreviewHandler()

    @classmethod
    def setup_routes(cls, app: web.Application) -> None:
        controller = cls()
        controller.register(app)

    def register(self, app: web.Application) -> None:
        app.router.add_get('/api/lm/previews', self._handler.serve_preview)


__all__ = ["PreviewRoutes"]
