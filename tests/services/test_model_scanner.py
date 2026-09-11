from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Dict, List, Optional
from types import MethodType

import pytest

from py.services import model_scanner
from py.services.model_cache import ModelCache
from py.services.model_hash_index import ModelHashIndex
from py.services.model_scanner import CacheBuildResult, ModelScanner
from py.services.pending_delete_service import (
    PENDING_DELETE_DIR_NAME,
    PENDING_DELETE_TTL_SECONDS,
    _reset_pending_delete_service,
)
from py.services.persistent_model_cache import PersistentModelCache, DEFAULT_LICENSE_FLAGS
from py.utils.civitai_utils import build_license_flags
from py.utils.models import BaseModelMetadata


class RecordingWebSocketManager:
    def __init__(self) -> None:
        self.payloads: List[Dict[str, Any]] = []
        self.broadcasts: List[Dict[str, Any]] = []

    async def broadcast_init_progress(self, payload: Dict[str, Any]) -> None:
        self.payloads.append(payload)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        self.broadcasts.append(payload)


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
    ) -> Optional[Dict[str, Any]]:
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


class MultiRootDummyScanner(DummyScanner):
    def __init__(self, roots: List[Path]):
        self._roots = [str(root) for root in roots]
        super().__init__(roots[0])

    def get_model_roots(self) -> List[str]:
        return list(self._roots)


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


@pytest.fixture(autouse=True)
def disable_persistent_cache_env(monkeypatch):
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '1')


@pytest.fixture(autouse=True)
def stub_register_service(monkeypatch):
    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(model_scanner.ServiceRegistry, "register_service", noop)


@pytest.fixture(autouse=True)
def _reset_pending_delete_singleton() -> Iterator[None]:
    """Reset the pending-delete singleton before and after each test."""
    _reset_pending_delete_service()
    yield
    _reset_pending_delete_service()


@pytest.fixture(autouse=True)
def _stub_service_registry_getters(monkeypatch) -> None:
    """Prevent pending-delete purge enumeration from building real scanners."""
    from py.services.service_registry import ServiceRegistry

    async def _none(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _none)
    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _none)
    monkeypatch.setattr(ServiceRegistry, "get_embedding_scanner", _none)


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
    # build_license_flags({}) returns 113 (defaults: allowNoCredit + ["Sell"] + derivatives + differentLicense)
    assert {item["license_flags"] for item in cache.raw_data} == {113}

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
    # build_license_flags({}) returns 113 (defaults: allowNoCredit + ["Sell"] + derivatives + differentLicense)
    assert {item["license_flags"] for item in cache.raw_data} == {113}
    assert scanner._hash_index.get_path("hash-two") == _normalize_path(tmp_path / "nested" / "two.txt")
    assert scanner._tags_count == {"alpha": 1, "beta": 1}
    assert scanner._excluded_models == [_normalize_path(tmp_path / "skip-file.txt")]
    assert ws_stub.payloads[-1]["progress"] == 100


@pytest.mark.asyncio
async def test_build_cache_entry_encodes_license_flags(tmp_path: Path):
    scanner = DummyScanner(tmp_path)

    metadata = {
        "file_path": _normalize_path(tmp_path / "sample.txt"),
        "file_name": "sample",
        "model_name": "Sample",
        "folder": "",
        "size": 1,
        "modified": 1.0,
        "sha256": "hash",
        "tags": [],
        "civitai": {
            "model": {
                "allowNoCredit": False,
                "allowCommercialUse": ["Image", "Rent"],
                "allowDerivatives": True,
                "allowDifferentLicense": False,
            }
        },
    }

    expected_flags = build_license_flags(
        {
            "allowNoCredit": False,
            "allowCommercialUse": ["Image", "Rent"],
            "allowDerivatives": True,
            "allowDifferentLicense": False,
        }
    )

    entry = scanner._build_cache_entry(metadata)
    assert entry["license_flags"] == expected_flags


@pytest.mark.asyncio
async def test_initialize_in_background_uses_persisted_cache_without_full_scan(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    db_path = tmp_path / 'cache.sqlite'
    store = PersistentModelCache(db_path=str(db_path))

    file_path = tmp_path / 'one.txt'
    file_path.write_text('one', encoding='utf-8')
    normalized = _normalize_path(file_path)

    raw_model = {
        'file_path': normalized,
        'file_name': 'one',
        'model_name': 'one',
        'folder': '',
        'size': 3,
        'modified': 123.0,
        'sha256': 'hash-one',
        'base_model': 'test',
        'preview_url': '',
        'preview_nsfw_level': 0,
        'from_civitai': True,
        'favorite': False,
        'notes': '',
        'usage_tips': '',
        'exclude': False,
        'db_checked': False,
        'last_checked_at': 0.0,
        'tags': ['alpha'],
        'civitai': {'id': 11, 'modelId': 22, 'name': 'ver'},
    }

    store.save_cache('dummy', [raw_model], {'hash-one': [normalized]}, [])

    monkeypatch.setattr(model_scanner, 'get_persistent_cache', lambda: store)

    scanner = DummyScanner(tmp_path)
    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, 'ws_manager', ws_stub)

    monkeypatch.setattr(scanner, '_count_model_files', lambda: pytest.fail('should not count files when cache loads'))

    def _fail_initialize(*_args, **_kwargs):
        pytest.fail('should not perform full scan when cache loads')

    monkeypatch.setattr(scanner, '_initialize_cache_sync', _fail_initialize)

    original_sleep = asyncio.sleep

    async def fast_sleep(duration: float) -> None:
        await original_sleep(0)

    monkeypatch.setattr(model_scanner.asyncio, 'sleep', fast_sleep)

    await scanner.initialize_in_background()

    cache = await scanner.get_cached_data()
    assert len(cache.raw_data) == 1
    assert cache.raw_data[0]['file_path'] == normalized
    assert cache.version_index[11]['file_path'] == normalized

    assert scanner._hash_index.get_path('hash-one') == normalized

    final_payload = ws_stub.payloads[-1]
    assert final_payload['progress'] == 100
    assert 'Loaded' in final_payload['details']


