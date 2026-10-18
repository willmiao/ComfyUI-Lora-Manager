"""Tests for QuantizationBackfillService."""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest

from py.services.model_cache import ModelCache
from py.services.model_hash_index import ModelHashIndex
from py.services.model_scanner import ModelScanner
from py.services.persistent_model_cache import DEFAULT_LICENSE_FLAGS, PersistentModelCache
from py.services.quantization_backfill_service import QuantizationBackfillService


@pytest.fixture(autouse=True)
def reset_backfill_singleton() -> Iterator[None]:
    """Reset the service singleton so every test starts from a fresh instance."""
    QuantizationBackfillService._instance = None
    yield
    QuantizationBackfillService._instance = None


def _entry(file_path: str, sha256: str, quantization: Optional[str] = None) -> Dict[str, Any]:
    return {
        'file_path': file_path,
        'file_name': Path(file_path).stem,
        'model_name': Path(file_path).stem,
        'folder': '',
        'size': 1,
        'modified': 1.0,
        'sha256': sha256,
        'autov3': '',
        'quantization': quantization,
        'base_model': '',
        'preview_url': '',
        'preview_nsfw_level': 0,
        'from_civitai': True,
        'favorite': False,
        'notes': '',
        'usage_tips': '',
        'metadata_source': None,
        'exclude': False,
        'db_checked': False,
        'last_checked_at': 0.0,
        'tags': [],
        'civitai': None,
        'civitai_deleted': False,
        'skip_metadata_refresh': False,
        'license_flags': DEFAULT_LICENSE_FLAGS,
        'hash_status': 'completed',
        'hf_url': '',
    }


class RecordingScanner:
    """Duck-typed scanner double persisting updates to a real cache."""

    def __init__(
        self,
        model_type: str,
        persistent_cache: PersistentModelCache,
        entries: List[Dict[str, Any]],
    ) -> None:
        self.model_type = model_type
        self._persistent_cache = persistent_cache
        self.entries: Dict[str, Dict[str, Any]] = {entry['file_path']: entry for entry in entries}
        self.update_calls: List[tuple[str, str, str]] = []

    async def update_quantization_for_model(self, model_type: str, file_path: str, quantization: str) -> bool:
        self.update_calls.append((model_type, file_path, quantization))
        entry = self.entries.get(file_path)
        if entry is None:
            return False
        old_item = dict(entry)
        new_item = dict(entry)
        new_item['quantization'] = quantization
        self._persistent_cache.update_single_model(model_type, new_item, old_item)
        entry['quantization'] = quantization
        return True


def _make_store(tmp_path: Path, monkeypatch, name: str = 'cache.sqlite') -> PersistentModelCache:
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    return PersistentModelCache(db_path=str(tmp_path / name))


