"""Route registrar for batch recipe import endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from aiohttp import web


@dataclass(frozen=True)
class RouteDefinition:
    """Declarative definition for a batch import HTTP route."""

    method: str
    path: str
    handler_name: str


BATCH_IMPORT_ROUTE_DEFINITIONS: tuple[RouteDefinition, ...] = (
    RouteDefinition("POST", "/api/lm/recipes/batch/import-directory", "import_from_directory"),
    RouteDefinition("POST", "/api/lm/recipes/batch/import-urls", "import_from_urls"),
    RouteDefinition("GET", "/api/lm/recipes/batch/status", "get_batch_status"),
)


@dataclass(frozen=True)
class BatchImportHandlerSet:
    """Group of handlers providing batch import route implementations."""

    handler: object

    def to_route_mapping(self) -> Mapping[str, Callable[[web.Request], web.StreamResponse]]:
        """Expose handler coroutines keyed by registrar handler names."""

        return {
            "import_from_directory": self.handler.import_from_directory,
            "import_from_urls": self.handler.import_from_urls,
            "get_batch_status": self.handler.get_batch_status,
        }


def register_batch_import_routes(
    app: web.Application,
    handler_set: BatchImportHandlerSet,
) -> None:
    """Register batch import routes on the application."""

    route_mapping = handler_set.to_route_mapping()

    for route_def in BATCH_IMPORT_ROUTE_DEFINITIONS:
        handler = route_mapping.get(route_def.handler_name)
        if handler is None:
            raise ValueError(f"Handler not found: {route_def.handler_name}")

        app.router.add_route(route_def.method, route_def.path, handler)
