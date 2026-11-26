"""Tests for the quantization helpers in py.utils.models."""

from __future__ import annotations

import io
import struct
from pathlib import Path

from py.utils.models import (
    BaseModelMetadata,
    infer_quantization_source,
    quantization_from_civitai_files,
    resolve_quantization,
)


def _civitai(fp: str, sha: str = "abc123") -> dict:
    return {
        "files": [
            {
                "name": "model.safetensors",
                "hashes": {"SHA256": sha.upper()},
                "metadata": {"fp": fp},
            }
        ]
    }


def _write_gguf(path: Path, file_type: int) -> None:
    """Write a minimal GGUF file whose general.file_type is ``file_type``."""
    blob = io.BytesIO()
    blob.write(b"GGUF")
    blob.write(struct.pack("<I", 3))  # version
    blob.write(struct.pack("<Q", 0))  # tensor_count
    blob.write(struct.pack("<Q", 1))  # metadata_kv_count
    key = b"general.file_type"
    blob.write(struct.pack("<Q", len(key)))
    blob.write(key)
    blob.write(struct.pack("<I", 4))  # UINT32
    blob.write(struct.pack("<I", file_type))
    path.write_bytes(blob.getvalue())


class TestQuantizationFromCivitaiFiles:
    def test_maps_quantized_fp_values(self):
        assert quantization_from_civitai_files(_civitai("fp8"), "abc123") == "FP8"
        assert quantization_from_civitai_files(_civitai("nvfp4"), "abc123") == "NVFP4"
        assert quantization_from_civitai_files(_civitai("int8"), "abc123") == "INT8"

    def test_fp_value_matching_is_case_insensitive(self):
        assert quantization_from_civitai_files(_civitai("FP8"), "abc123") == "FP8"
        assert quantization_from_civitai_files(_civitai("NvFp4"), "abc123") == "NVFP4"

    def test_full_precision_fp_values_yield_none(self):
        for fp in ("fp16", "bf16", "fp32"):
            assert quantization_from_civitai_files(_civitai(fp), "abc123") is None

    def test_unknown_fp_values_yield_none(self):
        assert quantization_from_civitai_files(_civitai("fp4"), "abc123") is None
        assert quantization_from_civitai_files(_civitai(""), "abc123") is None

    def test_sha_must_match(self):
        assert quantization_from_civitai_files(_civitai("fp8"), "999999") is None

    def test_missing_metadata_or_fp_yields_none(self):
        civitai = {"files": [{"name": "m.safetensors", "hashes": {"SHA256": "ABC123"}}]}
        assert quantization_from_civitai_files(civitai, "abc123") is None
        assert quantization_from_civitai_files(None, "abc123") is None
        assert quantization_from_civitai_files(civitai, "") is None


class TestInferQuantizationSource:
    def test_explicit_source_wins(self):
        assert infer_quantization_source("FP8", "manual") == "manual"
        assert infer_quantization_source("FP8", "content") == "content"

    def test_no_value_passes_source_through(self):
        assert infer_quantization_source("", None) is None
        assert infer_quantization_source(None, None) is None

    def test_gguf_names_are_content_derived(self):
        # CivitAI never reports GGUF quantization names, so a legacy untagged
        # one is provably content-detected.
        assert infer_quantization_source("Q4_K_M", None) == "content"
        assert infer_quantization_source("IQ4_XS", None) == "content"

    def test_fp8_is_conservatively_civitai(self):
        # A legacy untagged FP8 may come from CivitAI's fp flag — keep it
        # eligible for recomputation so a mislabeled upload self-heals.
        assert infer_quantization_source("FP8", None) == "civitai"
        assert infer_quantization_source("NVFP4", None) == "civitai"


class TestResolveQuantization:
    def test_content_detection_wins_over_civitai(self, tmp_path: Path):
        gguf = tmp_path / "model.gguf"
        _write_gguf(gguf, 15)  # MOSTLY_Q4_K_M

        value, source = resolve_quantization(str(gguf), _civitai("fp8"), "abc123")

        assert (value, source) == ("Q4_K_M", "content")

    def test_civitai_fallback_when_content_inconclusive(self, tmp_path: Path):
        fake = tmp_path / "model.safetensors"
        fake.write_bytes(b"not a real safetensors header")

        value, source = resolve_quantization(str(fake), _civitai("nvfp4"), "abc123")

        assert (value, source) == ("NVFP4", "civitai")

    def test_no_value_anywhere(self, tmp_path: Path):
        fake = tmp_path / "model.safetensors"
        fake.write_bytes(b"not a real safetensors header")

        value, source = resolve_quantization(str(fake), _civitai("fp16"), "abc123")

        assert (value, source) == (None, None)

    def test_missing_file_path_skips_detection(self):
        value, source = resolve_quantization(None, _civitai("fp8"), "abc123")

        assert (value, source) == ("FP8", "civitai")


class TestQuantizationSourceSerialization:
    def _make_metadata(self, **overrides) -> BaseModelMetadata:
        data = {
            "file_name": "model",
            "model_name": "Model",
            "file_path": "/tmp/model.safetensors",
            "size": 0,
            "modified": 0.0,
            "sha256": "deadbeef",
            "base_model": "Unknown",
            "preview_url": "",
        }
        data.update(overrides)
        return BaseModelMetadata.from_dict(data)

    def test_roundtrip_preserves_source(self):
        metadata = self._make_metadata(
            quantization="NVFP4", quantization_source="manual"
        )

        payload = metadata.to_dict()

        assert payload["quantization"] == "NVFP4"
        assert payload["quantization_source"] == "manual"
        restored = BaseModelMetadata.from_dict(payload)
        assert restored.quantization == "NVFP4"
        assert restored.quantization_source == "manual"

    def test_source_omitted_when_none(self):
        metadata = self._make_metadata(quantization="FP8")

        payload = metadata.to_dict()

        assert "quantization_source" not in payload

    def test_source_emitted_when_value_checked_unavailable(self):
        # "" (checked, no value) serializes as JSON null; the source tag is
        # independent and stays.
        metadata = self._make_metadata(
            quantization=None, quantization_source="civitai"
        )

        payload = metadata.to_dict()

        assert payload["quantization"] is None
        assert payload["quantization_source"] == "civitai"
