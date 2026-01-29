from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Protocol,
    Callable,
)

from ..utils.constants import NSFW_LEVELS
from ..utils.utils import fuzzy_match as default_fuzzy_match
import time
import logging

logger = logging.getLogger(__name__)


DEFAULT_CIVITAI_MODEL_TYPE = "LORA"


def _coerce_to_str(value: Any) -> Optional[str]:
    if value is None:
        return None

    candidate = str(value).strip()
    return candidate if candidate else None


def normalize_sub_type(value: Any) -> Optional[str]:
    """Return a lowercase string suitable for sub_type comparisons."""
    candidate = _coerce_to_str(value)
    return candidate.lower() if candidate else None


# Backward compatibility alias
normalize_civitai_model_type = normalize_sub_type


def resolve_sub_type(entry: Mapping[str, Any]) -> str:
    """Extract the sub-type from metadata, checking multiple sources.
    
    Priority:
    1. entry['sub_type'] - new canonical field
    2. entry['model_type'] - backward compatibility
    3. civitai.model.type - CivitAI API data
    4. DEFAULT_CIVITAI_MODEL_TYPE - fallback
    """
    if not isinstance(entry, Mapping):
        return DEFAULT_CIVITAI_MODEL_TYPE

    # Priority 1: Check new canonical field 'sub_type'
    sub_type = _coerce_to_str(entry.get("sub_type"))
    if sub_type:
        return sub_type

    # Priority 2: Backward compatibility - check 'model_type' field
    model_type = _coerce_to_str(entry.get("model_type"))
    if model_type:
        return model_type

    # Priority 3: Extract from CivitAI metadata
    civitai = entry.get("civitai")
    if isinstance(civitai, Mapping):
        civitai_model = civitai.get("model")
        if isinstance(civitai_model, Mapping):
            civitai_type = _coerce_to_str(civitai_model.get("type"))
            if civitai_type:
                return civitai_type

    return DEFAULT_CIVITAI_MODEL_TYPE


# Backward compatibility alias
resolve_civitai_model_type = resolve_sub_type


class SettingsProvider(Protocol):
    """Protocol describing the SettingsManager contract used by query helpers."""

    def get(self, key: str, default: Any = None) -> Any: ...


@dataclass(frozen=True)
class SortParams:
    """Normalized representation of sorting instructions."""

    key: str
    order: str


@dataclass(frozen=True)
class FilterCriteria:
    """Container for model list filtering options."""

    folder: Optional[str] = None
    folder_include: Optional[Sequence[str]] = None
    folder_exclude: Optional[Sequence[str]] = None
    base_models: Optional[Sequence[str]] = None
    tags: Optional[Dict[str, str]] = None
    favorites_only: bool = False
    search_options: Optional[Dict[str, Any]] = None
    model_types: Optional[Sequence[str]] = None


class ModelCacheRepository:
    """Adapter around scanner cache access and sort normalisation."""

    def __init__(self, scanner) -> None:
        self._scanner = scanner

    async def get_cache(self):
        """Return the underlying cache instance from the scanner."""
        return await self._scanner.get_cached_data()

    async def fetch_sorted(self, params: SortParams) -> List[Dict[str, Any]]:
        """Fetch cached data pre-sorted according to ``params``."""
        cache = await self.get_cache()
        return await cache.get_sorted_data(params.key, params.order)

    @staticmethod
    def parse_sort(sort_by: str) -> SortParams:
        """Parse an incoming sort string into key/order primitives."""
        if not sort_by:
            return SortParams(key="name", order="asc")

        if ":" in sort_by:
            raw_key, raw_order = sort_by.split(":", 1)
            sort_key = raw_key.strip().lower() or "name"
            order = raw_order.strip().lower()
        else:
            sort_key = sort_by.strip().lower() or "name"
            order = "asc"

        if order not in ("asc", "desc"):
            order = "asc"

        return SortParams(key=sort_key, order=order)


