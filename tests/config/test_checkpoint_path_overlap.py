"""Tests for checkpoint path overlap detection."""

import logging
import os

import pytest

from py import config as config_module


def _normalize(path: str) -> str:
    return os.path.normpath(path).replace(os.sep, "/")


class TestCheckpointPathOverlap:
    """Test detection of overlapping paths between checkpoints and unet."""

    def test_overlapping_paths_prioritizes_checkpoints(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
    ):
        """Test that overlapping paths prioritize checkpoints for backward compatibility."""
        # Create a shared physical folder
        shared_dir = tmp_path / "shared_models"
        shared_dir.mkdir()

        # Create two symlinks pointing to the same physical folder
        checkpoints_link = tmp_path / "checkpoints"
        unet_link = tmp_path / "unet"
        checkpoints_link.symlink_to(shared_dir, target_is_directory=True)
        unet_link.symlink_to(shared_dir, target_is_directory=True)

        # Create Config instance with overlapping paths
        with caplog.at_level(logging.WARNING, logger=config_module.logger.name):
            config = config_module.Config.__new__(config_module.Config)
            config._path_mappings = {}
            config._preview_root_paths = set()
            config._cached_fingerprint = None

            # Call the method under test
            result = config._prepare_checkpoint_paths(
                [str(checkpoints_link)], [str(unet_link)]
            )

        # Verify warning was logged
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING"
            and "overlapping paths" in record.message.lower()
        ]
        assert len(warning_messages) == 1
        assert "checkpoints" in warning_messages[0].lower()
        assert "diffusion_models" in warning_messages[0].lower() or "unet" in warning_messages[0].lower()
        # Verify warning mentions backward compatibility fallback
        assert "falling back" in warning_messages[0].lower() or "backward compatibility" in warning_messages[0].lower()

        # Verify only one path is returned (deduplication still works)
        assert len(result) == 1
        # Prioritizes checkpoints path for backward compatibility
        assert _normalize(result[0]) == _normalize(str(checkpoints_link))

        # Verify checkpoints_roots has the path (prioritized)
        assert len(config.checkpoints_roots) == 1
        assert _normalize(config.checkpoints_roots[0]) == _normalize(str(checkpoints_link))

        # Verify unet_roots is empty (overlapping paths removed)
        assert config.unet_roots == []

    def test_non_overlapping_paths_no_warning(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
    ):
        """Test that non-overlapping paths do not trigger a warning."""
        # Create separate physical folders
        checkpoints_dir = tmp_path / "checkpoints"
        checkpoints_dir.mkdir()
        unet_dir = tmp_path / "unet"
        unet_dir.mkdir()

        # Create Config instance with separate paths
        with caplog.at_level(logging.WARNING, logger=config_module.logger.name):
            config = config_module.Config.__new__(config_module.Config)
            config._path_mappings = {}
            config._preview_root_paths = set()
            config._cached_fingerprint = None

            result = config._prepare_checkpoint_paths(
                [str(checkpoints_dir)], [str(unet_dir)]
            )

        # Verify no overlapping paths warning was logged
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING"
            and "overlapping paths" in record.message.lower()
        ]
        assert len(warning_messages) == 0

        # Verify both paths are returned
        assert len(result) == 2
        normalized_result = [_normalize(p) for p in result]
        assert _normalize(str(checkpoints_dir)) in normalized_result
        assert _normalize(str(unet_dir)) in normalized_result

        # Verify both roots are properly set
        assert len(config.checkpoints_roots) == 1
        assert len(config.unet_roots) == 1

    def test_partial_overlap_prioritizes_checkpoints(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
    ):
        """Test partial overlap - overlapping paths prioritize checkpoints."""
        # Create folders
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()
        separate_checkpoint = tmp_path / "separate_ckpt"
        separate_checkpoint.mkdir()
        separate_unet = tmp_path / "separate_unet"
        separate_unet.mkdir()

        # Create symlinks - one shared, others separate
        shared_link = tmp_path / "shared_link"
        shared_link.symlink_to(shared_dir, target_is_directory=True)

        with caplog.at_level(logging.WARNING, logger=config_module.logger.name):
            config = config_module.Config.__new__(config_module.Config)
            config._path_mappings = {}
            config._preview_root_paths = set()
            config._cached_fingerprint = None

            # One checkpoint path overlaps with one unet path
            result = config._prepare_checkpoint_paths(
                [str(shared_link), str(separate_checkpoint)],
                [str(shared_link), str(separate_unet)]
            )

        # Verify warning was logged for the overlapping path
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING"
            and "overlapping paths" in record.message.lower()
        ]
        assert len(warning_messages) == 1

        # Verify 3 unique paths (shared counted once as checkpoint, plus separate ones)
        assert len(result) == 3

        # Verify the overlapping path appears in warning message
        assert str(shared_link.name) in warning_messages[0] or str(shared_dir.name) in warning_messages[0]

        # Verify checkpoints_roots includes both checkpoint paths (including the shared one)
        assert len(config.checkpoints_roots) == 2
        checkpoint_normalized = [_normalize(p) for p in config.checkpoints_roots]
        assert _normalize(str(shared_link)) in checkpoint_normalized
        assert _normalize(str(separate_checkpoint)) in checkpoint_normalized

        # Verify unet_roots only includes the non-overlapping unet path
        assert len(config.unet_roots) == 1
        assert _normalize(config.unet_roots[0]) == _normalize(str(separate_unet))
