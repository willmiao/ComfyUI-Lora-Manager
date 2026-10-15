"""Tests for py.utils.gguf_utils quantization detection."""

from __future__ import annotations

import io
import struct
from pathlib import Path
from typing import List, Tuple

import pytest

from py.utils.gguf_utils import detect_quantization, parse_gguf_quantization


def _string_kv(key: str, value: str) -> Tuple[bytes, int, bytes]:
    raw = value.encode("utf-8")
    return key.encode("utf-8"), 8, struct.pack("<Q", len(raw)) + raw


def _string_array_kv(key: str, values: List[str]) -> Tuple[bytes, int, bytes]:
    raw = struct.pack("<I", 8) + struct.pack("<Q", len(values))
    for value in values:
        encoded = value.encode("utf-8")
        raw += struct.pack("<Q", len(encoded)) + encoded
    return key.encode("utf-8"), 9, raw


def _uint32_kv(key: str, value: int) -> Tuple[bytes, int, bytes]:
    return key.encode("utf-8"), 4, struct.pack("<I", value)


def _write_gguf(
    path: Path,
    file_type: int,
    *,
    version: int = 3,
    extra_kvs: List[Tuple[bytes, int, bytes]] | None = None,
) -> Path:
    """Write a minimal in-memory-built GGUF file with the given file_type."""
    kvs = list(extra_kvs or []) + [_uint32_kv("general.file_type", file_type)]
    blob = io.BytesIO()
    blob.write(b"GGUF")
    blob.write(struct.pack("<I", version))
    blob.write(struct.pack("<Q", 0))  # tensor_count
    blob.write(struct.pack("<Q", len(kvs)))
    for key, value_type, raw in kvs:
        blob.write(struct.pack("<Q", len(key)))
        blob.write(key)
        blob.write(struct.pack("<I", value_type))
        blob.write(raw)
    path.write_bytes(blob.getvalue())
    return path


class TestGgufParser:
    @pytest.mark.parametrize(
        "file_type,expected",
        [
            (2, "Q4_0"),
            (3, "Q4_1"),
            (7, "Q8_0"),
            (8, "Q5_0"),
            (9, "Q5_1"),
            (10, "Q2_K"),
            (11, "Q3_K_S"),
            (12, "Q3_K_M"),
            (13, "Q3_K_L"),
            (14, "Q4_K_S"),
            (15, "Q4_K_M"),
            (16, "Q5_K_S"),
            (17, "Q5_K_M"),
            (18, "Q6_K"),
            (19, "IQ2_XXS"),
            (20, "IQ2_XS"),
            (21, "Q2_K_S"),
            (25, "IQ4_NL"),
            (30, "IQ4_XS"),
            (36, "TQ1_0"),
            (37, "TQ2_0"),
            (39, "MXFP4"),
        ],
    )
    def test_quantized_file_types_map_to_canonical_names(
        self, tmp_path: Path, file_type: int, expected: str
    ) -> None:
        path = _write_gguf(tmp_path / "model.gguf", file_type)
        assert parse_gguf_quantization(str(path)) == expected

    @pytest.mark.parametrize("file_type", [0, 1, 32])  # F32, F16, BF16
    def test_full_precision_file_types_return_none(
        self, tmp_path: Path, file_type: int
    ) -> None:
        path = _write_gguf(tmp_path / "model.gguf", file_type)
        assert parse_gguf_quantization(str(path)) is None

    def test_unknown_file_type_returns_none(self, tmp_path: Path) -> None:
        path = _write_gguf(tmp_path / "model.gguf", 999)
        assert parse_gguf_quantization(str(path)) is None

    def test_file_type_after_string_and_array_values(self, tmp_path: Path) -> None:
        """Values of other metadata entries must be skipped correctly."""
        path = _write_gguf(
            tmp_path / "model.gguf",
            15,
            extra_kvs=[
                _string_kv("general.architecture", "flux"),
                _string_array_kv("tokenizer.ggml.tokens", ["a", "bb", "ccc"]),
                _string_kv("tokenizer.chat_template", "x" * 5000),
            ],
        )
        assert parse_gguf_quantization(str(path)) == "Q4_K_M"

    def test_bad_magic_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "model.gguf"
        path.write_bytes(b"NOPE" + b"\x00" * 100)
        assert parse_gguf_quantization(str(path)) is None

    def test_unsupported_version_returns_none(self, tmp_path: Path) -> None:
        path = _write_gguf(tmp_path / "model.gguf", 15, version=99)
        assert parse_gguf_quantization(str(path)) is None

    def test_truncated_after_magic_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "model.gguf"
        path.write_bytes(b"GGUF")
        assert parse_gguf_quantization(str(path)) is None

    def test_truncated_mid_kv_returns_none(self, tmp_path: Path) -> None:
        full = _write_gguf(tmp_path / "full.gguf", 15).read_bytes()
        path = tmp_path / "model.gguf"
        path.write_bytes(full[:20])
        assert parse_gguf_quantization(str(path)) is None

    def test_absurd_kv_count_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "model.gguf"
        path.write_bytes(
            b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", 10**9)
        )
        assert parse_gguf_quantization(str(path)) is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert parse_gguf_quantization(str(tmp_path / "nope.gguf")) is None