class ModelFilterSet:
    """Applies common filtering rules to the model collection."""

    def __init__(
        self, settings: SettingsProvider, nsfw_levels: Optional[Dict[str, int]] = None
    ) -> None:
        self._settings = settings
        self._nsfw_levels = nsfw_levels or NSFW_LEVELS

    def apply(
        self, data: Iterable[Dict[str, Any]], criteria: FilterCriteria
    ) -> List[Dict[str, Any]]:
        """Return items that satisfy the provided criteria."""
        overall_start = time.perf_counter()
        items = list(data)
        initial_count = len(items)

        if self._settings.get("show_only_sfw", False):
            t0 = time.perf_counter()
            threshold = self._nsfw_levels.get("R", 0)
            items = [
                item
                for item in items
                if not item.get("preview_nsfw_level")
                or item.get("preview_nsfw_level") < threshold
            ]
            sfw_duration = time.perf_counter() - t0
        else:
            sfw_duration = 0

        favorites_duration = 0
        if criteria.favorites_only:
            t0 = time.perf_counter()
            items = [item for item in items if item.get("favorite", False)]
            favorites_duration = time.perf_counter() - t0

        folder_duration = 0
        folder = criteria.folder
        folder_include = criteria.folder_include or []
        folder_exclude = criteria.folder_exclude or []
        options = criteria.search_options or {}
        recursive = bool(options.get("recursive", True))

        # Apply folder exclude filters first
        if folder_exclude:
            t0 = time.perf_counter()
            for exclude_folder in folder_exclude:
                if exclude_folder:
                    # Check exact match OR prefix match (for subfolders)
                    # Normalize exclude_folder for prefix matching
                    if not exclude_folder.endswith("/"):
                        exclude_prefix = f"{exclude_folder}/"
                    else:
                        exclude_prefix = exclude_folder
                    items = [
                        item
                        for item in items
                        if item.get("folder") != exclude_folder
                        and not item.get("folder", "").startswith(exclude_prefix)
                    ]
            folder_duration = time.perf_counter() - t0

        # Apply folder include filters
        if folder is not None:
            t0 = time.perf_counter()
            if recursive:
                if folder:
                    folder_with_sep = f"{folder}/"
                    items = [
                        item
                        for item in items
                        if item.get("folder") == folder
                        or item.get("folder", "").startswith(folder_with_sep)
                    ]
            else:
                items = [item for item in items if item.get("folder") == folder]
            folder_duration = time.perf_counter() - t0 + folder_duration

        # Apply folder include filters
        if folder_include:
            t0 = time.perf_counter()
            matched_items = []
            for include_folder in folder_include:
                if include_folder:
                    if recursive:
                        # Normalize folder for prefix matching (similar to exclude logic)
                        if not include_folder.endswith("/"):
                            folder_prefix = f"{include_folder}/"
                        else:
                            folder_prefix = include_folder
                        folder_items = [
                            item
                            for item in items
                            if item.get("folder") == include_folder
                            or item.get("folder", "").startswith(folder_prefix)
                        ]
                    else:
                        folder_items = [
                            item
                            for item in items
                            if item.get("folder") == include_folder
                        ]
                    matched_items.extend(folder_items)
            # Remove duplicates while preserving order
            seen = set()
            items = []
            for item in matched_items:
                # Use sha256 or id as unique identifier if available, otherwise use tuple representation
                item_id = item.get("sha256") or item.get("id")
                if item_id is not None:
                    identifier = item_id
                else:
                    # For items without explicit id, use a tuple of key values
                    identifier = tuple(sorted((k, str(v)) for k, v in item.items()))
                if identifier not in seen:
                    seen.add(identifier)
                    items.append(item)
            folder_duration = time.perf_counter() - t0 + folder_duration
        # Apply folder include filters (legacy single folder)
        elif folder is not None:
            t0 = time.perf_counter()
            if recursive:
                if folder:
                    # Normalize folder for prefix matching
                    if not folder.endswith("/"):
                        folder_prefix = f"{folder}/"
                    else:
                        folder_prefix = folder
                    items = [
                        item
                        for item in items
                        if item.get("folder") == folder
                        or item.get("folder", "").startswith(folder_prefix)
                    ]
            else:
                items = [item for item in items if item.get("folder") == folder]
            folder_duration = time.perf_counter() - t0 + folder_duration

        base_models_duration = 0
        base_models = criteria.base_models or []
        if base_models:
            t0 = time.perf_counter()
            base_model_set = set(base_models)
            items = [item for item in items if item.get("base_model") in base_model_set]
            base_models_duration = time.perf_counter() - t0

        tags_duration = 0
        tag_filters = criteria.tags or {}
        if tag_filters:
            t0 = time.perf_counter()
            include_tags = set()
            exclude_tags = set()
            if isinstance(tag_filters, dict):
                for tag, state in tag_filters.items():
                    if not tag:
                        continue
                    if state == "exclude":
                        exclude_tags.add(tag)
                    else:
                        include_tags.add(tag)
            else:
                include_tags = {tag for tag in tag_filters if tag}

            if include_tags:

                def matches_include(item_tags):
                    if not item_tags and "__no_tags__" in include_tags:
                        return True
                    return any(tag in include_tags for tag in (item_tags or []))

                items = [item for item in items if matches_include(item.get("tags"))]

            if exclude_tags:

                def matches_exclude(item_tags):
                    if not item_tags and "__no_tags__" in exclude_tags:
                        return True
                    return any(tag in exclude_tags for tag in (item_tags or []))

                items = [
                    item for item in items if not matches_exclude(item.get("tags"))
                ]
            tags_duration = time.perf_counter() - t0

        model_types_duration = 0
        model_types = criteria.model_types or []
        if model_types:
            t0 = time.perf_counter()
            normalized_model_types = {
                model_type
                for model_type in (
                    normalize_sub_type(value) for value in model_types
                )
                if model_type
            }
            if normalized_model_types:
                items = [
                    item
                    for item in items
                    if normalize_sub_type(resolve_sub_type(item))
                    in normalized_model_types
                ]
            model_types_duration = time.perf_counter() - t0

        duration = time.perf_counter() - overall_start
        if duration > 0.1:  # Only log if it's potentially slow
            logger.debug(
                "ModelFilterSet.apply took %.3fs (sfw: %.3fs, fav: %.3fs, folder: %.3fs, base: %.3fs, tags: %.3fs, types: %.3fs). "
                "Count: %d -> %d",
                duration,
                sfw_duration,
                favorites_duration,
                folder_duration,
                base_models_duration,
                tags_duration,
                model_types_duration,
                initial_count,
                len(items),
            )
        return items


