"""Tests for the shared decode-tensor to PNG conversion."""

import numpy as np

from py.utils.image_tensor import tensor_to_png_bytes


def test_tensor_to_png_bytes_accepts_float_and_uint8_arrays():
    float_image = np.zeros((4, 4, 3), dtype=np.float32)
    png = tensor_to_png_bytes(float_image)
    assert png is not None
    assert png.startswith(b"\x89PNG")

    uint8_image = np.zeros((4, 4, 3), dtype=np.uint8)
    assert tensor_to_png_bytes(uint8_image) is not None


def test_tensor_to_png_bytes_unwraps_tuples_and_batches():
    batched = np.zeros((2, 4, 4, 3), dtype=np.float32)
    assert tensor_to_png_bytes(batched) is not None
    assert tensor_to_png_bytes((batched,)) is not None


def test_tensor_to_png_bytes_returns_none_for_unsupported_shapes():
    assert tensor_to_png_bytes(None) is None
    assert tensor_to_png_bytes(np.zeros((4, 4), dtype=np.float32)) is None
    assert tensor_to_png_bytes((None,)) is None
