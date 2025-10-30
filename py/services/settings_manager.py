import asyncio
import copy
import json
import os
import logging
from pathlib import Path
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Awaitable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..utils.constants import DEFAULT_PRIORITY_TAG_CONFIG
from ..utils.settings_paths import ensure_settings_file
from ..utils.tag_priorities import (
    PriorityTagEntry,
    collect_canonical_tags,
    parse_priority_tag_string,
    resolve_priority_tag,
)

logger = logging.getLogger(__name__)


CORE_USER_SETTING_KEYS: Tuple[str, ...] = (
    "civitai_api_key",
    "folder_paths",
)


DEFAULT_SETTINGS: Dict[str, Any] = {
    "civitai_api_key": "",
    "use_portable_settings": False,
    "language": "en",
    "show_only_sfw": False,
    "enable_metadata_archive_db": False,
    "proxy_enabled": False,
    "proxy_host": "",
    "proxy_port": "",
    "proxy_username": "",
    "proxy_password": "",
    "proxy_type": "http",
    "default_lora_root": "",
    "default_checkpoint_root": "",
    "default_embedding_root": "",
    "base_model_path_mappings": {},
    "download_path_templates": {},
    "folder_paths": {},
    "example_images_path": "",
    "optimize_example_images": True,
    "auto_download_example_images": False,
    "blur_mature_content": True,
    "autoplay_on_hover": False,
    "display_density": "default",
    "card_info_display": "always",
    "include_trigger_words": False,
    "compact_mode": False,
    "priority_tags": DEFAULT_PRIORITY_TAG_CONFIG.copy(),
    "model_name_display": "model_name",
    "model_card_footer_action": "example_images",
}


