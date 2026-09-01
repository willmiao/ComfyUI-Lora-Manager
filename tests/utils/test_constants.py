"""Tests for the empty-hash placeholder predicate in constants."""

from py.utils.constants import (
    EMPTY_HASH_SHA256,
    INVALID_AUTOV2_EMPTY_HASH,
    INVALID_AUTOV3_EMPTY_HASH,
    is_empty_placeholder_hash,
)


class TestIsEmptyPlaceholderHash:
    def test_full_length_sha256(self):
        assert is_empty_placeholder_hash(EMPTY_HASH_SHA256)

    def test_autov3_length(self):
        assert is_empty_placeholder_hash("e3b0c44298fc")

    def test_autov2_length(self):
        assert is_empty_placeholder_hash("e3b0c44298")

    def test_case_insensitive(self):
        assert is_empty_placeholder_hash("E3B0C44298FC")
        assert is_empty_placeholder_hash(EMPTY_HASH_SHA256.upper())

    def test_derived_constants_are_prefixes(self):
        assert INVALID_AUTOV2_EMPTY_HASH == EMPTY_HASH_SHA256[:10]
        assert INVALID_AUTOV3_EMPTY_HASH == EMPTY_HASH_SHA256[:12]

    def test_rejects_other_lengths(self):
        # 8-char AutoV1-style prefix and non-placeholder lengths are not it
        assert not is_empty_placeholder_hash("e3b0c442")
        assert not is_empty_placeholder_hash("e3b0c44298fc1c")
        assert not is_empty_placeholder_hash("")

    def test_rejects_real_hashes_that_share_the_prefix(self):
        # A real hash whose first characters coincide must not be rejected
        assert not is_empty_placeholder_hash("e3b0c44298aa")
        assert not is_empty_placeholder_hash("e3b0c44298fc" + "a" * 52)
        assert not is_empty_placeholder_hash("915a9a1f5f")
        assert not is_empty_placeholder_hash("915a9a1f5f58")
        assert not is_empty_placeholder_hash("a" * 64)

    def test_rejects_non_strings(self):
        assert not is_empty_placeholder_hash(None)
        assert not is_empty_placeholder_hash(123)