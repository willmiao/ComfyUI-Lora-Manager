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
    RouteDefinition("GET", "/api/lm/doctor/diagnostics", "get_doctor_diagnostics"),
    RouteDefinition("POST", "/api/lm/doctor/repair-cache", "repair_doctor_cache"),
    RouteDefinition("POST", "/api/lm/doctor/resolve-filename-conflicts", "resolve_doctor_filename_conflicts"),
    RouteDefinition("POST", "/api/lm/doctor/export-bundle", "export_doctor_bundle"),
    RouteDefinition("GET", "/api/lm/priority-tags", "get_priority_tags"),
    RouteDefinition("GET", "/api/lm/settings/libraries", "get_settings_libraries"),
    RouteDefinition("POST", "/api/lm/settings/libraries/activate", "activate_library"),
    RouteDefinition("GET", "/api/lm/health-check", "health_check"),
    RouteDefinition("GET", "/api/lm/supporters", "get_supporters"),
    RouteDefinition("GET", "/api/lm/wildcards/search", "search_wildcards"),
    RouteDefinition("POST", "/api/lm/wildcards/open-location", "open_wildcards_location"),
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
    RouteDefinition("GET", "/api/lm/check-models-exist", "check_models_exist"),
    RouteDefinition(
        "GET",
        "/api/lm/model-version-download-status",
        "get_model_version_download_status",
    ),
    RouteDefinition(
        "POST",
        "/api/lm/model-version-download-status",
        "set_model_version_download_status",
    ),
    RouteDefinition(
        "GET",
        "/api/lm/set-model-version-download-status",
        "set_model_version_download_status",
    ),
    RouteDefinition("GET", "/api/lm/civitai/user-models", "get_civitai_user_models"),
    RouteDefinition(
        "POST", "/api/lm/download-metadata-archive", "download_metadata_archive"
    ),
    RouteDefinition(
        "POST", "/api/lm/remove-metadata-archive", "remove_metadata_archive"
    ),
    RouteDefinition(
        "GET", "/api/lm/metadata-archive-status", "get_metadata_archive_status"
    ),
    RouteDefinition("GET", "/api/lm/backup/status", "get_backup_status"),
    RouteDefinition("POST", "/api/lm/backup/export", "export_backup"),
    RouteDefinition("POST", "/api/lm/backup/import", "import_backup"),
    RouteDefinition("POST", "/api/lm/backup/open-location", "open_backup_location"),
    RouteDefinition(
        "GET", "/api/lm/model-versions-status", "get_model_versions_status"
    ),
    RouteDefinition("POST", "/api/lm/settings/open-location", "open_settings_location"),
    RouteDefinition("GET", "/api/lm/custom-words/search", "search_custom_words"),
    RouteDefinition("GET", "/api/lm/example-workflows", "get_example_workflows"),
    RouteDefinition(
        "GET", "/api/lm/example-workflows/{filename}", "get_example_workflow"
    ),
    # Base model management routes
    RouteDefinition("GET", "/api/lm/base-models", "get_base_models"),
    RouteDefinition("POST", "/api/lm/base-models/refresh", "refresh_base_models"),
    RouteDefinition(
        "GET", "/api/lm/base-models/categories", "get_base_model_categories"
    ),
    RouteDefinition(
        "GET", "/api/lm/base-models/cache-status", "get_base_model_cache_status"
    ),
    RouteDefinition(
        "GET", "/api/lm/delete-model-version", "delete_model_version"
    ),
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
            self._bind(
                definition.method,
                definition.path,
                handler_lookup[definition.handler_name],
            )

    def _bind(self, method: str, path: str, handler: Callable) -> None:
        add_method_name = self._METHOD_MAP[method.upper()]
        add_method = getattr(self._app.router, add_method_name)
        add_method(path, handler)
