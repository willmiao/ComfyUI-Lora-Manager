import asyncio
import os
from pathlib import Path
from typing import List

import pytest

from py.services import model_scanner
from py.services.model_cache import ModelCache
from py.services.model_hash_index import ModelHashIndex
from py.services.model_scanner import CacheBuildResult, ModelScanner
from py.utils.models import BaseModelMetadata


class RecordingWebSocketManager:
    def __init__(self) -> None:
        self.payloads: List[dict] = []

    async def broadcast_init_progress(self, payload: dict) -> None:
        self.payloads.append(payload)


def _normalize_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


class DummyScanner(ModelScanner):
    def __init__(self, root: Path):
        self._root = str(root)
        super().__init__(
            model_type="dummy",
            model_class=BaseModelMetadata,
            file_extensions={".txt"},
            hash_index=ModelHashIndex(),
        )

    def get_model_roots(self) -> List[str]:
        return [self._root]

    async def _process_model_file(
        self,
        file_path: str,
        root_path: str,
        *,
        hash_index: ModelHashIndex | None = None,
        excluded_models: List[str] | None = None,
    ) -> dict:
        hash_index = hash_index or self._hash_index
        excluded_models = excluded_models if excluded_models is not None else self._excluded_models

        rel_path = os.path.relpath(file_path, root_path)
        folder = os.path.dirname(rel_path).replace(os.path.sep, "/")
        name = os.path.splitext(os.path.basename(file_path))[0]

        if name.startswith("skip"):
            excluded_models.append(file_path.replace(os.sep, "/"))
            return None

        tags = ["alpha"] if "one" in name else ["beta"]

        return {
            "file_path": file_path.replace(os.sep, "/"),
            "folder": folder,
            "sha256": f"hash-{name}",
            "tags": tags,
            "model_name": name,
            "size": 1,
            "modified": 1.0,
        }


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


@pytest.fixture(autouse=True)
def stub_register_service(monkeypatch):
    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(model_scanner.ServiceRegistry, "register_service", noop)


def _create_files(root: Path) -> tuple[Path, Path, Path]:
    first = root / "one.txt"
    first.write_text("one", encoding="utf-8")

    nested_dir = root / "nested"
    nested_dir.mkdir()
    second = nested_dir / "two.txt"
    second.write_text("two", encoding="utf-8")

    skipped = root / "skip-file.txt"
    skipped.write_text("skip", encoding="utf-8")

    return first, second, skipped


@pytest.mark.asyncio
async def test_initialize_cache_populates_cache(tmp_path: Path):
    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)

    await scanner._initialize_cache()
    cache = await scanner.get_cached_data()

    cached_paths = {item["file_path"] for item in cache.raw_data}
    assert cached_paths == {
        _normalize_path(tmp_path / "one.txt"),
        _normalize_path(tmp_path / "nested" / "two.txt"),
    }

    assert scanner._hash_index.get_path("hash-one") == _normalize_path(tmp_path / "one.txt")
    assert scanner._hash_index.get_path("hash-two") == _normalize_path(tmp_path / "nested" / "two.txt")
    assert scanner._tags_count == {"alpha": 1, "beta": 1}
    assert scanner._excluded_models == [_normalize_path(tmp_path / "skip-file.txt")]
    assert sorted(cache.folders) == ["", "nested"]


@pytest.mark.asyncio
async def test_initialize_cache_sync_returns_result_without_mutating_state(tmp_path: Path, monkeypatch):
    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)

    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, "ws_manager", ws_stub)

    scanner._cache = ModelCache(raw_data=[{"file_path": "sentinel", "folder": ""}], folders=["existing"])

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, scanner._initialize_cache_sync, 2, "dummy")

    assert isinstance(result, CacheBuildResult)
    assert {item["file_path"] for item in result.raw_data} == {
        _normalize_path(tmp_path / "one.txt"),
        _normalize_path(tmp_path / "nested" / "two.txt"),
    }
    assert result.tags_count == {"alpha": 1, "beta": 1}
    assert ws_stub.payloads, "expected progress updates from websocket manager"

    assert scanner._cache.raw_data == [{"file_path": "sentinel", "folder": ""}]
    assert scanner._hash_index.get_path("hash-one") is None


@pytest.mark.asyncio
async def test_initialize_in_background_applies_scan_result(tmp_path: Path, monkeypatch):
    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)

    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, "ws_manager", ws_stub)

    original_sleep = asyncio.sleep

    async def fast_sleep(duration: float) -> None:
        await original_sleep(0)

    monkeypatch.setattr(model_scanner.asyncio, "sleep", fast_sleep)

    await scanner.initialize_in_background()

    cache = await scanner.get_cached_data()
    cached_paths = {item["file_path"] for item in cache.raw_data}

    assert cached_paths == {
        _normalize_path(tmp_path / "one.txt"),
        _normalize_path(tmp_path / "nested" / "two.txt"),
    }
    assert scanner._hash_index.get_path("hash-two") == _normalize_path(tmp_path / "nested" / "two.txt")
    assert scanner._tags_count == {"alpha": 1, "beta": 1}
    assert scanner._excluded_models == [_normalize_path(tmp_path / "skip-file.txt")]
    assert ws_stub.payloads[-1]["progress"] == 100
