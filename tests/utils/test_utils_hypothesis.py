"""Property-based tests using Hypothesis.

These tests verify fundamental properties of utility functions using
property-based testing to catch edge cases and ensure correctness.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from py.utils.cache_paths import _sanitize_library_name
from py.utils.file_utils import get_preview_extension, normalize_path
from py.utils.model_utils import determine_base_model
from py.utils.utils import (
    calculate_recipe_fingerprint,
    fuzzy_match,
    sanitize_folder_name,
)


class TestSanitizeFolderName:
    """Property-based tests for sanitize_folder_name function."""

    @given(st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- '))
    def test_sanitize_is_idempotent_for_ascii(self, name: str):
        """Sanitizing an already sanitized ASCII name should not change it."""
        sanitized = sanitize_folder_name(name)
        resanitized = sanitize_folder_name(sanitized)
        assert sanitized == resanitized

    @given(st.text())
    def test_sanitize_never_contains_invalid_chars(self, name: str):
        """Sanitized names should never contain filesystem-invalid characters."""
        sanitized = sanitize_folder_name(name)
        invalid_chars = '<>:"/\\|?*\x00\x01\x02\x03\x04\x05\x06\x07\x08'
        for char in invalid_chars:
            assert char not in sanitized

    @given(st.text())
    def test_sanitize_never_returns_none(self, name: str):
        """Sanitize should never return None (always returns a string)."""
        result = sanitize_folder_name(name)
        assert result is not None
        assert isinstance(result, str)

    @given(st.text(min_size=1))
    def test_sanitize_preserves_some_content(self, name: str):
        """Sanitizing a non-empty string should not produce an empty result
        unless the input was only invalid characters."""
        result = sanitize_folder_name(name)
        # If input had valid characters, output should not be empty
        has_valid_chars = any(c.isalnum() or c in '._-' for c in name)
        if has_valid_chars:
            assert result != ""


class TestSanitizeLibraryName:
    """Property-based tests for _sanitize_library_name function."""

    @given(st.text() | st.none())
    def test_sanitize_library_name_is_idempotent(self, library_name: str | None):
        """Sanitizing an already sanitized library name should not change it."""
        sanitized = _sanitize_library_name(library_name)
        resanitized = _sanitize_library_name(sanitized)
        assert sanitized == resanitized

    @given(st.text())
    def test_sanitize_library_name_only_contains_safe_chars(self, library_name: str):
        """Sanitized library names should only contain safe filename characters."""
        sanitized = _sanitize_library_name(library_name)
        # Should only contain alphanumeric, underscore, dot, and hyphen
        for char in sanitized:
            assert char.isalnum() or char in '._-'


class TestNormalizePath:
    """Property-based tests for normalize_path function."""

    @given(st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/\\') | st.none())
    def test_normalize_path_is_idempotent_for_ascii(self, path: str | None):
        """Normalizing an already normalized ASCII path should not change it."""
        normalized = normalize_path(path)
        renormalized = normalize_path(normalized)
        assert normalized == renormalized

    @given(st.text())
    def test_normalized_path_returns_string(self, path: str):
        """Normalized path should always return a string (or None)."""
        normalized = normalize_path(path)
        # Result is either None or a string
        assert normalized is None or isinstance(normalized, str)


class TestFuzzyMatch:
    """Property-based tests for fuzzy_match function."""

    @given(st.text(), st.text())
    def test_fuzzy_match_empty_pattern_returns_false(self, text: str, pattern: str):
        """Empty pattern should never match (except empty text with exact match)."""
        if not pattern:
            result = fuzzy_match(text, pattern)
            assert result is False

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_fuzzy_match_exact_substring_always_matches(self, text: str, pattern: str):
        """If pattern is a substring of text (case-insensitive), it should match."""
        # Create a case where pattern is definitely in text
        combined = text.lower() + " " + pattern.lower()
        result = fuzzy_match(combined, pattern.lower())
        assert result is True

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_fuzzy_match_substring_always_matches(self, text: str, pattern: str):
        """If pattern is a substring of text, it should always match."""
        if pattern in text:
            result = fuzzy_match(text, pattern)
            assert result is True


class TestDetermineBaseModel:
    """Property-based tests for determine_base_model function."""

    @given(st.text() | st.none())
    def test_determine_base_model_never_returns_none(self, version_string: str | None):
        """Function should never return None (always returns a string)."""
        result = determine_base_model(version_string)
        assert result is not None
        assert isinstance(result, str)

    @given(st.text())
    def test_determine_base_model_case_insensitive(self, version: str):
        """Base model detection should be case-insensitive."""
        lower_result = determine_base_model(version.lower())
        upper_result = determine_base_model(version.upper())
        # Results should be the same for known mappings
        if version.lower() in ['sdxl', 'sd_1.5', 'pony', 'flux1']:
            assert lower_result == upper_result


class TestGetPreviewExtension:
    """Property-based tests for get_preview_extension function."""

    @given(st.text())
    def test_get_preview_extension_returns_string(self, preview_path: str):
        """Function should always return a string."""
        result = get_preview_extension(preview_path)
        assert isinstance(result, str)

    @given(st.text(alphabet='abcdefghijklmnopqrstuvwxyz._'))
    def test_get_preview_extension_starts_with_dot(self, preview_path: str):
        """Extension should always start with a dot for valid paths."""
        if '.' in preview_path:
            result = get_preview_extension(preview_path)
            if result:
                assert result.startswith('.')


class TestCalculateRecipeFingerprint:
    """Property-based tests for calculate_recipe_fingerprint function."""

    @given(st.lists(st.dictionaries(st.text(), st.text() | st.integers() | st.floats(), min_size=1), min_size=0, max_size=50))
    def test_fingerprint_is_deterministic(self, loras: list):
        """Same input should always produce same fingerprint."""
        fp1 = calculate_recipe_fingerprint(loras)
        fp2 = calculate_recipe_fingerprint(loras)
        assert fp1 == fp2

    @given(st.lists(st.dictionaries(st.text(), st.text() | st.integers() | st.floats(), min_size=1), min_size=0, max_size=50))
    def test_fingerprint_returns_string(self, loras: list):
        """Function should always return a string."""
        result = calculate_recipe_fingerprint(loras)
        assert isinstance(result, str)

    def test_fingerprint_empty_list_returns_empty_string(self):
        """Empty list should return empty string."""
        result = calculate_recipe_fingerprint([])
        assert result == ""

    @given(st.lists(st.dictionaries(st.text(), st.text() | st.integers() | st.floats(), min_size=1), min_size=1, max_size=10))
    def test_fingerprint_different_inputs_produce_different_results(self, loras1: list):
        """Different inputs should generally produce different fingerprints."""
        # Create a different input by modifying the first LoRA
        loras2 = loras1.copy()
        if loras2:
            loras2[0] = {**loras2[0], 'hash': 'different_hash_12345'}
        
        fp1 = calculate_recipe_fingerprint(loras1)
        fp2 = calculate_recipe_fingerprint(loras2)
        
        # If the first LoRA had a hash, fingerprints should differ
        if loras1 and loras1[0].get('hash'):
            assert fp1 != fp2