@pytest.mark.asyncio
async def test_load_persisted_cache_populates_cache(tmp_path: Path, monkeypatch):
    # Enable persistence for this specific test and back it with a temp database
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    db_path = tmp_path / 'cache.sqlite'
    store = PersistentModelCache(db_path=str(db_path))

    file_path = tmp_path / 'one.txt'
    file_path.write_text('one', encoding='utf-8')
    normalized = _normalize_path(file_path)

    raw_model = {
        'file_path': normalized,
        'file_name': 'one',
        'model_name': 'one',
        'folder': '',
        'size': 3,
        'modified': 123.0,
        'sha256': 'hash-one',
        'base_model': 'test',
        'preview_url': '',
        'preview_nsfw_level': 0,
        'from_civitai': True,
        'favorite': False,
        'notes': '',
        'usage_tips': '',
        'exclude': False,
        'db_checked': False,
        'last_checked_at': 0.0,
        'tags': ['alpha'],
        'civitai': {'id': 11, 'modelId': 22, 'name': 'ver', 'trainedWords': ['abc']},
    }

    store.save_cache('dummy', [raw_model], {'hash-one': [normalized]}, [])

    monkeypatch.setattr(model_scanner, 'get_persistent_cache', lambda: store)

    scanner = DummyScanner(tmp_path)
    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, 'ws_manager', ws_stub)

    loaded = await scanner._load_persisted_cache('dummy')
    assert loaded is True

    cache = await scanner.get_cached_data()
    assert len(cache.raw_data) == 1
    entry = cache.raw_data[0]
    assert entry['file_path'] == normalized
    assert entry['tags'] == ['alpha']
    assert entry['civitai']['trainedWords'] == ['abc']
    assert cache.version_index[11]['file_path'] == normalized
    assert scanner._hash_index.get_path('hash-one') == normalized
    assert scanner._tags_count == {'alpha': 1}
    assert ws_stub.payloads[-1]['stage'] == 'loading_cache'
    assert ws_stub.payloads[-1]['progress'] == 1


@pytest.mark.asyncio
async def test_load_persisted_cache_rebuilds_off_event_loop(tmp_path: Path, monkeypatch):
    """The SQLite read and per-model rebuild must not run on the event loop."""
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    db_path = tmp_path / 'cache.sqlite'
    store = PersistentModelCache(db_path=str(db_path))

    file_path = tmp_path / 'one.txt'
    file_path.write_text('one', encoding='utf-8')
    normalized = _normalize_path(file_path)

    raw_model = {
        'file_path': normalized,
        'file_name': 'one',
        'model_name': 'one',
        'folder': '',
        'size': 3,
        'modified': 123.0,
        'sha256': 'hash-one',
        'base_model': 'test',
        'preview_url': '',
        'preview_nsfw_level': 0,
        'from_civitai': True,
        'favorite': False,
        'notes': '',
        'usage_tips': '',
        'exclude': False,
        'db_checked': False,
        'last_checked_at': 0.0,
        'tags': ['alpha'],
        'civitai': {'id': 11, 'modelId': 22, 'name': 'ver', 'trainedWords': ['abc']},
    }

    store.save_cache('dummy', [raw_model], {'hash-one': [normalized]}, [])

    monkeypatch.setattr(model_scanner, 'get_persistent_cache', lambda: store)

    scanner = DummyScanner(tmp_path)
    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, 'ws_manager', ws_stub)

    loop_thread = threading.get_ident()
    worker_threads: List[int] = []

    original_load_cache = store.load_cache
    def tracking_load_cache(model_type):
        worker_threads.append(threading.get_ident())
        return original_load_cache(model_type)
    monkeypatch.setattr(store, 'load_cache', tracking_load_cache)

    original_adjust = scanner.adjust_cached_entry
    def tracking_adjust(entry):
        worker_threads.append(threading.get_ident())
        return original_adjust(entry)
    monkeypatch.setattr(scanner, 'adjust_cached_entry', tracking_adjust)

    loaded = await scanner._load_persisted_cache('dummy')
    assert loaded is True

    # Both the SQLite read and the per-entry adjustment ran off the loop
    assert len(worker_threads) == 2
    assert all(tid != loop_thread for tid in worker_threads)

    cache = await scanner.get_cached_data()
    assert len(cache.raw_data) == 1
    assert cache.raw_data[0]['file_path'] == normalized


@pytest.mark.asyncio
async def test_update_single_model_cache_persists_changes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    db_path = tmp_path / 'cache.sqlite'
    monkeypatch.setenv('LORA_MANAGER_CACHE_DB', str(db_path))
    monkeypatch.setattr(PersistentModelCache, '_instances', {}, raising=False)

    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)

    await scanner._initialize_cache()

    normalized = _normalize_path(tmp_path / 'one.txt')
    updated_metadata = {
        'file_path': normalized,
        'file_name': 'one',
        'model_name': 'renamed',
        'sha256': 'hash-one',
        'tags': ['gamma', 'delta'],
        'size': 42,
        'modified': 456.0,
        'base_model': 'base',
        'from_civitai': True,
    }

    await scanner.update_single_model_cache(normalized, normalized, updated_metadata)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT model_name FROM models WHERE file_path = ?",
            (normalized,),
        ).fetchone()

        assert row is not None
        assert row['model_name'] == 'renamed'

        tags = {
            record['tag']
            for record in conn.execute(
                "SELECT tag FROM model_tags WHERE file_path = ?",
                (normalized,),
            )
        }

        assert tags == {'gamma', 'delta'}


@pytest.mark.asyncio
async def test_batch_delete_persists_removal(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    db_path = tmp_path / 'cache.sqlite'
    monkeypatch.setenv('LORA_MANAGER_CACHE_DB', str(db_path))
    monkeypatch.setattr(PersistentModelCache, '_instances', {}, raising=False)

    first, _, _ = _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)

    await scanner._initialize_cache()

    normalized = _normalize_path(first)
    removed = await scanner._batch_update_cache_for_deleted_models([normalized])

    assert removed is True

    with sqlite3.connect(db_path) as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM models WHERE file_path = ?",
            (normalized,),
        ).fetchone()[0]

    assert remaining == 0


@pytest.mark.asyncio
async def test_version_index_tracks_version_ids(tmp_path: Path):
    scanner = DummyScanner(tmp_path)

    first_path = _normalize_path(tmp_path / 'alpha.txt')
    second_path = _normalize_path(tmp_path / 'beta.txt')

    first_entry = {
        'file_path': first_path,
        'file_name': 'alpha',
        'model_name': 'alpha',
        'folder': '',
        'size': 1,
        'modified': 1.0,
        'sha256': 'hash-alpha',
        'tags': [],
        'civitai': {'id': 101, 'modelId': 1, 'name': 'alpha'},
    }

    second_entry = {
        'file_path': second_path,
        'file_name': 'beta',
        'model_name': 'beta',
        'folder': '',
        'size': 1,
        'modified': 1.0,
        'sha256': 'hash-beta',
        'tags': [],
        'civitai': {'id': 202, 'modelId': 2, 'name': 'beta'},
    }

    hash_index = ModelHashIndex()
    hash_index.add_entry('hash-alpha', first_path)
    hash_index.add_entry('hash-beta', second_path)

    scan_result = CacheBuildResult(
        raw_data=[first_entry, second_entry],
        hash_index=hash_index,
        tags_count={},
        excluded_models=[],
    )

    await scanner._apply_scan_result(scan_result)

    cache = await scanner.get_cached_data()
    assert cache.version_index[101]['file_path'] == first_path
    assert cache.version_index[202]['file_path'] == second_path

    assert await scanner.check_model_version_exists(101) is True
    assert await scanner.check_model_version_exists('202') is True  # pyright: ignore[reportArgumentType]
    assert await scanner.check_model_version_exists(999) is False

    removed = await scanner._batch_update_cache_for_deleted_models([first_path])
    assert removed is True

    cache_after = await scanner.get_cached_data()
    assert 101 not in cache_after.version_index
    assert await scanner.check_model_version_exists(101) is False


