import asyncio
import importlib.util
import inspect
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest import mock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PY_INIT = REPO_ROOT / "py" / "__init__.py"


def _load_repo_package(name: str) -> types.ModuleType:
    """Ensure the repository's ``py`` package is importable under *name*."""

    module = sys.modules.get(name)
    if module and getattr(module, "__file__", None) == str(PY_INIT):
        return module

    spec = importlib.util.spec_from_file_location(
        name,
        PY_INIT,
        submodule_search_locations=[str(PY_INIT.parent)],
    )
    if spec is None or spec.loader is None:  # pragma: no cover - initialization guard
        raise ImportError(f"Unable to load repository package for alias '{name}'")

    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)  # type: ignore[attr-defined]
    package.__path__ = [str(PY_INIT.parent)]  # type: ignore[attr-defined]
    sys.modules[name] = package
    return package


_repo_package = _load_repo_package("py")
sys.modules.setdefault("py_local", _repo_package)

# Mock ComfyUI modules before any imports from the main project
server_mock = types.SimpleNamespace()
server_mock.PromptServer = mock.MagicMock()
sys.modules['server'] = server_mock

folder_paths_mock = types.SimpleNamespace()
folder_paths_mock.get_folder_paths = mock.MagicMock(return_value=[])
folder_paths_mock.folder_names_and_paths = {}
sys.modules['folder_paths'] = folder_paths_mock

# Mock other ComfyUI modules that might be imported
comfy_mock = types.SimpleNamespace()
comfy_mock.utils = types.SimpleNamespace()
comfy_mock.model_management = types.SimpleNamespace()
comfy_mock.comfy_types = types.SimpleNamespace()
comfy_mock.comfy_types.IO = mock.MagicMock()
sys.modules['comfy'] = comfy_mock
sys.modules['comfy.utils'] = comfy_mock.utils
sys.modules['comfy.model_management'] = comfy_mock.model_management
sys.modules['comfy.comfy_types'] = comfy_mock.comfy_types

execution_mock = types.SimpleNamespace()
execution_mock.PromptExecutor = mock.MagicMock()
sys.modules['execution'] = execution_mock

# Mock ComfyUI nodes module  
nodes_mock = types.SimpleNamespace()
nodes_mock.LoraLoader = mock.MagicMock()
nodes_mock.SaveImage = mock.MagicMock()
nodes_mock.NODE_CLASS_MAPPINGS = {}
sys.modules['nodes'] = nodes_mock


@pytest.fixture(autouse=True)
def _isolate_settings_dir(tmp_path_factory, monkeypatch):
    """Redirect settings.json into a temporary directory for each test."""

    settings_dir = tmp_path_factory.mktemp("settings_dir")

    def fake_get_settings_dir(create: bool = True) -> str:
        if create:
            settings_dir.mkdir(exist_ok=True)
        return str(settings_dir)

    monkeypatch.setattr("py.utils.settings_paths.get_settings_dir", fake_get_settings_dir)
    monkeypatch.setattr(
        "py.utils.settings_paths.user_config_dir",
        lambda *_args, **_kwargs: str(settings_dir),
    )

    from py.services import settings_manager as settings_manager_module

    settings_manager_module.reset_settings_manager()
    yield
    settings_manager_module.reset_settings_manager()


def pytest_pyfunc_call(pyfuncitem):
    """Allow bare async tests to run without pytest.mark.asyncio."""
    test_function = pyfuncitem.function
    if inspect.iscoroutinefunction(test_function):
        func = pyfuncitem.obj
        signature = inspect.signature(func)
        accepted_kwargs: Dict[str, Any] = {}
        for name, parameter in signature.parameters.items():
            if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                continue
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                accepted_kwargs = dict(pyfuncitem.funcargs)
                break
            if name in pyfuncitem.funcargs:
                accepted_kwargs[name] = pyfuncitem.funcargs[name]

        original_policy = asyncio.get_event_loop_policy()
        policy = pyfuncitem.funcargs.get("event_loop_policy")
        if policy is not None and policy is not original_policy:
            asyncio.set_event_loop_policy(policy)
        try:
            asyncio.run(func(**accepted_kwargs))
        finally:
            if policy is not None and policy is not original_policy:
                asyncio.set_event_loop_policy(original_policy)
        return True
    return None


@dataclass
class MockHashIndex:
    """Minimal hash index stub mirroring the scanner contract."""

    removed_paths: List[str] = field(default_factory=list)

    def remove_by_path(self, path: str) -> None:
        self.removed_paths.append(path)


class MockCache:
    """Cache object with the attributes."""

    def __init__(self, items: Optional[Sequence[Dict[str, Any]]] = None):
        self.raw_data: List[Dict[str, Any]] = list(items or [])
        self.resort_calls = 0

    async def resort(self) -> None:
        self.resort_calls += 1
        # expects the coroutine interface but does not
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


