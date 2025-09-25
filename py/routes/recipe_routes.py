"""Concrete recipe route configuration."""

from aiohttp import web

from .base_recipe_routes import BaseRecipeRoutes
from .recipe_route_registrar import RecipeRouteRegistrar


class RecipeRoutes(BaseRecipeRoutes):
    """API route handlers for Recipe management."""

    template_name = "recipes.html"

    @classmethod
    def setup_routes(cls, app: web.Application):
        """Register API routes using the declarative registrar."""

        routes = cls()
        registrar = RecipeRouteRegistrar(app)
        registrar.register_routes(routes.to_route_mapping())
        routes.register_startup_hooks(app)