@pytest.mark.asyncio
async def test_reconcile_cache_adds_new_files_and_updates_hash_index(tmp_path: Path):
    first, _, _ = _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)

    await scanner._initialize_cache()
    await scanner.get_cached_data()

    new_file = tmp_path / "three.txt"
    new_file.write_text("three", encoding="utf-8")
    (tmp_path / "nested" / "two.txt").unlink()

    await scanner._reconcile_cache()

    cache = await scanner.get_cached_data()
    cached_paths = {item["file_path"] for item in cache.raw_data}

    assert cached_paths == {
        _normalize_path(first),
        _normalize_path(new_file),
    }
    assert scanner._hash_index.get_path("hash-three") == _normalize_path(new_file)
    assert scanner._hash_index.get_path("hash-two") is None
    assert scanner._tags_count == {"alpha": 1, "beta": 1}
    assert cache.folders == [""]


@pytest.mark.asyncio
async def test_reconcile_cache_applies_adjust_cached_entry(tmp_path: Path):
    existing = tmp_path / "one.txt"
    existing.write_text("one", encoding="utf-8")

    scanner = DummyScanner(tmp_path)

    applied: List[str] = []

    def _adjust(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        applied.append(entry["file_path"])
        entry["custom_field"] = "adjusted"
        return entry

    scanner.adjust_cached_entry = MethodType(_adjust, scanner)

    await scanner._initialize_cache()
    applied.clear()

    new_file = tmp_path / "two.txt"
    new_file.write_text("two", encoding="utf-8")

    await scanner._reconcile_cache()

    normalized_new = _normalize_path(new_file)
    assert normalized_new in applied

    new_entry = next(item for item in scanner._cache.raw_data if item["file_path"] == normalized_new)
    assert new_entry["custom_field"] == "adjusted"


@pytest.mark.asyncio
async def test_count_model_files_handles_symlink_loops(tmp_path: Path):
    scanner = DummyScanner(tmp_path)

    root_file = tmp_path / "root.txt"
    root_file.write_text("root", encoding="utf-8")

    subdir = tmp_path / "sub"
    subdir.mkdir()
    nested_file = subdir / "nested.txt"
    nested_file.write_text("nested", encoding="utf-8")

    loop_link = subdir / "loop"
    loop_link.symlink_to(tmp_path)

    count = scanner._count_model_files()

    assert count == 2


@pytest.mark.asyncio
async def test_initialize_cache_dedupes_files_reachable_via_primary_symlink_and_extra_root(
    tmp_path: Path,
):
    loras_root = tmp_path / "loras"
    loras_root.mkdir()
    extra_root = tmp_path / "extra"
    extra_root.mkdir()
    (extra_root / "one.txt").write_text("one", encoding="utf-8")
    (loras_root / "link").symlink_to(extra_root, target_is_directory=True)

    scanner = MultiRootDummyScanner([loras_root, extra_root])

    await scanner._initialize_cache()
    cache = await scanner.get_cached_data()

    assert len(cache.raw_data) == 1
    assert cache.raw_data[0]["file_path"] == _normalize_path(loras_root / "link" / "one.txt")


@pytest.mark.asyncio
async def test_reconcile_cache_removes_duplicate_alias_when_same_real_file_seen_once(
    tmp_path: Path,
):
    loras_root = tmp_path / "loras"
    loras_root.mkdir()
    extra_root = tmp_path / "extra"
    extra_root.mkdir()
    real_file = extra_root / "one.txt"
    real_file.write_text("one", encoding="utf-8")
    (loras_root / "link").symlink_to(extra_root, target_is_directory=True)

    scanner = MultiRootDummyScanner([loras_root, extra_root])
    await scanner._initialize_cache()

    duplicate_entry: Dict[str, Any] = {
        "file_path": _normalize_path(extra_root / "one.txt"),
        "folder": "",
        "sha256": "hash-one",
        "tags": ["alpha"],
        "model_name": "one",
        "size": 1,
        "modified": 1.0,
        "license_flags": DEFAULT_LICENSE_FLAGS,
    }
    scanner._cache.raw_data.append(duplicate_entry)
    scanner._cache.add_to_version_index(duplicate_entry)
    scanner._hash_index.add_entry("hash-one", duplicate_entry["file_path"])

    await scanner._reconcile_cache()

    cache = await scanner.get_cached_data()
    cached_paths = {item["file_path"] for item in cache.raw_data}
    assert cached_paths == {_normalize_path(loras_root / "link" / "one.txt")}


@pytest.mark.asyncio
async def test_reconcile_cache_keeps_cached_path_when_walk_yields_a_live_alias(
    tmp_path: Path,
):
    """A root-order / symlink change can make the walk produce a *different but
    still live* business path for a file already in the cache. The realpath
    alias map must keep the cached entry instead of re-processing the file and
    swapping the path (which would re-read metadata and re-hash the weights)."""
    loras_root = tmp_path / "loras"
    loras_root.mkdir()
    extra_root = tmp_path / "extra"
    extra_root.mkdir()
    (extra_root / "one.txt").write_text("one", encoding="utf-8")
    (loras_root / "link").symlink_to(extra_root, target_is_directory=True)

    # `extra_root` comes first, so the cache entry is stored under its path.
    scanner = MultiRootDummyScanner([extra_root, loras_root])
    await scanner._initialize_cache()

    cached_before = {item["file_path"] for item in scanner._cache.raw_data}
    assert cached_before == {_normalize_path(extra_root / "one.txt")}

    # The symlinked path now wins the walk; the file itself is unchanged.
    scanner._roots = [str(loras_root), str(extra_root)]
    processed: List[str] = []

    async def _record_process(file_path: str, root_path: str, *args, **kwargs):
        processed.append(file_path)
        return await DummyScanner._process_model_file(
            scanner, file_path, root_path, *args, **kwargs
        )

    scanner._process_model_file = _record_process  # type: ignore[method-assign]

    await scanner._reconcile_cache()

    cache = await scanner.get_cached_data()
    assert {item["file_path"] for item in cache.raw_data} == cached_before
    assert processed == []


@pytest.mark.asyncio
async def test_reconcile_cache_defers_realpath_to_cache_misses(
    tmp_path: Path, monkeypatch
):
    """A no-change reconcile must not call realpath for unchanged files or for
    every cached entry: both the alias map and the per-file realpath are only
    needed for cache misses (they dominate the cost of a Refresh otherwise)."""
    root = tmp_path / "loras"
    root.mkdir()
    for i in range(5):
        (root / f"model{i}.txt").write_text("x", encoding="utf-8")

    scanner = DummyScanner(root)
    await scanner._initialize_cache()

    real_realpath = model_scanner.os.path.realpath
    realpath_args: List[str] = []

    def _recording_realpath(path, *args, **kwargs):
        realpath_args.append(os.fspath(path))
        return real_realpath(path, *args, **kwargs)

    monkeypatch.setattr(model_scanner.os.path, "realpath", _recording_realpath)

    await scanner._reconcile_cache()

    model_files = {_normalize_path(path) for path in root.glob("*.txt")}
    assert not (set(realpath_args) & model_files)


@pytest.mark.asyncio
async def test_reconcile_cache_cleans_pre_existing_duplicate_paths(tmp_path: Path):
    """External code rewrites raw_data directly, so a reconcile must still drop
    duplicate business paths even when nothing changed on disk: the O(1)
    integrity check may only skip the pass for a provably clean cache."""
    root = tmp_path / "loras"
    root.mkdir()
    (root / "one.txt").write_text("one", encoding="utf-8")
    (root / "two.txt").write_text("two", encoding="utf-8")

    scanner = DummyScanner(root)
    await scanner._initialize_cache()

    first_path = _normalize_path(root / "one.txt")
    duplicate = dict(next(i for i in scanner._cache.raw_data if i["file_path"] == first_path))
    duplicate["model_name"] = "duplicate-wins"
    scanner._cache.raw_data.append(duplicate)

    await scanner._reconcile_cache()

    cache = await scanner.get_cached_data()
    assert len(cache.raw_data) == 2
    survivor = next(i for i in cache.raw_data if i["file_path"] == first_path)
    assert survivor["model_name"] == "duplicate-wins"


@pytest.mark.asyncio
async def test_reconcile_cache_reads_model_roots_once_per_phase(tmp_path: Path, monkeypatch):
    """get_model_roots() must be snapshotted once for the walk and once for the
    new-file pass, not re-read for every new file."""
    root = tmp_path / "loras"
    root.mkdir()
    scanner = DummyScanner(root)
    await scanner._initialize_cache()

    calls = 0
    real_get_model_roots = scanner.get_model_roots

    def _counting_get_model_roots() -> List[str]:
        nonlocal calls
        calls += 1
        return real_get_model_roots()

    monkeypatch.setattr(scanner, "get_model_roots", _counting_get_model_roots)

    for i in range(3):
        (root / f"new{i}.txt").write_text("x", encoding="utf-8")

    await scanner._reconcile_cache()

    assert calls == 2


@pytest.mark.asyncio
async def test_log_duplicate_filename_summary_logs_warning(tmp_path: Path, caplog):
    """When duplicate filenames exist, _log_duplicate_filename_summary should emit
    a single warning log with the conflict count and total file count."""
    import logging
    caplog.set_level(logging.WARNING)

    root = tmp_path / "loras"
    root.mkdir()
    scanner = DummyScanner(root)
    # Duplicate filename detection is only active for LoRAs
    scanner.model_type = "lora"

    # Simulate duplicate filenames in the hash index
    scanner._hash_index.add_entry("aaa111", str(root / "model.safetensors"))
    scanner._hash_index.add_entry("bbb222", str(root / "dir" / "model.safetensors"))

    scanner._log_duplicate_filename_summary()

    assert len(caplog.records) >= 1
    log_msg = caplog.records[-1].message
    assert "Duplicate filename conflict detected" in log_msg
    assert "1 lora filename(s)" in log_msg
    assert "2 files total" in log_msg


@pytest.mark.asyncio
async def test_log_duplicate_filename_summary_silent_when_no_duplicates(tmp_path: Path, caplog):
    import logging
    caplog.set_level(logging.WARNING)

    root = tmp_path / "loras"
    root.mkdir()
    scanner = DummyScanner(root)
    scanner._log_duplicate_filename_summary()

    # No warning should be logged when there are no duplicates
    for record in caplog.records:
        assert "Duplicate filename conflict detected" not in record.message


# ── _cache_entries_differ ────────────────────────────────────────────


@pytest.mark.parametrize(
    "a_tags, b_tags, expect_differ",
    [
        (["alpha", "beta"], ["beta", "alpha"], False),  # order-insensitive
        (["alpha"], ["alpha", "beta"], True),            # count differs
        ([], ["alpha"], True),
        (None, [], False),                               # None ≈ []
        (["alpha"], None, True),
    ],
)
def test_cache_entries_differ_tags(a_tags, b_tags, expect_differ):
    base = {"file_path": "/m/a.safetensors", "model_name": "A", "size": 1}
    entry_a = {**base, "tags": a_tags}
    entry_b = {**base, "tags": b_tags}
    assert ModelScanner._cache_entries_differ(entry_a, entry_b) == expect_differ


def test_cache_entries_differ_identical():
    entry = {
        "file_path": "/m/a.safetensors", "model_name": "A", "size": 1,
        "tags": ["x"], "civitai": {"id": 1}, "notes": "hi",
    }
    assert ModelScanner._cache_entries_differ(entry, dict(entry)) is False


def test_cache_entries_differ_field_changed():
    a = {"file_path": "/m/a.safetensors", "model_name": "A", "size": 1}
    b = {**a, "model_name": "B"}
    assert ModelScanner._cache_entries_differ(a, b) is True


def test_cache_entries_differ_extra_key():
    a = {"file_path": "/m/a.safetensors", "model_name": "A"}
    b = {**a, "extra_field": "value"}
    assert ModelScanner._cache_entries_differ(a, b) is True


# ── sync_cache_from_metadata ─────────────────────────────────────────


def _make_cache_entry(**overrides) -> Dict[str, Any]:
    entry = {
        "file_path": "/m/a.safetensors",
        "model_name": "TestModel",
        "file_name": "a",
        "folder": "",
        "size": 100,
        "modified": 10.0,
        "sha256": "abc123",
        "base_model": "SD1.5",
        "preview_url": "",
        "preview_nsfw_level": 0,
        "from_civitai": True,
        "favorite": False,
        "notes": "old note",
        "usage_tips": "{}",
        "metadata_source": None,
        "exclude": False,
        "db_checked": False,
        "last_checked_at": 0.0,
        "tags": ["alpha"],
        "civitai": {"id": 111, "modelId": 222, "name": "v1"},
        "civitai_deleted": False,
        "skip_metadata_refresh": False,
        "hf_url": "",
        "license_flags": 113,
        "hash_status": "completed",
    }
    entry.update(overrides)
    return entry


@pytest.mark.asyncio
async def test_sync_cache_no_change(tmp_path: Path):
    """When metadata matches the cache entry, return False and mutate nothing."""
    scanner = DummyScanner(tmp_path)
    entry = _make_cache_entry()
    scanner._cache = ModelCache(
        raw_data=[dict(entry)], folders=[], name_display_mode="model_name"
    )
    await scanner._cache.resort()
    scanner._tags_count = {"alpha": 1}
    scanner._hash_index.add_entry("abc123", "/m/a.safetensors")

    # metadata_dict that would produce the identical cache entry
    metadata_dict = {
        "file_path": "/m/a.safetensors",
        "model_name": "TestModel",
        "file_name": "a",
        "folder": "",
        "size": 100,
        "modified": 10.0,
        "sha256": "abc123",
        "base_model": "SD1.5",
        "preview_url": "",
        "preview_nsfw_level": 0,
        "from_civitai": True,
        "favorite": False,
        "notes": "old note",
        "usage_tips": "{}",
        "tags": ["alpha"],
        "civitai": {"id": 111, "modelId": 222, "name": "v1"},
        "hf_url": "",
    }

    changed = await scanner.sync_cache_from_metadata(
        "/m/a.safetensors", metadata_dict
    )
    assert changed is False
    # Verify cache was NOT mutated
    cached = await scanner.get_cached_data()
    assert cached.raw_data[0]["notes"] == "old note"


@pytest.mark.asyncio
async def test_sync_cache_in_place_update(tmp_path: Path):
    """When metadata differs, update the cache entry in-place."""
    scanner = DummyScanner(tmp_path)
    entry = _make_cache_entry(notes="old note", tags=["alpha"], model_name="OldName")
    scanner._cache = ModelCache(
        raw_data=[dict(entry)], folders=[], name_display_mode="model_name"
    )
    await scanner._cache.resort()
    scanner._tags_count = {"alpha": 1}
    scanner._hash_index.add_entry("abc123", "/m/a.safetensors")

    # Capture the exact dict object in raw_data before sync
    original_entry_ref = scanner._cache.raw_data[0]

    metadata_dict = {
        "file_path": "/m/a.safetensors",
        "model_name": "NewName",
        "file_name": "a",
        "folder": "",
        "size": 100,
        "modified": 10.0,
        "sha256": "abc123",
        "base_model": "SD1.5",
        "preview_url": "",
        "preview_nsfw_level": 0,
        "from_civitai": True,
        "favorite": False,
        "notes": "new note",
        "usage_tips": "{}",
        "tags": ["beta", "gamma"],
        "civitai": {"id": 111, "modelId": 222, "name": "v1"},
        "hf_url": "",
    }

    changed = await scanner.sync_cache_from_metadata(
        "/m/a.safetensors", metadata_dict
    )
    assert changed is True

    cached = await scanner.get_cached_data()
    updated = cached.raw_data[0]
    # In-place: the same dict object persisted in raw_data
    assert updated is original_entry_ref
    assert updated["notes"] == "new note"
    assert updated["model_name"] == "NewName"
    assert sorted(updated["tags"]) == ["beta", "gamma"]
    # Tag counts updated incrementally
    assert scanner._tags_count.get("alpha", 0) == 0
    assert scanner._tags_count.get("beta", 0) == 1
    assert scanner._tags_count.get("gamma", 0) == 1


@pytest.mark.asyncio
async def test_sync_cache_not_in_cache_delegates(tmp_path: Path):
    """When the file_path is not in the cache at all, fall back to full update."""
    scanner = DummyScanner(tmp_path)
    scanner._cache = ModelCache(raw_data=[], folders=[], name_display_mode="model_name")
    await scanner._cache.resort()

    metadata_dict = {
        "file_path": "/m/b.safetensors",
        "model_name": "BrandNew",
        "file_name": "b",
        "folder": "",
        "size": 200,
        "modified": 20.0,
        "sha256": "def456",
        "base_model": "SDXL",
        "preview_url": "",
        "preview_nsfw_level": 0,
        "from_civitai": True,
        "favorite": False,
        "notes": "",
        "usage_tips": "{}",
        "tags": [],
        "civitai": {},
        "hf_url": "",
    }

    changed = await scanner.sync_cache_from_metadata(
        "/m/b.safetensors", metadata_dict
    )
    assert changed is True
    cached = await scanner.get_cached_data()
    assert len(cached.raw_data) == 1
    assert cached.raw_data[0]["model_name"] == "BrandNew"


@pytest.mark.asyncio
async def test_sync_cache_conditional_resort_skipped(tmp_path: Path, monkeypatch):
    """When only non-sort-key fields change, resort() is NOT called."""
    scanner = DummyScanner(tmp_path)
    entry = _make_cache_entry(notes="old note", model_name="SameName")
    scanner._cache = ModelCache(
        raw_data=[dict(entry)], folders=[], name_display_mode="model_name"
    )
    await scanner._cache.resort()
    scanner._cache._last_sort = ("name", "asc", None)  # name sort is active
    scanner._tags_count = {"alpha": 1}
    scanner._hash_index.add_entry("abc123", "/m/a.safetensors")

    # Track resort calls
    resort_called = False
    original_resort = scanner._cache.resort

    async def tracking_resort():
        nonlocal resort_called
        resort_called = True
        await original_resort()

    monkeypatch.setattr(scanner._cache, "resort", tracking_resort)

    metadata_dict = {
        "file_path": "/m/a.safetensors",
        "model_name": "SameName",  # unchanged — no resort needed
        "file_name": "a",
        "folder": "",
        "size": 100,
        "modified": 10.0,
        "sha256": "abc123",
        "base_model": "SD1.5",
        "preview_url": "",
        "preview_nsfw_level": 0,
        "from_civitai": True,
        "favorite": False,
        "notes": "updated note",  # changed, but not sort-relevant
        "usage_tips": "{}",
        "tags": ["alpha"],
        "civitai": {"id": 111, "modelId": 222, "name": "v1"},
        "hf_url": "",
    }

    changed = await scanner.sync_cache_from_metadata(
        "/m/a.safetensors", metadata_dict
    )
    assert changed is True
    assert resort_called is False


@pytest.mark.asyncio
async def test_sync_cache_conditional_resort_triggered(tmp_path: Path, monkeypatch):
    """When the sort-key field changes, resort() IS called."""
    scanner = DummyScanner(tmp_path)
    entry = _make_cache_entry(model_name="OldName")
    scanner._cache = ModelCache(
        raw_data=[dict(entry)], folders=[], name_display_mode="model_name"
    )
    await scanner._cache.resort()
    scanner._cache._last_sort = ("name", "asc", None)
    scanner._tags_count = {"alpha": 1}
    scanner._hash_index.add_entry("abc123", "/m/a.safetensors")

    resort_calls = 0
    original_resort = scanner._cache.resort

    async def tracking_resort():
        nonlocal resort_calls
        resort_calls += 1
        await original_resort()

    monkeypatch.setattr(scanner._cache, "resort", tracking_resort)

    metadata_dict = {
        "file_path": "/m/a.safetensors",
        "model_name": "NewName",  # changed — should trigger resort
        "file_name": "a",
        "folder": "",
        "size": 100,
        "modified": 10.0,
        "sha256": "abc123",
        "base_model": "SD1.5",
        "preview_url": "",
        "preview_nsfw_level": 0,
        "from_civitai": True,
        "favorite": False,
        "notes": "old note",
        "usage_tips": "{}",
        "tags": ["alpha"],
        "civitai": {"id": 111, "modelId": 222, "name": "v1"},
        "hf_url": "",
    }

    changed = await scanner.sync_cache_from_metadata(
        "/m/a.safetensors", metadata_dict
    )
    assert changed is True
    assert resort_calls == 1


# ── bulk_delete_models staging (undo-delete feature, todo 3) ───────────────


def _make_bulk_scanner(root: Path, file_paths: List[Path]) -> DummyScanner:
    """Build a DummyScanner whose cache mirrors the given files on disk."""
    scanner = DummyScanner(root)
    raw_data = []
    for path in file_paths:
        name = os.path.splitext(os.path.basename(path))[0]
        raw_data.append(
            {
                "file_path": str(path),
                "folder": "",
                "sha256": f"hash-{name}",
                "tags": ["alpha"] if "one" in name else ["beta"],
                "model_name": name,
                "file_name": name,
                "size": 1,
                "modified": 1.0,
            }
        )
    scanner._cache = ModelCache(
        raw_data=raw_data, folders=[], name_display_mode="model_name"
    )
    scanner._tags_count = {"alpha": 1, "beta": 1}
    for entry in raw_data:
        scanner._hash_index.add_entry(entry["sha256"], entry["file_path"])
    return scanner


@pytest.mark.asyncio
async def test_bulk_delete_stages_two_files_into_single_batch(tmp_path: Path):
    """Two-file bulk delete -> one merged batch id with both files staged."""
    root = tmp_path / "loras"
    root.mkdir()
    first = root / "one.txt"
    first.write_text("one", encoding="utf-8")
    second = root / "two.txt"
    second.write_text("two", encoding="utf-8")
    scanner = _make_bulk_scanner(root, [first, second])

    result = await scanner.bulk_delete_models([str(first), str(second)])

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["total_deleted"] == 2
    assert result["cache_updated"] is True

    # ONE batch id, no batch_ids array - the merge succeeded.
    assert "batch_id" in result
    assert "batch_ids" not in result
    batch_id = result["batch_id"]
    assert batch_id is not None
    staging = root / PENDING_DELETE_DIR_NAME
    batch_dir = staging / batch_id
    assert batch_dir.is_dir()
    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(os.path.basename(e["staged"]) for e in manifest["entries"]) == [
        "one.txt",
        "two.txt",
    ]

    # Manifest-only merge: each staged file physically remains in its OWN
    # batch dir (one.txt in the winner, two.txt in the loser storage dir) -
    # no file was moved, so no cross-volume IO ever happens.
    assert (batch_dir / "one.txt").read_bytes() == b"one"
    batch_dirs = [d.name for d in staging.iterdir() if d.is_dir()]
    assert len(batch_dirs) == 2
    assert batch_id in batch_dirs
    staged_files = {
        f.name
        for bid in batch_dirs
        for f in (staging / bid).iterdir()
        if f.is_file() and f.name != "manifest.json"
    }
    assert staged_files == {"one.txt", "two.txt"}

    # The manifest carries the winner's cache snapshot for later undo.
    assert manifest["model_snapshot"]["file_path"] == str(first)

    # Originals gone; cache entries removed.
    assert not first.exists()
    assert not second.exists()
    cached_paths = {item["file_path"] for item in scanner._cache.raw_data}
    assert str(first) not in cached_paths
    assert str(second) not in cached_paths


@pytest.mark.asyncio
async def test_bulk_delete_merged_manifest_reanchors_expiry(tmp_path: Path):
    """Merged manifest expires_at is re-anchored to now+TTL at merge time."""
    root = tmp_path / "loras"
    root.mkdir()
    first = root / "one.txt"
    first.write_text("one", encoding="utf-8")
    second = root / "two.txt"
    second.write_text("two", encoding="utf-8")
    scanner = _make_bulk_scanner(root, [first, second])

    before = int(time.time())
    result = await scanner.bulk_delete_models([str(first), str(second)])
    after = int(time.time())

    batch_dir = root / PENDING_DELETE_DIR_NAME / result["batch_id"]
    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    # expires_at >= staging completion time + TTL (re-anchor assertion).
    assert manifest["expires_at"] >= after + PENDING_DELETE_TTL_SECONDS - 2
    assert manifest["expires_at"] >= before + PENDING_DELETE_TTL_SECONDS
    # Both files are entries of the merged manifest; manifest-only merge means
    # each staged file stays where staging put it (still on disk, in its own
    # batch dir).
    assert len(manifest["entries"]) == 2
    assert all(os.path.exists(entry["staged"]) for entry in manifest["entries"])
    assert (batch_dir / "one.txt").exists()


@pytest.mark.asyncio
async def test_bulk_delete_merge_failure_falls_back_to_batch_ids(
    tmp_path: Path, monkeypatch
):
    """Merge unresolvable -> batch_ids array of the intact constituent batches."""
    root = tmp_path / "loras"
    root.mkdir()
    first = root / "one.txt"
    first.write_text("one", encoding="utf-8")
    second = root / "two.txt"
    second.write_text("two", encoding="utf-8")
    scanner = _make_bulk_scanner(root, [first, second])

    # Simulate a merge that cannot resolve the winner batch (the only real
    # merge failure mode since the merge no longer moves files): the caller
    # must fall back to returning the constituent batch_ids array.
    from py.services.pending_delete_service import get_pending_delete_service

    service = await get_pending_delete_service()

    async def _merge_unresolvable(_ids) -> None:
        return None

    monkeypatch.setattr(service, "merge_batches", _merge_unresolvable)

    result = await scanner.bulk_delete_models([str(first), str(second)])

    assert result["success"] is True
    assert result["total_deleted"] == 2
    # No single batch id - the constituent ids are returned instead.
    assert "batch_id" not in result
    assert "batch_ids" in result
    assert len(result["batch_ids"]) == 2

    # Both constituent batches are intact: dirs + manifests + staged files.
    staging = root / PENDING_DELETE_DIR_NAME
    batch_dirs = sorted(d.name for d in staging.iterdir() if d.is_dir())
    assert sorted(result["batch_ids"]) == batch_dirs
    for bid in result["batch_ids"]:
        batch_dir = staging / bid
        assert (batch_dir / "manifest.json").exists()
    staged_files = [
        f.name
        for bid in result["batch_ids"]
        for f in (staging / bid).iterdir()
        if f.is_file() and f.name != "manifest.json"
    ]
    assert sorted(staged_files) == ["one.txt", "two.txt"]


@pytest.mark.asyncio
async def test_bulk_delete_cancelled_after_one_staged_batch_present(
    tmp_path: Path, monkeypatch
):
    """Cancelled mid-way -> status='cancelled' AND the staged subset undoable."""
    root = tmp_path / "loras"
    root.mkdir()
    first = root / "one.txt"
    first.write_text("one", encoding="utf-8")
    second = root / "two.txt"
    second.write_text("two", encoding="utf-8")
    scanner = _make_bulk_scanner(root, [first, second])

    real_rename = os.rename
    rename_count = {"n": 0}

    def cancelling_rename(src: str, dst: str) -> None:
        rename_count["n"] += 1
        result = real_rename(src, dst)
        # After the first file is staged, request cancellation so the loop
        # stops before the second file is processed.
        if rename_count["n"] == 1:
            scanner.cancel_task()
        return result

    monkeypatch.setattr(
        "py.services.pending_delete_service.os.rename", cancelling_rename
    )

    result = await scanner.bulk_delete_models([str(first), str(second)])

    assert result["success"] is True
    assert result["status"] == "cancelled"
    assert result["total_deleted"] == 1
    assert "batch_id" in result
    assert result["batch_id"] is not None
    assert "batch_ids" not in result

    # The staged subset is merged into one undoable batch.
    batch_dir = root / PENDING_DELETE_DIR_NAME / result["batch_id"]
    assert batch_dir.is_dir()
    assert (batch_dir / "one.txt").read_bytes() == b"one"
    assert not first.exists()
    # The second file was never touched.
    assert second.exists()


@pytest.mark.asyncio
async def test_get_all_folders_records_empty_directories_during_scan(tmp_path: Path):
    _create_files(tmp_path)
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "nested_empty").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible" / ".hidden_child").mkdir(parents=True)
    (tmp_path / PENDING_DELETE_DIR_NAME).mkdir()

    scanner = DummyScanner(tmp_path)
    await scanner._initialize_cache()
    cache = await scanner.get_cached_data()

    all_folders = await scanner.get_all_folders()

    # cache.folders stays models-only
    assert sorted(cache.folders) == ["", "nested"]

    # Scan recording includes empty directories and stays a superset
    assert set(cache.folders) <= set(all_folders)
    assert "empty" in all_folders
    assert "empty/nested_empty" in all_folders
    assert "visible" in all_folders

    # Hidden directories (any segment starting with '.') are excluded
    assert not any(
        segment.startswith(".")
        for folder in all_folders
        for segment in folder.split("/")
    )
    # The pending-delete staging dir is excluded
    assert PENDING_DELETE_DIR_NAME not in all_folders


