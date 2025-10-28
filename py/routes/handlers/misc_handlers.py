"""Handlers for miscellaneous routes.

The legacy :mod:`py.routes.misc_routes` module bundled HTTP wiring and
business logic in a single class.  This module mirrors the model route
architecture by splitting the responsibilities into dedicated handler
objects that can be composed by the route controller.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Mapping, Protocol

from aiohttp import web

from ...config import config
from ...services.metadata_service import (
    get_metadata_archive_manager,
    update_metadata_providers,
)
from ...services.service_registry import ServiceRegistry
from ...services.settings_manager import get_settings_manager
from ...services.websocket_manager import ws_manager
from ...services.downloader import get_downloader
from ...services.errors import ResourceNotFoundError
from ...utils.constants import (
    CIVITAI_USER_MODEL_TYPES,
    DEFAULT_NODE_COLOR,
    NODE_TYPES,
    SUPPORTED_MEDIA_EXTENSIONS,
    VALID_LORA_TYPES,
)
from ...utils.civitai_utils import rewrite_preview_url
from ...utils.example_images_paths import is_valid_example_images_root
from ...utils.lora_metadata import extract_trained_words
from ...utils.usage_stats import UsageStats

logger = logging.getLogger(__name__)


class PromptServerProtocol(Protocol):
    """Subset of PromptServer used by the handlers."""

    instance: "PromptServerProtocol"

    def send_sync(self, event: str, payload: dict) -> None:  # pragma: no cover - protocol
        ...


class DownloaderProtocol(Protocol):
    async def refresh_session(self) -> None:  # pragma: no cover - protocol
        ...


class UsageStatsFactory(Protocol):
    def __call__(self) -> UsageStats:  # pragma: no cover - protocol
        ...


class MetadataProviderProtocol(Protocol):
    async def get_model_versions(self, model_id: int) -> dict | None:  # pragma: no cover - protocol
        ...


class MetadataArchiveManagerProtocol(Protocol):
    async def download_and_extract_database(
        self, progress_callback: Callable[[str, str], None]
    ) -> bool:  # pragma: no cover - protocol
        ...

    async def remove_database(self) -> bool:  # pragma: no cover - protocol
        ...

    def is_database_available(self) -> bool:  # pragma: no cover - protocol
        ...

    def get_database_path(self) -> str | None:  # pragma: no cover - protocol
        ...


class NodeRegistry:
    """Thread-safe registry for tracking LoRA nodes in active workflows."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._nodes: Dict[str, dict] = {}
        self._registry_updated = asyncio.Event()

    async def register_nodes(self, nodes: list[dict]) -> None:
        async with self._lock:
            self._nodes.clear()
            for node in nodes:
                node_id = node["node_id"]
                graph_id = str(node["graph_id"])
                unique_id = f"{graph_id}:{node_id}"
                node_type = node.get("type", "")
                type_id = NODE_TYPES.get(node_type, 0)
                bgcolor = node.get("bgcolor") or DEFAULT_NODE_COLOR
                raw_capabilities = node.get("capabilities")
                capabilities: dict = {}
                if isinstance(raw_capabilities, dict):
                    capabilities = dict(raw_capabilities)

                raw_widget_names: list | None = node.get("widget_names")
                if not isinstance(raw_widget_names, list):
                    capability_widget_names = capabilities.get("widget_names")
                    raw_widget_names = capability_widget_names if isinstance(capability_widget_names, list) else None

                widget_names: list[str] = []
                if isinstance(raw_widget_names, list):
                    widget_names = [
                        str(widget_name)
                        for widget_name in raw_widget_names
                        if isinstance(widget_name, str) and widget_name
                    ]

                if widget_names:
                    capabilities["widget_names"] = widget_names
                else:
                    capabilities.pop("widget_names", None)

                if "supports_lora" in capabilities:
                    capabilities["supports_lora"] = bool(capabilities["supports_lora"])

                comfy_class = node.get("comfy_class")
                if not isinstance(comfy_class, str) or not comfy_class:
                    comfy_class = node_type if isinstance(node_type, str) else None

                self._nodes[unique_id] = {
                    "id": node_id,
                    "graph_id": graph_id,
                    "graph_name": node.get("graph_name"),
                    "unique_id": unique_id,
                    "bgcolor": bgcolor,
                    "title": node.get("title"),
                    "type": type_id,
                    "type_name": node_type,
                    "comfy_class": comfy_class,
                    "capabilities": capabilities,
                    "widget_names": widget_names,
                }
            logger.debug("Registered %s nodes in registry", len(nodes))
            self._registry_updated.set()

    async def get_registry(self) -> dict:
        async with self._lock:
            return {
                "nodes": dict(self._nodes),
                "node_count": len(self._nodes),
            }

    async def wait_for_update(self, timeout: float = 1.0) -> bool:
        self._registry_updated.clear()
        try:
            await asyncio.wait_for(self._registry_updated.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False


class HealthCheckHandler:
    async def health_check(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})


