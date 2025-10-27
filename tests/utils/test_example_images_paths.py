from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils.example_images_paths import (
    ensure_library_root_exists,
    get_model_folder,
    get_model_relative_path,
    is_valid_example_images_root,
    iter_library_roots,
)


@pytest.fixture(autouse=True)
def restore_settings():
    manager = get_settings_manager()
    original = copy.deepcopy(manager.settings)
    try:
        yield
    finally:
        manager.settings.clear()
        manager.settings.update(original)


@pytest.fixture
def settings_manager():
    return get_settings_manager()


def test_get_model_folder_single_library(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    settings_manager.settings['libraries'] = {'default': {}}
    settings_manager.settings['active_library'] = 'default'

    model_hash = 'a' * 64
    folder = get_model_folder(model_hash)
    relative = get_model_relative_path(model_hash)

    assert Path(folder) == tmp_path / model_hash
    assert relative == model_hash


def test_get_model_folder_multi_library(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    settings_manager.settings['libraries'] = {
        'default': {},
        'Alt Library': {},
    }
    settings_manager.settings['active_library'] = 'Alt Library'

    model_hash = 'b' * 64
    expected_folder = tmp_path / 'Alt_Library' / model_hash

    folder = get_model_folder(model_hash)
    relative = get_model_relative_path(model_hash)

    assert Path(folder) == expected_folder
    assert relative == os.path.join('Alt_Library', model_hash).replace('\\', '/')


def test_get_model_folder_migrates_legacy_structure(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    settings_manager.settings['libraries'] = {
        'default': {},
        'extra': {},
    }
    settings_manager.settings['active_library'] = 'extra'

    model_hash = 'c' * 64
    legacy_folder = tmp_path / model_hash
    legacy_folder.mkdir()
    legacy_file = legacy_folder / 'image.png'
    legacy_file.write_text('data', encoding='utf-8')

    resolved_folder = get_model_folder(model_hash)
    relative = get_model_relative_path(model_hash)

    expected_folder = tmp_path / 'extra' / model_hash

    assert Path(resolved_folder) == expected_folder
    assert relative == os.path.join('extra', model_hash).replace('\\', '/')
    assert not legacy_folder.exists()
    assert (expected_folder / 'image.png').exists()


def test_ensure_library_root_exists_creates_directories(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    settings_manager.settings['libraries'] = {'default': {}, 'secondary': {}}
    settings_manager.settings['active_library'] = 'secondary'

    resolved = ensure_library_root_exists('secondary')
    assert Path(resolved) == tmp_path / 'secondary'
    assert (tmp_path / 'secondary').is_dir()


def test_iter_library_roots_returns_all_configured(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    settings_manager.settings['libraries'] = {'default': {}, 'alt': {}}
    settings_manager.settings['active_library'] = 'alt'

    roots = dict(iter_library_roots())
    assert roots['default'] == str(tmp_path / 'default')
    assert roots['alt'] == str(tmp_path / 'alt')


def test_is_valid_example_images_root_accepts_hash_directories(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    # Ensure single-library mode (not multi-library mode)
    settings_manager.settings['libraries'] = {'default': {}}
    settings_manager.settings['active_library'] = 'default'
    
    hash_folder = tmp_path / ('d' * 64)
    hash_folder.mkdir()
    (hash_folder / 'image.png').write_text('data', encoding='utf-8')

    assert is_valid_example_images_root(str(tmp_path)) is True

    invalid_folder = tmp_path / 'not_hash'
    invalid_folder.mkdir()
    # Add a non-hash file to make it clearly invalid
    (invalid_folder / 'invalid.txt').write_text('invalid', encoding='utf-8')
    assert is_valid_example_images_root(str(tmp_path)) is False


def test_is_valid_example_images_root_accepts_legacy_library_structure(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    # Simulate settings reset where libraries configuration is missing
    settings_manager.settings['libraries'] = {'default': {}}
    settings_manager.settings['active_library'] = 'default'

    legacy_library = tmp_path / 'My Library'
    legacy_library.mkdir()
    hash_folder = legacy_library / ('e' * 64)
    hash_folder.mkdir()
    (hash_folder / 'image.png').write_text('data', encoding='utf-8')

    assert is_valid_example_images_root(str(tmp_path)) is True
