"""Parse wildcard artifacts without extracting them into the runtime directory."""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import yaml


SUPPORTED_TEXT_EXTENSIONS = (".txt", ".yaml", ".yml", ".json")
SUPPORTED_ARTIFACT_EXTENSIONS = (*SUPPORTED_TEXT_EXTENSIONS, ".zip")
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_TEXT_BYTES = 128 * 1024 * 1024
MAX_CONTENT_BYTES = 2 * 1024 * 1024


class WildcardParseError(ValueError):
    """Raised when an artifact exceeds safety limits or has no usable entries."""


@dataclass(frozen=True)
class ParsedWildcardEntry:
    key: str
    values: tuple[str, ...]
    source_path: str

    def summary(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "source_path": self.source_path,
            "values_count": len(self.values),
        }


@dataclass
class ParsedWildcardArtifact:
    entries: list[ParsedWildcardEntry] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    unsupported_files: list[str] = field(default_factory=list)

    @property
    def value_count(self) -> int:
        return sum(len(entry.values) for entry in self.entries)


def normalize_wildcard_key(value: str) -> str:
    return value.replace("\\", "/").strip("/").lower()


def _safe_member_name(value: str) -> str | None:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or not normalized:
        return None
    return normalized.lstrip("/")


def _flatten_payload(payload: Any, prefix: str = "") -> list[tuple[str, tuple[str, ...]]]:
    if isinstance(payload, dict):
        entries: list[tuple[str, tuple[str, ...]]] = []
        for key, value in payload.items():
            next_prefix = f"{prefix}/{key}" if prefix else str(key)
            entries.extend(_flatten_payload(value, next_prefix))
        return entries
    if isinstance(payload, list):
        key = normalize_wildcard_key(prefix)
        values = tuple(
            value.strip()
            for value in payload
            if isinstance(value, str) and value.strip()
        )
        return [(key, values)] if key and values else []
    return []


def _parse_text(source_path: str, data: bytes) -> list[tuple[str, tuple[str, ...]]]:
    extension = os.path.splitext(source_path)[1].lower()
    if extension == ".txt":
        values = tuple(
            line.strip()
            for line in data.decode("utf-8", errors="ignore").splitlines()
            if line.strip()
        )
        key = normalize_wildcard_key(os.path.splitext(source_path)[0])
        return [(key, values)] if key and values else []
    text = data.decode("utf-8")
    if extension in (".yaml", ".yml"):
        payload = yaml.safe_load(text) or {}
    else:
        payload = json.loads(text)
    return _flatten_payload(payload)


def _add_entries(
    collected: dict[str, ParsedWildcardEntry],
    parsed: ParsedWildcardArtifact,
    source_path: str,
    entries: list[tuple[str, tuple[str, ...]]],
) -> None:
    for key, values in entries:
        if key in collected:
            previous = collected[key]
            parsed.errors.append(
                f"Duplicate wildcard key '{key}' in {source_path}; "
                f"keeping {previous.source_path}"
            )
            continue
        collected[key] = ParsedWildcardEntry(key, values, source_path)


def parse_wildcard_artifact(file_path: str) -> ParsedWildcardArtifact:
    extension = os.path.splitext(file_path)[1].lower()
    if extension not in SUPPORTED_ARTIFACT_EXTENSIONS:
        raise WildcardParseError(f"Unsupported wildcard artifact: {extension or 'no extension'}")
    size = os.path.getsize(file_path)
    if size > MAX_ARTIFACT_BYTES:
        raise WildcardParseError("Wildcard artifact exceeds the 256 MiB limit")

    parsed = ParsedWildcardArtifact()
    collected: dict[str, ParsedWildcardEntry] = {}
    if extension == ".zip":
        with zipfile.ZipFile(file_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise WildcardParseError("Wildcard archive has too many members")
            text_bytes = 0
            for info in infos:
                if info.is_dir() or info.filename.startswith("__MACOSX/"):
                    continue
                source_path = _safe_member_name(info.filename)
                if source_path is None:
                    parsed.errors.append(f"Unsafe archive member skipped: {info.filename}")
                    continue
                member_extension = os.path.splitext(source_path)[1].lower()
                if member_extension not in SUPPORTED_TEXT_EXTENSIONS:
                    parsed.unsupported_files.append(source_path)
                    continue
                if info.file_size > MAX_MEMBER_BYTES:
                    parsed.errors.append(f"Member exceeds the 16 MiB limit: {source_path}")
                    continue
                text_bytes += info.file_size
                if text_bytes > MAX_TEXT_BYTES:
                    raise WildcardParseError("Wildcard archive text exceeds the 128 MiB limit")
                parsed.files.append(source_path)
                try:
                    entries = _parse_text(source_path, archive.read(info))
                except Exception as exc:
                    parsed.errors.append(f"{source_path}: {exc}")
                    continue
                _add_entries(collected, parsed, source_path, entries)
    else:
        source_path = os.path.basename(file_path)
        if size > MAX_MEMBER_BYTES:
            raise WildcardParseError("Wildcard text file exceeds the 16 MiB limit")
        parsed.files.append(source_path)
        try:
            with open(file_path, "rb") as handle:
                entries = _parse_text(source_path, handle.read(MAX_MEMBER_BYTES + 1))
        except Exception as exc:
            raise WildcardParseError(f"Unable to parse {source_path}: {exc}") from exc
        _add_entries(collected, parsed, source_path, entries)

    parsed.entries = sorted(collected.values(), key=lambda entry: entry.key)
    if not parsed.entries:
        details = f": {'; '.join(parsed.errors)}" if parsed.errors else ""
        raise WildcardParseError(f"No usable wildcard entries found{details}")
    return parsed


def read_wildcard_source(
    file_path: str, source_path: str, *, max_bytes: int = MAX_CONTENT_BYTES
) -> dict[str, Any]:
    extension = os.path.splitext(file_path)[1].lower()
    safe_source = _safe_member_name(source_path)
    if safe_source is None:
        raise WildcardParseError("Invalid wildcard source path")
    if extension == ".zip":
        with zipfile.ZipFile(file_path) as archive:
            info = next(
                (
                    item
                    for item in archive.infolist()
                    if not item.is_dir()
                    and _safe_member_name(item.filename) == safe_source
                ),
                None,
            )
            if info is None:
                raise FileNotFoundError(safe_source)
            if info.file_size > max_bytes:
                raise WildcardParseError("Source file exceeds the content preview limit")
            data = archive.read(info)
    else:
        if safe_source != os.path.basename(file_path):
            raise FileNotFoundError(safe_source)
        if os.path.getsize(file_path) > max_bytes:
            raise WildcardParseError("Source file exceeds the content preview limit")
        with open(file_path, "rb") as handle:
            data = handle.read(max_bytes + 1)
    return {
        "source_path": safe_source,
        "content": data.decode("utf-8", errors="replace"),
        "size": len(data),
    }


__all__ = [
    "MAX_ARTIFACT_BYTES",
    "SUPPORTED_ARTIFACT_EXTENSIONS",
    "ParsedWildcardArtifact",
    "ParsedWildcardEntry",
    "WildcardParseError",
    "normalize_wildcard_key",
    "parse_wildcard_artifact",
    "read_wildcard_source",
]
