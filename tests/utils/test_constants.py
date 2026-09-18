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

class TestFolderPathSchema:
    def test_core_keys_first_in_canonical_order(self):
        from py.utils.constants import CORE_FOLDER_PATH_KEYS, folder_path_schema

        schema = folder_path_schema()
        core = [entry for entry in schema if entry["category"] == "core"]

        assert [entry["key"] for entry in core] == CORE_FOLDER_PATH_KEYS
        assert all(entry["sub_type"] is None for entry in core)
        assert schema[: len(core)] == core

    def test_other_entries_derive_from_subtypes_table(self):
        from py.utils.constants import OTHER_MODEL_FOLDER_SUBTYPES, folder_path_schema

        schema = folder_path_schema()
        other = {entry["key"]: entry for entry in schema if entry["category"] == "other"}

        assert set(other) == set(OTHER_MODEL_FOLDER_SUBTYPES)
        for folder_key, sub_type in OTHER_MODEL_FOLDER_SUBTYPES.items():
            assert other[folder_key]["sub_type"] == sub_type

    def test_text_encoder_exposes_both_folder_keys(self):
        from py.utils.constants import folder_path_schema

        text_encoder_keys = [
            entry["key"]
            for entry in folder_path_schema()
            if entry["sub_type"] == "text_encoder"
        ]

        assert text_encoder_keys == ["text_encoders", "clip"]
