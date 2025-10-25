"""Route registrar for model endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from aiohttp import web


@dataclass(frozen=True)
class RouteDefinition:
    """Declarative definition for a HTTP route."""

    method: str
    path_template: str
    handler_name: str

    def build_path(self, prefix: str) -> str:
        return self.path_template.replace("{prefix}", prefix)


COMMON_ROUTE_DEFINITIONS: tuple[RouteDefinition, ...] = (
    RouteDefinition("GET", "/api/lm/{prefix}/list", "get_models"),
    RouteDefinition("POST", "/api/lm/{prefix}/delete", "delete_model"),
    RouteDefinition("POST", "/api/lm/{prefix}/exclude", "exclude_model"),
    RouteDefinition("POST", "/api/lm/{prefix}/fetch-civitai", "fetch_civitai"),
    RouteDefinition("POST", "/api/lm/{prefix}/fetch-all-civitai", "fetch_all_civitai"),
    RouteDefinition("POST", "/api/lm/{prefix}/relink-civitai", "relink_civitai"),
    RouteDefinition("POST", "/api/lm/{prefix}/replace-preview", "replace_preview"),
    RouteDefinition("POST", "/api/lm/{prefix}/save-metadata", "save_metadata"),
    RouteDefinition("POST", "/api/lm/{prefix}/add-tags", "add_tags"),
    RouteDefinition("POST", "/api/lm/{prefix}/rename", "rename_model"),
    RouteDefinition("POST", "/api/lm/{prefix}/bulk-delete", "bulk_delete_models"),
    RouteDefinition("POST", "/api/lm/{prefix}/verify-duplicates", "verify_duplicates"),
    RouteDefinition("POST", "/api/lm/{prefix}/move_model", "move_model"),
    RouteDefinition("POST", "/api/lm/{prefix}/move_models_bulk", "move_models_bulk"),
    RouteDefinition("GET", "/api/lm/{prefix}/auto-organize", "auto_organize_models"),
    RouteDefinition("POST", "/api/lm/{prefix}/auto-organize", "auto_organize_models"),
    RouteDefinition("GET", "/api/lm/{prefix}/auto-organize-progress", "get_auto_organize_progress"),
    RouteDefinition("GET", "/api/lm/{prefix}/top-tags", "get_top_tags"),
    RouteDefinition("GET", "/api/lm/{prefix}/base-models", "get_base_models"),
    RouteDefinition("GET", "/api/lm/{prefix}/scan", "scan_models"),
    RouteDefinition("GET", "/api/lm/{prefix}/roots", "get_model_roots"),
    RouteDefinition("GET", "/api/lm/{prefix}/folders", "get_folders"),
    RouteDefinition("GET", "/api/lm/{prefix}/folder-tree", "get_folder_tree"),
    RouteDefinition("GET", "/api/lm/{prefix}/unified-folder-tree", "get_unified_folder_tree"),
    RouteDefinition("GET", "/api/lm/{prefix}/find-duplicates", "find_duplicate_models"),
    RouteDefinition("GET", "/api/lm/{prefix}/find-filename-conflicts", "find_filename_conflicts"),
    RouteDefinition("GET", "/api/lm/{prefix}/get-notes", "get_model_notes"),
    RouteDefinition("GET", "/api/lm/{prefix}/preview-url", "get_model_preview_url"),
    RouteDefinition("GET", "/api/lm/{prefix}/civitai-url", "get_model_civitai_url"),
    RouteDefinition("GET", "/api/lm/{prefix}/metadata", "get_model_metadata"),
    RouteDefinition("GET", "/api/lm/{prefix}/model-description", "get_model_description"),
    RouteDefinition("GET", "/api/lm/{prefix}/relative-paths", "get_relative_paths"),
    RouteDefinition("GET", "/api/lm/{prefix}/civitai/versions/{model_id}", "get_civitai_versions"),
    RouteDefinition("GET", "/api/lm/{prefix}/civitai/model/version/{modelVersionId}", "get_civitai_model_by_version"),
    RouteDefinition("GET", "/api/lm/{prefix}/civitai/model/hash/{hash}", "get_civitai_model_by_hash"),
    RouteDefinition("POST", "/api/lm/{prefix}/updates/refresh", "refresh_model_updates"),
    RouteDefinition("POST", "/api/lm/{prefix}/updates/ignore", "set_model_update_ignore"),
    RouteDefinition("POST", "/api/lm/{prefix}/updates/ignore-version", "set_version_update_ignore"),
    RouteDefinition("GET", "/api/lm/{prefix}/updates/status/{model_id}", "get_model_update_status"),
    RouteDefinition("GET", "/api/lm/{prefix}/updates/versions/{model_id}", "get_model_versions"),
    RouteDefinition("POST", "/api/lm/download-model", "download_model"),
    RouteDefinition("GET", "/api/lm/download-model-get", "download_model_get"),
    RouteDefinition("GET", "/api/lm/cancel-download-get", "cancel_download_get"),
    RouteDefinition("GET", "/api/lm/pause-download", "pause_download_get"),
    RouteDefinition("GET", "/api/lm/resume-download", "resume_download_get"),
    RouteDefinition("GET", "/api/lm/download-progress/{download_id}", "get_download_progress"),
    RouteDefinition("GET", "/{prefix}", "handle_models_page"),
)


class ModelRouteRegistrar:
    """Bind declarative definitions to an aiohttp router."""

    _METHOD_MAP = {
        "GET": "add_get",
        "POST": "add_post",
        "PUT": "add_put",
        "DELETE": "add_delete",
    }

    def __init__(self, app: web.Application) -> None:
        self._app = app

    def register_common_routes(
        self,
        prefix: str,
        handler_lookup: Mapping[str, Callable[[web.Request], object]],
        *,
        definitions: Iterable[RouteDefinition] = COMMON_ROUTE_DEFINITIONS,
    ) -> None:
        for definition in definitions:
            self._bind_route(definition.method, definition.build_path(prefix), handler_lookup[definition.handler_name])

    def add_route(self, method: str, path: str, handler: Callable) -> None:
        self._bind_route(method, path, handler)

    def add_prefixed_route(self, method: str, path_template: str, prefix: str, handler: Callable) -> None:
        self._bind_route(method, path_template.replace("{prefix}", prefix), handler)

    def _bind_route(self, method: str, path: str, handler: Callable) -> None:
        add_method_name = self._METHOD_MAP[method.upper()]
        add_method = getattr(self._app.router, add_method_name)
        add_method(path, handler)

