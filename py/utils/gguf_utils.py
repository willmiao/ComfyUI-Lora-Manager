"""Content-based quantization detection for model files.

Two formats are supported, both via cheap header-only reads:

- GGUF: the ``general.file_type`` metadata field maps to a canonical
  quantization name ("Q4_K_M", "IQ4_XS", ...). Full-precision file types
  (F32/F16/BF16), unknown enum values, and unreadable headers yield ``None``.
- safetensors: the per-tensor ``dtype`` entries in the JSON header are
  weighted by byte size; a dominant F8_* dtype means the model is fp8 and is
  reported as "FP8". Anything else yields ``None``.

Nothing in this module ever raises: detection runs on every model file during
scans, so corrupt or truncated files must degrade to ``None`` quietly.
"""

from __future__ import annotations

import json
import os
import struct
from typing import BinaryIO, Dict, Optional

from .constants import MAX_SAFETENSORS_HEADER_BYTES

_GGUF_MAGIC = b"GGUF"

# GGUF metadata value type ids (gguf.h: enum gguf_type).
_GGUF_VALUE_STRING = 8
_GGUF_VALUE_ARRAY = 9
_GGUF_VALUE_TYPE_SIZES: Dict[int, int] = {
    0: 1,  # UINT8
    1: 1,  # INT8
    2: 2,  # UINT16
    3: 2,  # INT16
    4: 4,  # UINT32
    5: 4,  # INT32
    6: 4,  # FLOAT32
    7: 1,  # BOOL
    10: 8,  # UINT64
    11: 8,  # INT64
    12: 8,  # FLOAT64
}

# Defensive caps so a corrupt header cannot make us read/loop forever.
_GGUF_MAX_KV_COUNT = 1_000_000
_GGUF_MAX_STRING_BYTES = MAX_SAFETENSORS_HEADER_BYTES
_GGUF_MAX_ARRAY_ELEMENTS = 100_000_000

# llama.cpp ``enum llama_ftype`` values written into ``general.file_type``.
# Full-precision types (F32/F16/BF16) are not quantizations and map to None.
_GGUF_FILE_TYPE_NAMES: Dict[int, str] = {
    0: "F32",
    1: "F16",
    2: "Q4_0",
    3: "Q4_1",
    7: "Q8_0",
    8: "Q5_0",
    9: "Q5_1",
    10: "Q2_K",
    11: "Q3_K_S",
    12: "Q3_K_M",
    13: "Q3_K_L",
    14: "Q4_K_S",
    15: "Q4_K_M",
    16: "Q5_K_S",
    17: "Q5_K_M",
    18: "Q6_K",
    19: "IQ2_XXS",
    20: "IQ2_XS",
    21: "Q2_K_S",
    22: "IQ3_XS",
    23: "IQ3_XXS",
    24: "IQ1_S",
    25: "IQ4_NL",
    26: "IQ3_S",
    27: "IQ3_M",
    28: "IQ2_S",
    29: "IQ2_M",
    30: "IQ4_XS",
    31: "IQ1_M",
    32: "BF16",
    36: "TQ1_0",
    37: "TQ2_0",
    38: "MXFP4_MOE",
    39: "MXFP4",
}

_GGUF_FULL_PRECISION_NAMES = {"F32", "F16", "BF16"}


class _GgufParseError(Exception):
    """Internal control-flow exception for malformed GGUF headers."""


def _read_exact(handle: BinaryIO, size: int) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise _GgufParseError("short read")
    return data


def _read_gguf_string(handle: BinaryIO) -> bytes:
    (length,) = struct.unpack("<Q", _read_exact(handle, 8))
    if length > _GGUF_MAX_STRING_BYTES:
        raise _GgufParseError("string too large")
    return _read_exact(handle, length)


def _skip_gguf_value(handle: BinaryIO, value_type: int) -> None:
    """Advance the stream past one metadata value of ``value_type``."""
    if value_type == _GGUF_VALUE_STRING:
        _read_gguf_string(handle)
        return
    if value_type == _GGUF_VALUE_ARRAY:
        (element_type,) = struct.unpack("<I", _read_exact(handle, 4))
        (count,) = struct.unpack("<Q", _read_exact(handle, 8))
        if count > _GGUF_MAX_ARRAY_ELEMENTS:
            raise _GgufParseError("array too large")
        if element_type == _GGUF_VALUE_STRING:
            for _ in range(count):
                _read_gguf_string(handle)
            return
        element_size = _GGUF_VALUE_TYPE_SIZES.get(element_type)
        if element_size is None:
            raise _GgufParseError(f"unknown array element type {element_type}")
        _read_exact(handle, element_size * count)
        return
    value_size = _GGUF_VALUE_TYPE_SIZES.get(value_type)
    if value_size is None:
        raise _GgufParseError(f"unknown value type {value_type}")
    _read_exact(handle, value_size)


