"""Route controller for the pending-delete undo endpoint."""

from __future__ import annotations

from aiohttp import web

from .handlers.pending_delete_handler import PendingDeleteHandler


class PendingDeleteRoutes:
    """Shared route controller mirroring MiscRoutes/UpdateRoutes.

    Registered ONCE per mode (py/lora_manager.py, standalone.py); NEVER through
    the per-model-type ModelRouteRegistrar, which is instantiated per model
    type and would register this non-prefixed route three times.
    """

    @staticmethod
    def setup_routes(app: web.Application) -> None:
        """Register the shared undo-delete endpoint."""
        handler = PendingDeleteHandler()
        _ = app.router.add_post("/api/lm/undo-delete", handler.undo_delete)


__all__ = ["PendingDeleteRoutes"]
