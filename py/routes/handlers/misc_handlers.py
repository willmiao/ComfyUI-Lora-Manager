"""Handlers for miscellaneous routes.

The legacy :mod:`py.routes.misc_routes` module bundled HTTP wiring and
business logic in a single class.  This module mirrors the model route
architecture by splitting the responsibilities into dedicated handler
objects that can be composed by the route controller.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import platform
import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Mapping, Protocol, Sequence

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
from ...services.cache_health_monitor import CacheHealthMonitor, CacheHealthStatus
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
from ...utils.session_logging import get_standalone_session_log_snapshot
from ...utils.usage_stats import UsageStats
from .base_model_handlers import BaseModelHandlerSet

logger = logging.getLogger(__name__)


def _get_project_root() -> str:
    current_file = os.path.abspath(__file__)
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    )


def _get_app_version_string() -> str:
    version = "1.0.0"
    short_hash = "stable"
    try:
        import toml

        root_dir = _get_project_root()
        pyproject_path = os.path.join(root_dir, "pyproject.toml")

        if os.path.exists(pyproject_path):
            with open(pyproject_path, "r", encoding="utf-8") as handle:
                data = toml.load(handle)
                version = (
                    data.get("project", {}).get("version", "1.0.0").replace("v", "")
                )

        git_dir = os.path.join(root_dir, ".git")
        if os.path.exists(git_dir):
            try:
                import git

                repo = git.Repo(root_dir)
                short_hash = repo.head.commit.hexsha[:7]
            except Exception:
                pass
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.debug("Failed to resolve app version for doctor diagnostics: %s", exc)

    return f"{version}-{short_hash}"


def _sanitize_sensitive_data(payload: Any) -> Any:
    sensitive_markers = (
        "api_key",
        "apikey",
        "token",
        "password",
        "secret",
        "authorization",
    )

    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            normalized_key = str(key).lower()
            if any(marker in normalized_key for marker in sensitive_markers):
                if isinstance(value, str) and value:
                    sanitized[key] = f"{value[:4]}***{value[-2:]}" if len(value) > 6 else "***"
                else:
                    sanitized[key] = "***"
            else:
                sanitized[key] = _sanitize_sensitive_data(value)
        return sanitized

    if isinstance(payload, list):
        return [_sanitize_sensitive_data(item) for item in payload]

    if isinstance(payload, str):
        return _sanitize_sensitive_text(payload)

    return payload


def _sanitize_sensitive_text(value: str) -> str:
    if not value:
        return value

    redacted = value
    patterns = (
        (
            r'(?i)("authorization"\s*:\s*")Bearer\s+([^"]+)(")',
            r'\1Bearer ***\3',
        ),
        (
            r'(?i)("x[-_]?api[-_]?key"\s*:\s*")([^"]+)(")',
            r'\1***\3',
        ),
        (
            r'(?i)("api[_-]?key"\s*:\s*")([^"]+)(")',
            r'\1***\3',
        ),
        (
            r'(?i)("token"\s*:\s*")([^"]+)(")',
            r'\1***\3',
        ),
        (
            r'(?i)("password"\s*:\s*")([^"]+)(")',
            r'\1***\3',
        ),
        (
            r'(?i)("secret"\s*:\s*")([^"]+)(")',
            r'\1***\3',
        ),
        (
            r"(?i)\b(authorization\s*[:=]\s*bearer\s+)([A-Za-z0-9._\-+/=]+)",
            r"\1***",
        ),
        (
            r"(?i)\b(x[-_]?api[-_]?key\s*[:=]\s*)([^\s,;]+)",
            r"\1***",
        ),
        (
            r"(?i)\b(api[_-]?key\s*[:=]\s*)([^\s,;]+)",
            r"\1***",
        ),
        (
            r"(?i)\b(token\s*[:=]\s*)([^\s,;]+)",
            r"\1***",
        ),
        (
            r"(?i)\b(password\s*[:=]\s*)([^\s,;]+)",
            r"\1***",
        ),
        (
            r"(?i)\b(secret\s*[:=]\s*)([^\s,;]+)",
            r"\1***",
        ),
    )

    import re

    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)

    return redacted


def _read_log_file_tail(path: str, max_bytes: int = 64 * 1024) -> str:
    if not path or not os.path.isfile(path):
        return ""

    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        file_size = handle.tell()
        handle.seek(max(file_size - max_bytes, 0))
        payload = handle.read()

    return payload.decode("utf-8", errors="replace")


def _read_text_file_head(path: str, max_bytes: int = 8 * 1024) -> str:
    if not path or not os.path.isfile(path):
        return ""

    with open(path, "rb") as handle:
        payload = handle.read(max_bytes)

    return payload.decode("utf-8", errors="replace")


def _extract_startup_marker(text: str, label: str) -> str | None:
    if not text:
        return None

    pattern = re.compile(rf"{re.escape(label)}\s*:\s*([^\r\n]+)")
    match = pattern.search(text)
    if not match:
        return None

    return match.group(1).strip()


def _format_comfyui_log_entries(entries: Sequence[Mapping[str, Any]] | None) -> str:
    if not entries:
        return ""

    rendered: list[str] = []
    for entry in entries:
        timestamp = str(entry.get("t", "")).strip()
        message = str(entry.get("m", ""))
        if not message:
            continue

        if timestamp:
            rendered.append(f"{timestamp} - {message}")
        else:
            rendered.append(message)

    if not rendered:
        return ""

    text = "".join(rendered)
    if text.endswith("\n"):
        return text
    return f"{text}\n"


def _get_embedded_comfyui_log_path() -> str:
    return os.path.abspath(
        os.path.join(_get_project_root(), "..", "..", "user", "comfyui.log")
    )


def _collect_comfyui_session_logs(
    *,
    log_entries: Sequence[Mapping[str, Any]] | None = None,
    log_file_path: str | None = None,
) -> dict[str, Any]:
    if log_entries is None:
        try:
            import app.logger as comfy_logger

            log_entries = list(comfy_logger.get_logs() or [])
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.debug("Failed to read ComfyUI in-memory logs: %s", exc)
            log_entries = []

    session_log_text = _format_comfyui_log_entries(log_entries)
    session_started_at = _extract_startup_marker(
        session_log_text, "** ComfyUI startup time"
    )
    if not session_started_at and log_entries:
        session_started_at = str(log_entries[0].get("t", "")).strip() or None

    resolved_log_path = os.path.abspath(log_file_path or _get_embedded_comfyui_log_path())
    persisted_log_text = ""
    notes: list[str] = []

    if os.path.isfile(resolved_log_path):
        head_text = _read_text_file_head(resolved_log_path)
        file_started_at = _extract_startup_marker(head_text, "** ComfyUI startup time")
        if session_started_at and file_started_at and file_started_at == session_started_at:
            persisted_log_text = _read_log_file_tail(resolved_log_path)
        elif session_started_at and file_started_at and file_started_at != session_started_at:
            notes.append(
                "Persistent ComfyUI log file does not match the current process session."
            )
        elif not session_started_at and file_started_at:
            persisted_log_text = _read_log_file_tail(resolved_log_path)
            session_started_at = file_started_at
        else:
            notes.append(
                "Persistent ComfyUI log file is missing a startup marker and was not trusted as the current session log."
            )
    else:
        notes.append("Persistent ComfyUI log file was not found.")

    source_method = "comfyui_in_memory"
    if persisted_log_text:
        source_method = "comfyui_in_memory+current_log_file"
    elif not session_log_text:
        source_method = "unavailable"

    return {
        "mode": "comfyui",
        "session_started_at": session_started_at,
        "session_log_text": session_log_text,
        "persistent_log_path": resolved_log_path,
        "persistent_log_text": persisted_log_text,
        "source_method": source_method,
        "notes": notes,
    }


def _collect_standalone_session_logs(
    *, snapshot: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    snapshot = snapshot or get_standalone_session_log_snapshot()

    if not snapshot:
        return {
            "mode": "standalone",
            "session_started_at": None,
            "session_log_text": "",
            "persistent_log_path": None,
            "persistent_log_text": "",
            "source_method": "unavailable",
            "session_id": None,
            "notes": ["Standalone session logging was not initialized."],
        }

    log_file_path = snapshot.get("log_file_path")
    persisted_log_text = _read_log_file_tail(log_file_path) if log_file_path else ""
    session_log_text = str(snapshot.get("in_memory_text") or "")
    source_method = "standalone_memory"
    if persisted_log_text:
        source_method = "standalone_session_file"
    elif session_log_text:
        source_method = "standalone_memory"
    else:
        source_method = "unavailable"

    return {
        "mode": "standalone",
        "session_started_at": snapshot.get("started_at"),
        "session_log_text": session_log_text,
        "persistent_log_path": log_file_path,
        "persistent_log_text": persisted_log_text,
        "source_method": source_method,
        "session_id": snapshot.get("session_id"),
        "notes": [],
    }


def _collect_backend_session_logs() -> dict[str, Any]:
    standalone_mode = os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"
    if standalone_mode:
        return _collect_standalone_session_logs()
    return _collect_comfyui_session_logs()


def _is_wsl() -> bool:
    """Check if running in WSL environment."""
    try:
        with open("/proc/version", "r") as f:
            version_info = f.read().lower()
            return "microsoft" in version_info or "wsl" in version_info
    except (OSError, IOError):
        return False


def _is_docker() -> bool:
    """Check if running in Docker container."""
    dockerenv_exists = os.path.exists("/.dockerenv")
    if dockerenv_exists:
        return True

    try:
        with open("/proc/1/cgroup", "r") as f:
            cgroup_content = f.read()
            return (
                "docker" in cgroup_content.lower()
                or "kubepods" in cgroup_content.lower()
            )
    except (OSError, IOError):
        return False


def _wsl_to_windows_path(wsl_path: str) -> str | None:
    """Convert WSL path to Windows path using wslpath."""
    try:
        result = subprocess.run(
            ["wslpath", "-w", wsl_path],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


class PromptServerProtocol(Protocol):
    """Subset of PromptServer used by the handlers."""

    instance: "PromptServerProtocol"

    def send_sync(
        self, event: str, payload: dict
    ) -> None:  # pragma: no cover - protocol
        ...


class DownloaderProtocol(Protocol):
    async def refresh_session(self) -> None:  # pragma: no cover - protocol
        ...


class UsageStatsFactory(Protocol):
    def __call__(self) -> UsageStats:  # pragma: no cover - protocol
        ...


class MetadataProviderProtocol(Protocol):
    async def get_model_versions(
        self, model_id: int
    ) -> dict | None:  # pragma: no cover - protocol
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


class BackupServiceProtocol(Protocol):
    async def create_snapshot(
        self, *, snapshot_type: str = "manual", persist: bool = False
    ) -> dict:  # pragma: no cover - protocol
        ...

    async def restore_snapshot(self, archive_path: str) -> dict:  # pragma: no cover - protocol
        ...

    def get_status(self) -> dict:  # pragma: no cover - protocol
        ...

    def get_available_snapshots(self) -> list[dict]:  # pragma: no cover - protocol
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
                    raw_widget_names = (
                        capability_widget_names
                        if isinstance(capability_widget_names, list)
                        else None
                    )

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
                    "mode": node.get("mode"),
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


class SupportersHandler:
    """Handler for supporters data."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def _load_supporters(self) -> dict:
        """Load supporters data from JSON file."""
        try:
            current_file = os.path.abspath(__file__)
            root_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
            )
            supporters_path = os.path.join(root_dir, "data", "supporters.json")

            if os.path.exists(supporters_path):
                with open(supporters_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            self._logger.debug(f"Failed to load supporters data: {e}")

        return {"specialThanks": [], "allSupporters": [], "totalCount": 0}

    async def get_supporters(self, request: web.Request) -> web.Response:
        """Return supporters data as JSON."""
        try:
            supporters = self._load_supporters()
            return web.json_response({"success": True, "supporters": supporters})
        except Exception as exc:
            self._logger.error("Error loading supporters: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class DoctorHandler:
    """Run environment diagnostics and export a support bundle."""

    def __init__(
        self,
        *,
        settings_service=None,
        civitai_client_factory: Callable[[], Awaitable[Any]] = ServiceRegistry.get_civitai_client,
        scanner_factories: Sequence[tuple[str, str, Callable[[], Awaitable[Any]]]] | None = None,
        app_version_getter: Callable[[], str] = _get_app_version_string,
    ) -> None:
        self._settings = settings_service or get_settings_manager()
        self._civitai_client_factory = civitai_client_factory
        self._scanner_factories = tuple(
            scanner_factories
            or (
                ("lora", "LoRAs", ServiceRegistry.get_lora_scanner),
                ("checkpoint", "Checkpoints", ServiceRegistry.get_checkpoint_scanner),
                ("embedding", "Embeddings", ServiceRegistry.get_embedding_scanner),
            )
        )
        self._app_version_getter = app_version_getter

    async def get_doctor_diagnostics(self, request: web.Request) -> web.Response:
        try:
            client_version = (request.query.get("clientVersion") or "").strip()
            app_version = self._app_version_getter()
            diagnostics = [
                await self._check_civitai_api_key(),
                await self._check_cache_health(),
                self._check_ui_version(client_version, app_version),
            ]

            issue_count = sum(
                1 for item in diagnostics if item.get("status") in {"warning", "error"}
            )
            error_count = sum(1 for item in diagnostics if item.get("status") == "error")
            warning_count = sum(
                1 for item in diagnostics if item.get("status") == "warning"
            )

            overall_status = "ok"
            if error_count:
                overall_status = "error"
            elif warning_count:
                overall_status = "warning"

            return web.json_response(
                {
                    "success": True,
                    "app_version": app_version,
                    "summary": {
                        "status": overall_status,
                        "issue_count": issue_count,
                        "warning_count": warning_count,
                        "error_count": error_count,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    },
                    "diagnostics": diagnostics,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error building doctor diagnostics: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def repair_doctor_cache(self, request: web.Request) -> web.Response:
        repaired: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []

        for model_type, label, factory in self._scanner_factories:
            try:
                scanner = await factory()
                await scanner.get_cached_data(force_refresh=True, rebuild_cache=True)
                repaired.append({"model_type": model_type, "label": label})
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Doctor cache rebuild failed for %s: %s", model_type, exc, exc_info=True)
                failures.append(
                    {
                        "model_type": model_type,
                        "label": label,
                        "error": str(exc),
                    }
                )

        status = 200 if not failures else 500
        return web.json_response(
            {
                "success": not failures,
                "repaired": repaired,
                "failures": failures,
            },
            status=status,
        )

    async def export_doctor_bundle(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        try:
            archive_bytes = self._build_support_bundle(payload)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            headers = {
                "Content-Type": "application/zip",
                "Content-Disposition": f'attachment; filename="lora-manager-doctor-{timestamp}.zip"',
            }
            return web.Response(body=archive_bytes, headers=headers)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error exporting doctor bundle: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def _check_civitai_api_key(self) -> dict[str, Any]:
        api_key = (self._settings.get("civitai_api_key", "") or "").strip()
        if not api_key:
            return {
                "id": "civitai_api_key",
                "title": "Civitai API Key",
                "status": "warning",
                "summary": "Civitai API key is not configured.",
                "details": [
                    "Downloads and authenticated Civitai requests may fail until a valid API key is saved."
                ],
                "actions": [{"id": "open-settings", "label": "Open Settings"}],
            }

        obvious_placeholders = {"your_api_key", "changeme", "placeholder", "none"}
        if api_key.lower() in obvious_placeholders:
            return {
                "id": "civitai_api_key",
                "title": "Civitai API Key",
                "status": "error",
                "summary": "Civitai API key looks like a placeholder value.",
                "details": ["Replace the placeholder with a real key from your Civitai account settings."],
                "actions": [{"id": "open-settings", "label": "Open Settings"}],
            }

        try:
            client = await self._civitai_client_factory()
            success, result = await client._make_request(  # noqa: SLF001 - internal diagnostic probe
                "GET",
                f"{client.base_url}/models",
                use_auth=True,
                params={"limit": 1},
            )
            if success:
                return {
                    "id": "civitai_api_key",
                    "title": "Civitai API Key",
                    "status": "ok",
                    "summary": "Civitai API key is configured and accepted.",
                    "details": [],
                    "actions": [{"id": "open-settings", "label": "Open Settings"}],
                }

            error_text = str(result)
            lowered = error_text.lower()
            if any(token in lowered for token in ("401", "403", "unauthorized", "forbidden", "invalid")):
                return {
                    "id": "civitai_api_key",
                    "title": "Civitai API Key",
                    "status": "error",
                    "summary": "Configured Civitai API key was rejected.",
                    "details": [error_text],
                    "actions": [{"id": "open-settings", "label": "Open Settings"}],
                }

            return {
                "id": "civitai_api_key",
                "title": "Civitai API Key",
                "status": "warning",
                "summary": "Unable to confirm whether the Civitai API key is valid.",
                "details": [error_text],
                "actions": [{"id": "open-settings", "label": "Open Settings"}],
            }
        except Exception as exc:  # pragma: no cover - network/path dependent
            logger.warning("Doctor API key validation failed: %s", exc)
            return {
                "id": "civitai_api_key",
                "title": "Civitai API Key",
                "status": "warning",
                "summary": "Could not validate the Civitai API key right now.",
                "details": [str(exc)],
                "actions": [{"id": "open-settings", "label": "Open Settings"}],
            }

    async def _check_cache_health(self) -> dict[str, Any]:
        details: list[dict[str, Any]] = []
        overall_status = "ok"
        summary = "All model caches look healthy."

        for model_type, label, factory in self._scanner_factories:
            try:
                scanner = await factory()
                persisted = None
                persistent_cache = getattr(scanner, "_persistent_cache", None)
                if persistent_cache and hasattr(persistent_cache, "load_cache"):
                    loop = asyncio.get_event_loop()
                    persisted = await loop.run_in_executor(
                        None,
                        persistent_cache.load_cache,
                        getattr(scanner, "model_type", model_type),
                    )

                raw_data = list(getattr(persisted, "raw_data", None) or [])
                if not raw_data:
                    cache = await scanner.get_cached_data(force_refresh=False)
                    raw_data = list(getattr(cache, "raw_data", None) or [])

                report = CacheHealthMonitor().check_health(raw_data, auto_repair=False)
                report_status = "ok"
                if report.status == CacheHealthStatus.CORRUPTED:
                    report_status = "error"
                elif report.status != CacheHealthStatus.HEALTHY:
                    report_status = "warning"

                details.append(
                    {
                        "model_type": model_type,
                        "label": label,
                        "status": report_status,
                        "message": report.message,
                        "total_entries": report.total_entries,
                        "invalid_entries": report.invalid_entries,
                        "repaired_entries": report.repaired_entries,
                        "corruption_rate": f"{report.corruption_rate:.1%}",
                    }
                )

                if report_status == "error":
                    overall_status = "error"
                elif report_status == "warning" and overall_status == "ok":
                    overall_status = "warning"
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Doctor cache health check failed for %s: %s", model_type, exc, exc_info=True)
                details.append(
                    {
                        "model_type": model_type,
                        "label": label,
                        "status": "error",
                        "message": str(exc),
                    }
                )
                overall_status = "error"

        if overall_status == "warning":
            summary = "One or more model caches contain invalid entries."
        elif overall_status == "error":
            summary = "One or more model caches are corrupted or unavailable."

        return {
            "id": "cache_health",
            "title": "Model Cache Health",
            "status": overall_status,
            "summary": summary,
            "details": details,
            "actions": [{"id": "repair-cache", "label": "Rebuild Cache"}],
        }

    def _check_ui_version(self, client_version: str, app_version: str) -> dict[str, Any]:
        if client_version and client_version != app_version:
            return {
                "id": "ui_version",
                "title": "UI Version",
                "status": "warning",
                "summary": "Browser is running an older UI bundle than the backend expects.",
                "details": [
                    {
                        "client_version": client_version,
                        "server_version": app_version,
                    }
                ],
                "actions": [{"id": "reload-page", "label": "Reload UI"}],
            }

        return {
            "id": "ui_version",
            "title": "UI Version",
            "status": "ok",
            "summary": "Browser UI bundle matches the backend version.",
            "details": [
                {
                    "client_version": client_version or app_version,
                    "server_version": app_version,
                }
            ],
            "actions": [{"id": "reload-page", "label": "Reload UI"}],
        }

    def _collect_backend_session_logs(self) -> dict[str, Any]:
        return _collect_backend_session_logs()

    def _build_support_bundle(self, payload: dict[str, Any]) -> bytes:
        diagnostics = payload.get("diagnostics") or []
        frontend_logs = payload.get("frontend_logs") or []
        client_context = payload.get("client_context") or {}

        app_version = self._app_version_getter()
        settings_snapshot = _sanitize_sensitive_data(
            getattr(self._settings, "settings", {}) or {}
        )
        startup_messages_getter = getattr(self._settings, "get_startup_messages", None)
        startup_messages = (
            list(startup_messages_getter()) if callable(startup_messages_getter) else []
        )

        environment = {
            "app_version": app_version,
            "python_version": sys.version,
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "standalone_mode": os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1",
            "settings_file": getattr(self._settings, "settings_file", None),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "client_context": client_context,
        }
        backend_logs = self._collect_backend_session_logs()
        backend_session_text = _sanitize_sensitive_text(
            str(backend_logs.get("session_log_text") or "")
        )
        backend_persisted_text = _sanitize_sensitive_text(
            str(backend_logs.get("persistent_log_text") or "")
        )
        if not backend_session_text and backend_persisted_text:
            backend_session_text = backend_persisted_text
        if not backend_session_text:
            backend_session_text = "No current backend session logs were available.\n"

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "doctor-report.json",
                json.dumps(
                    {
                        "app_version": app_version,
                        "diagnostics": diagnostics,
                        "summary": payload.get("summary"),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )
            archive.writestr(
                "settings-sanitized.json",
                json.dumps(settings_snapshot, indent=2, ensure_ascii=False),
            )
            archive.writestr(
                "startup-messages.json",
                json.dumps(startup_messages, indent=2, ensure_ascii=False),
            )
            archive.writestr(
                "environment.json",
                json.dumps(environment, indent=2, ensure_ascii=False),
            )
            archive.writestr(
                "frontend-console.json",
                json.dumps(_sanitize_sensitive_data(frontend_logs), indent=2, ensure_ascii=False),
            )
            archive.writestr("backend-logs.txt", backend_session_text)
            archive.writestr(
                "backend-log-source.json",
                json.dumps(
                    _sanitize_sensitive_data(
                        {
                            "mode": backend_logs.get("mode"),
                            "source_method": backend_logs.get("source_method"),
                            "session_started_at": backend_logs.get("session_started_at"),
                            "session_id": backend_logs.get("session_id"),
                            "persistent_log_path": backend_logs.get("persistent_log_path"),
                            "notes": backend_logs.get("notes") or [],
                        }
                    ),
                    indent=2,
                    ensure_ascii=False,
                ),
            )
            if backend_persisted_text:
                archive.writestr("backend-session-file-tail.txt", backend_persisted_text)

        return buffer.getvalue()


class ExampleWorkflowsHandler:
    """Handler for example workflow templates."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def _get_workflows_dir(self) -> str:
        """Get the example workflows directory path."""
        current_file = os.path.abspath(__file__)
        root_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
        )
        return os.path.join(root_dir, "example_workflows")

    def _format_workflow_name(self, filename: str) -> str:
        """Convert filename to human-readable name."""
        name = os.path.splitext(filename)[0]
        name = name.replace("_", " ")
        return name

    async def get_example_workflows(self, request: web.Request) -> web.Response:
        """Return list of available example workflows."""
        try:
            workflows_dir = self._get_workflows_dir()
            workflows = [
                {
                    "value": "Default",
                    "label": "Default (Blank)",
                    "path": None,
                }
            ]

            if os.path.exists(workflows_dir):
                for filename in sorted(os.listdir(workflows_dir)):
                    if filename.endswith(".json"):
                        workflows.append(
                            {
                                "value": filename,
                                "label": self._format_workflow_name(filename),
                                "path": f"example_workflows/{filename}",
                            }
                        )

            return web.json_response({"success": True, "workflows": workflows})
        except Exception as exc:
            self._logger.error(
                "Error listing example workflows: %s", exc, exc_info=True
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_example_workflow(self, request: web.Request) -> web.Response:
        """Return a specific example workflow JSON content."""
        try:
            filename = request.match_info.get("filename")
            if not filename:
                return web.json_response(
                    {"success": False, "error": "Filename not provided"}, status=400
                )

            if filename == "Default":
                return web.json_response(
                    {
                        "success": True,
                        "workflow": {
                            "last_node_id": 0,
                            "last_link_id": 0,
                            "nodes": [],
                            "links": [],
                            "groups": [],
                            "config": {},
                            "extra": {},
                            "version": 0.4,
                        },
                    }
                )

            workflows_dir = self._get_workflows_dir()
            filepath = os.path.join(workflows_dir, filename)

            if not os.path.exists(filepath):
                return web.json_response(
                    {"success": False, "error": f"Workflow not found: {filename}"},
                    status=404,
                )

            with open(filepath, "r", encoding="utf-8") as f:
                workflow = json.load(f)

            return web.json_response({"success": True, "workflow": workflow})
        except Exception as exc:
            self._logger.error("Error loading example workflow: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class SettingsHandler:
    """Sync settings between backend and frontend."""

    # Settings keys that should NOT be synced to frontend.
    # All other settings are synced by default.
    _NO_SYNC_KEYS = frozenset(
        {
            # Internal/performance settings (not used by frontend)
            "hash_chunk_size_mb",
            "download_stall_timeout_seconds",
            # Complex internal structures retrieved via separate endpoints
            "folder_paths",
            "libraries",
            "active_library",
        }
    )

    _PROXY_KEYS = {
        "proxy_enabled",
        "proxy_host",
        "proxy_port",
        "proxy_username",
        "proxy_password",
        "proxy_type",
    }

    def __init__(
        self,
        *,
        settings_service=None,
        metadata_provider_updater: Callable[
            [], Awaitable[None]
        ] = update_metadata_providers,
        downloader_factory: Callable[
            [], Awaitable[DownloaderProtocol]
        ] = get_downloader,
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
            # Sync all settings except those in _NO_SYNC_KEYS
            for key in self._settings.keys():
                if key not in self._NO_SYNC_KEYS:
                    value = self._settings.get(key)
                    if value is not None:
                        response_data[key] = value
            settings_file = getattr(self._settings, "settings_file", None)
            if settings_file:
                response_data["settings_file"] = settings_file
            messages_getter = getattr(self._settings, "get_startup_messages", None)
            messages = list(messages_getter()) if callable(messages_getter) else []
            return web.json_response(
                {
                    "success": True,
                    "settings": response_data,
                    "messages": messages,
                }
            )
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
            logger.error(
                "Error parsing activate library request: %s", exc, exc_info=True
            )
            return web.json_response(
                {"success": False, "error": "Invalid JSON payload"}, status=400
            )

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
            logger.error(
                "Error activating library '%s': %s", library_name, exc, exc_info=True
            )
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
                        return web.json_response(
                            {"success": False, "error": validation_error}
                        )

                if value == "__DELETE__" and key in (
                    "proxy_username",
                    "proxy_password",
                ):
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
                return web.json_response(
                    {"success": False, "error": "Missing prompt_id"}, status=400
                )
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
                return web.json_response(
                    {"success": False, "error": "Missing lora_code parameter"},
                    status=400,
                )

            results = []
            if node_ids is None:
                try:
                    self._prompt_server.instance.send_sync(
                        "lora_code_update",
                        {"id": -1, "lora_code": lora_code, "mode": mode},
                    )
                    results.append({"node_id": "broadcast", "success": True})
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error("Error broadcasting lora code: %s", exc)
                    results.append(
                        {"node_id": "broadcast", "success": False, "error": str(exc)}
                    )
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
                return web.json_response(
                    {"success": False, "error": "Missing file_path parameter"},
                    status=400,
                )
            if not os.path.exists(file_path):
                return web.json_response(
                    {"success": False, "error": "File not found"}, status=404
                )
            if not file_path.endswith(".safetensors"):
                return web.json_response(
                    {"success": False, "error": "File must be a safetensors file"},
                    status=400,
                )

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
                return web.json_response(
                    {"success": False, "error": "Missing model_path parameter"},
                    status=400,
                )
            model_dir = os.path.dirname(model_path)
            if not os.path.exists(model_dir):
                return web.json_response(
                    {"success": False, "error": "Model directory not found"}, status=404
                )

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
                if (
                    file_ext not in SUPPORTED_MEDIA_EXTENSIONS["images"]
                    and file_ext not in SUPPORTED_MEDIA_EXTENSIONS["videos"]
                ):
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


async def _noop_backup_service() -> None:
    return None


@dataclass
class ServiceRegistryAdapter:
    get_lora_scanner: Callable[[], Awaitable]
    get_checkpoint_scanner: Callable[[], Awaitable]
    get_embedding_scanner: Callable[[], Awaitable]
    get_downloaded_version_history_service: Callable[[], Awaitable]
    get_backup_service: Callable[[], Awaitable] = _noop_backup_service


class ModelLibraryHandler:
    def __init__(
        self,
        service_registry: ServiceRegistryAdapter,
        metadata_provider_factory: Callable[
            [], Awaitable[MetadataProviderProtocol | None]
        ],
    ) -> None:
        self._service_registry = service_registry
        self._metadata_provider_factory = metadata_provider_factory

    @staticmethod
    def _normalize_model_type(model_type: str | None) -> str | None:
        if not isinstance(model_type, str):
            return None
        normalized = model_type.strip().lower()
        if normalized in {"lora", "locon", "dora"}:
            return "lora"
        if normalized == "checkpoint":
            return "checkpoint"
        if normalized in {"embedding", "textualinversion"}:
            return "embedding"
        return None

    async def _get_scanner_for_type(self, model_type: str | None):
        normalized_type = self._normalize_model_type(model_type)
        if normalized_type == "lora":
            return normalized_type, await self._service_registry.get_lora_scanner()
        if normalized_type == "checkpoint":
            return normalized_type, await self._service_registry.get_checkpoint_scanner()
        if normalized_type == "embedding":
            return normalized_type, await self._service_registry.get_embedding_scanner()
        return None, None

    async def _get_download_history_service(self):
        return await self._service_registry.get_downloaded_version_history_service()

    @staticmethod
    def _with_downloaded_flag(versions: list[dict]) -> list[dict]:
        enriched: list[dict] = []
        for version in versions:
            entry = dict(version)
            entry.setdefault("hasBeenDownloaded", True)
            enriched.append(entry)
        return enriched

    async def check_model_exists(self, request: web.Request) -> web.Response:
        try:
            model_id_str = request.query.get("modelId")
            model_version_id_str = request.query.get("modelVersionId")
            if not model_id_str:
                return web.json_response(
                    {"success": False, "error": "Missing required parameter: modelId"},
                    status=400,
                )
            try:
                model_id = int(model_id_str)
            except ValueError:
                return web.json_response(
                    {"success": False, "error": "Parameter modelId must be an integer"},
                    status=400,
                )

            lora_scanner = await self._service_registry.get_lora_scanner()
            checkpoint_scanner = await self._service_registry.get_checkpoint_scanner()
            embedding_scanner = await self._service_registry.get_embedding_scanner()

            if model_version_id_str:
                try:
                    model_version_id = int(model_version_id_str)
                except ValueError:
                    return web.json_response(
                        {
                            "success": False,
                            "error": "Parameter modelVersionId must be an integer",
                        },
                        status=400,
                    )

                exists = False
                model_type = None
                if await lora_scanner.check_model_version_exists(model_version_id):
                    exists = True
                    model_type = "lora"
                elif (
                    checkpoint_scanner
                    and await checkpoint_scanner.check_model_version_exists(
                        model_version_id
                    )
                ):
                    exists = True
                    model_type = "checkpoint"
                elif (
                    embedding_scanner
                    and await embedding_scanner.check_model_version_exists(
                        model_version_id
                    )
                ):
                    exists = True
                    model_type = "embedding"

                history_service = await self._get_download_history_service()
                has_been_downloaded = False
                history_type = model_type
                if history_type:
                    has_been_downloaded = await history_service.has_been_downloaded(
                        history_type,
                        model_version_id,
                    )
                else:
                    for candidate_type in ("lora", "checkpoint", "embedding"):
                        if await history_service.has_been_downloaded(
                            candidate_type,
                            model_version_id,
                        ):
                            has_been_downloaded = True
                            history_type = candidate_type
                            break

                return web.json_response(
                    {
                        "success": True,
                        "exists": exists,
                        "modelType": model_type if exists else history_type,
                        "hasBeenDownloaded": has_been_downloaded,
                    }
                )

            lora_versions = await lora_scanner.get_model_versions_by_id(model_id)
            checkpoint_versions = []
            embedding_versions = []
            if not lora_versions and checkpoint_scanner:
                checkpoint_versions = await checkpoint_scanner.get_model_versions_by_id(
                    model_id
                )
            if not lora_versions and not checkpoint_versions and embedding_scanner:
                embedding_versions = await embedding_scanner.get_model_versions_by_id(
                    model_id
                )

            model_type = None
            versions = []
            downloaded_version_ids = []
            history_service = await self._get_download_history_service()
            if lora_versions:
                model_type = "lora"
                versions = self._with_downloaded_flag(lora_versions)
                downloaded_version_ids = await history_service.get_downloaded_version_ids(
                    model_type,
                    model_id,
                )
            elif checkpoint_versions:
                model_type = "checkpoint"
                versions = self._with_downloaded_flag(checkpoint_versions)
                downloaded_version_ids = await history_service.get_downloaded_version_ids(
                    model_type,
                    model_id,
                )
            elif embedding_versions:
                model_type = "embedding"
                versions = self._with_downloaded_flag(embedding_versions)
                downloaded_version_ids = await history_service.get_downloaded_version_ids(
                    model_type,
                    model_id,
                )
            else:
                for candidate_type in ("lora", "checkpoint", "embedding"):
                    candidate_downloaded_version_ids = (
                        await history_service.get_downloaded_version_ids(
                            candidate_type,
                            model_id,
                        )
                    )
                    if candidate_downloaded_version_ids:
                        model_type = candidate_type
                        downloaded_version_ids = candidate_downloaded_version_ids
                        break

            return web.json_response(
                {
                    "success": True,
                    "modelType": model_type,
                    "versions": versions,
                    "downloadedVersionIds": downloaded_version_ids,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to check model existence: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_model_version_download_status(
        self, request: web.Request
    ) -> web.Response:
        try:
            model_type, _ = await self._get_scanner_for_type(request.query.get("modelType"))
            if not model_type:
                return web.json_response(
                    {"success": False, "error": "Parameter modelType is required"},
                    status=400,
                )

            model_version_id_str = request.query.get("modelVersionId")
            if not model_version_id_str:
                return web.json_response(
                    {"success": False, "error": "Missing required parameter: modelVersionId"},
                    status=400,
                )
            try:
                model_version_id = int(model_version_id_str)
            except ValueError:
                return web.json_response(
                    {"success": False, "error": "Parameter modelVersionId must be an integer"},
                    status=400,
                )

            history_service = await self._get_download_history_service()
            return web.json_response(
                {
                    "success": True,
                    "modelType": model_type,
                    "modelVersionId": model_version_id,
                    "hasBeenDownloaded": await history_service.has_been_downloaded(
                        model_type,
                        model_version_id,
                    ),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Failed to get model version download status: %s",
                exc,
                exc_info=True,
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def set_model_version_download_status(
        self, request: web.Request
    ) -> web.Response:
        try:
            if request.method == "GET":
                data = request.query
            else:
                data = await request.json()
            model_type, _ = await self._get_scanner_for_type(data.get("modelType"))
            if not model_type:
                return web.json_response(
                    {"success": False, "error": "Parameter modelType is required"},
                    status=400,
                )

            try:
                model_version_id = int(data.get("modelVersionId"))
            except (TypeError, ValueError):
                return web.json_response(
                    {"success": False, "error": "Parameter modelVersionId must be an integer"},
                    status=400,
                )

            downloaded = data.get("downloaded")
            if isinstance(downloaded, str):
                normalized_downloaded = downloaded.strip().lower()
                if normalized_downloaded in {"true", "1"}:
                    downloaded = True
                elif normalized_downloaded in {"false", "0"}:
                    downloaded = False

            if not isinstance(downloaded, bool):
                return web.json_response(
                    {"success": False, "error": "Parameter downloaded must be a boolean"},
                    status=400,
                )

            history_service = await self._get_download_history_service()
            if downloaded:
                model_id = data.get("modelId")
                file_path = data.get("filePath")
                await history_service.mark_downloaded(
                    model_type,
                    model_version_id,
                    model_id=model_id,
                    source="manual",
                    file_path=file_path if isinstance(file_path, str) else None,
                )
            else:
                await history_service.mark_not_downloaded(model_type, model_version_id)

            return web.json_response(
                {
                    "success": True,
                    "modelType": model_type,
                    "modelVersionId": model_version_id,
                    "hasBeenDownloaded": downloaded,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Failed to set model version download status: %s",
                exc,
                exc_info=True,
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def get_model_versions_status(self, request: web.Request) -> web.Response:
        try:
            model_id_str = request.query.get("modelId")
            if not model_id_str:
                return web.json_response(
                    {"success": False, "error": "Missing required parameter: modelId"},
                    status=400,
                )
            try:
                model_id = int(model_id_str)
            except ValueError:
                return web.json_response(
                    {"success": False, "error": "Parameter modelId must be an integer"},
                    status=400,
                )

            metadata_provider = await self._metadata_provider_factory()
            if not metadata_provider:
                return web.json_response(
                    {"success": False, "error": "Metadata provider not available"},
                    status=503,
                )

            try:
                response = await metadata_provider.get_model_versions(model_id)
            except ResourceNotFoundError:
                return web.json_response(
                    {"success": False, "error": "Model not found"}, status=404
                )
            if not response or not response.get("modelVersions"):
                return web.json_response(
                    {"success": False, "error": "Model not found"}, status=404
                )

            versions = response.get("modelVersions", [])
            model_name = response.get("name", "")
            model_type = response.get("type", "").lower()

            normalized_type, scanner = await self._get_scanner_for_type(model_type)
            if not normalized_type:
                return web.json_response(
                    {
                        "success": False,
                        "error": f'Model type "{model_type}" is not supported',
                    },
                    status=400,
                )

            if not scanner:
                return web.json_response(
                    {
                        "success": False,
                        "error": f'Scanner for type "{normalized_type}" is not available',
                    },
                    status=503,
                )

            history_service = await self._get_download_history_service()
            local_versions = await scanner.get_model_versions_by_id(model_id)
            local_version_ids = {version["versionId"] for version in local_versions}
            downloaded_version_ids = await history_service.get_downloaded_version_ids(
                normalized_type,
                model_id,
            )
            downloaded_version_id_set = set(downloaded_version_ids)

            enriched_versions = []
            for version in versions:
                version_id = version.get("id")
                enriched_versions.append(
                    {
                        "id": version_id,
                        "name": version.get("name", ""),
                        "thumbnailUrl": version.get("images")[0]["url"]
                        if version.get("images")
                        else None,
                        "inLibrary": version_id in local_version_ids,
                        "hasBeenDownloaded": version_id in downloaded_version_id_set,
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
                return web.json_response(
                    {"success": False, "error": "Missing required parameter: username"},
                    status=400,
                )

            metadata_provider = await self._metadata_provider_factory()
            if not metadata_provider:
                return web.json_response(
                    {"success": False, "error": "Metadata provider not available"},
                    status=503,
                )

            try:
                models = await metadata_provider.get_user_models(username)
            except NotImplementedError:
                return web.json_response(
                    {
                        "success": False,
                        "error": "Metadata provider does not support user model queries",
                    },
                    status=501,
                )

            if models is None:
                return web.json_response(
                    {"success": False, "error": "Failed to fetch user models"},
                    status=502,
                )

            if not isinstance(models, list):
                models = []

            lora_scanner = await self._service_registry.get_lora_scanner()
            checkpoint_scanner = await self._service_registry.get_checkpoint_scanner()
            embedding_scanner = await self._service_registry.get_embedding_scanner()

            normalized_allowed_types = {
                model_type.lower() for model_type in CIVITAI_USER_MODEL_TYPES
            }
            lora_type_aliases = {model_type.lower() for model_type in VALID_LORA_TYPES}

            type_scanner_map: Dict[str, object | None] = {
                **{alias: lora_scanner for alias in lora_type_aliases},
                "checkpoint": checkpoint_scanner,
                "textualinversion": embedding_scanner,
            }

            versions: list[dict] = []
            history_service = await self._get_download_history_service()
            model_ids: list[int] = []
            for model in models:
                try:
                    model_ids.append(int(model.get("id")))
                except (TypeError, ValueError):
                    continue

            lora_downloaded = await history_service.get_downloaded_version_ids_bulk(
                "lora",
                model_ids,
            )
            checkpoint_downloaded = await history_service.get_downloaded_version_ids_bulk(
                "checkpoint",
                model_ids,
            )
            embedding_downloaded = await history_service.get_downloaded_version_ids_bulk(
                "embedding",
                model_ids,
            )
            downloaded_version_map: Dict[str, Dict[int, set[int]]] = {
                "lora": lora_downloaded,
                "locon": lora_downloaded,
                "dora": lora_downloaded,
                "checkpoint": checkpoint_downloaded,
                "textualinversion": embedding_downloaded,
            }
            for model in models:
                if not isinstance(model, dict):
                    continue

                model_type = str(model.get("type", "")).lower()
                if model_type not in normalized_allowed_types:
                    continue

                scanner = type_scanner_map.get(model_type)
                if scanner is None:
                    return web.json_response(
                        {
                            "success": False,
                            "error": f'Scanner for type "{model_type}" is not available',
                        },
                        status=503,
                    )

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

                    in_library = await scanner.check_model_version_exists(
                        version_id_int
                    )
                    downloaded_versions = downloaded_version_map.get(model_type, {})
                    downloaded_version_ids = downloaded_versions.get(model_id_int, set())

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
                            "hasBeenDownloaded": version_id_int in downloaded_version_ids,
                        }
                    )

            return web.json_response(
                {"success": True, "username": username, "versions": versions}
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to get Civitai user models: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class MetadataArchiveHandler:
    def __init__(
        self,
        *,
        metadata_archive_manager_factory: Callable[
            [], Awaitable[MetadataArchiveManagerProtocol]
        ] = get_metadata_archive_manager,
        settings_service=None,
        metadata_provider_updater: Callable[
            [], Awaitable[None]
        ] = update_metadata_providers,
    ) -> None:
        self._metadata_archive_manager_factory = metadata_archive_manager_factory
        self._settings = settings_service or get_settings_manager()
        self._metadata_provider_updater = metadata_provider_updater

    async def download_metadata_archive(self, request: web.Request) -> web.Response:
        try:
            archive_manager = await self._metadata_archive_manager_factory()
            download_id = request.query.get("download_id")

            def progress_callback(stage: str, message: str) -> None:
                data = {
                    "stage": stage,
                    "message": message,
                    "type": "metadata_archive_download",
                }
                if download_id:
                    asyncio.create_task(
                        ws_manager.broadcast_download_progress(download_id, data)
                    )
                else:
                    asyncio.create_task(ws_manager.broadcast(data))

            success = await archive_manager.download_and_extract_database(
                progress_callback
            )
            if success:
                self._settings.set("enable_metadata_archive_db", True)
                await self._metadata_provider_updater()
                return web.json_response(
                    {
                        "success": True,
                        "message": "Metadata archive database downloaded and extracted successfully",
                    }
                )
            return web.json_response(
                {
                    "success": False,
                    "error": "Failed to download and extract metadata archive database",
                },
                status=500,
            )
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
                return web.json_response(
                    {
                        "success": True,
                        "message": "Metadata archive database removed successfully",
                    }
                )
            return web.json_response(
                {
                    "success": False,
                    "error": "Failed to remove metadata archive database",
                },
                status=500,
            )
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
                    "databasePath": archive_manager.get_database_path()
                    if is_available
                    else None,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Error getting metadata archive status: %s", exc, exc_info=True
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class BackupHandler:
    """Handler for user-state backup export/import."""

    def __init__(
        self,
        *,
        backup_service_factory: Callable[[], Awaitable[BackupServiceProtocol]] = ServiceRegistry.get_backup_service,
    ) -> None:
        self._backup_service_factory = backup_service_factory

    async def get_backup_status(self, request: web.Request) -> web.Response:
        try:
            service = await self._backup_service_factory()
            return web.json_response(
                {
                    "success": True,
                    "status": service.get_status(),
                    "snapshots": service.get_available_snapshots(),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error getting backup status: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def export_backup(self, request: web.Request) -> web.Response:
        try:
            service = await self._backup_service_factory()
            result = await service.create_snapshot(snapshot_type="manual", persist=False)
            headers = {
                "Content-Type": "application/zip",
                "Content-Disposition": f'attachment; filename="{result["archive_name"]}"',
            }
            return web.Response(body=result["archive_bytes"], headers=headers)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error exporting backup: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def import_backup(self, request: web.Request) -> web.Response:
        temp_path: str | None = None
        try:
            fd, temp_path = tempfile.mkstemp(
                suffix=".zip", prefix="lora-manager-backup-"
            )
            os.close(fd)

            if request.content_type.startswith("multipart/"):
                reader = await request.multipart()
                field = await reader.next()
                uploaded = False
                while field is not None:
                    if getattr(field, "filename", None):
                        with open(temp_path, "wb") as handle:
                            while True:
                                chunk = await field.read_chunk()
                                if not chunk:
                                    break
                                handle.write(chunk)
                        uploaded = True
                        break
                    field = await reader.next()
                if not uploaded:
                    return web.json_response(
                        {"success": False, "error": "Missing backup archive"},
                        status=400,
                    )
            else:
                body = await request.read()
                if not body:
                    return web.json_response(
                        {"success": False, "error": "Missing backup archive"},
                        status=400,
                    )
                with open(temp_path, "wb") as handle:
                    handle.write(body)

            if not temp_path or not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                return web.json_response(
                    {"success": False, "error": "Missing backup archive"},
                    status=400,
                )

            service = await self._backup_service_factory()
            result = await service.restore_snapshot(temp_path)
            return web.json_response({"success": True, **result})
        except (ValueError, zipfile.BadZipFile) as exc:
            logger.error("Error importing backup: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error importing backup: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)
        finally:
            if temp_path and os.path.exists(temp_path):
                with contextlib.suppress(OSError):
                    os.remove(temp_path)


class FileSystemHandler:
    def __init__(self, settings_service=None) -> None:
        self._settings = settings_service or get_settings_manager()

    async def _open_path(self, path: str) -> web.Response:
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            return web.json_response(
                {"success": False, "error": "Folder does not exist"},
                status=404,
            )

        if os.name == "nt":
            subprocess.Popen(["explorer", path])
        elif os.name == "posix":
            if _is_docker():
                return web.json_response(
                    {
                        "success": True,
                        "message": "Running in Docker: Path available for copying",
                        "path": path,
                        "mode": "clipboard",
                    }
                )
            if _is_wsl():
                windows_path = _wsl_to_windows_path(path)
                if windows_path:
                    subprocess.Popen(["explorer.exe", windows_path])
                else:
                    logger.error(
                        "Failed to convert WSL path to Windows path: %s", path
                    )
                    return web.json_response(
                        {
                            "success": False,
                            "error": "Failed to open folder location: path conversion error",
                        },
                        status=500,
                    )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])

        return web.json_response(
            {"success": True, "message": f"Opened folder: {path}", "path": path}
        )

    async def open_file_location(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            file_path = data.get("file_path")
            if not file_path:
                return web.json_response(
                    {"success": False, "error": "Missing file_path parameter"},
                    status=400,
                )
            file_path = os.path.abspath(file_path)
            if not os.path.isfile(file_path):
                return web.json_response(
                    {"success": False, "error": "File does not exist"}, status=404
                )

            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", file_path])
            elif os.name == "posix":
                if _is_docker():
                    return web.json_response(
                        {
                            "success": True,
                            "message": "Running in Docker: Path available for copying",
                            "path": file_path,
                            "mode": "clipboard",
                        }
                    )
                elif _is_wsl():
                    windows_path = _wsl_to_windows_path(file_path)
                    if windows_path:
                        subprocess.Popen(["explorer.exe", "/select,", windows_path])
                    else:
                        logger.error(
                            "Failed to convert WSL path to Windows path: %s", file_path
                        )
                        return web.json_response(
                            {
                                "success": False,
                                "error": "Failed to open file location: path conversion error",
                            },
                            status=500,
                        )
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", file_path])
                else:
                    folder = os.path.dirname(file_path)
                    subprocess.Popen(["xdg-open", folder])

            return web.json_response(
                {
                    "success": True,
                    "message": f"Opened folder and selected file: {file_path}",
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to open file location: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def open_settings_location(self, request: web.Request) -> web.Response:
        try:
            settings_file = getattr(self._settings, "settings_file", None)
            if not settings_file:
                return web.json_response(
                    {"success": False, "error": "Settings file not found"}, status=404
                )

            settings_file = os.path.abspath(settings_file)
            if not os.path.isfile(settings_file):
                return web.json_response(
                    {"success": False, "error": "Settings file does not exist"},
                    status=404,
                )

            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", settings_file])
            elif os.name == "posix":
                if _is_docker():
                    return web.json_response(
                        {
                            "success": True,
                            "message": "Running in Docker: Path available for copying",
                            "path": settings_file,
                            "mode": "clipboard",
                        }
                    )
                elif _is_wsl():
                    windows_path = _wsl_to_windows_path(settings_file)
                    if windows_path:
                        subprocess.Popen(["explorer.exe", "/select,", windows_path])
                    else:
                        logger.error(
                            "Failed to convert WSL path to Windows path: %s",
                            settings_file,
                        )
                        return web.json_response(
                            {
                                "success": False,
                                "error": "Failed to open settings location: path conversion error",
                            },
                            status=500,
                        )
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", settings_file])
                else:
                    folder = os.path.dirname(settings_file)
                    subprocess.Popen(["xdg-open", folder])

            return web.json_response(
                {"success": True, "message": f"Opened settings folder: {settings_file}"}
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to open settings location: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def open_backup_location(self, request: web.Request) -> web.Response:
        try:
            settings_file = getattr(self._settings, "settings_file", None)
            if not settings_file:
                return web.json_response(
                    {"success": False, "error": "Settings file not found"}, status=404
                )

            backup_dir = os.path.join(os.path.dirname(os.path.abspath(settings_file)), "backups")
            return await self._open_path(backup_dir)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to open backup location: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class CustomWordsHandler:
    """Handler for autocomplete via TagFTSIndex."""

    def __init__(self) -> None:
        from ...services.custom_words_service import get_custom_words_service

        self._service = get_custom_words_service()

    async def search_custom_words(self, request: web.Request) -> web.Response:
        """Search custom words with autocomplete.

        Query parameters:
            search: The search term to match against.
            limit: Maximum number of results to return (default: 20).
            offset: Number of results to skip (default: 0).
            category: Optional category filter. Can be:
                - A category name (e.g., "character", "artist", "general")
                - Comma-separated category IDs (e.g., "4,11" for character)
            enriched: If "true", return enriched results with category and post_count
                      even without category filtering.
        """
        try:
            search_term = request.query.get("search", "")
            limit = int(request.query.get("limit", "20"))
            offset = max(0, int(request.query.get("offset", "0")))
            category_param = request.query.get("category", "")
            enriched_param = request.query.get("enriched", "").lower() == "true"

            # Parse category parameter
            categories = None
            if category_param:
                categories = self._parse_category_param(category_param)

            results = self._service.search_words(
                search_term,
                limit,
                offset=offset,
                categories=categories,
                enriched=enriched_param,
            )

            return web.json_response({"success": True, "words": results})
        except Exception as exc:
            logger.error("Error searching custom words: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    def _parse_category_param(self, param: str) -> list[int] | None:
        """Parse category parameter into list of category IDs.

        Args:
            param: Category parameter value (name or comma-separated IDs).

        Returns:
            List of category IDs, or None if parsing fails.
        """
        from ...services.tag_fts_index import CATEGORY_NAME_TO_IDS

        param = param.strip().lower()
        if not param:
            return None

        # Try to parse as category name first
        if param in CATEGORY_NAME_TO_IDS:
            return CATEGORY_NAME_TO_IDS[param]

        # Try to parse as comma-separated integers
        try:
            category_ids = []
            for part in param.split(","):
                part = part.strip()
                if part:
                    category_ids.append(int(part))
            return category_ids if category_ids else None
        except ValueError:
            logger.debug("Invalid category parameter: %s", param)
            return None


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
                return web.json_response(
                    {"success": False, "error": "nodes must be a list"}, status=400
                )
            for index, node in enumerate(nodes):
                if not isinstance(node, dict):
                    return web.json_response(
                        {"success": False, "error": f"Node {index} must be an object"},
                        status=400,
                    )
                node_id = node.get("node_id")
                if node_id is None:
                    return web.json_response(
                        {
                            "success": False,
                            "error": f"Node {index} missing node_id parameter",
                        },
                        status=400,
                    )
                graph_id = node.get("graph_id")
                if graph_id is None:
                    return web.json_response(
                        {
                            "success": False,
                            "error": f"Node {index} missing graph_id parameter",
                        },
                        status=400,
                    )
                graph_name = node.get("graph_name")
                try:
                    node["node_id"] = int(node_id)
                except (TypeError, ValueError):
                    return web.json_response(
                        {
                            "success": False,
                            "error": f"Node {index} node_id must be an integer",
                        },
                        status=400,
                    )
                node["graph_id"] = str(graph_id)
                if graph_name is None:
                    node["graph_name"] = None
                elif isinstance(graph_name, str):
                    node["graph_name"] = graph_name
                else:
                    node["graph_name"] = str(graph_name)

            await self._node_registry.register_nodes(nodes)
            return web.json_response(
                {
                    "success": True,
                    "message": f"{len(nodes)} nodes registered successfully",
                }
            )
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
            return web.json_response(
                {"success": False, "error": "Internal Error", "message": str(exc)},
                status=500,
            )

    async def update_node_widget(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            widget_name = data.get("widget_name")
            value = data.get("value")
            node_ids = data.get("node_ids")

            if not isinstance(widget_name, str) or not widget_name:
                return web.json_response(
                    {"success": False, "error": "Missing widget_name parameter"},
                    status=400,
                )

            if not isinstance(value, str) or not value:
                return web.json_response(
                    {"success": False, "error": "Missing value parameter"}, status=400
                )

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
        backup: BackupHandler,
        filesystem: FileSystemHandler,
        custom_words: CustomWordsHandler,
        supporters: SupportersHandler,
        doctor: DoctorHandler,
        example_workflows: ExampleWorkflowsHandler,
        base_model: BaseModelHandlerSet,
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
        self.backup = backup
        self.filesystem = filesystem
        self.custom_words = custom_words
        self.supporters = supporters
        self.doctor = doctor
        self.example_workflows = example_workflows
        self.base_model = base_model

    def to_route_mapping(
        self,
    ) -> Mapping[str, Callable[[web.Request], Awaitable[web.StreamResponse]]]:
        return {
            "health_check": self.health.health_check,
            "get_settings": self.settings.get_settings,
            "update_settings": self.settings.update_settings,
            "get_doctor_diagnostics": self.doctor.get_doctor_diagnostics,
            "repair_doctor_cache": self.doctor.repair_doctor_cache,
            "export_doctor_bundle": self.doctor.export_doctor_bundle,
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
            "get_model_version_download_status": self.model_library.get_model_version_download_status,
            "set_model_version_download_status": self.model_library.set_model_version_download_status,
            "get_civitai_user_models": self.model_library.get_civitai_user_models,
            "download_metadata_archive": self.metadata_archive.download_metadata_archive,
            "remove_metadata_archive": self.metadata_archive.remove_metadata_archive,
            "get_metadata_archive_status": self.metadata_archive.get_metadata_archive_status,
            "get_backup_status": self.backup.get_backup_status,
            "export_backup": self.backup.export_backup,
            "import_backup": self.backup.import_backup,
            "get_model_versions_status": self.model_library.get_model_versions_status,
            "open_file_location": self.filesystem.open_file_location,
            "open_settings_location": self.filesystem.open_settings_location,
            "open_backup_location": self.filesystem.open_backup_location,
            "search_custom_words": self.custom_words.search_custom_words,
            "get_supporters": self.supporters.get_supporters,
            "get_example_workflows": self.example_workflows.get_example_workflows,
            "get_example_workflow": self.example_workflows.get_example_workflow,
            # Base model handlers
            "get_base_models": self.base_model.get_base_models,
            "refresh_base_models": self.base_model.refresh_base_models,
            "get_base_model_categories": self.base_model.get_base_model_categories,
            "get_base_model_cache_status": self.base_model.get_base_model_cache_status,
        }


def build_service_registry_adapter() -> ServiceRegistryAdapter:
    return ServiceRegistryAdapter(
        get_lora_scanner=ServiceRegistry.get_lora_scanner,
        get_checkpoint_scanner=ServiceRegistry.get_checkpoint_scanner,
        get_embedding_scanner=ServiceRegistry.get_embedding_scanner,
        get_downloaded_version_history_service=ServiceRegistry.get_downloaded_version_history_service,
        get_backup_service=ServiceRegistry.get_backup_service,
    )
