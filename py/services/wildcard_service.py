"""Managed wildcard loading, search, and text expansion."""

from __future__ import annotations

import json
import logging
import os
import random
import re
from dataclasses import dataclass
from typing import Any, Optional

import yaml

from ..utils.settings_paths import get_settings_dir

logger = logging.getLogger(__name__)

_WILDCARD_PATTERN = re.compile(r"__([\w\s.\-+/*\\]+?)__")
_OPTION_PATTERN = re.compile(r"{([^{}]*?)}")
_TRIGGER_WORD_PATTERN = re.compile(r"^trigger_words\d+$")
_WEIGHTED_OPTION_PATTERN = re.compile(r"^\s*([0-9.]+)::")
_NUMERIC_PATTERN = re.compile(r"^-?\d+(\.\d+)?$")


def _normalize_wildcard_key(value: str) -> str:
    return value.replace("\\", "/").strip("/").lower()


def _is_numeric_string(value: str) -> bool:
    return bool(_NUMERIC_PATTERN.match(value))


def contains_dynamic_syntax(text: str) -> bool:
    """Return True when text contains supported wildcard or option syntax."""

    return isinstance(text, str) and bool(
        _WILDCARD_PATTERN.search(text) or _OPTION_PATTERN.search(text)
    )


def get_wildcards_dir(create: bool = False) -> str:
    """Return the managed wildcard directory inside the settings folder."""

    settings_dir = get_settings_dir(create=create)
    wildcards_dir = os.path.join(settings_dir, "wildcards")
    if create:
        os.makedirs(wildcards_dir, exist_ok=True)
    return wildcards_dir


@dataclass(frozen=True)
class WildcardEntry:
    key: str
    values_count: int


@dataclass(frozen=True)
class WildcardMetadata:
    has_wildcards: bool
    wildcards_dir: str
    supported_formats: tuple[str, ...]


