import hashlib
import os

import pytest

from py.utils.file_utils import (
    calculate_sha256,
    find_preview_file,
    get_preview_extension,
)


@pytest.mark.asyncio
async def test_calculate_sha256(tmp_path):
    file_path = tmp_path / "sample.bin"
    file_path.write_bytes(b"test-bytes")

    expected_hash = hashlib.sha256(b"test-bytes").hexdigest()

    result = await calculate_sha256(str(file_path))

    assert result == expected_hash


def test_find_preview_file_returns_normalized_path(tmp_path):
    file_path = tmp_path / "model.preview.png"
    file_path.write_bytes(b"")

    result = find_preview_file("model", str(tmp_path))

    assert result == str(file_path).replace(os.sep, "/")


def test_find_preview_file_supports_example_extension(tmp_path):
    file_path = tmp_path / "model.example.0.jpeg"
    file_path.write_bytes(b"")

    result = find_preview_file("model", str(tmp_path))

    assert result == str(file_path).replace(os.sep, "/")


@pytest.mark.parametrize(
    "preview_name,expected",
    [
        ("/path/to/model.preview.png", ".preview.png"),
        ("/path/to/model.png", ".png"),
    ],
)
def test_get_preview_extension(preview_name, expected):
    assert get_preview_extension(preview_name) == expected