@pytest.mark.asyncio
async def test_get_all_folders_never_walks_filesystem(tmp_path: Path, monkeypatch):
    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)
    await scanner._initialize_cache()

    def failing_walk(*args, **kwargs):
        raise AssertionError("get_all_folders must not walk the filesystem")

    monkeypatch.setattr(model_scanner.os, "walk", failing_walk)

    all_folders = await scanner.get_all_folders()
    assert all_folders == ["" , "nested"]
    # No backfill is scheduled when the scan already recorded the folders
    assert scanner._all_folders_backfill_running is False


@pytest.mark.asyncio
async def test_get_all_folders_backfills_when_never_recorded(tmp_path: Path):
    _create_files(tmp_path)
    (tmp_path / "empty").mkdir()
    scanner = DummyScanner(tmp_path)
    await scanner._initialize_cache()

    # Simulate a cache hydrated from a persisted snapshot that predates
    # folder recording.
    cache = await scanner.get_cached_data()
    cache.all_folders = None

    # The cold path returns the models-only folders immediately...
    all_folders = await scanner.get_all_folders()
    assert set(all_folders) == {"", "nested"}
    # ...and schedules a one-shot background walk to backfill the rest.
    assert scanner._all_folders_backfill_running is True

    for _ in range(200):
        if not scanner._all_folders_backfill_running:
            break
        await asyncio.sleep(0.01)

    assert scanner._all_folders_backfill_running is False
    assert cache.all_folders is not None
    assert "empty" in cache.all_folders
    all_folders = await scanner.get_all_folders()
    assert "empty" in all_folders


