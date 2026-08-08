"""Tests for Autov3BackfillService."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from py.services.autov3_backfill_service import Autov3BackfillService
from py.services.model_cache import ModelCache
from py.services.model_hash_index import ModelHashIndex
from py.services.model_scanner import ModelScanner
from py.services.persistent_model_cache import DEFAULT_LICENSE_FLAGS, PersistentModelCache


@pytest.fixture(autouse=True)
def reset_backfill_singleton() -> None:
    """Reset the service singleton so every test starts from a fresh instance."""
    Autov3BackfillService._instance = None
    yield
    Autov3BackfillService._instance = None


def _entry(file_path: str, sha256: str, autov3: Optional[str] = None) -> Dict[str, Any]:
    return {
        'file_path': file_path,
        'file_name': Path(file_path).stem,
        'model_name': Path(file_path).stem,
        'folder': '',
        'size': 1,
        'modified': 1.0,
        'sha256': sha256,
        'autov3': autov3,
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
        self.update_calls: List[tuple] = []

    async def update_autov3_for_model(self, model_type: str, file_path: str, autov3: str) -> bool:
        self.update_calls.append((model_type, file_path, autov3))
        entry = self.entries.get(file_path)
        if entry is None:
            return False
        old_item = dict(entry)
        new_item = dict(entry)
        new_item['autov3'] = autov3
        self._persistent_cache.update_single_model(model_type, new_item, old_item)
        entry['autov3'] = autov3
        return True


def _make_store(tmp_path: Path, monkeypatch, name: str = 'cache.sqlite') -> PersistentModelCache:
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    return PersistentModelCache(db_path=str(tmp_path / name))


def _write_file(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_text(name, encoding='utf-8')
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
        _entry(checked, 'hash-checked', autov3=''),
        _entry(valued, 'hash-valued', autov3='a1b2c3d4e5f6'),
    ]
    store.save_cache(
        'dummy',
        entries,
        {e['sha256']: [e['file_path']] for e in entries},
        [],
    )

    scanner = RecordingScanner('dummy', store, entries)
    updated = await Autov3BackfillService.get_instance().backfill(scanner)

    # Non-safetensors files yield no embedded hash, so both are marked ''.
    assert updated == 2
    assert set(scanner.update_calls) == {('dummy', path_a, ''), ('dummy', path_b, '')}

    # Self-terminating: the driving query now finds no remaining rows.
    assert store.get_models_missing_autov3('dummy') == []

    persisted = store.load_cache('dummy')
    items = {item['file_path']: item for item in persisted.raw_data}
    assert items[path_a]['autov3'] == ''
    assert items[path_b]['autov3'] == ''
    # Checked-unavailable and valued rows are never recomputed or touched.
    assert items[checked]['autov3'] == ''
    assert items[valued]['autov3'] == 'a1b2c3d4e5f6'


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
    updated = await Autov3BackfillService.get_instance().backfill(scanner)

    assert updated == 1
    assert scanner.update_calls == [('dummy', existing, '')]
    # The missing row was not marked, so it still appears in the query.
    assert store.get_models_missing_autov3('dummy') == [missing]


async def test_backfill_returns_zero_when_same_type_already_running(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)
    scanner = RecordingScanner('dummy', store, [])

    service = Autov3BackfillService.get_instance()
    service._running_types = {'dummy'}
    try:
        assert await service.backfill(scanner) == 0
    finally:
        service._running_types = set()
    assert scanner.update_calls == []


async def test_backfill_runs_concurrently_for_different_model_types(tmp_path: Path, monkeypatch) -> None:
    """Scanners initialize in parallel (lora_manager.py), so a backfill for one
    model type must not skip another type's backfill."""
    store = _make_store(tmp_path, monkeypatch)
    lora_file = _write_file(tmp_path, 'lora.txt')
    ckpt_file = _write_file(tmp_path, 'ckpt.txt')
    store.save_cache(
        'lora',
        [_entry(lora_file, 'hash-lora')],
        {'hash-lora': [lora_file]},
        [],
    )
    store.save_cache(
        'checkpoint',
        [_entry(ckpt_file, 'hash-ckpt')],
        {'hash-ckpt': [ckpt_file]},
        [],
    )

    lora_scanner = RecordingScanner('lora', store, [_entry(lora_file, 'hash-lora')])
    ckpt_scanner = RecordingScanner('checkpoint', store, [_entry(ckpt_file, 'hash-ckpt')])

    service = Autov3BackfillService.get_instance()
    service._running_types = {'checkpoint'}  # Simulate a checkpoint backfill in flight

    try:
        # The lora backfill must still run while checkpoint is in progress.
        assert await service.backfill(lora_scanner) == 1
        assert lora_scanner.update_calls == [('lora', lora_file, '')]
    finally:
        service._running_types = set()


async def test_backfill_never_raises_on_failure(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)
    existing = _write_file(tmp_path, 'boom.txt')

    class RaisingScanner(RecordingScanner):
        async def update_autov3_for_model(self, model_type: str, file_path: str, autov3: str) -> bool:
            raise RuntimeError('boom')

    entries = [_entry(existing, 'hash-boom')]
    store.save_cache('dummy', entries, {'hash-boom': [existing]}, [])

    scanner = RaisingScanner('dummy', store, entries)
    updated = await Autov3BackfillService.get_instance().backfill(scanner)
    assert updated == 0


