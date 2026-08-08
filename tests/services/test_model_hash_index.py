import pytest
from py.services.model_hash_index import ModelHashIndex


class TestModelHashIndexRemoveByPath:
    def test_remove_by_path_finds_hash_in_hash_to_path(self):
        index = ModelHashIndex()
        index.add_entry("abc123", "/models/lora.safetensors")
        index.remove_by_path("/models/lora.safetensors")
        assert len(index) == 0
        assert not index.get_duplicate_filenames()

    def test_remove_by_path_falls_back_to_duplicate_hashes(self):
        """When a path is only tracked in _duplicate_hashes, remove_by_path
        should still find and remove it."""
        index = ModelHashIndex()
        index.add_entry("abc123", "/models/lora_v1.safetensors")
        index.add_entry("abc123", "/models/lora_v2.safetensors")

        # lora_v1 is the primary (_hash_to_path), lora_v2 is in _duplicate_hashes
        index.remove_by_path("/models/lora_v2.safetensors")

        assert len(index) == 1
        assert index._hash_to_path.get("abc123") == "/models/lora_v1.safetensors"
        assert "abc123" not in index._duplicate_hashes

    def test_remove_by_path_cleans_up_duplicate_filenames(self):
        """After removing a path, _duplicate_filenames should be updated."""
        index = ModelHashIndex()
        index.add_entry("abc123", "/models/mylora.safetensors")
        index.add_entry("def456", "/other/mylora.safetensors")

        assert "mylora" in index.get_duplicate_filenames()
        assert len(index.get_duplicate_filenames()["mylora"]) == 2

        index.remove_by_path("/other/mylora.safetensors")

        # After removing one duplicate, only one path remains — no longer a duplicate
        assert "mylora" not in index.get_duplicate_filenames()

    def test_remove_by_path_keeps_duplicate_filenames_with_three_entries(self):
        """With 3 entries for the same filename, removing one should leave 2."""
        index = ModelHashIndex()
        index.add_entry("abc123", "/models/mylora.safetensors")
        index.add_entry("def456", "/other/mylora.safetensors")
        index.add_entry("ghi789", "/third/mylora.safetensors")

        index.remove_by_path("/other/mylora.safetensors")

        assert "mylora" in index.get_duplicate_filenames()
        paths = index.get_duplicate_filenames()["mylora"]
        assert len(paths) == 2
        assert "/other/mylora.safetensors" not in paths

    def test_remove_by_path_noop_on_unknown_path(self):
        index = ModelHashIndex()
        index.add_entry("abc123", "/models/lora.safetensors")
        # Should not raise
        index.remove_by_path("/nonexistent/lora.safetensors")
        assert len(index) == 1

    def test_remove_by_path_handles_hash_from_duplicate_hashes_only(self):
        """Remove a path whose hash exists ONLY in _duplicate_hashes,
        not in _hash_to_path (edge case from index rebuilds)."""
        index = ModelHashIndex()
        index.add_entry("abc123", "/a/model.safetensors")
        index.add_entry("abc123", "/b/model.safetensors")

        # Manually remove the primary entry to simulate edge case
        del index._hash_to_path["abc123"]
        # Now the path is only referenced in _duplicate_hashes
        assert "abc123" in index._duplicate_hashes

        index.remove_by_path("/b/model.safetensors")
        # The remaining path is promoted to _hash_to_path, duplicates cleared
        assert "abc123" not in index._duplicate_hashes
        assert index._hash_to_path.get("abc123") == "/a/model.safetensors"


