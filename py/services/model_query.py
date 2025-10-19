from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Protocol, Callable

from ..utils.constants import NSFW_LEVELS
from ..utils.utils import fuzzy_match as default_fuzzy_match


class SettingsProvider(Protocol):
    """Protocol describing the SettingsManager contract used by query helpers."""

    def get(self, key: str, default: Any = None) -> Any:
        ...


@dataclass(frozen=True)
class SortParams:
    """Normalized representation of sorting instructions."""

    key: str
    order: str


@dataclass(frozen=True)
class FilterCriteria:
    """Container for model list filtering options."""

    folder: Optional[str] = None
    base_models: Optional[Sequence[str]] = None
    tags: Optional[Sequence[str]] = None
    favorites_only: bool = False
    search_options: Optional[Dict[str, Any]] = None


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

    def __init__(self, settings: SettingsProvider, nsfw_levels: Optional[Dict[str, int]] = None) -> None:
        self._settings = settings
        self._nsfw_levels = nsfw_levels or NSFW_LEVELS

    def apply(self, data: Iterable[Dict[str, Any]], criteria: FilterCriteria) -> List[Dict[str, Any]]:
        """Return items that satisfy the provided criteria."""
        items = list(data)

        if self._settings.get("show_only_sfw", False):
            threshold = self._nsfw_levels.get("R", 0)
            items = [
                item for item in items
                if not item.get("preview_nsfw_level") or item.get("preview_nsfw_level") < threshold
            ]

        if criteria.favorites_only:
            items = [item for item in items if item.get("favorite", False)]

        folder = criteria.folder
        options = criteria.search_options or {}
        recursive = bool(options.get("recursive", True))
        if folder is not None:
            if recursive:
                if folder:
                    folder_with_sep = f"{folder}/"
                    items = [
                        item for item in items
                        if item.get("folder") == folder or item.get("folder", "").startswith(folder_with_sep)
                    ]
            else:
                items = [item for item in items if item.get("folder") == folder]

        base_models = criteria.base_models or []
        if base_models:
            base_model_set = set(base_models)
            items = [item for item in items if item.get("base_model") in base_model_set]

        tags = criteria.tags or []
        if tags:
            tag_set = set(tags)
            items = [
                item for item in items
                if any(tag in tag_set for tag in item.get("tags", []))
            ]

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

    def __init__(self, fuzzy_matcher: Optional[Callable[[str, str], bool]] = None) -> None:
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
                if any(self._matches(tag, search_term, search_lower, fuzzy) for tag in tags):
                    results.append(item)
                    continue

            if options.get("creator", False):
                creator_username = ""
                civitai = item.get("civitai")
                if isinstance(civitai, dict):
                    creator = civitai.get("creator")
                    if isinstance(creator, dict):
                        creator_username = creator.get("username", "")
                if creator_username and self._matches(creator_username, search_term, search_lower, fuzzy):
                    results.append(item)
                    continue

        return results

    def _matches(self, candidate: str, search_term: str, search_lower: str, fuzzy: bool) -> bool:
        if not isinstance(candidate, str):
            candidate = "" if candidate is None else str(candidate)

        if not candidate:
            return False

        candidate_lower = candidate.lower()
        if fuzzy:
            return self._fuzzy_match(candidate, search_term)
        return search_lower in candidate_lower
