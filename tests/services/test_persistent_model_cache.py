from pathlib import Path

import pytest

from py.services.persistent_model_cache import PersistentModelCache


def test_persistent_cache_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    db_path = tmp_path / 'cache.sqlite'
    store = PersistentModelCache(db_path=str(db_path))

    file_a = (tmp_path / 'a.txt').as_posix()
    file_b = (tmp_path / 'b.txt').as_posix()
    duplicate_path = f"{file_b}.copy"

    raw_data = [
        {
            'file_path': file_a,
            'file_name': 'a',
            'model_name': 'Model A',
            'folder': '',
            'size': 10,
            'modified': 100.0,
            'sha256': 'hash-a',
            'base_model': 'base',
            'preview_url': 'preview/a.png',
            'preview_nsfw_level': 1,
            'from_civitai': True,
            'favorite': True,
            'notes': 'note',
            'usage_tips': '{}',
            'metadata_source': 'civitai_api',
            'exclude': False,
            'db_checked': True,
            'last_checked_at': 200.0,
            'tags': ['alpha', 'beta'],
            'civitai_deleted': False,
            'civitai': {
                'id': 1,
                'modelId': 2,
                'name': 'verA',
                'trainedWords': ['word1'],
                'creator': {'username': 'artist42'},
            },
        },
        {
            'file_path': file_b,
            'file_name': 'b',
            'model_name': 'Model B',
            'folder': 'folder',
            'size': 20,
            'modified': 120.0,
            'sha256': 'hash-b',
            'base_model': '',
            'preview_url': '',
            'preview_nsfw_level': 0,
            'from_civitai': False,
            'favorite': False,
            'notes': '',
            'usage_tips': '',
            'metadata_source': None,
            'exclude': True,
            'db_checked': False,
            'last_checked_at': 0.0,
            'tags': [],
            'civitai_deleted': True,
            'civitai': None,
        },
    ]

    hash_index = {
        'hash-a': [file_a],
        'hash-b': [file_b, duplicate_path],
    }
    excluded = [duplicate_path]

    store.save_cache('dummy', raw_data, hash_index, excluded)

    persisted = store.load_cache('dummy')
    assert persisted is not None
    assert len(persisted.raw_data) == 2

    items = {item['file_path']: item for item in persisted.raw_data}
    assert set(items.keys()) == {file_a, file_b}
    first = items[file_a]
    assert first['favorite'] is True
    assert first['civitai']['id'] == 1
    assert first['civitai']['trainedWords'] == ['word1']
    assert first['tags'] == ['alpha', 'beta']
    assert first['metadata_source'] == 'civitai_api'
    assert first['civitai']['creator']['username'] == 'artist42'
    assert first['civitai_deleted'] is False

    second = items[file_b]
    assert second['exclude'] is True
    assert second['civitai'] is None
    assert second['metadata_source'] is None
    assert second['civitai_deleted'] is True

    expected_hash_pairs = {
        ('hash-a', file_a),
        ('hash-b', file_b),
        ('hash-b', duplicate_path),
    }
    assert set((sha, path) for sha, path in persisted.hash_rows) == expected_hash_pairs
    assert persisted.excluded_models == excluded


def test_incremental_updates_only_touch_changed_rows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('LORA_MANAGER_DISABLE_PERSISTENT_CACHE', '0')
    db_path = tmp_path / 'cache.sqlite'
    store = PersistentModelCache(db_path=str(db_path))

    file_a = (tmp_path / 'a.txt').as_posix()
    file_b = (tmp_path / 'b.txt').as_posix()

    initial_payload = [
        {
            'file_path': file_a,
            'file_name': 'a',
            'model_name': 'Model A',
            'folder': '',
            'size': 10,
            'modified': 100.0,
            'sha256': 'hash-a',
            'base_model': 'base',
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
            'tags': ['alpha'],
            'civitai_deleted': False,
            'civitai': None,
        },
        {
            'file_path': file_b,
            'file_name': 'b',
            'model_name': 'Model B',
            'folder': '',
            'size': 20,
            'modified': 120.0,
            'sha256': 'hash-b',
            'base_model': '',
            'preview_url': '',
            'preview_nsfw_level': 0,
            'from_civitai': False,
            'favorite': False,
            'notes': '',
            'usage_tips': '',
            'metadata_source': 'civarchive',
            'exclude': False,
            'db_checked': False,
            'last_checked_at': 0.0,
            'tags': ['beta'],
            'civitai_deleted': False,
            'civitai': {'creator': {'username': 'builder'}},
        },
    ]

    statements: list[str] = []
    original_connect = store._connect

    def _recording_connect(readonly: bool = False):
        conn = original_connect(readonly=readonly)
        conn.set_trace_callback(statements.append)
        return conn

    store._connect = _recording_connect  # type: ignore[method-assign]

    store.save_cache('dummy', initial_payload, {'hash-a': [file_a], 'hash-b': [file_b]}, [])
    statements.clear()

    updated_payload = [
        initial_payload[0],
        {
            **initial_payload[1],
            'model_name': 'Model B Updated',
            'favorite': True,
            'tags': ['beta', 'gamma'],
            'metadata_source': 'archive_db',
            'civitai_deleted': True,
            'civitai': {'creator': {'username': 'builder_v2'}},
        },
    ]
    hash_index = {'hash-a': [file_a], 'hash-b': [file_b]}

    store.save_cache('dummy', updated_payload, hash_index, [])

    broad_delete = [
        stmt for stmt in statements if "DELETE FROM models WHERE model_type = 'dummy'" in stmt and "file_path" not in stmt
    ]
    assert not broad_delete

    updated_stmt_present = any(
        "UPDATE models" in stmt and f"file_path = '{file_b}'" in stmt for stmt in statements
    )
    assert updated_stmt_present

    unchanged_stmt_present = any(
        "UPDATE models" in stmt and f"file_path = '{file_a}'" in stmt for stmt in statements
    )
    assert not unchanged_stmt_present

    tag_insert = any(
        "INSERT INTO model_tags" in stmt and "gamma" in stmt for stmt in statements
    )
    assert tag_insert

    assert any("metadata_source" in stmt for stmt in statements if "UPDATE models" in stmt)

    persisted = store.load_cache('dummy')
    assert persisted is not None
    items = {item['file_path']: item for item in persisted.raw_data}
    second = items[file_b]
    assert second['metadata_source'] == 'archive_db'
    assert second['civitai_deleted'] is True
    assert second['civitai']['creator']['username'] == 'builder_v2'
