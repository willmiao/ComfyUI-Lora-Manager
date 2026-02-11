"""Performance benchmarks using pytest-benchmark.

These tests measure the performance of critical operations to detect
regressions and ensure acceptable performance with large datasets.
"""

from __future__ import annotations

import random
import string
import pytest

from py.services.model_hash_index import ModelHashIndex
from py.utils.utils import fuzzy_match, calculate_recipe_fingerprint


class TestHashIndexPerformance:
    """Performance benchmarks for hash index operations."""

    def test_hash_index_lookup_small(self, benchmark):
        """Benchmark hash index lookup with 100 models."""
        index, target_hash = self._create_hash_index_with_n_models(100, return_target=True)

        def lookup():
            return index.get_path(target_hash)

        result = benchmark(lookup)
        assert result is not None

    def test_hash_index_lookup_medium(self, benchmark):
        """Benchmark hash index lookup with 1,000 models."""
        index, target_hash = self._create_hash_index_with_n_models(1000, return_target=True)

        def lookup():
            return index.get_path(target_hash)

        result = benchmark(lookup)
        assert result is not None

    def test_hash_index_lookup_large(self, benchmark):
        """Benchmark hash index lookup with 10,000 models."""
        index, target_hash = self._create_hash_index_with_n_models(10000, return_target=True)

        def lookup():
            return index.get_path(target_hash)

        result = benchmark(lookup)
        assert result is not None

    def test_hash_index_add_entry_small(self, benchmark):
        """Benchmark adding entries to hash index with 100 existing models."""
        index = self._create_hash_index_with_n_models(100)
        new_hash = f"new_hash_{self._random_string(16)}"
        new_path = "/path/to/new_model.safetensors"

        def add_entry():
            index.add_entry(new_hash, new_path)

        benchmark(add_entry)

    def test_hash_index_add_entry_large(self, benchmark):
        """Benchmark adding entries to hash index with 10,000 existing models."""
        index = self._create_hash_index_with_n_models(10000)
        new_hash = f"new_hash_{self._random_string(16)}"
        new_path = "/path/to/new_model.safetensors"

        def add_entry():
            index.add_entry(new_hash, new_path)

        benchmark(add_entry)

    def _create_hash_index_with_n_models(self, n: int, return_target: bool = False):
        """Create a hash index with n mock models.
        
        Args:
            n: Number of models to create
            return_target: If True, returns the hash of the middle model for lookup testing
            
        Returns:
            ModelHashIndex or tuple of (ModelHashIndex, target_hash)
        """
        index = ModelHashIndex()
        target_hash = None
        target_index = n // 2
        for i in range(n):
            sha256 = f"hash_{i:08d}_{self._random_string(24)}"
            file_path = f"/path/to/model_{i}.safetensors"
            index.add_entry(sha256, file_path)
            if i == target_index:
                target_hash = sha256
        if return_target:
            return index, target_hash
        return index

    def _random_string(self, length: int) -> str:
        """Generate a random string of fixed length."""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


class TestFuzzyMatchPerformance:
    """Performance benchmarks for fuzzy matching."""

    def test_fuzzy_match_short_text(self, benchmark):
        """Benchmark fuzzy matching with short text."""
        text = "lora model for character generation"
        pattern = "character lora"

        def match():
            return fuzzy_match(text, pattern)

        benchmark(match)

    def test_fuzzy_match_long_text(self, benchmark):
        """Benchmark fuzzy matching with long text."""
        text = "This is a very long description of a LoRA model that contains many words and details about what it does and how it works for character generation in stable diffusion"
        pattern = "character generation stable diffusion"

        def match():
            return fuzzy_match(text, pattern)

        benchmark(match)

    def test_fuzzy_match_many_words(self, benchmark):
        """Benchmark fuzzy matching with many search words."""
        text = "lora model anime style character portrait high quality detailed"
        pattern = "anime style character portrait high quality"

        def match():
            return fuzzy_match(text, pattern)

        benchmark(match)


class TestRecipeFingerprintPerformance:
    """Performance benchmarks for recipe fingerprint calculation."""

    def test_fingerprint_small_recipe(self, benchmark):
        """Benchmark fingerprint calculation with 5 LoRAs."""
        loras = self._create_loras(5)

        def calculate():
            return calculate_recipe_fingerprint(loras)

        benchmark(calculate)

    def test_fingerprint_medium_recipe(self, benchmark):
        """Benchmark fingerprint calculation with 50 LoRAs."""
        loras = self._create_loras(50)

        def calculate():
            return calculate_recipe_fingerprint(loras)

        benchmark(calculate)

    def test_fingerprint_large_recipe(self, benchmark):
        """Benchmark fingerprint calculation with 200 LoRAs."""
        loras = self._create_loras(200)

        def calculate():
            return calculate_recipe_fingerprint(loras)

        benchmark(calculate)

    def _create_loras(self, n: int) -> list:
        """Create a list of n mock LoRA dictionaries."""
        loras = []
        for i in range(n):
            lora = {
                "hash": f"abc{i:08d}",
                "strength": round(random.uniform(0.0, 2.0), 2),
                "modelVersionId": i,
            }
            loras.append(lora)
        return loras
