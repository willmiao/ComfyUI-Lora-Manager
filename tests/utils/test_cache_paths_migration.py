"""Cache path migration tests."""

from pathlib import Path

import pytest

from py.utils.cache_paths import (
    CacheType,
    resolve_cache_path_with_migration,
)


class TestResolveCachePathWithMigration:
    """Tests for resolve_cache_path_with_migration function."""

    def test_returns_env_override_when_set(self, tmp_path, monkeypatch):
        """Test that env override takes precedence."""
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
        """Test that canonical path is returned when it exists."""
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
        """Test migration from root-level legacy cache."""
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
        """Test migration from per-library legacy cache."""
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
        """Test that per-library cache is preferred over root for migration."""
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
        """Test that canonical path is returned when no legacy exists."""
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
