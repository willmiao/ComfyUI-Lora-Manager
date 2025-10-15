"""Route registrar for example image endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from aiohttp import web


@dataclass(frozen=True)
class RouteDefinition:
    """Declarative configuration for a HTTP route."""

    method: str
    path: str
    handler_name: str


ROUTE_DEFINITIONS: tuple[RouteDefinition, ...] = (
    RouteDefinition("POST", "/api/lm/download-example-images", "download_example_images"),
    RouteDefinition("POST", "/api/lm/import-example-images", "import_example_images"),
    RouteDefinition("GET", "/api/lm/example-images-status", "get_example_images_status"),
    RouteDefinition("POST", "/api/lm/pause-example-images", "pause_example_images"),
    RouteDefinition("POST", "/api/lm/resume-example-images", "resume_example_images"),
    RouteDefinition("POST", "/api/lm/stop-example-images", "stop_example_images"),
    RouteDefinition("POST", "/api/lm/open-example-images-folder", "open_example_images_folder"),
    RouteDefinition("GET", "/api/lm/example-image-files", "get_example_image_files"),
    RouteDefinition("GET", "/api/lm/has-example-images", "has_example_images"),
    RouteDefinition("POST", "/api/lm/delete-example-image", "delete_example_image"),
    RouteDefinition("POST", "/api/lm/force-download-example-images", "force_download_example_images"),
    RouteDefinition("POST", "/api/lm/cleanup-example-image-folders", "cleanup_example_image_folders"),
)


class ExampleImagesRouteRegistrar:
    """Bind declarative example image routes to an aiohttp router."""

    _METHOD_MAP = {
        "GET": "add_get",
        "POST": "add_post",
        "PUT": "add_put",
        "DELETE": "add_delete",
    }

    def __init__(self, app: web.Application) -> None:
        self._app = app

    def register_routes(
        self,
        handler_lookup: Mapping[str, Callable[[web.Request], object]],
        *,
        definitions: Iterable[RouteDefinition] = ROUTE_DEFINITIONS,
    ) -> None:
        """Register each route definition using the supplied handlers."""

        for definition in definitions:
            handler = handler_lookup[definition.handler_name]
            self._bind_route(definition.method, definition.path, handler)

    def _bind_route(self, method: str, path: str, handler: Callable[[web.Request], object]) -> None:
        add_method_name = self._METHOD_MAP[method.upper()]
        add_method = getattr(self._app.router, add_method_name)
        add_method(path, handler)
