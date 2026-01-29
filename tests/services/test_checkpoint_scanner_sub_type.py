"""Tests for CheckpointScanner sub_type resolution."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch

from py.services.checkpoint_scanner import CheckpointScanner
from py.utils.models import CheckpointMetadata


class TestCheckpointScannerSubType:
    """Test CheckpointScanner sub_type resolution logic."""

    def create_scanner(self):
        """Create scanner with no async initialization."""
        # Create scanner without calling __init__ to avoid async issues
        scanner = object.__new__(CheckpointScanner)
        scanner.model_type = "checkpoint"
        scanner.model_class = CheckpointMetadata
        scanner.file_extensions = {'.ckpt', '.safetensors'}
        scanner._hash_index = MagicMock()
        return scanner

    def test_resolve_sub_type_checkpoint_root(self):
        """_resolve_sub_type should return 'checkpoint' for checkpoints_roots."""
        scanner = self.create_scanner()
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        original_unet_roots = getattr(config_module.config, 'unet_roots', None)
        
        try:
            config_module.config.checkpoints_roots = ["/models/checkpoints"]
            config_module.config.unet_roots = ["/models/unet"]
            
            result = scanner._resolve_sub_type("/models/checkpoints")
            assert result == "checkpoint"
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots
            if original_unet_roots is not None:
                config_module.config.unet_roots = original_unet_roots

    def test_resolve_sub_type_unet_root(self):
        """_resolve_sub_type should return 'diffusion_model' for unet_roots."""
        scanner = self.create_scanner()
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        original_unet_roots = getattr(config_module.config, 'unet_roots', None)
        
        try:
            config_module.config.checkpoints_roots = ["/models/checkpoints"]
            config_module.config.unet_roots = ["/models/unet"]
            
            result = scanner._resolve_sub_type("/models/unet")
            assert result == "diffusion_model"
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots
            if original_unet_roots is not None:
                config_module.config.unet_roots = original_unet_roots

    def test_resolve_sub_type_none_root(self):
        """_resolve_sub_type should return None for None input."""
        scanner = self.create_scanner()
        result = scanner._resolve_sub_type(None)
        assert result is None

    def test_resolve_sub_type_unknown_root(self):
        """_resolve_sub_type should return None for unknown root."""
        scanner = self.create_scanner()
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        original_unet_roots = getattr(config_module.config, 'unet_roots', None)
        
        try:
            config_module.config.checkpoints_roots = ["/models/checkpoints"]
            config_module.config.unet_roots = ["/models/unet"]
            
            result = scanner._resolve_sub_type("/models/unknown")
            assert result is None
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots
            if original_unet_roots is not None:
                config_module.config.unet_roots = original_unet_roots

    def test_adjust_metadata_sets_sub_type(self):
        """adjust_metadata should set sub_type on metadata."""
        scanner = self.create_scanner()
        
        metadata = CheckpointMetadata(
            file_name="test",
            model_name="Test",
            file_path="/models/checkpoints/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
        )
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        
        try:
            config_module.config.checkpoints_roots = ["/models/checkpoints"]
            config_module.config.unet_roots = []
            
            result = scanner.adjust_metadata(metadata, "/models/checkpoints/model.safetensors", "/models/checkpoints")
            assert result.sub_type == "checkpoint"
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots

    def test_adjust_cached_entry_sets_sub_type(self):
        """adjust_cached_entry should set sub_type on entry."""
        scanner = self.create_scanner()
        # Mock get_model_roots to return the expected roots
        scanner.get_model_roots = lambda: ["/models/unet"]
        
        entry = {
            "file_path": "/models/unet/model.safetensors",
            "model_name": "Test",
        }
        
        from py import config as config_module
        original_checkpoints_roots = getattr(config_module.config, 'checkpoints_roots', None)
        original_unet_roots = getattr(config_module.config, 'unet_roots', None)
        
        try:
            config_module.config.checkpoints_roots = []
            config_module.config.unet_roots = ["/models/unet"]
            
            result = scanner.adjust_cached_entry(entry)
            assert result["sub_type"] == "diffusion_model"
            assert "model_type" not in result  # Removed in refactoring
        finally:
            if original_checkpoints_roots is not None:
                config_module.config.checkpoints_roots = original_checkpoints_roots
            if original_unet_roots is not None:
                config_module.config.unet_roots = original_unet_roots
