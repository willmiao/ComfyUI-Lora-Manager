"""Route registrar for miscellaneous endpoints.

This module mirrors the model route registrar architecture so that
miscellaneous endpoints share a consistent registration flow.
"""

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from aiohttp import web


@dataclass(frozen=True)
class RouteDefinition:
    """Declarative definition for a HTTP route."""

    method: str
    path: str
    handler_name: str


MISC_ROUTE_DEFINITIONS: tuple[RouteDefinition, ...] = (
    RouteDefinition("GET", "/api/lm/settings", "get_settings"),
    RouteDefinition("POST", "/api/lm/settings", "update_settings"),
    RouteDefinition("GET", "/api/lm/priority-tags", "get_priority_tags"),
    RouteDefinition("GET", "/api/lm/settings/libraries", "get_settings_libraries"),
    RouteDefinition("POST", "/api/lm/settings/libraries/activate", "activate_library"),
    RouteDefinition("GET", "/api/lm/health-check", "health_check"),
    RouteDefinition("POST", "/api/lm/open-file-location", "open_file_location"),
    RouteDefinition("POST", "/api/lm/update-usage-stats", "update_usage_stats"),
    RouteDefinition("GET", "/api/lm/get-usage-stats", "get_usage_stats"),
    RouteDefinition("POST", "/api/lm/update-lora-code", "update_lora_code"),
    RouteDefinition("GET", "/api/lm/trained-words", "get_trained_words"),
    RouteDefinition("GET", "/api/lm/model-example-files", "get_model_example_files"),
    RouteDefinition("POST", "/api/lm/register-nodes", "register_nodes"),
    RouteDefinition("POST", "/api/lm/update-node-widget", "update_node_widget"),
    RouteDefinition("GET", "/api/lm/get-registry", "get_registry"),
    RouteDefinition("GET", "/api/lm/check-model-exists", "check_model_exists"),
    RouteDefinition("GET", "/api/lm/civitai/user-models", "get_civitai_user_models"),
    RouteDefinition("POST", "/api/lm/download-metadata-archive", "download_metadata_archive"),
    RouteDefinition("POST", "/api/lm/remove-metadata-archive", "remove_metadata_archive"),
    RouteDefinition("GET", "/api/lm/metadata-archive-status", "get_metadata_archive_status"),
    RouteDefinition("GET", "/api/lm/model-versions-status", "get_model_versions_status"),
)


class MiscRouteRegistrar:
    """Bind miscellaneous route definitions to an aiohttp router."""

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
        definitions: Iterable[RouteDefinition] = MISC_ROUTE_DEFINITIONS,
    ) -> None:
        for definition in definitions:
            self._bind(definition.method, definition.path, handler_lookup[definition.handler_name])

    def _bind(self, method: str, path: str, handler: Callable) -> None:
        add_method_name = self._METHOD_MAP[method.upper()]
        add_method = getattr(self._app.router, add_method_name)
        add_method(path, handler)