@pytest.mark.asyncio
async def test_get_all_folders_updated_after_move(tmp_path: Path):
    first, _, _ = _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)

    await scanner._initialize_cache()

    cached = await scanner.get_all_folders()
    assert "new/deep" not in cached

    # Simulate a move: target directories exist on disk (created by
    # os.makedirs in move_model) and the cache entry is relocated.
    (tmp_path / "new" / "deep").mkdir(parents=True)
    original = _normalize_path(first)
    new_path = _normalize_path(tmp_path / "new" / "deep" / "one.txt")
    moved_metadata = {
        "file_path": new_path,
        "file_name": "one",
        "model_name": "one",
        "sha256": "hash-one",
        "tags": ["alpha"],
        "size": 1,
        "modified": 1.0,
    }

    await scanner.update_single_model_cache(original, new_path, moved_metadata)

    # The recorded folder list picked up the destination (and its parents)
    all_folders = await scanner.get_all_folders()
    cache = await scanner.get_cached_data()
    assert sorted(cache.folders) == ["nested", "new/deep"]
    assert "new" in all_folders
    assert "new/deep" in all_folders
    assert set(cache.folders) <= set(all_folders)


@pytest.mark.asyncio
async def test_all_folders_persisted_and_hydrated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    db_path = tmp_path / 'cache.sqlite'
    store = PersistentModelCache(db_path=str(db_path))
    monkeypatch.setattr(model_scanner, 'get_persistent_cache', lambda: store)

    root = tmp_path / 'models'
    root.mkdir()
    (root / 'one.txt').write_text('one', encoding='utf-8')
    (root / 'empty').mkdir()

    scanner = DummyScanner(root)
    await scanner._initialize_cache()
    cache = await scanner.get_cached_data()
    assert cache.all_folders is not None
    assert 'empty' in cache.all_folders

    # The folder list (including the empty dir) survives in SQLite.
    persisted = store.load_cache('dummy')
    assert persisted is not None
    assert persisted.all_folders is not None
    assert 'empty' in persisted.all_folders

    # A fresh scanner hydrates the recorded folders without any walk.
    ModelScanner._instances.clear()
    hydrated = DummyScanner(root)
    scan_result, invalid = hydrated._rebuild_persisted_cache()
    assert scan_result is not None
    assert scan_result.all_folders == persisted.all_folders


