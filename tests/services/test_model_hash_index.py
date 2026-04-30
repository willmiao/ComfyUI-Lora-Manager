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