async def test_backfill_uses_default_cache_when_scanner_has_none(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)
    existing = _write_file(tmp_path, 'model.txt')
    entries = [_entry(existing, 'hash-x')]
    store.save_cache('dummy', entries, {'hash-x': [existing]}, [])

    from py.services import persistent_model_cache as pmc_module

    monkeypatch.setattr(pmc_module, 'get_persistent_cache', lambda: store)

    class BareScanner:
        model_type = 'dummy'

        async def update_autov3_for_model(self, model_type: str, file_path: str, autov3: str) -> bool:
            entry = next(e for e in entries if e['file_path'] == file_path)
            old_item = dict(entry)
            new_item = dict(entry)
            new_item['autov3'] = autov3
            store.update_single_model(model_type, new_item, old_item)
            return True

    updated = await Autov3BackfillService.get_instance().backfill(BareScanner())
    assert updated == 1
    assert store.get_models_missing_autov3('dummy') == []


async def test_backfill_idempotent_second_run_is_noop(tmp_path: Path, monkeypatch) -> None:
    store = _make_store(tmp_path, monkeypatch)
    existing = _write_file(tmp_path, 'idem.txt')

    entries = [_entry(existing, 'hash-idem')]
    store.save_cache('dummy', entries, {'hash-idem': [existing]}, [])

    scanner = RecordingScanner('dummy', store, entries)
    service = Autov3BackfillService.get_instance()

    assert await service.backfill(scanner) == 1
    # A re-run has nothing left to do.
    assert await service.backfill(scanner) == 0
    assert len(scanner.update_calls) == 1


async def test_backfill_end_to_end_through_scanner_lazy_import(tmp_path: Path, monkeypatch) -> None:
    """Drive the scanner's lazy-import trigger (`_run_autov3_backfill`) end to end."""
    store = _make_store(tmp_path, monkeypatch)

    path_a = _write_file(tmp_path, 'alpha.txt')
    path_b = _write_file(tmp_path, 'beta.txt')

    entries = [_entry(path_a, 'hash-alpha'), _entry(path_b, 'hash-beta')]
    store.save_cache(
        'dummy',
        entries,
        {'hash-alpha': [path_a], 'hash-beta': [path_b]},
        [],
    )

    class RealScanner(ModelScanner):
        def __init__(self) -> None:
            self.model_type = 'dummy'
            self._persistent_cache = store
            self._cache = ModelCache(raw_data=[dict(e) for e in entries], folders=[])
            self._hash_index = ModelHashIndex()

    await RealScanner()._run_autov3_backfill()

    assert store.get_models_missing_autov3('dummy') == []
    persisted = store.load_cache('dummy')
    items = {item['file_path']: item for item in persisted.raw_data}
    assert items[path_a]['autov3'] == ''
    assert items[path_b]['autov3'] == ''


async def test_backfill_prefers_civitai_autov3_from_sidecar(tmp_path: Path, monkeypatch) -> None:
    """Backfill uses the Civitai AutoV3 for the SHA256-matching file when the
    sidecar carries Civitai metadata, even if the file itself has no embedded
    header hash (the checkpoint case)."""
    store = _make_store(tmp_path, monkeypatch)

    path = _write_file(tmp_path, 'ckpt.txt')  # non-safetensors: no header hash
    sidecar = tmp_path / 'ckpt.metadata.json'
    sidecar.write_text(
        json.dumps({
            "sha256": "hash-ckpt",
            "civitai": {
                "files": [
                    {"name": "other.safetensors", "hashes": {"SHA256": "zzz999"}},
                    {"name": "ckpt.safetensors", "hashes": {"SHA256": "HASH-CKPT", "AutoV3": "ABCDEF1234567890"}},
                ]
            },
        }),
        encoding='utf-8',
    )

    store.save_cache('dummy', [_entry(path, 'hash-ckpt')], {'hash-ckpt': [path]}, [])

    scanner = RecordingScanner('dummy', store, [_entry(path, 'hash-ckpt')])
    updated = await Autov3BackfillService.get_instance().backfill(scanner)

    assert updated == 1
    assert scanner.update_calls == [('dummy', path, 'abcdef123456')]

    persisted = store.load_cache('dummy')
    items = {item['file_path']: item for item in persisted.raw_data}
    assert items[path]['autov3'] == 'abcdef123456'
    # Self-terminating: the row is marked and the driving query empties.
    assert store.get_models_missing_autov3('dummy') == []


async def test_backfill_falls_back_to_header_when_sidecar_has_no_match(tmp_path: Path, monkeypatch) -> None:
    """When the sidecar's Civitai files do not contain a SHA256 match, the
    backfill falls back to the embedded header hash ('' for non-safetensors)."""
    store = _make_store(tmp_path, monkeypatch)

    path = _write_file(tmp_path, 'plain.txt')
    sidecar = tmp_path / 'plain.metadata.json'
    sidecar.write_text(
        json.dumps({
            "sha256": "hash-plain",
            "civitai": {"files": [{"name": "other.safetensors", "hashes": {"SHA256": "zzz999", "AutoV3": "ABCDEF123456"}}]},
        }),
        encoding='utf-8',
    )

    store.save_cache('dummy', [_entry(path, 'hash-plain')], {'hash-plain': [path]}, [])

    scanner = RecordingScanner('dummy', store, [_entry(path, 'hash-plain')])
    updated = await Autov3BackfillService.get_instance().backfill(scanner)

    assert updated == 1
    assert scanner.update_calls == [('dummy', path, '')]
