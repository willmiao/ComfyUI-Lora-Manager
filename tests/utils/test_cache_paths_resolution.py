"""Cache path resolution tests."""

import os
from pathlib import Path

import pytest

from py.utils.cache_paths import (
    CacheType,
    get_cache_base_dir,
    get_cache_file_path,
)


class TestCacheType:
    """Tests for the CacheType enum."""

    def test_enum_values(self):
        """Test that CacheType enum has correct values."""
        assert CacheType.MODEL.value == "model"
        assert CacheType.RECIPE.value == "recipe"
        assert CacheType.RECIPE_FTS.value == "recipe_fts"
        assert CacheType.TAG_FTS.value == "tag_fts"
        assert CacheType.SYMLINK.value == "symlink"


class TestGetCacheBaseDir:
    """Tests for get_cache_base_dir function."""

    def test_returns_cache_subdirectory(self):
        """Test that cache base dir ends with 'cache'."""
        cache_dir = get_cache_base_dir(create=True)
        assert cache_dir.endswith("cache")
        assert os.path.isdir(cache_dir)

    def test_creates_directory_when_requested(self, tmp_path, monkeypatch):
        """Test that directory is created when requested."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        cache_dir = get_cache_base_dir(create=True)
        assert os.path.isdir(cache_dir)
        assert cache_dir == str(settings_dir / "cache")


class TestGetCacheFilePath:
    """Tests for get_cache_file_path function."""

    def test_model_cache_path(self, tmp_path, monkeypatch):
        """Test model cache file path generation."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.MODEL, "my_library", create_dir=True)
        expected = settings_dir / "cache" / "model" / "my_library.sqlite"
        assert path == str(expected)
        assert os.path.isdir(expected.parent)

    def test_recipe_cache_path(self, tmp_path, monkeypatch):
        """Test recipe cache file path generation."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.RECIPE, "default", create_dir=True)
        expected = settings_dir / "cache" / "recipe" / "default.sqlite"
        assert path == str(expected)

    def test_recipe_fts_path(self, tmp_path, monkeypatch):
        """Test recipe FTS cache file path generation."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.RECIPE_FTS, create_dir=True)
        expected = settings_dir / "cache" / "fts" / "recipe_fts.sqlite"
        assert path == str(expected)

    def test_tag_fts_path(self, tmp_path, monkeypatch):
        """Test tag FTS cache file path generation."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.TAG_FTS, create_dir=True)
        expected = settings_dir / "cache" / "fts" / "tag_fts.sqlite"
        assert path == str(expected)

    def test_symlink_path(self, tmp_path, monkeypatch):
        """Test symlink cache file path generation."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.SYMLINK, create_dir=True)
        expected = settings_dir / "cache" / "symlink" / "symlink_map.json"
        assert path == str(expected)

    def test_sanitizes_library_name(self, tmp_path, monkeypatch):
        """Test that library names are sanitized in paths."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.MODEL, "my/bad:name", create_dir=True)
        assert "my_bad_name" in path

    def test_none_library_name_defaults_to_default(self, tmp_path, monkeypatch):
        """Test that None library name defaults to 'default'."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.MODEL, None, create_dir=True)
        assert "default.sqlite" in path