class TestModelHashIndexGetDuplicateFilenames:
    def test_empty_index_returns_empty_dict(self):
        index = ModelHashIndex()
        assert index.get_duplicate_filenames() == {}

    def test_no_duplicates_returns_empty_dict(self):
        index = ModelHashIndex()
        index.add_entry("abc123", "/models/lora.safetensors")
        index.add_entry("def456", "/models/other.safetensors")
        assert index.get_duplicate_filenames() == {}

    def test_duplicate_filenames_detected(self):
        index = ModelHashIndex()
        index.add_entry("abc123", "/a/mylora.safetensors")
        index.add_entry("def456", "/b/mylora.safetensors")
        dupes = index.get_duplicate_filenames()
        assert "mylora" in dupes
        assert len(dupes["mylora"]) == 2

    def test_same_hash_same_name_not_a_filename_duplicate(self):
        """Same hash with same filename = hash duplicate, not filename conflict."""
        index = ModelHashIndex()
        index.add_entry("abc123", "/a/lora.safetensors")
        # Same hash, same filename — this is a true duplicate (hash collision)
        # but the filename index only tracks different files with same name
        # Currently add_entry for same hash+path would update, not create duplicate
        # This is correct behavior — filename dupes are for different files

    def test_add_entry_idempotent_for_same_path_and_hash(self):
        index = ModelHashIndex()
        index.add_entry("abc123", "/a/lora.safetensors")
        index.add_entry("abc123", "/a/lora.safetensors")
        assert len(index) == 1
        assert index.get_duplicate_filenames() == {}


