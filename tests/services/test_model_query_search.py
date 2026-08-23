"""Tests for SearchStrategy hash-based exact matching and autov3 passthrough."""

from unittest.mock import MagicMock

import pytest

from py.services.checkpoint_service import CheckpointService
from py.services.embedding_service import EmbeddingService
from py.services.lora_service import LoraService
from py.services.model_query import SearchStrategy

SHA256 = "abcdef1234567890" + "f" * 48  # 64-char hex
AUTOV2 = SHA256[:10]
AUTOV3 = "0123456789ab"

HASH_ONLY_OPTIONS = {
    "filename": False,
    "modelname": False,
    "tags": False,
    "creator": False,
    "hash": True,
}

HASH_OFF_OPTIONS = {
    "filename": False,
    "modelname": False,
    "tags": False,
    "creator": False,
    "hash": False,
}


def make_item(**overrides):
    item = {
        "file_name": "model.safetensors",
        "model_name": "Some Model",
        "tags": [],
        "sha256": SHA256,
        "autov3": AUTOV3,
    }
    item.update(overrides)
    return item


@pytest.fixture
def strategy():
    return SearchStrategy()


class TestSearchStrategyHash:
    """Hash search matches exactly against sha256, autov2, and autov3."""

    def test_full_sha256_matches(self, strategy):
        items = [make_item(), make_item(file_name="other.safetensors", sha256="0" * 64)]
        result = strategy.apply(items, SHA256, HASH_ONLY_OPTIONS)
        assert [item["file_name"] for item in result] == ["model.safetensors"]

    def test_autov2_prefix_matches(self, strategy):
        result = strategy.apply([make_item()], AUTOV2, HASH_ONLY_OPTIONS)
        assert len(result) == 1

    def test_autov3_matches(self, strategy):
        result = strategy.apply([make_item()], AUTOV3, HASH_ONLY_OPTIONS)
        assert len(result) == 1

    def test_query_is_case_insensitive(self, strategy):
        result = strategy.apply([make_item()], SHA256.upper(), HASH_ONLY_OPTIONS)
        assert len(result) == 1
        result = strategy.apply([make_item()], AUTOV3.upper(), HASH_ONLY_OPTIONS)
        assert len(result) == 1

    def test_query_whitespace_is_stripped(self, strategy):
        result = strategy.apply([make_item()], f"  {AUTOV3}  ", HASH_ONLY_OPTIONS)
        assert len(result) == 1

    def test_partial_hash_does_not_match(self, strategy):
        # Exact semantics: a 5-char fragment is neither autov2 nor autov3
        result = strategy.apply([make_item()], SHA256[:5], HASH_ONLY_OPTIONS)
        assert result == []

    def test_autov3_none_is_skipped(self, strategy):
        item = make_item(autov3=None)
        assert strategy.apply([item], AUTOV3, HASH_ONLY_OPTIONS) == []
        # sha256 matching still works
        assert len(strategy.apply([item], SHA256, HASH_ONLY_OPTIONS)) == 1

    def test_autov3_empty_string_is_skipped(self, strategy):
        item = make_item(autov3="")
        assert strategy.apply([item], AUTOV3, HASH_ONLY_OPTIONS) == []

    def test_hash_option_disabled(self, strategy):
        assert strategy.apply([make_item()], SHA256, HASH_OFF_OPTIONS) == []
        assert strategy.apply([make_item()], AUTOV3, HASH_OFF_OPTIONS) == []

    def test_fuzzy_mode_still_exact(self, strategy):
        # Fuzzy matching must never apply to the hash field
        result = strategy.apply([make_item()], AUTOV3, HASH_ONLY_OPTIONS, fuzzy=True)
        assert len(result) == 1
        result = strategy.apply([make_item()], SHA256[:5], HASH_ONLY_OPTIONS, fuzzy=True)
        assert result == []

    def test_missing_sha256_does_not_match(self, strategy):
        item = make_item(sha256="", autov3=None)
        assert strategy.apply([item], SHA256, HASH_ONLY_OPTIONS) == []


class TestFormatResponseAutov3:
    """format_response should pass the autov3 field through unchanged."""

    @pytest.fixture
    def mock_scanner(self):
        scanner = MagicMock()
        scanner._hash_index = MagicMock()
        return scanner

    def make_model_data(self, autov3):
        return {
            "model_name": "Test Model",
            "file_name": "test_model",
            "base_model": "SDXL",
            "folder": "",
            "sha256": SHA256,
            "autov3": autov3,
            "file_path": "/models/test_model.safetensors",
            "size": 1000,
            "modified": 1234567890.0,
            "tags": [],
            "from_civitai": True,
            "civitai": {},
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("autov3", [AUTOV3, "", None])
    async def test_lora_format_response_autov3(self, mock_scanner, autov3):
        service = LoraService(mock_scanner)
        result = await service.format_response(self.make_model_data(autov3))
        assert result["autov3"] == autov3

    @pytest.mark.asyncio
    @pytest.mark.parametrize("autov3", [AUTOV3, "", None])
    async def test_checkpoint_format_response_autov3(self, mock_scanner, autov3):
        service = CheckpointService(mock_scanner)
        result = await service.format_response(self.make_model_data(autov3))
        assert result["autov3"] == autov3

    @pytest.mark.asyncio
    @pytest.mark.parametrize("autov3", [AUTOV3, "", None])
    async def test_embedding_format_response_autov3(self, mock_scanner, autov3):
        service = EmbeddingService(mock_scanner)
        result = await service.format_response(self.make_model_data(autov3))
        assert result["autov3"] == autov3

    @pytest.mark.asyncio
    async def test_autov3_defaults_to_none(self, mock_scanner):
        data = self.make_model_data(AUTOV3)
        del data["autov3"]
        result = await LoraService(mock_scanner).format_response(data)
        assert result["autov3"] is None