def test_all_folders_absent_in_legacy_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    store = PersistentModelCache(db_path=str(tmp_path / 'cache.sqlite'))

    normalized = _normalize_path(tmp_path / 'one.txt')
    raw_model = {
        'file_path': normalized,
        'file_name': 'one',
        'model_name': 'one',
        'folder': '',
        'size': 3,
        'modified': 123.0,
        'sha256': 'hash-one',
        'tags': [],
    }

    # Save without folder data, mimicking a snapshot written before folder
    # recording existed.
    store.save_cache('dummy', [raw_model], {'hash-one': [normalized]}, [])

    persisted = store.load_cache('dummy')
    assert persisted is not None
    assert persisted.all_folders is None


@pytest.mark.asyncio
async def test_initialize_cache_broadcasts_scan_progress(tmp_path: Path, monkeypatch):
    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)

    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, "ws_manager", ws_stub)

    await scanner._initialize_cache()

    messages = ws_stub.broadcasts
    assert messages, "expected scan_progress broadcasts"

    started = messages[0]
    assert started["type"] == "scan_progress"
    assert started["status"] == "started"
    assert started["stage"] == "scan_folders"
    assert started["progress"] == 0
    assert started["model_type"] == "dummy"
    assert started["pageType"] == "dummy"
    assert started["full_rebuild"] is True

    count_messages = [m for m in messages if m["stage"] == "count_models"]
    assert count_messages and count_messages[0]["total"] == 3

    process_messages = [
        m for m in messages
        if m["stage"] == "process_models" and m["status"] == "processing"
    ]
    assert process_messages, "expected at least one process_models update"
    final_process = process_messages[-1]
    assert final_process["processed"] == 3
    assert final_process["total"] == 3
    assert final_process["current_name"].endswith(".txt")
    for message in process_messages:
        assert 0 < message["progress"] <= 99

    stages = [m["stage"] for m in messages]
    assert "finalizing" in stages
    completed = messages[-1]
    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert completed["elapsed_seconds"] >= 0