class TestSafetensorsDetection:
    def test_fp8_dominant_dtype_reports_fp8(self, tmp_path: Path) -> None:
        torch = pytest.importorskip("torch")
        from safetensors.torch import save_file

        path = tmp_path / "fp8.safetensors"
        save_file(
            {"weight": torch.zeros(64, 64, dtype=torch.float8_e4m3fn)},
            str(path),
        )
        assert detect_quantization(str(path)) == "FP8"

    def test_fp16_returns_none(self, tmp_path: Path) -> None:
        torch = pytest.importorskip("torch")
        from safetensors.torch import save_file

        path = tmp_path / "fp16.safetensors"
        save_file({"weight": torch.zeros(64, 64, dtype=torch.float16)}, str(path))
        assert detect_quantization(str(path)) is None

    def test_dominance_is_by_bytes_not_tensor_count(self, tmp_path: Path) -> None:
        """Many tiny fp8 tensors must not flip a large fp16 model to FP8."""
        torch = pytest.importorskip("torch")
        from safetensors.torch import save_file

        path = tmp_path / "mixed.safetensors"
        tensors = {"big": torch.zeros(1024, 1024, dtype=torch.float16)}
        for i in range(10):
            tensors[f"tiny_fp8_{i}"] = torch.zeros(4, dtype=torch.float8_e4m3fn)
        save_file(tensors, str(path))
        assert detect_quantization(str(path)) is None

    def test_large_fp8_with_small_fp32_side_tensors_reports_fp8(self, tmp_path: Path) -> None:
        torch = pytest.importorskip("torch")
        from safetensors.torch import save_file

        path = tmp_path / "mixed_fp8.safetensors"
        save_file(
            {
                "weight": torch.zeros(1024, 1024, dtype=torch.float8_e4m3fn),
                "bias": torch.zeros(16, dtype=torch.float32),
            },
            str(path),
        )
        assert detect_quantization(str(path)) == "FP8"

    def test_invalid_safetensors_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.safetensors"
        path.write_bytes(b"not a safetensors file")
        assert detect_quantization(str(path)) is None


class TestDetectQuantizationDispatch:
    def test_gguf_extension_dispatches_to_gguf_parser(self, tmp_path: Path) -> None:
        path = _write_gguf(tmp_path / "model.GGUF", 15)
        assert detect_quantization(str(path)) == "Q4_K_M"

    def test_unknown_extension_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "model.txt"
        path.write_text("hello", encoding="utf-8")
        assert detect_quantization(str(path)) is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert detect_quantization(str(tmp_path / "missing.safetensors")) is None