class SettingsHandler:
    """Sync settings between backend and frontend."""

    _SYNC_KEYS = (
        "civitai_api_key",
        "default_lora_root",
        "default_checkpoint_root",
        "default_embedding_root",
        "base_model_path_mappings",
        "download_path_templates",
        "enable_metadata_archive_db",
        "language",
        "proxy_enabled",
        "proxy_type",
        "proxy_host",
        "proxy_port",
        "proxy_username",
        "proxy_password",
        "example_images_path",
        "optimize_example_images",
        "auto_download_example_images",
        "blur_mature_content",
        "autoplay_on_hover",
        "display_density",
        "card_info_display",
        "include_trigger_words",
        "show_only_sfw",
        "compact_mode",
        "priority_tags",
        "model_card_footer_action",
        "model_name_display",
    )

    _PROXY_KEYS = {"proxy_enabled", "proxy_host", "proxy_port", "proxy_username", "proxy_password", "proxy_type"}

    def __init__(
        self,
        *,
        settings_service=None,
        metadata_provider_updater: Callable[[], Awaitable[None]] = update_metadata_providers,
        downloader_factory: Callable[[], Awaitable[DownloaderProtocol]] = get_downloader,
    ) -> None:
        self._settings = settings_service or get_settings_manager()
        self._metadata_provider_updater = metadata_provider_updater
        self._downloader_factory = downloader_factory

    async def get_libraries(self, request: web.Request) -> web.Response:
        """Return the registered libraries and the active selection."""

        try:
            snapshot = config.get_library_registry_snapshot()
            libraries = snapshot.get("libraries", {})
            active_library = snapshot.get("active_library", "")
            return web.json_response(
                {
                    "success": True,
                    "libraries": libraries,
                    "active_library": active_library,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error getting library registry: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_settings(self, request: web.Request) -> web.Response:
        try:
            response_data = {}
            for key in self._SYNC_KEYS:
                value = self._settings.get(key)
                if value is not None:
                    response_data[key] = value
            settings_file = getattr(self._settings, "settings_file", None)
            if settings_file:
                response_data["settings_file"] = settings_file
            messages_getter = getattr(self._settings, "get_startup_messages", None)
            messages = list(messages_getter()) if callable(messages_getter) else []
            return web.json_response({
                "success": True,
                "settings": response_data,
                "messages": messages,
            })
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error getting settings: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_priority_tags(self, request: web.Request) -> web.Response:
        try:
            suggestions = self._settings.get_priority_tag_suggestions()
            return web.json_response({"success": True, "tags": suggestions})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error getting priority tags: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def activate_library(self, request: web.Request) -> web.Response:
        """Activate the selected library."""

        try:
            data = await request.json()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error parsing activate library request: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": "Invalid JSON payload"}, status=400)

        library_name = data.get("library") or data.get("library_name")
        if not isinstance(library_name, str) or not library_name.strip():
            return web.json_response(
                {"success": False, "error": "Library name is required"}, status=400
            )

        try:
            normalized_name = library_name.strip()
            self._settings.activate_library(normalized_name)
            snapshot = config.get_library_registry_snapshot()
            libraries = snapshot.get("libraries", {})
            active_library = snapshot.get("active_library", "")
            return web.json_response(
                {
                    "success": True,
                    "active_library": active_library,
                    "libraries": libraries,
                }
            )
        except KeyError as exc:
            logger.debug("Attempted to activate unknown library '%s'", library_name)
            return web.json_response({"success": False, "error": str(exc)}, status=404)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error activating library '%s': %s", library_name, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def update_settings(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            proxy_changed = False

            for key, value in data.items():
                if value == self._settings.get(key):
                    continue

                if key == "example_images_path" and value:
                    validation_error = self._validate_example_images_path(value)
                    if validation_error:
                        return web.json_response({"success": False, "error": validation_error})

                if value == "__DELETE__" and key in ("proxy_username", "proxy_password"):
                    self._settings.delete(key)
                else:
                    self._settings.set(key, value)

                if key == "enable_metadata_archive_db":
                    await self._metadata_provider_updater()

                if key in self._PROXY_KEYS:
                    proxy_changed = True

            if proxy_changed:
                downloader = await self._downloader_factory()
                await downloader.refresh_session()

            return web.json_response({"success": True})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error updating settings: %s", exc, exc_info=True)
            return web.Response(status=500, text=str(exc))

    def _validate_example_images_path(self, folder_path: str) -> str | None:
        if not os.path.exists(folder_path):
            return f"Path does not exist: {folder_path}"
        if not os.path.isdir(folder_path):
            return "Please set a dedicated folder for example images."
        if not self._is_dedicated_example_images_folder(folder_path):
            return "Please set a dedicated folder for example images."
        return None

    def _is_dedicated_example_images_folder(self, folder_path: str) -> bool:
        return is_valid_example_images_root(folder_path)


class UsageStatsHandler:
    def __init__(self, usage_stats_factory: UsageStatsFactory = UsageStats) -> None:
        self._usage_stats_factory = usage_stats_factory

    async def update_usage_stats(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                return web.json_response({"success": False, "error": "Missing prompt_id"}, status=400)
            usage_stats = self._usage_stats_factory()
            await usage_stats.process_execution(prompt_id)
            return web.json_response({"success": True})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to update usage stats: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_usage_stats(self, request: web.Request) -> web.Response:
        try:
            usage_stats = self._usage_stats_factory()
            stats = await usage_stats.get_stats()
            stats_response = {"success": True, "data": stats, "format_version": 2}
            return web.json_response(stats_response)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to get usage stats: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class LoraCodeHandler:
    def __init__(self, prompt_server: type[PromptServerProtocol]) -> None:
        self._prompt_server = prompt_server

    async def update_lora_code(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            node_ids = data.get("node_ids")
            lora_code = data.get("lora_code", "")
            mode = data.get("mode", "append")

            if not lora_code:
                return web.json_response({"success": False, "error": "Missing lora_code parameter"}, status=400)

            results = []
            if node_ids is None:
                try:
                    self._prompt_server.instance.send_sync(
                        "lora_code_update", {"id": -1, "lora_code": lora_code, "mode": mode}
                    )
                    results.append({"node_id": "broadcast", "success": True})
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error("Error broadcasting lora code: %s", exc)
                    results.append({"node_id": "broadcast", "success": False, "error": str(exc)})
            else:
                for entry in node_ids:
                    node_identifier = entry
                    graph_identifier = None
                    if isinstance(entry, dict):
                        node_identifier = entry.get("node_id")
                        graph_identifier = entry.get("graph_id")

                    if node_identifier is None:
                        results.append(
                            {
                                "node_id": node_identifier,
                                "graph_id": graph_identifier,
                                "success": False,
                                "error": "Missing node_id parameter",
                            }
                        )
                        continue

                    try:
                        parsed_node_id = int(node_identifier)
                    except (TypeError, ValueError):
                        parsed_node_id = node_identifier

                    payload = {
                        "id": parsed_node_id,
                        "lora_code": lora_code,
                        "mode": mode,
                    }

                    if graph_identifier is not None:
                        payload["graph_id"] = str(graph_identifier)

                    try:
                        self._prompt_server.instance.send_sync(
                            "lora_code_update",
                            payload,
                        )
                        results.append(
                            {
                                "node_id": parsed_node_id,
                                "graph_id": payload.get("graph_id"),
                                "success": True,
                            }
                        )
                    except Exception as exc:  # pragma: no cover - defensive logging
                        logger.error(
                            "Error sending lora code to node %s (graph %s): %s",
                            parsed_node_id,
                            graph_identifier,
                            exc,
                        )
                        results.append(
                            {
                                "node_id": parsed_node_id,
                                "graph_id": payload.get("graph_id"),
                                "success": False,
                                "error": str(exc),
                            }
                        )

            return web.json_response({"success": True, "results": results})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to update lora code: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class TrainedWordsHandler:
    async def get_trained_words(self, request: web.Request) -> web.Response:
        try:
            file_path = request.query.get("file_path")
            if not file_path:
                return web.json_response({"success": False, "error": "Missing file_path parameter"}, status=400)
            if not os.path.exists(file_path):
                return web.json_response({"success": False, "error": "File not found"}, status=404)
            if not file_path.endswith(".safetensors"):
                return web.json_response({"success": False, "error": "File must be a safetensors file"}, status=400)

            trained_words, class_tokens = await extract_trained_words(file_path)
            return web.json_response(
                {
                    "success": True,
                    "trained_words": trained_words,
                    "class_tokens": class_tokens,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to get trained words: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class ModelExampleFilesHandler:
    async def get_model_example_files(self, request: web.Request) -> web.Response:
        try:
            model_path = request.query.get("model_path")
            if not model_path:
                return web.json_response({"success": False, "error": "Missing model_path parameter"}, status=400)
            model_dir = os.path.dirname(model_path)
            if not os.path.exists(model_dir):
                return web.json_response({"success": False, "error": "Model directory not found"}, status=404)

            base_name = os.path.splitext(os.path.basename(model_path))[0]
            files = []
            pattern = f"{base_name}.example."
            for file in os.listdir(model_dir):
                if not file.startswith(pattern):
                    continue
                file_full_path = os.path.join(model_dir, file)
                if not os.path.isfile(file_full_path):
                    continue
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext not in SUPPORTED_MEDIA_EXTENSIONS["images"] and file_ext not in SUPPORTED_MEDIA_EXTENSIONS["videos"]:
                    continue
                try:
                    index = int(file[len(pattern) :].split(".")[0])
                except (ValueError, IndexError):
                    index = float("inf")
                static_url = config.get_preview_static_url(file_full_path)
                files.append(
                    {
                        "name": file,
                        "path": static_url,
                        "extension": file_ext,
                        "is_video": file_ext in SUPPORTED_MEDIA_EXTENSIONS["videos"],
                        "index": index,
                    }
                )

            files.sort(key=lambda item: item["index"])
            for file in files:
                file.pop("index", None)

            return web.json_response({"success": True, "files": files})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to get model example files: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


@dataclass
class ServiceRegistryAdapter:
    get_lora_scanner: Callable[[], Awaitable]
    get_checkpoint_scanner: Callable[[], Awaitable]
    get_embedding_scanner: Callable[[], Awaitable]


class ModelLibraryHandler:
    def __init__(self, service_registry: ServiceRegistryAdapter, metadata_provider_factory: Callable[[], Awaitable[MetadataProviderProtocol | None]]) -> None:
        self._service_registry = service_registry
        self._metadata_provider_factory = metadata_provider_factory

    async def check_model_exists(self, request: web.Request) -> web.Response:
        try:
            model_id_str = request.query.get("modelId")
            model_version_id_str = request.query.get("modelVersionId")
            if not model_id_str:
                return web.json_response({"success": False, "error": "Missing required parameter: modelId"}, status=400)
            try:
                model_id = int(model_id_str)
            except ValueError:
                return web.json_response({"success": False, "error": "Parameter modelId must be an integer"}, status=400)

            lora_scanner = await self._service_registry.get_lora_scanner()
            checkpoint_scanner = await self._service_registry.get_checkpoint_scanner()
            embedding_scanner = await self._service_registry.get_embedding_scanner()

            if model_version_id_str:
                try:
                    model_version_id = int(model_version_id_str)
                except ValueError:
                    return web.json_response({"success": False, "error": "Parameter modelVersionId must be an integer"}, status=400)

                exists = False
                model_type = None
                if await lora_scanner.check_model_version_exists(model_version_id):
                    exists = True
                    model_type = "lora"
                elif checkpoint_scanner and await checkpoint_scanner.check_model_version_exists(model_version_id):
                    exists = True
                    model_type = "checkpoint"
                elif embedding_scanner and await embedding_scanner.check_model_version_exists(model_version_id):
                    exists = True
                    model_type = "embedding"

                return web.json_response({"success": True, "exists": exists, "modelType": model_type if exists else None})

            lora_versions = await lora_scanner.get_model_versions_by_id(model_id)
            checkpoint_versions = []
            embedding_versions = []
            if not lora_versions and checkpoint_scanner:
                checkpoint_versions = await checkpoint_scanner.get_model_versions_by_id(model_id)
            if not lora_versions and not checkpoint_versions and embedding_scanner:
                embedding_versions = await embedding_scanner.get_model_versions_by_id(model_id)

            model_type = None
            versions = []
            if lora_versions:
                model_type = "lora"
                versions = lora_versions
            elif checkpoint_versions:
                model_type = "checkpoint"
                versions = checkpoint_versions
            elif embedding_versions:
                model_type = "embedding"
                versions = embedding_versions

            return web.json_response({"success": True, "modelType": model_type, "versions": versions})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to check model existence: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_model_versions_status(self, request: web.Request) -> web.Response:
        try:
            model_id_str = request.query.get("modelId")
            if not model_id_str:
                return web.json_response({"success": False, "error": "Missing required parameter: modelId"}, status=400)
            try:
                model_id = int(model_id_str)
            except ValueError:
                return web.json_response({"success": False, "error": "Parameter modelId must be an integer"}, status=400)

            metadata_provider = await self._metadata_provider_factory()
            if not metadata_provider:
                return web.json_response({"success": False, "error": "Metadata provider not available"}, status=503)

            try:
                response = await metadata_provider.get_model_versions(model_id)
            except ResourceNotFoundError:
                return web.json_response({"success": False, "error": "Model not found"}, status=404)
            if not response or not response.get("modelVersions"):
                return web.json_response({"success": False, "error": "Model not found"}, status=404)

            versions = response.get("modelVersions", [])
            model_name = response.get("name", "")
            model_type = response.get("type", "").lower()

            scanner = None
            normalized_type = None
            if model_type in {"lora", "locon", "dora"}:
                scanner = await self._service_registry.get_lora_scanner()
                normalized_type = "lora"
            elif model_type == "checkpoint":
                scanner = await self._service_registry.get_checkpoint_scanner()
                normalized_type = "checkpoint"
            elif model_type == "textualinversion":
                scanner = await self._service_registry.get_embedding_scanner()
                normalized_type = "embedding"
            else:
                return web.json_response({"success": False, "error": f'Model type "{model_type}" is not supported'}, status=400)

            if not scanner:
                return web.json_response({"success": False, "error": f'Scanner for type "{normalized_type}" is not available'}, status=503)

            local_versions = await scanner.get_model_versions_by_id(model_id)
            local_version_ids = {version["versionId"] for version in local_versions}

            enriched_versions = []
            for version in versions:
                version_id = version.get("id")
                enriched_versions.append(
                    {
                        "id": version_id,
                        "name": version.get("name", ""),
                        "thumbnailUrl": version.get("images")[0]["url"] if version.get("images") else None,
                        "inLibrary": version_id in local_version_ids,
                    }
                )

            return web.json_response(
                {
                    "success": True,
                    "modelId": model_id,
                    "modelName": model_name,
                    "modelType": model_type,
                    "versions": enriched_versions,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to get model versions status: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_civitai_user_models(self, request: web.Request) -> web.Response:
        try:
            username = request.query.get("username")
            if not username:
                return web.json_response({"success": False, "error": "Missing required parameter: username"}, status=400)

            metadata_provider = await self._metadata_provider_factory()
            if not metadata_provider:
                return web.json_response({"success": False, "error": "Metadata provider not available"}, status=503)

            try:
                models = await metadata_provider.get_user_models(username)
            except NotImplementedError:
                return web.json_response({"success": False, "error": "Metadata provider does not support user model queries"}, status=501)

            if models is None:
                return web.json_response({"success": False, "error": "Failed to fetch user models"}, status=502)

            if not isinstance(models, list):
                models = []

            lora_scanner = await self._service_registry.get_lora_scanner()
            checkpoint_scanner = await self._service_registry.get_checkpoint_scanner()
            embedding_scanner = await self._service_registry.get_embedding_scanner()

            normalized_allowed_types = {model_type.lower() for model_type in CIVITAI_USER_MODEL_TYPES}
            lora_type_aliases = {model_type.lower() for model_type in VALID_LORA_TYPES}

            type_scanner_map: Dict[str, object | None] = {
                **{alias: lora_scanner for alias in lora_type_aliases},
                "checkpoint": checkpoint_scanner,
                "textualinversion": embedding_scanner,
            }

            versions: list[dict] = []
            for model in models:
                if not isinstance(model, dict):
                    continue

                model_type = str(model.get("type", "")).lower()
                if model_type not in normalized_allowed_types:
                    continue

                scanner = type_scanner_map.get(model_type)
                if scanner is None:
                    return web.json_response({"success": False, "error": f'Scanner for type "{model_type}" is not available'}, status=503)

                tags_value = model.get("tags")
                tags = tags_value if isinstance(tags_value, list) else []
                model_id = model.get("id")
                try:
                    model_id_int = int(model_id)
                except (TypeError, ValueError):
                    continue
                model_name = model.get("name", "")

                versions_data = model.get("modelVersions")
                if not isinstance(versions_data, list):
                    continue

                for version in versions_data:
                    if not isinstance(version, dict):
                        continue

                    version_id = version.get("id")
                    try:
                        version_id_int = int(version_id)
                    except (TypeError, ValueError):
                        continue

                    images = version.get("images") or []
                    thumbnail_url = None
                    if images and isinstance(images, list):
                        first_image = images[0]
                        if isinstance(first_image, dict):
                            raw_url = first_image.get("url")
                            media_type = first_image.get("type")
                            rewritten_url, _ = rewrite_preview_url(raw_url, media_type)
                            thumbnail_url = rewritten_url

                    in_library = await scanner.check_model_version_exists(version_id_int)

                    versions.append(
                        {
                            "modelId": model_id_int,
                            "versionId": version_id_int,
                            "modelName": model_name,
                            "versionName": version.get("name", ""),
                            "type": model.get("type"),
                            "tags": tags,
                            "baseModel": version.get("baseModel"),
                            "thumbnailUrl": thumbnail_url,
                            "inLibrary": in_library,
                        }
                    )

            return web.json_response({"success": True, "username": username, "versions": versions})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to get Civitai user models: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class MetadataArchiveHandler:
    def __init__(
        self,
        *,
        metadata_archive_manager_factory: Callable[[], Awaitable[MetadataArchiveManagerProtocol]] = get_metadata_archive_manager,
        settings_service=None,
        metadata_provider_updater: Callable[[], Awaitable[None]] = update_metadata_providers,
    ) -> None:
        self._metadata_archive_manager_factory = metadata_archive_manager_factory
        self._settings = settings_service or get_settings_manager()
        self._metadata_provider_updater = metadata_provider_updater

    async def download_metadata_archive(self, request: web.Request) -> web.Response:
        try:
            archive_manager = await self._metadata_archive_manager_factory()
            download_id = request.query.get("download_id")

            def progress_callback(stage: str, message: str) -> None:
                data = {"stage": stage, "message": message, "type": "metadata_archive_download"}
                if download_id:
                    asyncio.create_task(ws_manager.broadcast_download_progress(download_id, data))
                else:
                    asyncio.create_task(ws_manager.broadcast(data))

            success = await archive_manager.download_and_extract_database(progress_callback)
            if success:
                self._settings.set("enable_metadata_archive_db", True)
                await self._metadata_provider_updater()
                return web.json_response({"success": True, "message": "Metadata archive database downloaded and extracted successfully"})
            return web.json_response({"success": False, "error": "Failed to download and extract metadata archive database"}, status=500)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error downloading metadata archive: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def remove_metadata_archive(self, request: web.Request) -> web.Response:
        try:
            archive_manager = await self._metadata_archive_manager_factory()
            success = await archive_manager.remove_database()
            if success:
                self._settings.set("enable_metadata_archive_db", False)
                await self._metadata_provider_updater()
                return web.json_response({"success": True, "message": "Metadata archive database removed successfully"})
            return web.json_response({"success": False, "error": "Failed to remove metadata archive database"}, status=500)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error removing metadata archive: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_metadata_archive_status(self, request: web.Request) -> web.Response:
        try:
            archive_manager = await self._metadata_archive_manager_factory()
            is_available = archive_manager.is_database_available()
            is_enabled = self._settings.get("enable_metadata_archive_db", False)
            db_size = 0
            if is_available:
                db_path = archive_manager.get_database_path()
                if db_path and os.path.exists(db_path):
                    db_size = os.path.getsize(db_path)
            return web.json_response(
                {
                    "success": True,
                    "isAvailable": is_available,
                    "isEnabled": is_enabled,
                    "databaseSize": db_size,
                    "databasePath": archive_manager.get_database_path() if is_available else None,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error getting metadata archive status: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class FileSystemHandler:
    async def open_file_location(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_path = data.get("file_path")
            if not file_path:
                return web.json_response({"success": False, "error": "Missing file_path parameter"}, status=400)
            file_path = os.path.abspath(file_path)
            if not os.path.isfile(file_path):
                return web.json_response({"success": False, "error": "File does not exist"}, status=404)

            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", file_path])
            elif os.name == "posix":
                if sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", file_path])
                else:
                    folder = os.path.dirname(file_path)
                    subprocess.Popen(["xdg-open", folder])

            return web.json_response({"success": True, "message": f"Opened folder and selected file: {file_path}"})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to open file location: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class NodeRegistryHandler:
    def __init__(
        self,
        node_registry: NodeRegistry,
        prompt_server: type[PromptServerProtocol],
        *,
        standalone_mode: bool,
    ) -> None:
        self._node_registry = node_registry
        self._prompt_server = prompt_server
        self._standalone_mode = standalone_mode

    async def register_nodes(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            nodes = data.get("nodes", [])
            if not isinstance(nodes, list):
                return web.json_response({"success": False, "error": "nodes must be a list"}, status=400)
            for index, node in enumerate(nodes):
                if not isinstance(node, dict):
                    return web.json_response({"success": False, "error": f"Node {index} must be an object"}, status=400)
                node_id = node.get("node_id")
                if node_id is None:
                    return web.json_response({"success": False, "error": f"Node {index} missing node_id parameter"}, status=400)
                graph_id = node.get("graph_id")
                if graph_id is None:
                    return web.json_response({"success": False, "error": f"Node {index} missing graph_id parameter"}, status=400)
                graph_name = node.get("graph_name")
                try:
                    node["node_id"] = int(node_id)
                except (TypeError, ValueError):
                    return web.json_response({"success": False, "error": f"Node {index} node_id must be an integer"}, status=400)
                node["graph_id"] = str(graph_id)
                if graph_name is None:
                    node["graph_name"] = None
                elif isinstance(graph_name, str):
                    node["graph_name"] = graph_name
                else:
                    node["graph_name"] = str(graph_name)

            await self._node_registry.register_nodes(nodes)
            return web.json_response({"success": True, "message": f"{len(nodes)} nodes registered successfully"})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to register nodes: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_registry(self, request: web.Request) -> web.Response:
        try:
            if self._standalone_mode:
                logger.warning("Registry refresh not available in standalone mode")
                return web.json_response(
                    {
                        "success": False,
                        "error": "Standalone Mode Active",
                        "message": "Cannot interact with ComfyUI in standalone mode.",
                    },
                    status=503,
                )

            try:
                self._prompt_server.instance.send_sync("lora_registry_refresh", {})
                logger.debug("Sent registry refresh request to frontend")
            except Exception as exc:
                logger.error("Failed to send registry refresh message: %s", exc)
                return web.json_response(
                    {
                        "success": False,
                        "error": "Communication Error",
                        "message": f"Failed to communicate with ComfyUI frontend: {exc}",
                    },
                    status=500,
                )

            registry_updated = await self._node_registry.wait_for_update(timeout=1.0)
            if not registry_updated:
                logger.warning("Registry refresh timeout after 1 second")
                return web.json_response(
                    {
                        "success": False,
                        "error": "Timeout Error",
                        "message": "Registry refresh timeout - ComfyUI frontend may not be responsive",
                    },
                    status=408,
                )

            registry_info = await self._node_registry.get_registry()
            return web.json_response({"success": True, "data": registry_info})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to get registry: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": "Internal Error", "message": str(exc)}, status=500)

    async def update_node_widget(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            widget_name = data.get("widget_name")
            value = data.get("value")
            node_ids = data.get("node_ids")

            if not isinstance(widget_name, str) or not widget_name:
                return web.json_response({"success": False, "error": "Missing widget_name parameter"}, status=400)

            if not isinstance(value, str) or not value:
                return web.json_response({"success": False, "error": "Missing value parameter"}, status=400)

            if not isinstance(node_ids, list) or not node_ids:
                return web.json_response(
                    {"success": False, "error": "node_ids must be a non-empty list"},
                    status=400,
                )

            results = []
            for entry in node_ids:
                node_identifier = entry
                graph_identifier = None
                if isinstance(entry, dict):
                    node_identifier = entry.get("node_id")
                    graph_identifier = entry.get("graph_id")

                if node_identifier is None:
                    results.append(
                        {
                            "node_id": node_identifier,
                            "graph_id": graph_identifier,
                            "success": False,
                            "error": "Missing node_id parameter",
                        }
                    )
                    continue

                try:
                    parsed_node_id = int(node_identifier)
                except (TypeError, ValueError):
                    parsed_node_id = node_identifier

                payload = {
                    "id": parsed_node_id,
                    "widget_name": widget_name,
                    "value": value,
                }

                if graph_identifier is not None:
                    payload["graph_id"] = str(graph_identifier)

                try:
                    self._prompt_server.instance.send_sync("lm_widget_update", payload)
                    results.append(
                        {
                            "node_id": parsed_node_id,
                            "graph_id": payload.get("graph_id"),
                            "success": True,
                        }
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error(
                        "Error sending widget update to node %s (graph %s): %s",
                        parsed_node_id,
                        graph_identifier,
                        exc,
                    )
                    results.append(
                        {
                            "node_id": parsed_node_id,
                            "graph_id": payload.get("graph_id"),
                            "success": False,
                            "error": str(exc),
                        }
                    )

            return web.json_response({"success": True, "results": results})
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to update node widget: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class MiscHandlerSet:
    """Aggregate handlers into a lookup compatible with the registrar."""

    def __init__(
        self,
        *,
        health: HealthCheckHandler,
        settings: SettingsHandler,
        usage_stats: UsageStatsHandler,
        lora_code: LoraCodeHandler,
        trained_words: TrainedWordsHandler,
        model_examples: ModelExampleFilesHandler,
        node_registry: NodeRegistryHandler,
        model_library: ModelLibraryHandler,
        metadata_archive: MetadataArchiveHandler,
        filesystem: FileSystemHandler,
    ) -> None:
        self.health = health
        self.settings = settings
        self.usage_stats = usage_stats
        self.lora_code = lora_code
        self.trained_words = trained_words
        self.model_examples = model_examples
        self.node_registry = node_registry
        self.model_library = model_library
        self.metadata_archive = metadata_archive
        self.filesystem = filesystem

    def to_route_mapping(self) -> Mapping[str, Callable[[web.Request], Awaitable[web.StreamResponse]]]:
        return {
            "health_check": self.health.health_check,
            "get_settings": self.settings.get_settings,
            "update_settings": self.settings.update_settings,
            "get_priority_tags": self.settings.get_priority_tags,
            "get_settings_libraries": self.settings.get_libraries,
            "activate_library": self.settings.activate_library,
            "update_usage_stats": self.usage_stats.update_usage_stats,
            "get_usage_stats": self.usage_stats.get_usage_stats,
            "update_lora_code": self.lora_code.update_lora_code,
            "get_trained_words": self.trained_words.get_trained_words,
            "get_model_example_files": self.model_examples.get_model_example_files,
            "register_nodes": self.node_registry.register_nodes,
            "update_node_widget": self.node_registry.update_node_widget,
            "get_registry": self.node_registry.get_registry,
            "check_model_exists": self.model_library.check_model_exists,
            "get_civitai_user_models": self.model_library.get_civitai_user_models,
            "download_metadata_archive": self.metadata_archive.download_metadata_archive,
            "remove_metadata_archive": self.metadata_archive.remove_metadata_archive,
            "get_metadata_archive_status": self.metadata_archive.get_metadata_archive_status,
            "get_model_versions_status": self.model_library.get_model_versions_status,
            "open_file_location": self.filesystem.open_file_location,
        }


def build_service_registry_adapter() -> ServiceRegistryAdapter:
    return ServiceRegistryAdapter(
        get_lora_scanner=ServiceRegistry.get_lora_scanner,
        get_checkpoint_scanner=ServiceRegistry.get_checkpoint_scanner,
        get_embedding_scanner=ServiceRegistry.get_embedding_scanner,
    )
