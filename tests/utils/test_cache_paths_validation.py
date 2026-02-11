"""Cache path validation tests."""

import os
from pathlib import Path

import pytest

from py.utils.cache_paths import (
    CacheType,
    get_legacy_cache_paths,
    get_legacy_cache_files_for_cleanup,
    cleanup_legacy_cache_files,
)


class TestGetLegacyCachePaths:
    """Tests for get_legacy_cache_paths function."""

    def test_model_legacy_paths_for_default(self, tmp_path, monkeypatch):
        """Test legacy paths for default model cache."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.MODEL, "default")
        assert len(paths) == 2
        assert str(settings_dir / "model_cache" / "default.sqlite") in paths
        assert str(settings_dir / "model_cache.sqlite") in paths

    def test_model_legacy_paths_for_named_library(self, tmp_path, monkeypatch):
        """Test legacy paths for named model library."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.MODEL, "my_library")
        assert len(paths) == 1
        assert str(settings_dir / "model_cache" / "my_library.sqlite") in paths

    def test_recipe_legacy_paths(self, tmp_path, monkeypatch):
        """Test legacy paths for recipe cache."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.RECIPE, "default")
        assert len(paths) == 2
        assert str(settings_dir / "recipe_cache" / "default.sqlite") in paths
        assert str(settings_dir / "recipe_cache.sqlite") in paths

    def test_recipe_fts_legacy_path(self, tmp_path, monkeypatch):
        """Test legacy path for recipe FTS cache."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.RECIPE_FTS)
        assert len(paths) == 1
        assert str(settings_dir / "recipe_fts.sqlite") in paths

    def test_tag_fts_legacy_path(self, tmp_path, monkeypatch):
        """Test legacy path for tag FTS cache."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.TAG_FTS)
        assert len(paths) == 1
        assert str(settings_dir / "tag_fts.sqlite") in paths

    def test_symlink_legacy_path(self, tmp_path, monkeypatch):
        """Test legacy path for symlink cache."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.SYMLINK)
        assert len(paths) == 1
        assert str(settings_dir / "cache" / "symlink_map.json") in paths


class TestLegacyCacheCleanup:
    """Tests for legacy cache cleanup functions."""

    def test_get_legacy_cache_files_for_cleanup(self, tmp_path, monkeypatch):
        """Test detection of legacy cache files for cleanup."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Create canonical and legacy files
        canonical = settings_dir / "cache" / "model" / "default.sqlite"
        canonical.parent.mkdir(parents=True)
        canonical.write_text("canonical")

        legacy = settings_dir / "model_cache.sqlite"
        legacy.write_text("legacy")

        files = get_legacy_cache_files_for_cleanup()
        assert str(legacy) in files

    def test_cleanup_legacy_cache_files_dry_run(self, tmp_path, monkeypatch):
        """Test dry run cleanup does not delete files."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Create canonical and legacy files
        canonical = settings_dir / "cache" / "model" / "default.sqlite"
        canonical.parent.mkdir(parents=True)
        canonical.write_text("canonical")

        legacy = settings_dir / "model_cache.sqlite"
        legacy.write_text("legacy")

        removed = cleanup_legacy_cache_files(dry_run=True)
        assert str(legacy) in removed
        # File should still exist (dry run)
        assert legacy.exists()

    def test_cleanup_legacy_cache_files_actual(self, tmp_path, monkeypatch):
        """Test actual cleanup deletes legacy files."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Create canonical and legacy files
        canonical = settings_dir / "cache" / "model" / "default.sqlite"
        canonical.parent.mkdir(parents=True)
        canonical.write_text("canonical")

        legacy = settings_dir / "model_cache.sqlite"
        legacy.write_text("legacy")

        removed = cleanup_legacy_cache_files(dry_run=False)
        assert str(legacy) in removed
        # File should be deleted
        assert not legacy.exists()