def _write_file(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_text(name, encoding='utf-8')
    return path.as_posix()


def _write_gguf(tmp_path: Path, name: str, file_type: int) -> str:
    """Write a minimal GGUF file whose general.file_type is ``file_type``."""
    blob = io.BytesIO()
    blob.write(b"GGUF")
    blob.write(struct.pack("<I", 3))  # version
    blob.write(struct.pack("<Q", 0))  # tensor_count
    blob.write(struct.pack("<Q", 1))  # metadata_kv_count
    key = b"general.file_type"
    blob.write(struct.pack("<Q", len(key)))
    blob.write(key)
    blob.write(struct.pack("<I", 4))  # UINT32
    blob.write(struct.pack("<I", file_type))
    path = tmp_path / name
    path.write_bytes(blob.getvalue())
    return path.as_posix()


async def test_backfill_updates_models_and_self_terminates(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)

    path_a = _write_file(tmp_path, 'a.txt')
    path_b = _write_file(tmp_path, 'b.txt')
    checked = (tmp_path / 'checked.txt').as_posix()
    valued = (tmp_path / 'valued.txt').as_posix()

    entries = [
        _entry(path_a, 'hash-a'),
        _entry(path_b, 'hash-b'),
        _entry(checked, 'hash-checked', quantization=''),
        _entry(valued, 'hash-valued', quantization='Q4_K_M'),
    ]
    store.save_cache(
        'dummy',
        entries,
        {e['sha256']: [e['file_path']] for e in entries},
        [],
    )

    scanner = RecordingScanner('dummy', store, entries)
    updated = await QuantizationBackfillService.get_instance().backfill(scanner)  # pyright: ignore[reportArgumentType]

    # Non-model files yield no detectable quantization, so both are marked ''.
    assert updated == 2
    assert set(scanner.update_calls) == {('dummy', path_a, ''), ('dummy', path_b, '')}

    # Self-terminating: the driving query now finds no remaining rows.
    assert store.get_models_missing_quantization('dummy') == []

    persisted = store.load_cache('dummy')
    assert persisted is not None
    items = {item['file_path']: item for item in persisted.raw_data}
    assert items[path_a]['quantization'] == ''
    assert items[path_b]['quantization'] == ''
    # Checked-unavailable and valued rows are never recomputed or touched.
    assert items[checked]['quantization'] == ''
    assert items[valued]['quantization'] == 'Q4_K_M'


async def test_backfill_detects_gguf_quantization(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)

    path = _write_gguf(tmp_path, 'model.gguf', 15)  # MOSTLY_Q4_K_M

    entries = [_entry(path, 'hash-gguf')]
    store.save_cache('dummy', entries, {'hash-gguf': [path]}, [])

    scanner = RecordingScanner('dummy', store, entries)
    updated = await QuantizationBackfillService.get_instance().backfill(scanner)  # pyright: ignore[reportArgumentType]

    assert updated == 1
    assert scanner.update_calls == [('dummy', path, 'Q4_K_M')]

    persisted = store.load_cache('dummy')
    assert persisted is not None
    items = {item['file_path']: item for item in persisted.raw_data}
    assert items[path]['quantization'] == 'Q4_K_M'
    assert store.get_models_missing_quantization('dummy') == []


async def test_backfill_falls_back_to_civitai_fp8_from_sidecar(tmp_path: Path, monkeypatch) -> None:
    """Content detection is inconclusive for a non-model file; the Civitai
    fp8 flag of the SHA256-matching file fills the gap."""
    store = _make_store(tmp_path, monkeypatch)

    path = _write_file(tmp_path, 'ckpt.txt')
    sidecar = tmp_path / 'ckpt.metadata.json'
    sidecar.write_text(
        json.dumps({
            "sha256": "hash-ckpt",
            "civitai": {
                "files": [
                    {"name": "other.safetensors", "hashes": {"SHA256": "zzz999"}, "metadata": {"fp": "fp16"}},
                    {"name": "ckpt.safetensors", "hashes": {"SHA256": "HASH-CKPT"}, "metadata": {"fp": "fp8"}},
                ]
            },
        }),
        encoding='utf-8',
    )

    store.save_cache('dummy', [_entry(path, 'hash-ckpt')], {'hash-ckpt': [path]}, [])

    scanner = RecordingScanner('dummy', store, [_entry(path, 'hash-ckpt')])
    updated = await QuantizationBackfillService.get_instance().backfill(scanner)  # pyright: ignore[reportArgumentType]

    assert updated == 1
    assert scanner.update_calls == [('dummy', path, 'FP8')]

    persisted = store.load_cache('dummy')
    assert persisted is not None
    items = {item['file_path']: item for item in persisted.raw_data}
    assert items[path]['quantization'] == 'FP8'
    assert store.get_models_missing_quantization('dummy') == []


async def test_backfill_content_detection_beats_civitai_fp16(tmp_path: Path, monkeypatch) -> None:
    """A detected GGUF quantization wins over Civitai metadata."""
    store = _make_store(tmp_path, monkeypatch)

    path = _write_gguf(tmp_path, 'model.gguf', 7)  # MOSTLY_Q8_0
    sidecar = tmp_path / 'model.metadata.json'
    sidecar.write_text(
        json.dumps({
            "sha256": "hash-gguf",
            "civitai": {
                "files": [
                    {"name": "model.gguf", "hashes": {"SHA256": "hash-gguf"}, "metadata": {"fp": "fp8"}},
                ]
            },
        }),
        encoding='utf-8',
    )

    store.save_cache('dummy', [_entry(path, 'hash-gguf')], {'hash-gguf': [path]}, [])

    scanner = RecordingScanner('dummy', store, [_entry(path, 'hash-gguf')])
    updated = await QuantizationBackfillService.get_instance().backfill(scanner)  # pyright: ignore[reportArgumentType]

    assert updated == 1
    assert scanner.update_calls == [('dummy', path, 'Q8_0')]


async def test_backfill_skips_missing_files_without_marking(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)

    existing = _write_file(tmp_path, 'existing.txt')
    missing = (tmp_path / 'missing.txt').as_posix()

    entries = [_entry(existing, 'hash-existing'), _entry(missing, 'hash-missing')]
    store.save_cache(
        'dummy',
        entries,
        {'hash-existing': [existing], 'hash-missing': [missing]},
        [],
    )

    scanner = RecordingScanner('dummy', store, entries)
    updated = await QuantizationBackfillService.get_instance().backfill(scanner)  # pyright: ignore[reportArgumentType]

    assert updated == 1
    assert scanner.update_calls == [('dummy', existing, '')]
    # The missing row was not marked, so it still appears in the query.
    assert store.get_models_missing_quantization('dummy') == [missing]


async def test_backfill_returns_zero_when_same_type_already_running(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)
    scanner = RecordingScanner('dummy', store, [])

    service = QuantizationBackfillService.get_instance()
    service._running_types = {'dummy'}
    try:
        assert await service.backfill(scanner) == 0  # pyright: ignore[reportArgumentType]
    finally:
        service._running_types = set()
    assert scanner.update_calls == []


async def test_backfill_never_raises_on_failure(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)
    existing = _write_file(tmp_path, 'boom.txt')

    class RaisingScanner(RecordingScanner):
        async def update_quantization_for_model(self, model_type: str, file_path: str, quantization: str) -> bool:
            raise RuntimeError('boom')

    entries = [_entry(existing, 'hash-boom')]
    store.save_cache('dummy', entries, {'hash-boom': [existing]}, [])

    scanner = RaisingScanner('dummy', store, entries)
    updated = await QuantizationBackfillService.get_instance().backfill(scanner)  # pyright: ignore[reportArgumentType]
    assert updated == 0


async def test_backfill_idempotent_second_run_is_noop(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)
    existing = _write_file(tmp_path, 'idem.txt')

    entries = [_entry(existing, 'hash-idem')]
    store.save_cache('dummy', entries, {'hash-idem': [existing]}, [])

    scanner = RecordingScanner('dummy', store, entries)
    service = QuantizationBackfillService.get_instance()

    assert await service.backfill(scanner) == 1  # pyright: ignore[reportArgumentType]
    # A re-run has nothing left to do.
    assert await service.backfill(scanner) == 0  # pyright: ignore[reportArgumentType]
    assert len(scanner.update_calls) == 1


async def test_backfill_end_to_end_through_scanner_lazy_import(tmp_path: Path, monkeypatch) -> None:
    """Drive the scanner's lazy-import trigger (`_run_quantization_backfill`) end to end."""
    store = _make_store(tmp_path, monkeypatch)

    path_a = _write_gguf(tmp_path, 'alpha.gguf', 15)
    path_b = _write_file(tmp_path, 'beta.txt')

    entries = [_entry(path_a, 'hash-alpha'), _entry(path_b, 'hash-beta')]
    store.save_cache(
        'dummy',
        entries,
        {'hash-alpha': [path_a], 'hash-beta': [path_b]},
        [],
    )

    class RealScanner(ModelScanner):
        def __init__(self) -> None:  # pyright: ignore[reportMissingSuperCall]
            self.model_type = 'dummy'
            self._persistent_cache = store
            self._cache = ModelCache(raw_data=[dict(e) for e in entries], folders=[])
            self._hash_index = ModelHashIndex()
            self._cache_version = 0

    await RealScanner()._run_quantization_backfill()

    assert store.get_models_missing_quantization('dummy') == []
    persisted = store.load_cache('dummy')
    assert persisted is not None
    items = {item['file_path']: item for item in persisted.raw_data}
    assert items[path_a]['quantization'] == 'Q4_K_M'
    assert items[path_b]['quantization'] == ''