@pytest.mark.asyncio
async def test_initialize_cache_broadcasts_cancelled(tmp_path: Path, monkeypatch):
    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)

    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, "ws_manager", ws_stub)

    original_process = DummyScanner._process_model_file

    async def cancelling_process(self, file_path, root_path, **kwargs):
        scanner.cancel_task()
        return await original_process(self, file_path, root_path, **kwargs)

    monkeypatch.setattr(DummyScanner, "_process_model_file", cancelling_process)

    await scanner._initialize_cache()

    messages = ws_stub.broadcasts
    assert messages[0]["status"] == "started"
    assert messages[-1]["status"] == "cancelled"
    assert messages[-1]["elapsed_seconds"] >= 0
    assert not any(m["status"] == "completed" for m in messages)


@pytest.mark.asyncio
async def test_initialize_cache_broadcasts_error(tmp_path: Path, monkeypatch):
    scanner = DummyScanner(tmp_path)

    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, "ws_manager", ws_stub)

    async def raising_gather(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(scanner, "_gather_model_data", raising_gather)

    await scanner._initialize_cache()

    messages = ws_stub.broadcasts
    assert messages[0]["status"] == "started"
    assert messages[-1]["status"] == "error"
    assert messages[-1]["error"] == "boom"


@pytest.mark.asyncio
async def test_reconcile_cache_broadcasts_scan_progress(tmp_path: Path, monkeypatch):
    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)
    await scanner._initialize_cache()

    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, "ws_manager", ws_stub)

    new_file = tmp_path / "three.txt"
    new_file.write_text("three", encoding="utf-8")

    await scanner._reconcile_cache()

    messages = ws_stub.broadcasts
    assert messages, "expected scan_progress broadcasts"

    started = messages[0]
    assert started["type"] == "scan_progress"
    assert started["status"] == "started"
    assert started["stage"] == "reconcile_scan"
    assert started["progress"] == 0
    assert started["full_rebuild"] is False

    process_messages = [
        m for m in messages
        if m["stage"] == "process_new" and m["status"] == "processing"
    ]
    assert process_messages, "expected process_new progress updates"
    assert process_messages[-1]["processed"] == 1
    assert process_messages[-1]["total"] == 1
    assert process_messages[-1]["current_name"] == "three.txt"

    completed = messages[-1]
    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert completed["added"] == 1
    assert completed["removed"] == 0
    assert completed["elapsed_seconds"] >= 0


