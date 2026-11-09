from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils.example_images_paths import (
    ensure_library_root_exists,
    find_non_compliant_items_in_example_images_root,
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


def test_get_model_folder_ignores_legacy_library_name(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    settings_manager.settings['libraries'] = {'default': {}}
    settings_manager.settings['active_library'] = 'default'

    model_hash = 'b' * 64

    folder = get_model_folder(model_hash, 'Alt Library')
    relative = get_model_relative_path(model_hash, 'Alt Library')

    assert Path(folder) == tmp_path / model_hash
    assert relative == model_hash


def test_ensure_library_root_exists_creates_root(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path / 'examples')
    settings_manager.settings['libraries'] = {'default': {}}
    settings_manager.settings['active_library'] = 'default'

    resolved = ensure_library_root_exists('secondary')
    assert Path(resolved) == tmp_path / 'examples'
    assert (tmp_path / 'examples').is_dir()


def test_iter_library_roots_returns_single_root(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    settings_manager.settings['libraries'] = {'default': {}}
    settings_manager.settings['active_library'] = 'default'

    assert list(iter_library_roots()) == [('default', str(tmp_path))]


def test_is_valid_example_images_root_accepts_hash_directories(tmp_path, settings_manager):
    settings_manager.settings['example_images_path'] = str(tmp_path)
    # Use the single-library storage layout.
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


def test_find_non_compliant_items_returns_empty_for_valid_root(tmp_path, settings_manager):
    """An empty folder or one with only hash dirs should return []."""
    settings_manager.settings['example_images_path'] = str(tmp_path)

    # Empty folder
    assert find_non_compliant_items_in_example_images_root(str(tmp_path)) == []

    # Only hash folders
    hash_folder = tmp_path / ('f' * 64)
    hash_folder.mkdir()
    (hash_folder / 'image.png').write_text('data', encoding='utf-8')
    assert find_non_compliant_items_in_example_images_root(str(tmp_path)) == []


def test_find_non_compliant_items_returns_offending_names(tmp_path, settings_manager):
    """A folder with non-hash items should return their names."""
    settings_manager.settings['example_images_path'] = str(tmp_path)

    # Create a valid hash folder so the root is otherwise acceptable
    hash_folder = tmp_path / ('a' * 64)
    hash_folder.mkdir()

    # Add an offending file
    (tmp_path / 'readme.txt').write_text('hello', encoding='utf-8')
    assert find_non_compliant_items_in_example_images_root(str(tmp_path)) == ['readme.txt']

    # Add an offending directory with content (empty dirs are accepted as
    # potential legacy library folders by _library_folder_has_only_hash_dirs)
    offending_dir = tmp_path / 'not_a_hash'
    offending_dir.mkdir()
    (offending_dir / 'some_file.txt').write_text('data', encoding='utf-8')
    items = find_non_compliant_items_in_example_images_root(str(tmp_path))
    assert 'readme.txt' in items
    assert 'not_a_hash' in items


def test_find_non_compliant_items_ignores_hidden_files(tmp_path, settings_manager):
    """Hidden/system files should not appear in offending list."""
    settings_manager.settings['example_images_path'] = str(tmp_path)

    # .DS_Store is an allowed file
    (tmp_path / '.DS_Store').write_text('', encoding='utf-8')
    assert find_non_compliant_items_in_example_images_root(str(tmp_path)) == []

    # Thumbs.db too
    (tmp_path / 'Thumbs.db').write_text('', encoding='utf-8')
    assert find_non_compliant_items_in_example_images_root(str(tmp_path)) == []


def test_find_non_compliant_items_accepts_download_progress_json(tmp_path, settings_manager):
    """.download_progress.json should be recognised as a valid metadata file."""
    settings_manager.settings['example_images_path'] = str(tmp_path)

    (tmp_path / '.download_progress.json').write_text('{}', encoding='utf-8')
    assert find_non_compliant_items_in_example_images_root(str(tmp_path)) == []


def test_find_non_compliant_items_reports_directory_error(tmp_path):
    """When the directory cannot be listed, return an explanatory message."""
    non_existent = tmp_path / 'does-not-exist'
    result = find_non_compliant_items_in_example_images_root(str(non_existent))
    assert len(result) == 1
    assert 'cannot list directory' in result[0]
