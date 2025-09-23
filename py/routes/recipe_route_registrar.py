"""Route registrar for recipe endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from aiohttp import web


@dataclass(frozen=True)
class RouteDefinition:
    """Declarative definition for a recipe HTTP route."""

    method: str
    path: str
    handler_name: str


ROUTE_DEFINITIONS: tuple[RouteDefinition, ...] = (
    RouteDefinition("GET", "/loras/recipes", "render_page"),
    RouteDefinition("GET", "/api/lm/recipes", "list_recipes"),
    RouteDefinition("GET", "/api/lm/recipe/{recipe_id}", "get_recipe"),
    RouteDefinition("POST", "/api/lm/recipes/analyze-image", "analyze_uploaded_image"),
    RouteDefinition("POST", "/api/lm/recipes/analyze-local-image", "analyze_local_image"),
    RouteDefinition("POST", "/api/lm/recipes/save", "save_recipe"),
    RouteDefinition("DELETE", "/api/lm/recipe/{recipe_id}", "delete_recipe"),
    RouteDefinition("GET", "/api/lm/recipes/top-tags", "get_top_tags"),
    RouteDefinition("GET", "/api/lm/recipes/base-models", "get_base_models"),
    RouteDefinition("GET", "/api/lm/recipe/{recipe_id}/share", "share_recipe"),
    RouteDefinition("GET", "/api/lm/recipe/{recipe_id}/share/download", "download_shared_recipe"),
    RouteDefinition("GET", "/api/lm/recipe/{recipe_id}/syntax", "get_recipe_syntax"),
    RouteDefinition("PUT", "/api/lm/recipe/{recipe_id}/update", "update_recipe"),
    RouteDefinition("POST", "/api/lm/recipe/lora/reconnect", "reconnect_lora"),
    RouteDefinition("GET", "/api/lm/recipes/find-duplicates", "find_duplicates"),
    RouteDefinition("POST", "/api/lm/recipes/bulk-delete", "bulk_delete"),
    RouteDefinition("POST", "/api/lm/recipes/save-from-widget", "save_recipe_from_widget"),
    RouteDefinition("GET", "/api/lm/recipes/for-lora", "get_recipes_for_lora"),
    RouteDefinition("GET", "/api/lm/recipes/scan", "scan_recipes"),
)


class RecipeRouteRegistrar:
    """Bind declarative recipe definitions to an aiohttp router."""

    _METHOD_MAP = {
        "GET": "add_get",
        "POST": "add_post",
        "PUT": "add_put",
        "DELETE": "add_delete",
    }

    def __init__(self, app: web.Application) -> None:
        self._app = app

    def register_routes(self, handler_lookup: Mapping[str, Callable[[web.Request], object]]) -> None:
        for definition in ROUTE_DEFINITIONS:
            handler = handler_lookup[definition.handler_name]
            self._bind_route(definition.method, definition.path, handler)

    def _bind_route(self, method: str, path: str, handler: Callable) -> None:
        add_method_name = self._METHOD_MAP[method.upper()]
        add_method = getattr(self._app.router, add_method_name)
        add_method(path, handler)

