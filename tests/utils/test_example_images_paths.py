from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from py.services.settings_manager import settings
from py.utils.example_images_paths import get_model_folder, get_model_relative_path


@pytest.fixture(autouse=True)
def restore_settings():
    original = copy.deepcopy(settings.settings)
    try:
        yield
    finally:
        settings.settings.clear()
        settings.settings.update(original)


def test_get_model_folder_single_library(tmp_path):
    settings.settings['example_images_path'] = str(tmp_path)
    settings.settings['libraries'] = {'default': {}}
    settings.settings['active_library'] = 'default'

    model_hash = 'a' * 64
    folder = get_model_folder(model_hash)
    relative = get_model_relative_path(model_hash)

    assert Path(folder) == tmp_path / model_hash
    assert relative == model_hash


def test_get_model_folder_multi_library(tmp_path):
    settings.settings['example_images_path'] = str(tmp_path)
    settings.settings['libraries'] = {
        'default': {},
        'Alt Library': {},
    }
    settings.settings['active_library'] = 'Alt Library'

    model_hash = 'b' * 64
    expected_folder = tmp_path / 'Alt_Library' / model_hash

    folder = get_model_folder(model_hash)
    relative = get_model_relative_path(model_hash)

    assert Path(folder) == expected_folder
    assert relative == os.path.join('Alt_Library', model_hash).replace('\\', '/')


def test_get_model_folder_migrates_legacy_structure(tmp_path):
    settings.settings['example_images_path'] = str(tmp_path)
    settings.settings['libraries'] = {
        'default': {},
        'extra': {},
    }
    settings.settings['active_library'] = 'extra'

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
