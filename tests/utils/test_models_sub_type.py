"""Tests for model sub_type field refactoring."""

import pytest
from py.utils.models import (
    BaseModelMetadata,
    LoraMetadata,
    CheckpointMetadata,
    EmbeddingMetadata,
)


class TestCheckpointMetadataSubType:
    """Test CheckpointMetadata uses sub_type field."""

    def test_checkpoint_has_sub_type_field(self):
        """CheckpointMetadata should have sub_type field."""
        metadata = CheckpointMetadata(
            file_name="test",
            model_name="Test Model",
            file_path="/test/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
        )
        assert hasattr(metadata, "sub_type")
        assert metadata.sub_type == "checkpoint"

    def test_checkpoint_sub_type_can_be_diffusion_model(self):
        """CheckpointMetadata sub_type can be set to diffusion_model."""
        metadata = CheckpointMetadata(
            file_name="test",
            model_name="Test Model",
            file_path="/test/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
            sub_type="diffusion_model",
        )
        assert metadata.sub_type == "diffusion_model"

    def test_checkpoint_from_civitai_info_uses_sub_type(self):
        """from_civitai_info should use sub_type from version_info."""
        version_info = {
            "baseModel": "SDXL",
            "model": {"name": "Test", "description": "", "tags": []},
            "files": [{"name": "model.safetensors", "sizeKB": 1000, "hashes": {"SHA256": "abc123"}, "primary": True}],
        }
        file_info = version_info["files"][0]
        save_path = "/test/model.safetensors"
        
        metadata = CheckpointMetadata.from_civitai_info(version_info, file_info, save_path)
        
        assert hasattr(metadata, "sub_type")
        # When type is missing from version_info, defaults to "checkpoint"
        assert metadata.sub_type == "checkpoint"


class TestEmbeddingMetadataSubType:
    """Test EmbeddingMetadata uses sub_type field."""

    def test_embedding_has_sub_type_field(self):
        """EmbeddingMetadata should have sub_type field."""
        metadata = EmbeddingMetadata(
            file_name="test",
            model_name="Test Model",
            file_path="/test/model.pt",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SD1.5",
            preview_url="",
        )
        assert hasattr(metadata, "sub_type")
        assert metadata.sub_type == "embedding"

    def test_embedding_from_civitai_info_uses_sub_type(self):
        """from_civitai_info should use sub_type from version_info."""
        version_info = {
            "baseModel": "SD1.5",
            "model": {"name": "Test", "description": "", "tags": []},
            "files": [{"name": "model.pt", "sizeKB": 1000, "hashes": {"SHA256": "abc123"}, "primary": True}],
        }
        file_info = version_info["files"][0]
        save_path = "/test/model.pt"
        
        metadata = EmbeddingMetadata.from_civitai_info(version_info, file_info, save_path)
        
        assert hasattr(metadata, "sub_type")
        assert metadata.sub_type == "embedding"


class TestLoraMetadataConsistency:
    """Test LoraMetadata consistency (no sub_type field, uses civitai data)."""

    def test_lora_does_not_have_sub_type_field(self):
        """LoraMetadata should not have sub_type field (uses civitai.model.type)."""
        metadata = LoraMetadata(
            file_name="test",
            model_name="Test Model",
            file_path="/test/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
        )
        # Lora doesn't have sub_type field - it uses civitai data
        assert not hasattr(metadata, "sub_type")

    def test_lora_from_civitai_info_extracts_type(self):
        """from_civitai_info should extract type from civitai data."""
        version_info = {
            "baseModel": "SDXL",
            "model": {"name": "Test", "description": "", "tags": [], "type": "Lora"},
            "files": [{"name": "model.safetensors", "sizeKB": 1000, "hashes": {"SHA256": "abc123"}, "primary": True}],
        }
        file_info = version_info["files"][0]
        save_path = "/test/model.safetensors"
        
        metadata = LoraMetadata.from_civitai_info(version_info, file_info, save_path)
        
        # Type is stored in civitai dict
        assert metadata.civitai.get("model", {}).get("type") == "Lora"