class SearchStrategy:
    """Encapsulates text and fuzzy matching behaviour for model queries."""

    DEFAULT_OPTIONS: Dict[str, Any] = {
        "filename": True,
        "modelname": True,
        "tags": False,
        "recursive": True,
        "creator": False,
    }

    def __init__(
        self, fuzzy_matcher: Optional[Callable[[str, str], bool]] = None
    ) -> None:
        self._fuzzy_match = fuzzy_matcher or default_fuzzy_match

    def normalize_options(self, options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge provided options with defaults without mutating input."""
        normalized = dict(self.DEFAULT_OPTIONS)
        if options:
            normalized.update(options)
        return normalized

    def apply(
        self,
        data: Iterable[Dict[str, Any]],
        search_term: str,
        options: Dict[str, Any],
        fuzzy: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return items matching the search term using the configured strategy."""
        if not search_term:
            return list(data)

        search_lower = search_term.lower()
        results: List[Dict[str, Any]] = []

        for item in data:
            if options.get("filename", True):
                candidate = item.get("file_name", "")
                if self._matches(candidate, search_term, search_lower, fuzzy):
                    results.append(item)
                    continue

            if options.get("modelname", True):
                candidate = item.get("model_name", "")
                if self._matches(candidate, search_term, search_lower, fuzzy):
                    results.append(item)
                    continue

            if options.get("tags", False):
                tags = item.get("tags", []) or []
                if any(
                    self._matches(tag, search_term, search_lower, fuzzy) for tag in tags
                ):
                    results.append(item)
                    continue

            if options.get("creator", False):
                creator_username = ""
                civitai = item.get("civitai")
                if isinstance(civitai, dict):
                    creator = civitai.get("creator")
                    if isinstance(creator, dict):
                        creator_username = creator.get("username", "")
                if creator_username and self._matches(
                    creator_username, search_term, search_lower, fuzzy
                ):
                    results.append(item)
                    continue

        return results

    def _matches(
        self, candidate: str, search_term: str, search_lower: str, fuzzy: bool
    ) -> bool:
        if not isinstance(candidate, str):
            candidate = "" if candidate is None else str(candidate)

        if not candidate:
            return False

        candidate_lower = candidate.lower()
        if fuzzy:
            return self._fuzzy_match(candidate, search_term)
        return search_lower in candidate_lower