class TestModelHashIndexAutov3:
    """AutoV3 hash index behavior."""

    def test_add_entry_with_autov3_supports_lookup_by_autov3(self):
        index = ModelHashIndex()
        index.add_entry("a" * 64, "/models/lora.safetensors", autov3="AbCdEf123456")

        assert index.has_hash("abcdef123456") is True
        assert index.get_path("abcdef123456") == "/models/lora.safetensors"
        assert index.get_all_autov3() == {"abcdef123456": "/models/lora.safetensors"}

    def test_add_entry_without_autov3_creates_no_autov3_lookup(self):
        index = ModelHashIndex()
        index.add_entry("b" * 64, "/models/lora.safetensors")

        assert index.has_hash("abcdef123456") is False
        assert index.get_path("abcdef123456") is None
        assert index.get_all_autov3() == {}

    def test_add_autov3_standalone_supports_lookup(self):
        index = ModelHashIndex()
        index.add_autov3("cdef123456ab", "/models/only_autov3.safetensors")

        assert index.has_hash("cdef123456ab") is True
        assert index.get_path("cdef123456ab") == "/models/only_autov3.safetensors"
        assert index.get_all_autov3() == {"cdef123456ab": "/models/only_autov3.safetensors"}

    def test_remove_by_path_removes_autov3_mapping(self):
        index = ModelHashIndex()
        index.add_entry("a" * 64, "/models/lora.safetensors", autov3="abcdef123456")

        index.remove_by_path("/models/lora.safetensors")

        assert index.has_hash("abcdef123456") is False
        assert index.get_all_autov3() == {}

    def test_remove_by_hash_removes_autov3_mapping(self):
        index = ModelHashIndex()
        sha256 = "a" * 64
        index.add_entry(sha256, "/models/lora.safetensors", autov3="abcdef123456")

        index.remove_by_hash(sha256)

        assert index.has_hash("abcdef123456") is False
        assert index.get_all_autov3() == {}

    def test_clear_empties_autov3_index(self):
        index = ModelHashIndex()
        index.add_entry("a" * 64, "/models/a.safetensors", autov3="aaaaabbbbbcc")
        index.add_entry("b" * 64, "/models/b.safetensors", autov3="dddddeeeeeff")

        index.clear()

        assert index.get_all_autov3() == {}
        assert index.has_hash("aaaaabbbbbcc") is False

    def test_same_autov3_last_write_wins(self):
        index = ModelHashIndex()
        index.add_entry("a" * 64, "/models/first.safetensors", autov3="abcdef123456")
        index.add_entry("b" * 64, "/models/second.safetensors", autov3="abcdef123456")

        assert index.get_path("abcdef123456") == "/models/second.safetensors"
        assert index.get_all_autov3() == {"abcdef123456": "/models/second.safetensors"}

    def test_dispatch_len_10_hits_autov2(self):
        index = ModelHashIndex()
        sha256 = "a" * 64
        index.add_entry(sha256, "/models/lora.safetensors")

        assert index.get_path(sha256[:10]) == "/models/lora.safetensors"
        assert index.has_hash(sha256[:10]) is True

    def test_dispatch_len_64_hits_sha256(self):
        index = ModelHashIndex()
        sha256 = "b" * 64
        index.add_entry(sha256, "/models/lora.safetensors")

        assert index.get_path(sha256) == "/models/lora.safetensors"
        assert index.has_hash(sha256) is True

    def test_dispatch_len_12_hits_autov3(self):
        index = ModelHashIndex()
        index.add_entry("c" * 64, "/models/lora.safetensors", autov3="cdef123456ab")

        assert index.get_path("cdef123456ab") == "/models/lora.safetensors"
        assert index.has_hash("cdef123456ab") is True

    def test_add_entry_drops_stale_autov3_for_replaced_path(self):
        # A file replaced in place (new content → new sha256 and new autov3)
        # must not keep the old autov3 mapping — it would survive into the
        # persisted snapshot and make lookups resolve the wrong file.
        index = ModelHashIndex()
        index.add_entry("a" * 64, "/models/lora.safetensors", autov3="abcdef123456")
        index.add_entry("b" * 64, "/models/lora.safetensors", autov3="fedcba654321")

        assert index.get_path("abcdef123456") is None
        assert index.has_hash("abcdef123456") is False
        assert index.get_path("fedcba654321") == "/models/lora.safetensors"
        assert index.get_all_autov3() == {"fedcba654321": "/models/lora.safetensors"}

    def test_add_entry_without_autov3_drops_stale_mapping_for_replaced_path(self):
        # Replaced file whose new content has no embedded hash: the stale
        # autov3 mapping must be dropped, not left pointing at the path.
        index = ModelHashIndex()
        index.add_entry("a" * 64, "/models/lora.safetensors", autov3="abcdef123456")
        index.add_entry("b" * 64, "/models/lora.safetensors")

        assert index.get_path("abcdef123456") is None
        assert index.get_all_autov3() == {}

    def test_add_entry_re_registration_with_same_autov3_is_idempotent(self):
        index = ModelHashIndex()
        index.add_entry("a" * 64, "/models/lora.safetensors", autov3="abcdef123456")
        index.add_entry("a" * 64, "/models/lora.safetensors", autov3="abcdef123456")

        assert index.get_path("abcdef123456") == "/models/lora.safetensors"
        assert index.get_all_autov3() == {"abcdef123456": "/models/lora.safetensors"}

    def test_add_entry_same_sha_without_autov3_preserves_existing_mapping(self):
        # A lazy-hash completion (checkpoint_scanner) re-registers the SAME
        # file with the same sha256 but omits autov3. That must never clear
        # the previously registered autov3 mapping.
        index = ModelHashIndex()
        index.add_entry("a" * 64, "/models/ckpt.safetensors", autov3="abcdef123456")
        index.add_entry("a" * 64, "/models/ckpt.safetensors")

        assert index.get_path("abcdef123456") == "/models/ckpt.safetensors"
        assert index.get_all_autov3() == {"abcdef123456": "/models/ckpt.safetensors"}

    def test_add_entry_same_sha_with_new_autov3_drops_old_mapping(self):
        # Re-registration with an explicit, different autov3 (metadata
        # correction) must drop the stale mapping for that path.
        index = ModelHashIndex()
        index.add_entry("a" * 64, "/models/ckpt.safetensors", autov3="abcdef123456")
        index.add_entry("a" * 64, "/models/ckpt.safetensors", autov3="fedcba654321")

        assert index.get_path("abcdef123456") is None
        assert index.has_hash("abcdef123456") is False
        assert index.get_path("fedcba654321") == "/models/ckpt.safetensors"
        assert index.get_all_autov3() == {"fedcba654321": "/models/ckpt.safetensors"}
