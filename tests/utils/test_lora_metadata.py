import pytest

from py.utils import lora_metadata


class DummySafeOpen:
    def __init__(self, metadata):
        self._metadata = metadata

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def metadata(self):
        return self._metadata


@pytest.mark.asyncio
async def test_extract_lora_metadata_returns_base_model(monkeypatch, tmp_path):
    file_path = tmp_path / "model.safetensors"
    file_path.write_bytes(b"")

    monkeypatch.setattr(
        lora_metadata,
        "safe_open",
        lambda *args, **kwargs: DummySafeOpen({"ss_base_model_version": "sdxl"}),
    )

    metadata = await lora_metadata.extract_lora_metadata(str(file_path))

    assert metadata == {"base_model": "SDXL 1.0"}


@pytest.mark.asyncio
async def test_extract_lora_metadata_handles_errors(monkeypatch):
    def raising_safe_open(*_, **__):
        raise RuntimeError("boom")

    monkeypatch.setattr(lora_metadata, "safe_open", raising_safe_open)

    metadata = await lora_metadata.extract_lora_metadata("missing.safetensors")

    assert metadata == {"base_model": "Unknown"}