@pytest.mark.asyncio
async def test_reconcile_cache_broadcasts_cancelled(tmp_path: Path, monkeypatch):
    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)
    await scanner._initialize_cache()

    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, "ws_manager", ws_stub)

    new_file = tmp_path / "four.txt"
    new_file.write_text("four", encoding="utf-8")

    original_process = DummyScanner._process_model_file

    async def cancelling_process(self, file_path, root_path, **kwargs):
        scanner.cancel_task()
        return await original_process(self, file_path, root_path, **kwargs)

    monkeypatch.setattr(DummyScanner, "_process_model_file", cancelling_process)

    await scanner._reconcile_cache()

    messages = ws_stub.broadcasts
    assert messages[0]["status"] == "started"
    assert messages[-1]["status"] == "cancelled"
    assert messages[-1]["elapsed_seconds"] >= 0
    assert not any(m["status"] == "completed" for m in messages)


@pytest.mark.asyncio
async def test_reconcile_cache_broadcasts_error(tmp_path: Path, monkeypatch):
    _create_files(tmp_path)
    scanner = DummyScanner(tmp_path)
    await scanner._initialize_cache()

    ws_stub = RecordingWebSocketManager()
    monkeypatch.setattr(model_scanner, "ws_manager", ws_stub)

    def raising_walk(*_args, **_kwargs):
        raise RuntimeError("walk failed")

    monkeypatch.setattr(model_scanner.os, "walk", raising_walk)

    await scanner._reconcile_cache()

    messages = ws_stub.broadcasts
    assert messages[0]["status"] == "started"
    assert messages[-1]["status"] == "error"
    assert messages[-1]["error"] == "walk failed"