class SettingsManager:
    def __init__(self):
        self.settings_file = ensure_settings_file(logger)
        self._standalone_mode = self._detect_standalone_mode()
        self._startup_messages: List[Dict[str, Any]] = []
        self._needs_initial_save = False
        self._bootstrap_reason: Optional[str] = None
        self._seed_template: Optional[Dict[str, Any]] = None
        self._template_payload_cache: Optional[Dict[str, Any]] = None
        self._template_payload_cache_loaded = False
        self._original_disk_payload: Optional[Dict[str, Any]] = None
        self._preserve_disk_template = False
        self._template_path = Path(__file__).resolve().parents[2] / "settings.json.example"
        self.settings = self._load_settings()
        self._migrate_setting_keys()
        self._ensure_default_settings()
        self._migrate_to_library_registry()
        self._migrate_download_path_template()
        self._auto_set_default_roots()
        self._check_environment_variables()
        self._collect_configuration_warnings()

        if self._needs_initial_save:
            self._save_settings()
            self._needs_initial_save = False

    def _detect_standalone_mode(self) -> bool:
        """Return ``True`` when running in standalone mode."""

        return os.environ.get("LORA_MANAGER_STANDALONE") == "1"

    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from file"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._original_disk_payload = copy.deepcopy(data)
                    if self._matches_template_payload(data):
                        self._preserve_disk_template = True
                return data
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse settings.json: %s", exc)
                self._add_startup_message(
                    code="settings-json-invalid",
                    title="Settings file could not be parsed",
                    message=(
                        "LoRA Manager could not parse settings.json. Default settings "
                        "will be used for this session."
                    ),
                    severity="error",
                    actions=self._default_settings_actions(),
                    details=str(exc),
                    dismissible=False,
                )
                self._needs_initial_save = True
                self._bootstrap_reason = "invalid"
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.error("Unexpected error loading settings: %s", exc)
                self._add_startup_message(
                    code="settings-json-unreadable",
                    title="Settings file could not be read",
                    message="LoRA Manager could not read settings.json. Default settings will be used for this session.",
                    severity="error",
                    actions=self._default_settings_actions(),
                    details=str(exc),
                    dismissible=False,
                )
                self._needs_initial_save = True
                self._bootstrap_reason = "unreadable"

        if not os.path.exists(self.settings_file):
            self._needs_initial_save = True
            self._bootstrap_reason = "missing"
            seeded = self._load_settings_template()
            if seeded is not None:
                defaults = self._get_default_settings()
                merged = self._merge_template_with_defaults(defaults, seeded)
                return merged
        return self._get_default_settings()

    def _load_settings_template(self) -> Optional[Dict[str, Any]]:
        """Load the bundled template when no user settings are found."""

        payload = self._read_template_payload()
        if payload is None:
            return None

        self._seed_template = copy.deepcopy(payload)
        return copy.deepcopy(payload)

    def _read_template_payload(self) -> Optional[Dict[str, Any]]:
        """Return the cached contents of ``settings.json.example`` when available."""

        if self._template_payload_cache_loaded:
            if self._template_payload_cache is None:
                return None
            return copy.deepcopy(self._template_payload_cache)

        self._template_payload_cache_loaded = True

        try:
            with self._template_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            logger.debug("settings.json.example not found at %s", self._template_path)
            return None
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse settings.json.example: %s", exc)
            return None

        if not isinstance(data, dict):
            logger.debug("settings.json.example is not a JSON object; ignoring template")
            return None

        self._template_payload_cache = copy.deepcopy(data)
        return copy.deepcopy(self._template_payload_cache)

    def _matches_template_payload(self, payload: Mapping[str, Any]) -> bool:
        """Return ``True`` when ``payload`` matches the bundled template."""

        template = self._read_template_payload()
        if template is None:
            return False

        return payload == template

    def _merge_template_with_defaults(
        self, defaults: Dict[str, Any], template: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Merge template values into the in-memory defaults."""

        merged = copy.deepcopy(defaults)
        for key, value in template.items():
            if key == "folder_paths" and isinstance(value, Mapping):
                merged[key] = self._normalize_folder_paths(value)
            else:
                merged[key] = copy.deepcopy(value)

        merged.setdefault("language", "en")
        merged.setdefault("folder_paths", {})
        library_name = merged.get("active_library") or "default"
        merged["libraries"] = {
            library_name: self._build_library_payload(
                folder_paths=merged.get("folder_paths", {}),
                default_lora_root=merged.get("default_lora_root"),
                default_checkpoint_root=merged.get("default_checkpoint_root"),
                default_embedding_root=merged.get("default_embedding_root"),
            )
        }
        merged["active_library"] = library_name
        return merged

    def _ensure_default_settings(self) -> None:
        """Ensure all default settings keys exist"""
        defaults = self._get_default_settings()
        updated_existing = False
        inserted_defaults = False

        if "priority_tags" in self.settings:
            normalized_priority = self._normalize_priority_tag_config(
                self.settings.get("priority_tags")
            )
            if normalized_priority != self.settings.get("priority_tags"):
                self.settings["priority_tags"] = normalized_priority
                updated_existing = True
        else:
            self.settings["priority_tags"] = copy.deepcopy(
                defaults.get("priority_tags", DEFAULT_PRIORITY_TAG_CONFIG)
            )
            inserted_defaults = True

        for key, value in defaults.items():
            if key == "priority_tags":
                continue
            if key not in self.settings:
                if isinstance(value, dict):
                    self.settings[key] = copy.deepcopy(value)
                else:
                    self.settings[key] = value
                inserted_defaults = True

        if updated_existing or (
            inserted_defaults and self._bootstrap_reason in {"invalid", "unreadable"}
        ):
            self._save_settings()

    def _migrate_to_library_registry(self) -> None:
        """Ensure settings include the multi-library registry structure."""
        libraries = self.settings.get("libraries")
        active_name = self.settings.get("active_library")
        initial_bootstrap = self._bootstrap_reason == "missing"

        raw_top_level_paths = self.settings.get("folder_paths", {})
        normalized_top_level_paths: Dict[str, List[str]] = {}
        if isinstance(raw_top_level_paths, Mapping):
            normalized_top_level_paths = self._normalize_folder_paths(raw_top_level_paths)
            if normalized_top_level_paths != raw_top_level_paths:
                self.settings["folder_paths"] = copy.deepcopy(normalized_top_level_paths)

        top_level_has_paths = self._has_configured_paths(normalized_top_level_paths)

        needs_library_bootstrap = not isinstance(libraries, dict) or not libraries

        if (
            not needs_library_bootstrap
            and top_level_has_paths
            and len(libraries) == 1
        ):
            only_library_payload = next(iter(libraries.values()))
            if isinstance(only_library_payload, Mapping):
                folder_payload = only_library_payload.get("folder_paths")
                if not self._has_configured_paths(folder_payload):
                    needs_library_bootstrap = True

        if needs_library_bootstrap:
            library_name = active_name or "default"
            library_payload = self._build_library_payload(
                folder_paths=normalized_top_level_paths,
                default_lora_root=self.settings.get("default_lora_root", ""),
                default_checkpoint_root=self.settings.get("default_checkpoint_root", ""),
                default_embedding_root=self.settings.get("default_embedding_root", ""),
            )
            libraries = {library_name: library_payload}
            self.settings["libraries"] = libraries
            self.settings["active_library"] = library_name
            self._sync_active_library_to_root(save=False)
            if not initial_bootstrap and not self._preserve_disk_template:
                self._save_settings()
            return

        seed_library_name: Optional[str] = None
        if top_level_has_paths and isinstance(libraries, dict):
            target_name: Optional[str] = None
            if active_name and active_name in libraries:
                target_name = active_name
            elif len(libraries) == 1:
                target_name = next(iter(libraries.keys()))

            if target_name:
                candidate_payload = libraries.get(target_name)
                if isinstance(candidate_payload, Mapping) and not self._has_configured_paths(candidate_payload.get("folder_paths")):
                    seed_library_name = target_name

        sanitized_libraries: Dict[str, Dict[str, Any]] = {}
        changed = False
        for name, data in libraries.items():
            if not isinstance(data, dict):
                data = {}
                changed = True

            candidate_folder_paths = data.get("folder_paths")
            if (
                seed_library_name == name
                and not self._has_configured_paths(candidate_folder_paths)
                and top_level_has_paths
            ):
                candidate_folder_paths = normalized_top_level_paths

            payload = self._build_library_payload(
                folder_paths=candidate_folder_paths,
                default_lora_root=data.get("default_lora_root"),
                default_checkpoint_root=data.get("default_checkpoint_root"),
                default_embedding_root=data.get("default_embedding_root"),
                metadata=data.get("metadata"),
                base=data,
            )
            sanitized_libraries[name] = payload
            if payload is not data:
                changed = True

        if changed:
            self.settings["libraries"] = sanitized_libraries

        if not active_name or active_name not in sanitized_libraries:
            changed = True
            if sanitized_libraries:
                self.settings["active_library"] = next(iter(sanitized_libraries.keys()))
            else:
                self.settings["active_library"] = "default"

        self._sync_active_library_to_root(save=changed and not initial_bootstrap)
        if changed and initial_bootstrap:
            self._needs_initial_save = True

    def _sync_active_library_to_root(self, *, save: bool = False) -> None:
        """Update top-level folder path settings to mirror the active library."""
        libraries = self.settings.get("libraries", {})
        active_name = self.settings.get("active_library")
        if not libraries:
            return

        if active_name not in libraries:
            active_name = next(iter(libraries.keys()))
            self.settings["active_library"] = active_name

        active_library = libraries.get(active_name, {})
        folder_paths = copy.deepcopy(active_library.get("folder_paths", {}))
        self.settings["folder_paths"] = folder_paths
        self.settings["default_lora_root"] = active_library.get("default_lora_root", "")
        self.settings["default_checkpoint_root"] = active_library.get("default_checkpoint_root", "")
        self.settings["default_embedding_root"] = active_library.get("default_embedding_root", "")

        if save:
            self._save_settings()

    def _current_timestamp(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _build_library_payload(
        self,
        *,
        folder_paths: Optional[Mapping[str, Iterable[str]]] = None,
        default_lora_root: Optional[str] = None,
        default_checkpoint_root: Optional[str] = None,
        default_embedding_root: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        base: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = dict(base or {})
        timestamp = self._current_timestamp()

        if folder_paths is not None:
            payload["folder_paths"] = self._normalize_folder_paths(folder_paths)
        else:
            payload.setdefault("folder_paths", {})

        if default_lora_root is not None:
            payload["default_lora_root"] = default_lora_root
        else:
            payload.setdefault("default_lora_root", "")

        if default_checkpoint_root is not None:
            payload["default_checkpoint_root"] = default_checkpoint_root
        else:
            payload.setdefault("default_checkpoint_root", "")

        if default_embedding_root is not None:
            payload["default_embedding_root"] = default_embedding_root
        else:
            payload.setdefault("default_embedding_root", "")

        if metadata:
            merged_meta = dict(payload.get("metadata", {}))
            merged_meta.update(metadata)
            payload["metadata"] = merged_meta

        payload.setdefault("created_at", timestamp)
        payload["updated_at"] = timestamp
        return payload

    def _normalize_folder_paths(
        self, folder_paths: Mapping[str, Iterable[str]]
    ) -> Dict[str, List[str]]:
        normalized: Dict[str, List[str]] = {}
        for key, values in folder_paths.items():
            if not isinstance(values, Iterable):
                continue
            cleaned: List[str] = []
            seen = set()
            for value in values:
                if not isinstance(value, str):
                    continue
                stripped = value.strip()
                if not stripped:
                    continue
                if stripped not in seen:
                    cleaned.append(stripped)
                    seen.add(stripped)
            normalized[key] = cleaned
        return normalized

    def _has_configured_paths(self, folder_paths: Any) -> bool:
        if not isinstance(folder_paths, Mapping):
            return False

        for values in folder_paths.values():
            if isinstance(values, str):
                candidate_values = [values]
            else:
                try:
                    candidate_values = list(values)  # type: ignore[arg-type]
                except TypeError:
                    continue

            for path in candidate_values:
                if isinstance(path, str) and path.strip():
                    return True

        return False

    def _validate_folder_paths(
        self,
        library_name: str,
        folder_paths: Mapping[str, Iterable[str]],
    ) -> None:
        """Ensure folder paths do not overlap with other libraries."""
        libraries = self.settings.get("libraries", {})
        normalized_new: Dict[str, Dict[str, str]] = {}
        for key, values in folder_paths.items():
            path_map: Dict[str, str] = {}
            for value in values:
                if not isinstance(value, str):
                    continue
                stripped = value.strip()
                if not stripped:
                    continue
                normalized_value = os.path.normcase(os.path.normpath(stripped))
                path_map[normalized_value] = stripped
            if path_map:
                normalized_new[key] = path_map

        if not normalized_new:
            return

        for other_name, other in libraries.items():
            if other_name == library_name:
                continue
            other_paths = other.get("folder_paths", {})
            for key, new_paths in normalized_new.items():
                existing = {
                    os.path.normcase(os.path.normpath(path))
                    for path in other_paths.get(key, [])
                    if isinstance(path, str) and path
                }
                overlap = existing.intersection(new_paths.keys())
                if overlap:
                    collisions = ", ".join(sorted(new_paths[value] for value in overlap))
                    raise ValueError(
                        f"Folder path(s) {collisions} already assigned to library '{other_name}'"
                    )

    def _update_active_library_entry(
        self,
        *,
        folder_paths: Optional[Mapping[str, Iterable[str]]] = None,
        default_lora_root: Optional[str] = None,
        default_checkpoint_root: Optional[str] = None,
        default_embedding_root: Optional[str] = None,
    ) -> bool:
        libraries = self.settings.get("libraries", {})
        active_name = self.settings.get("active_library")
        if not active_name or active_name not in libraries:
            return False

        library = libraries[active_name]
        changed = False

        if folder_paths is not None:
            normalized_paths = self._normalize_folder_paths(folder_paths)
            if library.get("folder_paths") != normalized_paths:
                library["folder_paths"] = normalized_paths
                changed = True

        if default_lora_root is not None and library.get("default_lora_root") != default_lora_root:
            library["default_lora_root"] = default_lora_root
            changed = True

        if default_checkpoint_root is not None and library.get("default_checkpoint_root") != default_checkpoint_root:
            library["default_checkpoint_root"] = default_checkpoint_root
            changed = True

        if default_embedding_root is not None and library.get("default_embedding_root") != default_embedding_root:
            library["default_embedding_root"] = default_embedding_root
            changed = True

        if changed:
            library.setdefault("created_at", self._current_timestamp())
            library["updated_at"] = self._current_timestamp()

        return changed

    def _migrate_setting_keys(self) -> None:
        """Migrate legacy camelCase setting keys to snake_case"""
        key_migrations = {
            'optimizeExampleImages': 'optimize_example_images',
            'autoDownloadExampleImages': 'auto_download_example_images',
            'blurMatureContent': 'blur_mature_content',
            'autoplayOnHover': 'autoplay_on_hover',
            'displayDensity': 'display_density',
            'cardInfoDisplay': 'card_info_display',
            'includeTriggerWords': 'include_trigger_words',
            'compactMode': 'compact_mode',
            'modelCardFooterAction': 'model_card_footer_action',
        }

        updated = False
        for old_key, new_key in key_migrations.items():
            if old_key in self.settings:
                if new_key not in self.settings:
                    self.settings[new_key] = self.settings[old_key]
                del self.settings[old_key]
                updated = True

        if updated:
            logger.info("Migrated legacy setting keys to snake_case")
            self._save_settings()

    def _migrate_download_path_template(self):
        """Migrate old download_path_template to new download_path_templates"""
        old_template = self.settings.get('download_path_template')
        templates = self.settings.get('download_path_templates')

        # If old template exists and new templates don't exist, migrate
        if old_template is not None and not templates:
            logger.info("Migrating download_path_template to download_path_templates")
            self.settings['download_path_templates'] = {
                'lora': old_template,
                'checkpoint': old_template,
                'embedding': old_template
            }
            # Remove old setting
            del self.settings['download_path_template']
            self._save_settings()
            logger.info("Migration completed")

    def _auto_set_default_roots(self):
        """Auto set default root paths when only one folder is present and the current default is unset or not among the options."""
        folder_paths = self.settings.get('folder_paths', {})
        updated = False
        # loras
        loras = folder_paths.get('loras', [])
        if isinstance(loras, list) and len(loras) == 1:
            current_lora_root = self.settings.get('default_lora_root')
            if current_lora_root not in loras:
                self.settings['default_lora_root'] = loras[0]
                updated = True
        # checkpoints
        checkpoints = folder_paths.get('checkpoints', [])
        if isinstance(checkpoints, list) and len(checkpoints) == 1:
            current_checkpoint_root = self.settings.get('default_checkpoint_root')
            if current_checkpoint_root not in checkpoints:
                self.settings['default_checkpoint_root'] = checkpoints[0]
                updated = True
        # embeddings
        embeddings = folder_paths.get('embeddings', [])
        if isinstance(embeddings, list) and len(embeddings) == 1:
            current_embedding_root = self.settings.get('default_embedding_root')
            if current_embedding_root not in embeddings:
                self.settings['default_embedding_root'] = embeddings[0]
                updated = True
        if updated:
            self._update_active_library_entry(
                default_lora_root=self.settings.get('default_lora_root'),
                default_checkpoint_root=self.settings.get('default_checkpoint_root'),
                default_embedding_root=self.settings.get('default_embedding_root'),
            )
            if self._bootstrap_reason == "missing":
                self._needs_initial_save = True
            else:
                self._save_settings()

    def _check_environment_variables(self) -> None:
        """Check for environment variables and update settings if needed"""
        env_api_key = os.environ.get('CIVITAI_API_KEY')
        if env_api_key:  # Check if the environment variable exists and is not empty
            logger.info("Found CIVITAI_API_KEY environment variable")
            # Always use the environment variable if it exists
            self.settings['civitai_api_key'] = env_api_key
            self._save_settings()

    def _default_settings_actions(self) -> List[Dict[str, Any]]:
        return [
            {
                "action": "open-settings-location",
                "label": "Open settings folder",
                "type": "primary",
                "icon": "fas fa-folder-open",
            }
        ]

    def _add_startup_message(
        self,
        *,
        code: str,
        title: str,
        message: str,
        severity: str = "info",
        actions: Optional[List[Dict[str, Any]]] = None,
        details: Optional[str] = None,
        dismissible: bool = False,
    ) -> None:
        if any(existing.get("code") == code for existing in self._startup_messages):
            return

        payload: Dict[str, Any] = {
            "code": code,
            "title": title,
            "message": message,
            "severity": severity.lower(),
            "dismissible": bool(dismissible),
        }

        if actions:
            payload["actions"] = [dict(action) for action in actions]
        if details:
            payload["details"] = details
        payload["settings_file"] = self.settings_file

        self._startup_messages.append(payload)

    def _collect_configuration_warnings(self) -> None:
        if not self._standalone_mode:
            return

        folder_paths = self.settings.get('folder_paths', {}) or {}
        monitored_keys = ('loras', 'checkpoints', 'embeddings')

        has_valid_paths = False
        for key in monitored_keys:
            raw_paths = folder_paths.get(key) or []
            if isinstance(raw_paths, str):
                raw_paths = [raw_paths]
            try:
                iterator = list(raw_paths)
            except TypeError:
                continue
            if any(isinstance(path, str) and path and os.path.exists(path) for path in iterator):
                has_valid_paths = True
                break

        if not has_valid_paths:
            if self._bootstrap_reason == "missing":
                message = (
                    "LoRA Manager created a default settings.json because no configuration was found. "
                    "Edit settings.json to add your model directories so library scanning can run."
                )
            else:
                message = (
                    "LoRA Manager could not locate any configured model directories. "
                    "Edit settings.json to add your model folders so library scanning can run."
                )
            self._add_startup_message(
                code="missing-model-paths",
                title="Model folders need setup",
                message=message,
                severity="warning",
                actions=self._default_settings_actions(),
                dismissible=False,
            )

    def refresh_environment_variables(self) -> None:
        """Refresh settings from environment variables"""
        self._check_environment_variables()

    def _get_default_settings(self) -> Dict[str, Any]:
        """Return default settings"""
        defaults = copy.deepcopy(DEFAULT_SETTINGS)
        defaults['base_model_path_mappings'] = {}
        defaults['download_path_templates'] = {}
        defaults['priority_tags'] = DEFAULT_PRIORITY_TAG_CONFIG.copy()
        defaults.setdefault('folder_paths', {})

        library_name = defaults.get("active_library") or "default"
        default_library = self._build_library_payload(
            folder_paths=defaults.get("folder_paths", {}),
            default_lora_root=defaults.get("default_lora_root"),
            default_checkpoint_root=defaults.get("default_checkpoint_root"),
            default_embedding_root=defaults.get("default_embedding_root"),
        )
        defaults['libraries'] = {library_name: default_library}
        defaults['active_library'] = library_name
        return defaults

    def _normalize_priority_tag_config(self, value: Any) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        if isinstance(value, Mapping):
            for key, raw in value.items():
                if not isinstance(key, str) or not isinstance(raw, str):
                    continue
                normalized[key] = raw.strip()

        for model_type, default_value in DEFAULT_PRIORITY_TAG_CONFIG.items():
            normalized.setdefault(model_type, default_value)

        return normalized

    def get_priority_tag_config(self) -> Dict[str, str]:
        stored_value = self.settings.get("priority_tags")
        normalized = self._normalize_priority_tag_config(stored_value)
        if normalized != stored_value:
            self.settings["priority_tags"] = normalized
            self._save_settings()
        return normalized.copy()

    def get_startup_messages(self) -> List[Dict[str, Any]]:
        return [message.copy() for message in self._startup_messages]

    def get_priority_tag_entries(self, model_type: str) -> List[PriorityTagEntry]:
        config = self.get_priority_tag_config()
        raw_config = config.get(model_type, "")
        return parse_priority_tag_string(raw_config)

    def resolve_priority_tag_for_model(
        self, tags: Sequence[str] | Iterable[str], model_type: str
    ) -> str:
        entries = self.get_priority_tag_entries(model_type)
        resolved = resolve_priority_tag(tags, entries)
        if resolved:
            return resolved

        for tag in tags:
            if isinstance(tag, str) and tag:
                return tag
        return ""

    def get_priority_tag_suggestions(self) -> Dict[str, List[str]]:
        suggestions: Dict[str, List[str]] = {}
        config = self.get_priority_tag_config()
        for model_type, raw_value in config.items():
            entries = parse_priority_tag_string(raw_value)
            suggestions[model_type] = collect_canonical_tags(entries)
        return suggestions

    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value"""
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set setting value and save"""
        self.settings[key] = value
        if key == 'folder_paths' and isinstance(value, Mapping):
            self._update_active_library_entry(folder_paths=value)  # type: ignore[arg-type]
        elif key == 'default_lora_root':
            self._update_active_library_entry(default_lora_root=str(value))
        elif key == 'default_checkpoint_root':
            self._update_active_library_entry(default_checkpoint_root=str(value))
        elif key == 'default_embedding_root':
            self._update_active_library_entry(default_embedding_root=str(value))
        elif key == 'model_name_display':
            self._notify_model_name_display_change(value)
        self._save_settings()

    def delete(self, key: str) -> None:
        """Delete setting key and save"""
        if key in self.settings:
            del self.settings[key]
            self._save_settings()
            logger.info(f"Deleted setting: {key}")

    def _notify_model_name_display_change(self, value: Any) -> None:
        """Trigger cache resorting when the model name display preference updates."""

        try:
            from .service_registry import ServiceRegistry  # type: ignore
        except Exception:  # pragma: no cover - registry optional in some contexts
            return

        display_mode = value if isinstance(value, str) else "model_name"
        pending: List[Tuple[Optional[asyncio.AbstractEventLoop], Awaitable[Any]]] = []

        def _resolve_service_loop(service: Any) -> Optional[asyncio.AbstractEventLoop]:
            loop = getattr(service, "loop", None)
            if loop is None:
                loop = getattr(service, "_loop", None)
            return loop if isinstance(loop, asyncio.AbstractEventLoop) else None

        for service_name in (
            "lora_scanner",
            "checkpoint_scanner",
            "embedding_scanner",
            "recipe_scanner",
        ):
            service = ServiceRegistry.get_service_sync(service_name)
            if not service or not hasattr(service, "on_model_name_display_changed"):
                continue

            try:
                result = service.on_model_name_display_changed(display_mode)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.debug(
                    "Service %s failed to schedule name display update: %s",
                    service_name,
                    exc,
                )
                continue

            if asyncio.iscoroutine(result):
                service_loop = _resolve_service_loop(service)
                pending.append((service_loop, result))

        if not pending:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        for service_loop, coroutine in pending:
            target_loop = service_loop or loop

            if target_loop is None:
                try:
                    asyncio.run(coroutine)
                except RuntimeError:
                    logger.debug("Skipping name display update due to missing event loop")
                continue

            if loop is not None and target_loop is loop:
                target_loop.create_task(coroutine)
                continue

            if target_loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(coroutine, target_loop)
                except Exception as exc:  # pragma: no cover - defensive guard
                    logger.debug("Failed to dispatch name display update: %s", exc)
                continue

            try:
                asyncio.run(coroutine)
            except RuntimeError:
                logger.debug("Skipping name display update due to closed loop")

    def _save_settings(self) -> None:
        """Save settings to file"""
        try:
            payload = self._serialize_settings_for_disk()
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
        else:
            if self._bootstrap_reason == "missing":
                self._bootstrap_reason = None
            self._seed_template = None

    def _serialize_settings_for_disk(self) -> Dict[str, Any]:
        """Return the settings payload that should be persisted to disk."""

        if self._bootstrap_reason == "missing":
            minimal: Dict[str, Any] = {}
            for key in CORE_USER_SETTING_KEYS:
                if key in self.settings:
                    minimal[key] = copy.deepcopy(self.settings[key])

            if self._seed_template:
                for key, value in self._seed_template.items():
                    minimal.setdefault(key, copy.deepcopy(value))

            return minimal

        return copy.deepcopy(self.settings)

    def get_libraries(self) -> Dict[str, Dict[str, Any]]:
        """Return a copy of the registered libraries."""
        libraries = self.settings.get("libraries", {})
        return copy.deepcopy(libraries)

    def get_active_library_name(self) -> str:
        """Return the currently active library name."""
        libraries = self.settings.get("libraries", {})
        active_name = self.settings.get("active_library")
        if active_name and active_name in libraries:
            return active_name
        if libraries:
            return next(iter(libraries.keys()))
        return "default"

    def get_active_library(self) -> Dict[str, Any]:
        """Return a copy of the active library configuration."""
        libraries = self.settings.get("libraries", {})
        active_name = self.get_active_library_name()
        return copy.deepcopy(libraries.get(active_name, {}))

    def activate_library(self, library_name: str) -> None:
        """Activate a library by name and refresh dependent services."""
        libraries = self.settings.get("libraries", {})
        if library_name not in libraries:
            raise KeyError(f"Library '{library_name}' does not exist")

        current_active = self.get_active_library_name()
        if current_active == library_name:
            # Ensure root settings stay in sync even if already active
            self._sync_active_library_to_root(save=False)
            self._save_settings()
            self._notify_library_change(library_name)
            return

        self.settings["active_library"] = library_name
        self._sync_active_library_to_root(save=False)
        self._save_settings()
        self._notify_library_change(library_name)

    def upsert_library(
        self,
        library_name: str,
        *,
        folder_paths: Optional[Mapping[str, Iterable[str]]] = None,
        default_lora_root: Optional[str] = None,
        default_checkpoint_root: Optional[str] = None,
        default_embedding_root: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        activate: bool = False,
    ) -> Dict[str, Any]:
        """Create or update a library definition."""

        name = library_name.strip()
        if not name:
            raise ValueError("Library name cannot be empty")

        if folder_paths is not None:
            self._validate_folder_paths(name, folder_paths)

        libraries = self.settings.setdefault("libraries", {})
        existing = libraries.get(name, {})

        payload = self._build_library_payload(
            folder_paths=folder_paths if folder_paths is not None else existing.get("folder_paths"),
            default_lora_root=default_lora_root if default_lora_root is not None else existing.get("default_lora_root"),
            default_checkpoint_root=(
                default_checkpoint_root
                if default_checkpoint_root is not None
                else existing.get("default_checkpoint_root")
            ),
            default_embedding_root=(
                default_embedding_root
                if default_embedding_root is not None
                else existing.get("default_embedding_root")
            ),
            metadata=metadata if metadata is not None else existing.get("metadata"),
            base=existing,
        )

        libraries[name] = payload

        if activate or not self.settings.get("active_library"):
            self.settings["active_library"] = name

        self._sync_active_library_to_root(save=False)
        self._save_settings()

        if self.settings.get("active_library") == name:
            self._notify_library_change(name)

        return payload

    def create_library(
        self,
        library_name: str,
        *,
        folder_paths: Mapping[str, Iterable[str]],
        default_lora_root: str = "",
        default_checkpoint_root: str = "",
        default_embedding_root: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
        activate: bool = False,
    ) -> Dict[str, Any]:
        """Create a new library entry."""

        libraries = self.settings.get("libraries", {})
        if library_name in libraries:
            raise ValueError(f"Library '{library_name}' already exists")

        return self.upsert_library(
            library_name,
            folder_paths=folder_paths,
            default_lora_root=default_lora_root,
            default_checkpoint_root=default_checkpoint_root,
            default_embedding_root=default_embedding_root,
            metadata=metadata,
            activate=activate,
        )

    def rename_library(self, old_name: str, new_name: str) -> None:
        """Rename an existing library."""

        libraries = self.settings.get("libraries", {})
        if old_name not in libraries:
            raise KeyError(f"Library '{old_name}' does not exist")
        new_name_stripped = new_name.strip()
        if not new_name_stripped:
            raise ValueError("New library name cannot be empty")
        if new_name_stripped in libraries:
            raise ValueError(f"Library '{new_name_stripped}' already exists")

        libraries[new_name_stripped] = libraries.pop(old_name)
        if self.settings.get("active_library") == old_name:
            self.settings["active_library"] = new_name_stripped
            active_name = new_name_stripped
        else:
            active_name = self.settings.get("active_library")

        self._sync_active_library_to_root(save=False)
        self._save_settings()

        if active_name == new_name_stripped:
            self._notify_library_change(new_name_stripped)

    def delete_library(self, library_name: str) -> None:
        """Remove a library definition."""

        libraries = self.settings.get("libraries", {})
        if library_name not in libraries:
            raise KeyError(f"Library '{library_name}' does not exist")
        if len(libraries) == 1:
            raise ValueError("At least one library must remain")

        was_active = self.settings.get("active_library") == library_name
        libraries.pop(library_name)

        if was_active:
            new_active = next(iter(libraries.keys()))
            self.settings["active_library"] = new_active
        self._sync_active_library_to_root(save=False)
        self._save_settings()

        if was_active:
            self._notify_library_change(self.settings["active_library"])

    def update_active_library_paths(
        self,
        folder_paths: Mapping[str, Iterable[str]],
        *,
        default_lora_root: Optional[str] = None,
        default_checkpoint_root: Optional[str] = None,
        default_embedding_root: Optional[str] = None,
    ) -> None:
        """Update folder paths for the active library."""

        active_name = self.get_active_library_name()
        self.upsert_library(
            active_name,
            folder_paths=folder_paths,
            default_lora_root=default_lora_root,
            default_checkpoint_root=default_checkpoint_root,
            default_embedding_root=default_embedding_root,
            activate=True,
        )

    def _notify_library_change(self, library_name: str) -> None:
        """Notify dependent services that the active library changed."""
        libraries = self.settings.get("libraries", {})
        library_config = libraries.get(library_name, {})
        library_snapshot = copy.deepcopy(library_config)

        try:
            from ..config import config  # Local import to avoid circular dependency

            config.apply_library_settings(library_snapshot)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to apply library settings to config: %s", exc)

        try:
            from .service_registry import ServiceRegistry  # type: ignore

            for service_name in (
                "lora_scanner",
                "checkpoint_scanner",
                "embedding_scanner",
                "recipe_scanner",
            ):
                service = ServiceRegistry.get_service_sync(service_name)
                if service and hasattr(service, "on_library_changed"):
                    try:
                        service.on_library_changed()
                    except Exception as service_exc:  # pragma: no cover - defensive logging
                        logger.debug(
                            "Service %s failed to handle library change: %s",
                            service_name,
                            service_exc,
                        )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to notify services about library change: %s", exc)

    def get_download_path_template(self, model_type: str) -> str:
        """Get download path template for specific model type
        
        Args:
            model_type: The type of model ('lora', 'checkpoint', 'embedding')
            
        Returns:
            Template string for the model type, defaults to '{base_model}/{first_tag}'
        """
        templates = self.settings.get('download_path_templates', {})
        
        # Handle edge case where templates might be stored as JSON string
        if isinstance(templates, str):
            try:
                # Try to parse JSON string
                parsed_templates = json.loads(templates)
                if isinstance(parsed_templates, dict):
                    # Update settings with parsed dictionary
                    self.settings['download_path_templates'] = parsed_templates
                    self._save_settings()
                    templates = parsed_templates
                    logger.info("Successfully parsed download_path_templates from JSON string")
                else:
                    raise ValueError("Parsed JSON is not a dictionary")
            except (json.JSONDecodeError, ValueError) as e:
                # If parsing fails, set default values
                logger.warning(f"Failed to parse download_path_templates JSON string: {e}. Setting default values.")
                default_template = '{base_model}/{first_tag}'
                templates = {
                    'lora': default_template,
                    'checkpoint': default_template,
                    'embedding': default_template
                }
                self.settings['download_path_templates'] = templates
                self._save_settings()
        
        # Ensure templates is a dictionary
        if not isinstance(templates, dict):
            default_template = '{base_model}/{first_tag}'
            templates = {
                'lora': default_template,
                'checkpoint': default_template,
                'embedding': default_template
            }
            self.settings['download_path_templates'] = templates
            self._save_settings()
        
        return templates.get(model_type, '{base_model}/{first_tag}')


_SETTINGS_MANAGER: Optional["SettingsManager"] = None
_SETTINGS_MANAGER_LOCK = Lock()
# Legacy module-level alias for backwards compatibility with callers that
# monkeypatch ``py.services.settings_manager.settings`` during tests.
settings: Optional["SettingsManager"] = None


def get_settings_manager() -> "SettingsManager":
    """Return the lazily initialised global :class:`SettingsManager`."""

    global _SETTINGS_MANAGER, settings
    if settings is not None:
        return settings

    if _SETTINGS_MANAGER is None:
        with _SETTINGS_MANAGER_LOCK:
            if _SETTINGS_MANAGER is None:
                _SETTINGS_MANAGER = SettingsManager()

    settings = _SETTINGS_MANAGER
    return _SETTINGS_MANAGER


def reset_settings_manager() -> None:
    """Reset the cached settings manager instance.

    Primarily intended for tests so they can configure the settings
    directory before the manager touches the filesystem.
    """

    global _SETTINGS_MANAGER, settings
    with _SETTINGS_MANAGER_LOCK:
        _SETTINGS_MANAGER = None
        settings = None