def parse_gguf_quantization(file_path: str) -> Optional[str]:
    """Return the canonical quantization name stored in a GGUF header.

    Reads only the header metadata (seeking past values until
    ``general.file_type`` is found). Returns ``None`` for full-precision
    models (F32/F16/BF16), unknown file-type values, and any unreadable or
    malformed header.
    """
    try:
        with open(file_path, "rb") as handle:
            if _read_exact(handle, 4) != _GGUF_MAGIC:
                return None
            (version,) = struct.unpack("<I", _read_exact(handle, 4))
            if version < 1 or version > 3:
                return None
            # tensor_count is irrelevant for quantization detection.
            _read_exact(handle, 8)
            (kv_count,) = struct.unpack("<Q", _read_exact(handle, 8))
            if kv_count > _GGUF_MAX_KV_COUNT:
                return None
            for _ in range(kv_count):
                key = _read_gguf_string(handle)
                (value_type,) = struct.unpack("<I", _read_exact(handle, 4))
                if key == b"general.file_type":
                    if value_type != 4:  # UINT32
                        return None
                    (file_type,) = struct.unpack("<I", _read_exact(handle, 4))
                    name = _GGUF_FILE_TYPE_NAMES.get(file_type)
                    if name is None or name in _GGUF_FULL_PRECISION_NAMES:
                        return None
                    return name
                _skip_gguf_value(handle, value_type)
        return None
    except (OSError, struct.error, _GgufParseError, MemoryError, Exception):
        return None


def _detect_safetensors_quantization(file_path: str) -> Optional[str]:
    """Return "FP8" when the dominant tensor dtype is an F8 variant.

    "Dominant" is measured by byte size (``data_offsets`` span) rather than
    tensor count, so a handful of tiny non-quantized side tensors (biases,
    norms) cannot flip the result of a quantized model.
    """
    try:
        with open(file_path, "rb") as handle:
            header_len_bytes = handle.read(8)
            if len(header_len_bytes) < 8:
                return None
            (header_len,) = struct.unpack("<Q", header_len_bytes)
            if header_len > MAX_SAFETENSORS_HEADER_BYTES:
                return None
            header_bytes = handle.read(header_len)
            if len(header_bytes) < header_len:
                return None
        header = json.loads(header_bytes.decode("utf-8"))
        if not isinstance(header, dict):
            return None

        bytes_per_dtype: Dict[str, int] = {}
        for name, info in header.items():
            if name == "__metadata__" or not isinstance(info, dict):
                continue
            dtype = info.get("dtype")
            offsets = info.get("data_offsets")
            if (
                not isinstance(dtype, str)
                or not isinstance(offsets, (list, tuple))
                or len(offsets) != 2
            ):
                continue
            try:
                span = int(offsets[1]) - int(offsets[0])
            except (TypeError, ValueError):
                continue
            if span <= 0:
                continue
            bytes_per_dtype[dtype] = bytes_per_dtype.get(dtype, 0) + span

        if not bytes_per_dtype:
            return None
        dominant_dtype = max(bytes_per_dtype, key=lambda d: bytes_per_dtype[d])
        if dominant_dtype.startswith("F8"):
            return "FP8"
        return None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, struct.error, MemoryError, Exception):
        return None


def detect_quantization(file_path: str) -> Optional[str]:
    """Detect the quantization of a model file from its header.

    Dispatches on extension: ``.gguf`` files are parsed for
    ``general.file_type`` (canonical names such as "Q4_K_M"; full-precision
    and unknown types yield ``None``), ``.safetensors`` files are checked for
    a dominant F8_* tensor dtype ("FP8"). Every other extension and any read
    failure yields ``None``. Reads only file headers and never raises.
    """
    extension = os.path.splitext(file_path)[1].lower()
    if extension == ".gguf":
        return parse_gguf_quantization(file_path)
    if extension == ".safetensors":
        return _detect_safetensors_quantization(file_path)
    return None