class WildcardService:
    """Discover wildcard keys and expand wildcard syntax."""

    _instance: Optional["WildcardService"] = None

    def __new__(cls) -> "WildcardService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._cached_signature: tuple[tuple[str, int, int], ...] | None = None
        self._wildcard_dict: dict[str, list[str]] = {}

    @classmethod
    def get_instance(cls) -> "WildcardService":
        return cls()

    def search_keys(
        self, search_term: str, limit: int = 20, offset: int = 0
    ) -> list[str]:
        """Search wildcard keys for autocomplete."""

        normalized_term = _normalize_wildcard_key(search_term).strip()
        if not normalized_term:
            return []

        ranked: list[tuple[int, str]] = []
        compact_term = normalized_term.replace("/", "")
        for key in self.get_wildcard_dict().keys():
            score = self._score_entry(key, normalized_term, compact_term)
            if score is not None:
                ranked.append((score, key))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        keys = [key for _, key in ranked]
        return keys[offset : offset + limit]

    def expand_text(self, text: str, seed: int | None = None) -> str:
        """Expand wildcard and dynamic prompt syntax for a text value."""

        if not isinstance(text, str) or not text:
            return text

        rng = random.Random(seed) if seed is not None else random.Random()
        wildcard_dict = self.get_wildcard_dict()
        if not wildcard_dict:
            return self._expand_options_only(text, rng)

        current = text
        remaining_depth = 100

        while remaining_depth > 0:
            remaining_depth -= 1
            after_options, options_replaced = self._replace_options(current, rng)
            current, wildcards_replaced = self._replace_wildcards(
                after_options, rng, wildcard_dict
            )
            if not options_replaced and not wildcards_replaced:
                break

        return current

    def get_wildcard_dict(self) -> dict[str, list[str]]:
        signature = self._build_signature()
        if signature != self._cached_signature:
            self._wildcard_dict = self._scan_wildcard_dict()
            self._cached_signature = signature
        return self._wildcard_dict

    def get_entries(self) -> list[WildcardEntry]:
        return [
            WildcardEntry(key=key, values_count=len(values))
            for key, values in sorted(self.get_wildcard_dict().items())
        ]

    def get_metadata(self, *, create_dir: bool = False) -> WildcardMetadata:
        wildcards_dir = get_wildcards_dir(create=create_dir)
        return WildcardMetadata(
            has_wildcards=bool(self.get_wildcard_dict()),
            wildcards_dir=wildcards_dir,
            supported_formats=(".txt", ".yaml", ".yml", ".json"),
        )

    def _build_signature(self) -> tuple[tuple[str, int, int], ...]:
        root = get_wildcards_dir(create=False)
        if not os.path.isdir(root):
            return ()

        signature: list[tuple[str, int, int]] = []
        for current_root, _dirs, files in os.walk(root, followlinks=True):
            for file_name in sorted(files):
                if not file_name.lower().endswith((".txt", ".yaml", ".yml", ".json")):
                    continue
                file_path = os.path.join(current_root, file_name)
                try:
                    stat = os.stat(file_path)
                except OSError:
                    continue
                rel_path = os.path.relpath(file_path, root).replace("\\", "/")
                signature.append((rel_path, int(stat.st_mtime_ns), int(stat.st_size)))
        signature.sort()
        return tuple(signature)

    def _scan_wildcard_dict(self) -> dict[str, list[str]]:
        root = get_wildcards_dir(create=False)
        if not os.path.isdir(root):
            return {}

        collected: dict[str, list[str]] = {}
        for current_root, _dirs, files in os.walk(root, followlinks=True):
            for file_name in sorted(files):
                file_path = os.path.join(current_root, file_name)
                lower_name = file_name.lower()
                try:
                    if lower_name.endswith(".txt"):
                        rel_path = os.path.relpath(file_path, root)
                        key = _normalize_wildcard_key(os.path.splitext(rel_path)[0])
                        values = self._read_txt(file_path)
                        if values:
                            collected[key] = values
                    elif lower_name.endswith((".yaml", ".yml")):
                        payload = self._read_yaml(file_path)
                        self._merge_nested_entries(collected, payload)
                    elif lower_name.endswith(".json"):
                        payload = self._read_json(file_path)
                        self._merge_nested_entries(collected, payload)
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("Failed to load wildcard file %s: %s", file_path, exc)

        return collected

    def _read_txt(self, file_path: str) -> list[str]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                return [line.strip() for line in handle.read().splitlines() if line.strip()]
        except OSError as exc:
            logger.warning("Failed to read wildcard txt file %s: %s", file_path, exc)
            return []

    def _read_yaml(self, file_path: str) -> Any:
        with open(file_path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def _read_json(self, file_path: str) -> Any:
        with open(file_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _merge_nested_entries(
        self, collected: dict[str, list[str]], payload: Any
    ) -> None:
        for key, values in self._flatten_payload(payload):
            collected[key] = values

    def _flatten_payload(
        self, payload: Any, prefix: str = ""
    ) -> list[tuple[str, list[str]]]:
        entries: list[tuple[str, list[str]]] = []

        if isinstance(payload, dict):
            for key, value in payload.items():
                next_prefix = f"{prefix}/{key}" if prefix else str(key)
                entries.extend(self._flatten_payload(value, next_prefix))
            return entries

        if isinstance(payload, list):
            normalized_prefix = _normalize_wildcard_key(prefix)
            values = [value.strip() for value in payload if isinstance(value, str) and value.strip()]
            if normalized_prefix and values:
                entries.append((normalized_prefix, values))
            return entries

        return entries

    def _score_entry(
        self, key: str, normalized_term: str, compact_term: str
    ) -> int | None:
        key_compact = key.replace("/", "")
        if key == normalized_term:
            return 5000
        if key.startswith(normalized_term):
            return 4000
        if f"/{normalized_term}" in key:
            return 3500
        if normalized_term in key:
            return 3000
        if compact_term and key_compact.startswith(compact_term):
            return 2500
        if compact_term and compact_term in key_compact:
            return 2000
        return None

    def _expand_options_only(self, text: str, rng: random.Random) -> str:
        current = text
        remaining_depth = 100
        while remaining_depth > 0:
            remaining_depth -= 1
            current, replaced = self._replace_options(current, rng)
            if not replaced:
                break
        return current

    def _replace_options(
        self, text: str, rng: random.Random
    ) -> tuple[str, bool]:
        replaced_any = False

        def replace_option(match: re.Match[str]) -> str:
            nonlocal replaced_any
            replacement = self._resolve_option_group(match.group(1), rng)
            replaced_any = True
            return replacement

        return _OPTION_PATTERN.sub(replace_option, text), replaced_any

    def _resolve_option_group(self, group_text: str, rng: random.Random) -> str:
        options = group_text.split("|")
        multi_select_pattern = options[0].split("$$")
        select_range: tuple[int, int] | None = None
        select_separator = " "

        if len(multi_select_pattern) > 1:
            count_spec = multi_select_pattern[0]
            range_match = re.match(r"(\d+)(-(\d+))?$", count_spec)
            shorthand_match = re.match(r"-(\d+)$", count_spec)
            if range_match:
                start_text = range_match.group(1)
                end_text = range_match.group(3)
                if end_text is not None and _is_numeric_string(start_text) and _is_numeric_string(end_text):
                    select_range = (int(start_text), int(end_text))
                elif _is_numeric_string(start_text):
                    value = int(start_text)
                    select_range = (value, value)
            elif shorthand_match:
                end_text = shorthand_match.group(1)
                if _is_numeric_string(end_text):
                    select_range = (1, int(end_text))

            if select_range is not None and len(multi_select_pattern) == 2:
                options[0] = multi_select_pattern[1]
            elif select_range is not None and len(multi_select_pattern) >= 3:
                select_separator = multi_select_pattern[1]
                options[0] = multi_select_pattern[2]

        weighted_options: list[tuple[float, str]] = []
        for option in options:
            weight = 1.0
            parts = option.split("::", 1)
            if len(parts) == 2 and _is_numeric_string(parts[0].strip()):
                weight = float(parts[0].strip())
            weighted_options.append((weight, option))

        if select_range is None:
            selection_count = 1
        else:
            selection_count = rng.randint(select_range[0], select_range[1])

        if selection_count <= 1:
            return self._strip_weight_prefix(self._weighted_choice(weighted_options, rng))

        selection_count = min(selection_count, len(weighted_options))
        selected: list[str] = []
        used_indexes: set[int] = set()
        while len(selected) < selection_count:
            picked_index = self._weighted_choice_index(weighted_options, rng)
            if picked_index in used_indexes:
                if len(used_indexes) == len(weighted_options):
                    break
                continue
            used_indexes.add(picked_index)
            selected.append(
                self._strip_weight_prefix(weighted_options[picked_index][1])
            )

        return select_separator.join(selected)

    def _weighted_choice(
        self, weighted_options: list[tuple[float, str]], rng: random.Random
    ) -> str:
        return weighted_options[self._weighted_choice_index(weighted_options, rng)][1]

    def _weighted_choice_index(
        self, weighted_options: list[tuple[float, str]], rng: random.Random
    ) -> int:
        total_weight = sum(max(weight, 0.0) for weight, _value in weighted_options)
        if total_weight <= 0:
            return rng.randrange(len(weighted_options))

        threshold = rng.uniform(0, total_weight)
        cumulative = 0.0
        for index, (weight, _value) in enumerate(weighted_options):
            cumulative += max(weight, 0.0)
            if threshold <= cumulative:
                return index
        return len(weighted_options) - 1

    def _strip_weight_prefix(self, value: str) -> str:
        return _WEIGHTED_OPTION_PATTERN.sub("", value, count=1)

    def _replace_wildcards(
        self,
        text: str,
        rng: random.Random,
        wildcard_dict: dict[str, list[str]],
    ) -> tuple[str, bool]:
        replaced_any = False

        def replace_match(match: re.Match[str]) -> str:
            nonlocal replaced_any
            replacement = self._resolve_wildcard_match(match.group(1), rng, wildcard_dict)
            if replacement is None:
                return match.group(0)
            replaced_any = True
            return replacement

        return _WILDCARD_PATTERN.sub(replace_match, text), replaced_any

    def _resolve_wildcard_match(
        self,
        raw_key: str,
        rng: random.Random,
        wildcard_dict: dict[str, list[str]],
    ) -> str | None:
        keyword = _normalize_wildcard_key(raw_key)
        if keyword in wildcard_dict:
            return rng.choice(wildcard_dict[keyword])

        if "*" in keyword:
            regex_pattern = keyword.replace("*", ".*").replace("+", r"\+")
            compiled = re.compile(f"^{regex_pattern}$")
            aggregated: list[str] = []
            for key, values in wildcard_dict.items():
                if compiled.match(key):
                    aggregated.extend(values)
            if aggregated:
                return rng.choice(aggregated)

        if "/" not in keyword:
            fallback_keyword = _normalize_wildcard_key(f"*/{keyword}")
            if fallback_keyword != keyword:
                return self._resolve_wildcard_match(fallback_keyword, rng, wildcard_dict)

        return None


def is_trigger_words_input(name: str) -> bool:
    return bool(_TRIGGER_WORD_PATTERN.match(name))


def get_wildcard_service() -> WildcardService:
    return WildcardService.get_instance()


__all__ = [
    "WildcardService",
    "WildcardMetadata",
    "contains_dynamic_syntax",
    "get_wildcard_service",
    "get_wildcards_dir",
    "is_trigger_words_input",
]
