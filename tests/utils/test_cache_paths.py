"""Unit tests for the cache_paths module."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from py.utils.cache_paths import (
    CacheType,
    cleanup_legacy_cache_files,
    get_cache_base_dir,
    get_cache_file_path,
    get_legacy_cache_files_for_cleanup,
    get_legacy_cache_paths,
    resolve_cache_path_with_migration,
)


class TestCacheType:
    """Tests for the CacheType enum."""

    def test_enum_values(self):
        assert CacheType.MODEL.value == "model"
        assert CacheType.RECIPE.value == "recipe"
        assert CacheType.RECIPE_FTS.value == "recipe_fts"
        assert CacheType.TAG_FTS.value == "tag_fts"
        assert CacheType.SYMLINK.value == "symlink"


class TestGetCacheBaseDir:
    """Tests for get_cache_base_dir function."""

    def test_returns_cache_subdirectory(self):
        cache_dir = get_cache_base_dir(create=True)
        assert cache_dir.endswith("cache")
        assert os.path.isdir(cache_dir)

    def test_creates_directory_when_requested(self, tmp_path, monkeypatch):
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
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.RECIPE, "default", create_dir=True)
        expected = settings_dir / "cache" / "recipe" / "default.sqlite"
        assert path == str(expected)

    def test_recipe_fts_path(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.RECIPE_FTS, create_dir=True)
        expected = settings_dir / "cache" / "fts" / "recipe_fts.sqlite"
        assert path == str(expected)

    def test_tag_fts_path(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.TAG_FTS, create_dir=True)
        expected = settings_dir / "cache" / "fts" / "tag_fts.sqlite"
        assert path == str(expected)

    def test_symlink_path(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.SYMLINK, create_dir=True)
        expected = settings_dir / "cache" / "symlink" / "symlink_map.json"
        assert path == str(expected)

    def test_sanitizes_library_name(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.MODEL, "my/bad:name", create_dir=True)
        assert "my_bad_name" in path

    def test_none_library_name_defaults_to_default(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = get_cache_file_path(CacheType.MODEL, None, create_dir=True)
        assert "default.sqlite" in path


class TestGetLegacyCachePaths:
    """Tests for get_legacy_cache_paths function."""

    def test_model_legacy_paths_for_default(self, tmp_path, monkeypatch):
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
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.MODEL, "my_library")
        assert len(paths) == 1
        assert str(settings_dir / "model_cache" / "my_library.sqlite") in paths

    def test_recipe_legacy_paths(self, tmp_path, monkeypatch):
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
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.RECIPE_FTS)
        assert len(paths) == 1
        assert str(settings_dir / "recipe_fts.sqlite") in paths

    def test_tag_fts_legacy_path(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.TAG_FTS)
        assert len(paths) == 1
        assert str(settings_dir / "tag_fts.sqlite") in paths

    def test_symlink_legacy_path(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        paths = get_legacy_cache_paths(CacheType.SYMLINK)
        assert len(paths) == 1
        assert str(settings_dir / "cache" / "symlink_map.json") in paths


class TestResolveCachePathWithMigration:
    """Tests for resolve_cache_path_with_migration function."""

    def test_returns_env_override_when_set(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        override_path = "/custom/path/cache.sqlite"
        path = resolve_cache_path_with_migration(
            CacheType.MODEL,
            library_name="default",
            env_override=override_path,
        )
        assert path == override_path

    def test_returns_canonical_path_when_exists(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Create the canonical path
        canonical = settings_dir / "cache" / "model" / "default.sqlite"
        canonical.parent.mkdir(parents=True)
        canonical.write_text("existing")

        path = resolve_cache_path_with_migration(CacheType.MODEL, "default")
        assert path == str(canonical)

    def test_migrates_from_legacy_root_level_cache(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Create legacy cache at root level
        legacy_path = settings_dir / "model_cache.sqlite"
        legacy_path.write_text("legacy data")

        path = resolve_cache_path_with_migration(CacheType.MODEL, "default")

        # Should return canonical path
        canonical = settings_dir / "cache" / "model" / "default.sqlite"
        assert path == str(canonical)

        # File should be copied to canonical location
        assert canonical.exists()
        assert canonical.read_text() == "legacy data"

        # Legacy file should be automatically cleaned up
        assert not legacy_path.exists()

    def test_migrates_from_legacy_per_library_cache(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Create legacy per-library cache
        legacy_dir = settings_dir / "model_cache"
        legacy_dir.mkdir()
        legacy_path = legacy_dir / "my_library.sqlite"
        legacy_path.write_text("legacy library data")

        path = resolve_cache_path_with_migration(CacheType.MODEL, "my_library")

        # Should return canonical path
        canonical = settings_dir / "cache" / "model" / "my_library.sqlite"
        assert path == str(canonical)
        assert canonical.exists()
        assert canonical.read_text() == "legacy library data"

        # Legacy file should be automatically cleaned up
        assert not legacy_path.exists()

        # Empty legacy directory should be cleaned up
        assert not legacy_dir.exists()

    def test_prefers_per_library_over_root_for_migration(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Create both legacy caches
        legacy_root = settings_dir / "model_cache.sqlite"
        legacy_root.write_text("root legacy")

        legacy_dir = settings_dir / "model_cache"
        legacy_dir.mkdir()
        legacy_lib = legacy_dir / "default.sqlite"
        legacy_lib.write_text("library legacy")

        path = resolve_cache_path_with_migration(CacheType.MODEL, "default")

        canonical = settings_dir / "cache" / "model" / "default.sqlite"
        assert path == str(canonical)
        # Should migrate from per-library path (first in legacy list)
        assert canonical.read_text() == "library legacy"

    def test_returns_canonical_path_when_no_legacy_exists(self, tmp_path, monkeypatch):
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        path = resolve_cache_path_with_migration(CacheType.MODEL, "new_library")

        canonical = settings_dir / "cache" / "model" / "new_library.sqlite"
        assert path == str(canonical)
        # Directory should be created
        assert canonical.parent.exists()
        # But file should not exist yet
        assert not canonical.exists()


class TestLegacyCacheCleanup:
    """Tests for legacy cache cleanup functions."""

    def test_get_legacy_cache_files_for_cleanup(self, tmp_path, monkeypatch):
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


class TestAutomaticCleanup:
    """Tests for automatic cleanup during migration."""

    def test_automatic_cleanup_on_migration(self, tmp_path, monkeypatch):
        """Test that legacy files are automatically cleaned up after migration."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Create a legacy cache file
        legacy_dir = settings_dir / "model_cache"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / "default.sqlite"
        legacy_file.write_text("test data")

        # Verify legacy file exists
        assert legacy_file.exists()

        # Trigger migration (this should auto-cleanup)
        resolved_path = resolve_cache_path_with_migration(CacheType.MODEL, "default")

        # Verify canonical file exists
        canonical_path = settings_dir / "cache" / "model" / "default.sqlite"
        assert resolved_path == str(canonical_path)
        assert canonical_path.exists()
        assert canonical_path.read_text() == "test data"

        # Verify legacy file was cleaned up
        assert not legacy_file.exists()

        # Verify empty directory was cleaned up
        assert not legacy_dir.exists()

    def test_automatic_cleanup_with_verification(self, tmp_path, monkeypatch):
        """Test that cleanup verifies file integrity before deletion."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Create legacy cache
        legacy_dir = settings_dir / "recipe_cache"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / "my_library.sqlite"
        legacy_file.write_text("data")

        # Trigger migration
        resolved_path = resolve_cache_path_with_migration(CacheType.RECIPE, "my_library")
        canonical_path = settings_dir / "cache" / "recipe" / "my_library.sqlite"

        # Both should exist initially (migration successful)
        assert canonical_path.exists()
        assert legacy_file.exists() is False  # Auto-cleanup removes it

        # File content should match (integrity check)
        assert canonical_path.read_text() == "data"

        # Directory should be cleaned up
        assert not legacy_dir.exists()

    def test_automatic_cleanup_multiple_cache_types(self, tmp_path, monkeypatch):
        """Test automatic cleanup for different cache types."""
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()

        def fake_get_settings_dir(create: bool = True) -> str:
            return str(settings_dir)

        monkeypatch.setattr("py.utils.cache_paths.get_settings_dir", fake_get_settings_dir)

        # Test RECIPE_FTS migration
        legacy_fts = settings_dir / "recipe_fts.sqlite"
        legacy_fts.write_text("fts data")
        resolve_cache_path_with_migration(CacheType.RECIPE_FTS)
        canonical_fts = settings_dir / "cache" / "fts" / "recipe_fts.sqlite"

        assert canonical_fts.exists()
        assert not legacy_fts.exists()

        # Test TAG_FTS migration
        legacy_tag = settings_dir / "tag_fts.sqlite"
        legacy_tag.write_text("tag data")
        resolve_cache_path_with_migration(CacheType.TAG_FTS)
        canonical_tag = settings_dir / "cache" / "fts" / "tag_fts.sqlite"

        assert canonical_tag.exists()
        assert not legacy_tag.exists()
