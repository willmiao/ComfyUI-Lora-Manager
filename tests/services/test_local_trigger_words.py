from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from py.services.lora_service import LoraService
from py.services.checkpoint_service import CheckpointService
from py.services.embedding_service import EmbeddingService


@pytest.mark.asyncio
@pytest.mark.parametrize("service_class", [LoraService, CheckpointService, EmbeddingService])
async def test_catalog_response_exposes_local_trigger_words(service_class) -> None:
    scanner = SimpleNamespace()
    service = service_class(scanner)
    response = await service.format_response({
        "file_path": "/models/local.safetensors", "file_name": "local", "model_name": "Local",
        "trainedWords": ["subject1"], "from_civitai": False, "civitai": {},
    })
    assert response["trainedWords"] == ["subject1"]
    assert not response["civitai"]


@pytest.mark.asyncio
async def test_trigger_lookup_prefers_local_words_and_keeps_legacy_fallback() -> None:
    item = {"file_name": "local", "trainedWords": ["subject1"], "civitai": {"trainedWords": ["legacy"]}}
    scanner = SimpleNamespace(get_cached_data=AsyncMock(return_value=SimpleNamespace(raw_data=[item])))
    service = LoraService(scanner)
    assert await service.get_lora_trigger_words("local") == ["subject1"]
    item["trainedWords"] = []
    assert await service.get_lora_trigger_words("local") == ["legacy"]
