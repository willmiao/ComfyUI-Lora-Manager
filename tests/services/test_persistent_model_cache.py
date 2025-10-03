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
            'exclude': False,
            'db_checked': True,
            'last_checked_at': 200.0,
            'tags': ['alpha', 'beta'],
            'civitai': {'id': 1, 'modelId': 2, 'name': 'verA', 'trainedWords': ['word1']},
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
            'exclude': True,
            'db_checked': False,
            'last_checked_at': 0.0,
            'tags': [],
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

    second = items[file_b]
    assert second['exclude'] is True
    assert second['civitai'] is None

    expected_hash_pairs = {
        ('hash-a', file_a),
        ('hash-b', file_b),
        ('hash-b', duplicate_path),
    }
    assert set((sha, path) for sha, path in persisted.hash_rows) == expected_hash_pairs
    assert persisted.excluded_models == excluded
