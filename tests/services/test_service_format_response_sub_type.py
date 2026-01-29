"""Tests for service format_response sub_type inclusion."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from py.services.lora_service import LoraService
from py.services.checkpoint_service import CheckpointService
from py.services.embedding_service import EmbeddingService


class TestLoraServiceFormatResponse:
    """Test LoraService.format_response includes sub_type."""

    @pytest.fixture
    def mock_scanner(self):
        scanner = MagicMock()
        scanner._hash_index = MagicMock()
        return scanner

    @pytest.fixture
    def lora_service(self, mock_scanner):
        return LoraService(mock_scanner)

    @pytest.mark.asyncio
    async def test_format_response_includes_sub_type(self, lora_service):
        """format_response should include sub_type field."""
        lora_data = {
            "model_name": "Test LoRA",
            "file_name": "test_lora",
            "preview_url": "test.webp",
            "preview_nsfw_level": 0,
            "base_model": "SDXL",
            "folder": "",
            "sha256": "abc123",
            "file_path": "/models/test_lora.safetensors",
            "size": 1000,
            "modified": 1234567890.0,
            "tags": [],
            "from_civitai": True,
            "usage_count": 0,
            "usage_tips": "",
            "notes": "",
            "favorite": False,
            "sub_type": "locon",
            "civitai": {},
        }
        
        result = await lora_service.format_response(lora_data)
        
        assert "sub_type" in result
        assert result["sub_type"] == "locon"
        assert "model_type" not in result  # Removed in refactoring

    @pytest.mark.asyncio
    async def test_format_response_defaults_to_lora(self, lora_service):
        """format_response should default to 'lora' if no type field."""
        lora_data = {
            "model_name": "Test LoRA",
            "file_name": "test_lora",
            "preview_url": "test.webp",
            "preview_nsfw_level": 0,
            "base_model": "SDXL",
            "folder": "",
            "sha256": "abc123",
            "file_path": "/models/test_lora.safetensors",
            "size": 1000,
            "modified": 1234567890.0,
            "tags": [],
            "from_civitai": True,
            "civitai": {},
        }
        
        result = await lora_service.format_response(lora_data)
        
        assert result["sub_type"] == "lora"
        assert "model_type" not in result  # Removed in refactoring


class TestCheckpointServiceFormatResponse:
    """Test CheckpointService.format_response includes sub_type."""

    @pytest.fixture
    def mock_scanner(self):
        scanner = MagicMock()
        scanner._hash_index = MagicMock()
        return scanner

    @pytest.fixture
    def checkpoint_service(self, mock_scanner):
        return CheckpointService(mock_scanner)

    @pytest.mark.asyncio
    async def test_format_response_includes_sub_type_checkpoint(self, checkpoint_service):
        """format_response should include sub_type field for checkpoint."""
        checkpoint_data = {
            "model_name": "Test Checkpoint",
            "file_name": "test_ckpt",
            "preview_url": "test.webp",
            "preview_nsfw_level": 0,
            "base_model": "SDXL",
            "folder": "",
            "sha256": "abc123",
            "file_path": "/models/test.safetensors",
            "size": 1000,
            "modified": 1234567890.0,
            "tags": [],
            "from_civitai": True,
            "sub_type": "checkpoint",
            "civitai": {},
        }
        
        result = await checkpoint_service.format_response(checkpoint_data)
        
        assert "sub_type" in result
        assert result["sub_type"] == "checkpoint"
        assert "model_type" not in result  # Removed in refactoring

    @pytest.mark.asyncio
    async def test_format_response_includes_sub_type_diffusion_model(self, checkpoint_service):
        """format_response should include sub_type field for diffusion_model."""
        checkpoint_data = {
            "model_name": "Test Diffusion Model",
            "file_name": "test_unet",
            "preview_url": "test.webp",
            "preview_nsfw_level": 0,
            "base_model": "SDXL",
            "folder": "",
            "sha256": "abc123",
            "file_path": "/models/test.safetensors",
            "size": 1000,
            "modified": 1234567890.0,
            "tags": [],
            "from_civitai": True,
            "sub_type": "diffusion_model",
            "civitai": {},
        }
        
        result = await checkpoint_service.format_response(checkpoint_data)
        
        assert result["sub_type"] == "diffusion_model"
        assert "model_type" not in result  # Removed in refactoring


class TestEmbeddingServiceFormatResponse:
    """Test EmbeddingService.format_response includes sub_type."""

    @pytest.fixture
    def mock_scanner(self):
        scanner = MagicMock()
        scanner._hash_index = MagicMock()
        return scanner

    @pytest.fixture
    def embedding_service(self, mock_scanner):
        return EmbeddingService(mock_scanner)

    @pytest.mark.asyncio
    async def test_format_response_includes_sub_type(self, embedding_service):
        """format_response should include sub_type field."""
        embedding_data = {
            "model_name": "Test Embedding",
            "file_name": "test_emb",
            "preview_url": "test.webp",
            "preview_nsfw_level": 0,
            "base_model": "SD1.5",
            "folder": "",
            "sha256": "abc123",
            "file_path": "/models/test.pt",
            "size": 1000,
            "modified": 1234567890.0,
            "tags": [],
            "from_civitai": True,
            "sub_type": "embedding",
            "civitai": {},
        }
        
        result = await embedding_service.format_response(embedding_data)
        
        assert "sub_type" in result
        assert result["sub_type"] == "embedding"
        assert "model_type" not in result  # Removed in refactoring

    @pytest.mark.asyncio
    async def test_format_response_defaults_to_embedding(self, embedding_service):
        """format_response should default to 'embedding' if no type field."""
        embedding_data = {
            "model_name": "Test Embedding",
            "file_name": "test_emb",
            "preview_url": "test.webp",
            "preview_nsfw_level": 0,
            "base_model": "SD1.5",
            "folder": "",
            "sha256": "abc123",
            "file_path": "/models/test.pt",
            "size": 1000,
            "modified": 1234567890.0,
            "tags": [],
            "from_civitai": True,
            "civitai": {},
        }
        
        result = await embedding_service.format_response(embedding_data)
        
        assert result["sub_type"] == "embedding"
        assert "model_type" not in result  # Removed in refactoring
