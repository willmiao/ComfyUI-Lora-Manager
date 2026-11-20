"""Global wildcard activation state shared by LM and ComfyUI."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from ..utils.settings_paths import get_settings_dir
from .wildcard_parser import (
    normalize_wildcard_key,
    parse_wildcard_artifact,
    read_wildcard_source,
)

logger = logging.getLogger(__name__)

_SAFE_KEY_SEGMENT = re.compile(r"^[\w .\-+]+$", re.UNICODE)


class WildcardLibraryError(ValueError):
    pass


class WildcardConflictError(WildcardLibraryError):
    def __init__(self, conflicts: list[dict[str, Any]]) -> None:
        super().__init__("Activation would replace an existing wildcard key")
        self.conflicts = conflicts


def _path_key(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)).replace(os.sep, "/")


def _is_active_record(record: dict[str, Any] | None) -> bool:
    """Return whether an activation record is currently active.

    Records written before activation state was retained have no ``active``
    key; they were active by definition.
    """

    if not record:
        return False
    return record.get("active", True) is not False


def _file_signature(path: str) -> tuple[int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return int(stat.st_mtime_ns), int(stat.st_size)


def _validate_key_mapping(value: Any, *, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise WildcardLibraryError("Wildcard names must be strings")
    value = value.replace("\\", "/").strip().strip("/")
    if not value:
        if allow_empty:
            return ""
        raise WildcardLibraryError("A wildcard alias cannot be empty")
    if len(value) > 240:
        raise WildcardLibraryError("Wildcard names are limited to 240 characters")
    for segment in value.split("/"):
        if segment in (".", "..") or not _SAFE_KEY_SEGMENT.match(segment):
            raise WildcardLibraryError(f"Invalid wildcard name segment: {segment}")
    return normalize_wildcard_key(value)


class WildcardActivationService:
    _instance: "WildcardActivationService | None" = None

    def __init__(self, activations_path: str | None = None) -> None:
        self._fixed_path = activations_path
        self._lock = threading.RLock()
        self._runtime_signature: tuple[Any, ...] | None = None
        self._runtime_entries: dict[str, list[str]] = {}
        self._runtime_conflicts: list[dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> "WildcardActivationService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def activations_path(self) -> str:
        return self._fixed_path or os.path.join(
            get_settings_dir(create=True), "wildcard-activations.json"
        )

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            with open(self.activations_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            resources = payload.get("resources", {})
            if not isinstance(resources, dict):
                return {}
            valid: dict[str, dict[str, Any]] = {}
            for key, record in resources.items():
                if not isinstance(record, dict):
                    continue
                # Older files predate retained activation state; they were
                # active by definition.
                record.setdefault("active", True)
                valid[str(key)] = record
            return valid
        except FileNotFoundError:
            return {}
        except Exception:
            logger.error("Unable to load wildcard activations", exc_info=True)
            return {}

    def _save(self, activations: dict[str, dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.activations_path), exist_ok=True)
        temporary = f"{self.activations_path}.{uuid.uuid4().hex}.tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "resources": activations}, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary, self.activations_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _effective_key(original_key: str, activation: dict[str, Any] | None) -> str:
        if not activation:
            return original_key
        aliases = activation.get("aliases")
        if not isinstance(aliases, dict):
            aliases = {}
        alias = aliases.get(original_key, original_key)
        namespace = activation.get("namespace") or ""
        return normalize_wildcard_key(f"{namespace}/{alias}" if namespace else alias)

    def activation_for(
        self, file_path: str, *, include_inactive: bool = False
    ) -> dict[str, Any] | None:
        record = self._load().get(_path_key(file_path))
        if record is None:
            return None
        if not include_inactive and not _is_active_record(record):
            return None
        return record

    def decorate(self, resource: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(resource)
        record = self.activation_for(
            resource.get("file_path", ""), include_inactive=True
        )
        active = _is_active_record(record)
        # Keep the last namespace/alias on an inactive record so a later
        # reactivation can restore them, but effective keys only exist while
        # the resource is active.
        result["active"] = active
        result["activation_namespace"] = (record or {}).get("namespace") or ""
        result["activation_aliases"] = (record or {}).get("aliases") or {}
        result["activated_at"] = (record or {}).get("activated_at")
        for entry in result.get("entries", []):
            entry["effective_key"] = self._effective_key(
                entry["key"], record if active else None
            )
        return result

    @staticmethod
    def _short_key_warnings(key_sets: list[set[str]]) -> list[str]:
        leaves: dict[str, set[str]] = {}
        for keys in key_sets:
            for key in keys:
                leaves.setdefault(key.rsplit("/", 1)[-1], set()).add(key)
        return sorted(leaf for leaf, keys in leaves.items() if len(keys) > 1)

    def preview_activation(
        self,
        resource: dict[str, Any],
        namespace: str = "",
        aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        file_path = resource["file_path"]
        resource_key = _path_key(file_path)
        namespace = _validate_key_mapping(namespace, allow_empty=True)
        source_entries = resource.get("entries") or [
            entry.summary() for entry in parse_wildcard_artifact(file_path).entries
        ]
        source_keys = {entry["key"] for entry in source_entries}
        clean_aliases: dict[str, str] = {}
        for original, alias in (aliases or {}).items():
            if original not in source_keys:
                raise WildcardLibraryError(f"Unknown wildcard key: {original}")
            normalized = _validate_key_mapping(alias, allow_empty=False)
            if normalized != original:
                clean_aliases[original] = normalized
        activation = {"namespace": namespace, "aliases": clean_aliases}
        proposed_keys = [
            self._effective_key(entry["key"], activation) for entry in source_entries
        ]
        owners: dict[str, list[dict[str, str]]] = {}
        for entry in source_entries:
            effective = self._effective_key(entry["key"], activation)
            owners.setdefault(effective, []).append(
                {"resource_id": file_path, "source": entry["key"]}
            )
        activations = self._load()
        other_key_sets: list[set[str]] = []
        for other_key, other_activation in activations.items():
            if other_key == resource_key:
                continue
            if not _is_active_record(other_activation):
                continue
            other_entries = other_activation.get("entries") or []
            other_keys = {
                self._effective_key(entry["key"], other_activation)
                for entry in other_entries
            }
            other_key_sets.append(other_keys)
            for entry in other_entries:
                effective = self._effective_key(entry["key"], other_activation)
                if effective in owners:
                    owners[effective].append(
                        {
                            "resource_id": other_activation.get("file_path", other_key),
                            "source": entry["key"],
                        }
                    )
        from .wildcard_service import get_wildcard_service

        manual_keys = set(get_wildcard_service().get_manual_wildcard_dict())
        for key in manual_keys:
            if key in owners:
                owners[key].append({"resource_id": "manual", "source": key})
        conflicts = [
            {"key": key, "owners": key_owners}
            for key, key_owners in sorted(owners.items())
            if len(key_owners) > 1
        ]
        proposed_leaves = {key.rsplit("/", 1)[-1] for key in proposed_keys}
        warnings = [
            leaf
            for leaf in self._short_key_warnings([set(owners), *other_key_sets, manual_keys])
            if leaf in proposed_leaves
        ]
        return {
            "resource_id": file_path,
            "namespace": namespace,
            "aliases": clean_aliases,
            "keys": proposed_keys,
            "conflicts": conflicts,
            "short_key_warnings": warnings,
        }

    def activate(
        self,
        resource: dict[str, Any],
        namespace: str = "",
        aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        entries = resource.get("entries") or [
            entry.summary() for entry in parse_wildcard_artifact(resource["file_path"]).entries
        ]
        # Deactivation keeps the record so namespace/aliases survive a later
        # reactivation. Only reuse them when the caller did not supply a new
        # value; stale aliases for source keys that disappeared are dropped.
        existing = self.activation_for(
            resource["file_path"], include_inactive=True
        )
        if existing is not None and not _is_active_record(existing):
            if not namespace:
                namespace = existing.get("namespace") or ""
            stored_aliases = existing.get("aliases")
            if not aliases and isinstance(stored_aliases, dict):
                source_keys = {entry.get("key") for entry in entries if entry.get("key")}
                aliases = {
                    key: value
                    for key, value in stored_aliases.items()
                    if key in source_keys
                }
        preview = self.preview_activation(resource, namespace, aliases)
        if preview["conflicts"]:
            raise WildcardConflictError(preview["conflicts"])
        with self._lock:
            activations = self._load()
            record = {
                "file_path": resource["file_path"],
                "sha256": resource.get("sha256", ""),
                "name": resource.get("model_name") or resource.get("file_name") or "",
                "namespace": preview["namespace"],
                "aliases": preview["aliases"],
                "entries": entries,
                "active": True,
                "activated_at": datetime.now(timezone.utc).isoformat(),
            }
            activations[_path_key(resource["file_path"])] = record
            self._save(activations)
        return preview

    def deactivate(self, file_path: str) -> None:
        with self._lock:
            activations = self._load()
            key = _path_key(file_path)
            record = activations.get(key)
            if record is None:
                return
            # Keep the record (and therefore namespace/aliases) so the next
            # activation can restore it; the runtime ignores inactive records.
            updated = dict(record)
            updated["active"] = False
            updated["deactivated_at"] = datetime.now(timezone.utc).isoformat()
            activations[key] = updated
            self._save(activations)

    def read_source(self, file_path: str, source_path: str) -> dict[str, Any]:
        return read_wildcard_source(file_path, source_path)

    def get_entry_values(
        self, file_path: str, key: str, offset: int = 0, limit: int = 200
    ) -> dict[str, Any]:
        activation = self.activation_for(file_path)
        parsed = parse_wildcard_artifact(file_path)
        normalized = normalize_wildcard_key(key)
        for entry in parsed.entries:
            if normalized in (entry.key, self._effective_key(entry.key, activation)):
                return {
                    "key": self._effective_key(entry.key, activation),
                    "source_key": entry.key,
                    "source_path": entry.source_path,
                    "values": list(entry.values[offset : offset + limit]),
                    "total": len(entry.values),
                    "offset": offset,
                }
        raise FileNotFoundError(key)

    def get_active_runtime(
        self,
    ) -> tuple[dict[str, list[str]], tuple[Any, ...], list[dict[str, Any]]]:
        with self._lock:
            activations = self._load()
            signature = (
                self.activations_path,
                _file_signature(self.activations_path),
                tuple(
                    (key, _file_signature(record.get("file_path", "")))
                    for key, record in sorted(activations.items())
                ),
            )
            if signature == self._runtime_signature:
                return self._runtime_entries, signature, self._runtime_conflicts
            collected: dict[str, list[str]] = {}
            conflicts: list[dict[str, Any]] = []
            for key, activation in sorted(activations.items()):
                if not _is_active_record(activation):
                    continue
                file_path = activation.get("file_path", "")
                if not os.path.isfile(file_path):
                    continue
                try:
                    parsed = parse_wildcard_artifact(file_path)
                except Exception:
                    logger.error("Unable to load active wildcard %s", file_path, exc_info=True)
                    continue
                for entry in parsed.entries:
                    effective = self._effective_key(entry.key, activation)
                    if effective in collected:
                        conflicts.append(
                            {"key": effective, "owners": [file_path], "kept": "earlier active or manual resource"}
                        )
                        continue
                    collected[effective] = list(entry.values)
            self._runtime_signature = signature
            self._runtime_entries = collected
            self._runtime_conflicts = conflicts
            return collected, signature, conflicts


def get_wildcard_activation_service() -> WildcardActivationService:
    return WildcardActivationService.get_instance()


__all__ = [
    "WildcardActivationService",
    "WildcardConflictError",
    "WildcardLibraryError",
    "get_wildcard_activation_service",
]
