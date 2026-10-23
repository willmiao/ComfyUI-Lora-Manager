import hashlib
import json
import os
import struct

import pytest

from py.utils.constants import MAX_SAFETENSORS_HEADER_BYTES
from py.utils.file_utils import (
    calculate_autov3,
    calculate_sha256,
    find_preview_file,
    get_preview_extension,
    reconcile_media_extension,
)


def _write_safetensors(path, metadata, payload=b"payload-bytes"):
    """Write a minimal real safetensors file: 8-byte little-endian header
    length, a JSON header containing ``__metadata__``, then arbitrary payload."""
    header = json.dumps({"__metadata__": metadata}).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)


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


class TestCalculateAutov3:
    def test_returns_first_12_chars_from_sshs_model_hash(self, tmp_path):
        file_path = tmp_path / "lora.safetensors"
        _write_safetensors(file_path, {"sshs_model_hash": "abcdef1234567890abcdef"})

        assert calculate_autov3(str(file_path)) == "abcdef123456"

    def test_lowercases_uppercase_embedded_hash(self, tmp_path):
        file_path = tmp_path / "upper.safetensors"
        _write_safetensors(file_path, {"sshs_model_hash": "ABCDEF1234567890ABCDEF"})

        assert calculate_autov3(str(file_path)) == "abcdef123456"

    def test_returns_first_12_chars_from_modelspec_hash_sha256(self, tmp_path):
        file_path = tmp_path / "model.safetensors"
        _write_safetensors(file_path, {"modelspec.hash_sha256": "00112233445566778899aabb"})

        assert calculate_autov3(str(file_path)) == "001122334455"

    def test_prefers_sshs_model_hash_over_modelspec_hash(self, tmp_path):
        file_path = tmp_path / "model.safetensors"
        _write_safetensors(
            file_path,
            {
                "sshs_model_hash": "aaaaaaaaaaaaaaaaaaaaaaaa",
                "modelspec.hash_sha256": "bbbbbbbbbbbbbbbbbbbbbbbb",
            },
        )

        assert calculate_autov3(str(file_path)) == "aaaaaaaaaaaa"

    def test_returns_none_for_non_safetensors_file(self, tmp_path):
        file_path = tmp_path / "plain.bin"
        file_path.write_bytes(b"just some plain bytes, not a safetensors file")

        assert calculate_autov3(str(file_path)) is None

    def test_returns_none_for_empty_file(self, tmp_path):
        file_path = tmp_path / "empty.safetensors"
        file_path.write_bytes(b"")

        assert calculate_autov3(str(file_path)) is None

    def test_returns_none_for_header_length_shorter_than_8_bytes(self, tmp_path):
        file_path = tmp_path / "short.safetensors"
        file_path.write_bytes(b"\x10\x00")
        assert calculate_autov3(str(file_path)) is None

    def test_returns_none_for_truncated_json_header(self, tmp_path):
        file_path = tmp_path / "truncated.safetensors"
        file_path.write_bytes(struct.pack("<Q", 100) + b'{"__metadata__":')

        assert calculate_autov3(str(file_path)) is None

    def test_returns_none_when_metadata_lacks_recognized_hash(self, tmp_path):
        file_path = tmp_path / "model.safetensors"
        _write_safetensors(file_path, {"ss_model_name": "something-else"})

        assert calculate_autov3(str(file_path)) is None

    def test_returns_none_when_embedded_hash_is_too_short(self, tmp_path):
        file_path = tmp_path / "model.safetensors"
        _write_safetensors(file_path, {"sshs_model_hash": "abc123"})

        assert calculate_autov3(str(file_path)) is None

    def test_returns_none_when_embedded_hash_is_not_a_string(self, tmp_path):
        file_path = tmp_path / "model.safetensors"
        _write_safetensors(file_path, {"sshs_model_hash": 123456})

        assert calculate_autov3(str(file_path)) is None

    def test_strips_0x_prefix_from_modelspec_hash(self, tmp_path):
        # OneTrainer writes modelspec.hash_sha256 with a "0x" prefix.
        file_path = tmp_path / "onetrainer.safetensors"
        _write_safetensors(
            file_path, {"modelspec.hash_sha256": "0x1585b50b9d7d66778899aabb"}
        )

        assert calculate_autov3(str(file_path)) == "1585b50b9d7d"

    def test_returns_none_for_empty_string_sha256_placeholder(self, tmp_path):
        # Repackaging tools sometimes write the SHA256-of-empty placeholder
        # instead of a real hash; it must not be treated as a valid AutoV3.
        file_path = tmp_path / "broken.safetensors"
        _write_safetensors(
            file_path,
            {"sshs_model_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
        )

        assert calculate_autov3(str(file_path)) is None

    def test_strips_0x_prefix_from_empty_hash_placeholder(self, tmp_path):
        file_path = tmp_path / "onetrainer_broken.safetensors"
        _write_safetensors(
            file_path,
            {"modelspec.hash_sha256": "0xe3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
        )

        assert calculate_autov3(str(file_path)) is None

    def test_returns_none_for_header_length_over_limit(self, tmp_path):
        # A crafted file whose 64-bit header length exceeds the cap must not
        # trigger a giant allocation; it is rejected before any read.
        file_path = tmp_path / "huge_header.safetensors"
        file_path.write_bytes(
            struct.pack("<Q", MAX_SAFETENSORS_HEADER_BYTES + 1) + b'{"__metadata__": {}}'
        )

        assert calculate_autov3(str(file_path)) is None

    def test_reads_header_at_exact_limit_boundary(self, tmp_path):
        # A header length exactly at the cap is still valid.
        file_path = tmp_path / "at_limit.safetensors"
        file_path.write_bytes(
            struct.pack("<Q", MAX_SAFETENSORS_HEADER_BYTES) + b'{"__metadata__": {"sshs_model_hash": "abcdef1234567890abcdef"}}'
        )

        # The read returns {} because the actual bytes are shorter than the
        # claimed length (short-read guard), without allocating anything huge.
        assert calculate_autov3(str(file_path)) is None


class TestReconcileMediaExtension:
    def test_renames_webp_bytes_saved_as_jpeg(self, tmp_path):
        file_path = tmp_path / "preview.jpeg"
        file_path.write_bytes(b"RIFF\x00\x00\x00\x00WEBPdata")

        result = reconcile_media_extension(str(file_path))

        assert result == str(tmp_path / "preview.webp")
        assert not file_path.exists()
        assert (tmp_path / "preview.webp").read_bytes() == b"RIFF\x00\x00\x00\x00WEBPdata"

    def test_renames_webm_bytes_saved_as_mp4(self, tmp_path):
        file_path = tmp_path / "preview.mp4"
        file_path.write_bytes(b"\x1a\x45\xdf\xa3" + b"webm-data")

        result = reconcile_media_extension(str(file_path))

        assert result == str(tmp_path / "preview.webm")
        assert (tmp_path / "preview.webm").exists()

    def test_keeps_path_when_extension_matches_content(self, tmp_path):
        file_path = tmp_path / "preview.webp"
        file_path.write_bytes(b"RIFF\x00\x00\x00\x00WEBPdata")

        assert reconcile_media_extension(str(file_path)) == str(file_path)

    def test_treats_jpg_and_jpeg_as_equivalent(self, tmp_path):
        file_path = tmp_path / "preview.jpeg"
        file_path.write_bytes(b"\xff\xd8\xff" + b"jpeg-data")

        assert reconcile_media_extension(str(file_path)) == str(file_path)
        assert file_path.exists()

    def test_keeps_path_for_unrecognized_content(self, tmp_path):
        file_path = tmp_path / "preview.mp4"
        file_path.write_bytes(b"not-a-real-video")

        assert reconcile_media_extension(str(file_path)) == str(file_path)
        assert file_path.exists()

    def test_keeps_path_for_missing_file(self, tmp_path):
        missing = str(tmp_path / "nope.mp4")

        assert reconcile_media_extension(missing) == missing
