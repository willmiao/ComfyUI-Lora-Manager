from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pytest


@dataclass
class MockHashIndex:
    """Minimal hash index stub mirroring the scanner contract."""

    removed_paths: List[str] = field(default_factory=list)

    def remove_by_path(self, path: str) -> None:
        self.removed_paths.append(path)


class MockCache:
    """Cache object with the attributes consumed by ``ModelRouteUtils``."""

    def __init__(self, items: Optional[Sequence[Dict[str, Any]]] = None):
        self.raw_data: List[Dict[str, Any]] = list(items or [])
        self.resort_calls = 0

    async def resort(self) -> None:
        self.resort_calls += 1
        # ``ModelRouteUtils`` expects the coroutine interface but does not
        # rely on the return value.


class MockScanner:
    """Scanner double that exposes the attributes used by route utilities."""

    def __init__(self, cache: Optional[MockCache] = None, hash_index: Optional[MockHashIndex] = None):
        self._cache = cache or MockCache()
        self._hash_index = hash_index or MockHashIndex()
        self._tags_count: Dict[str, int] = {}
        self._excluded_models: List[str] = []
        self.updated_models: List[Dict[str, Any]] = []
        self.preview_updates: List[Dict[str, Any]] = []
        self.bulk_deleted: List[Sequence[str]] = []

    async def get_cached_data(self, force_refresh: bool = False):
        return self._cache

    async def update_single_model_cache(self, original_path: str, new_path: str, metadata: Dict[str, Any]) -> bool:
        self.updated_models.append({
            "original_path": original_path,
            "new_path": new_path,
            "metadata": metadata,
        })
        for item in self._cache.raw_data:
            if item.get("file_path") == original_path:
                item.update(metadata)
        return True

    async def update_preview_in_cache(self, model_path: str, preview_path: str, nsfw_level: int) -> bool:
        self.preview_updates.append({
            "model_path": model_path,
            "preview_path": preview_path,
            "nsfw_level": nsfw_level,
        })
        for item in self._cache.raw_data:
            if item.get("file_path") == model_path:
                item["preview_url"] = preview_path
                item["preview_nsfw_level"] = nsfw_level
        return True

    async def bulk_delete_models(self, file_paths: Sequence[str]) -> Dict[str, Any]:
        self.bulk_deleted.append(tuple(file_paths))
        self._cache.raw_data = [item for item in self._cache.raw_data if item.get("file_path") not in file_paths]
        await self._cache.resort()
        for path in file_paths:
            self._hash_index.remove_by_path(path)
        return {"success": True, "deleted": list(file_paths)}


class MockModelService:
    """Service stub consumed by the shared routes."""

    def __init__(self, scanner: MockScanner):
        self.scanner = scanner
        self.model_type = "test-model"
        self.paginated_items: List[Dict[str, Any]] = []
        self.formatted: List[Dict[str, Any]] = []

    async def get_paginated_data(self, **params: Any) -> Dict[str, Any]:
        items = [dict(item) for item in self.paginated_items]
        total = len(items)
        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    async def format_response(self, item: Dict[str, Any]) -> Dict[str, Any]:
        formatted = {**item, "formatted": True}
        self.formatted.append(formatted)
        return formatted

    # Convenience helpers used by assorted routes.  They are no-ops for the
    # smoke tests but document the expected surface area of the real services.
    def get_model_roots(self) -> List[str]:
        return ["."]

    async def scan_models(self, *_, **__):  # pragma: no cover - behaviour exercised via mocks
        return None

    async def get_model_notes(self, *_args, **_kwargs):  # pragma: no cover
        return None

    async def get_model_preview_url(self, *_args, **_kwargs):  # pragma: no cover
        return ""

    async def get_model_civitai_url(self, *_args, **_kwargs):  # pragma: no cover
        return {"civitai_url": ""}

    async def get_model_metadata(self, *_args, **_kwargs):  # pragma: no cover
        return {}

    async def get_model_description(self, *_args, **_kwargs):  # pragma: no cover
        return ""

    async def get_relative_paths(self, *_args, **_kwargs):  # pragma: no cover
        return []

    def has_hash(self, *_args, **_kwargs):  # pragma: no cover
        return False

    def get_path_by_hash(self, *_args, **_kwargs):  # pragma: no cover
        return ""


@pytest.fixture
def mock_hash_index() -> MockHashIndex:
    return MockHashIndex()


@pytest.fixture
def mock_cache() -> MockCache:
    return MockCache()


@pytest.fixture
def mock_scanner(mock_cache: MockCache, mock_hash_index: MockHashIndex) -> MockScanner:
    return MockScanner(cache=mock_cache, hash_index=mock_hash_index)


@pytest.fixture
def mock_service(mock_scanner: MockScanner) -> MockModelService:
    return MockModelService(scanner=mock_scanner)
