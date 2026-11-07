"""Performance benchmarks using pytest-benchmark.

These tests measure the performance of critical operations to detect
regressions and ensure acceptable performance with large datasets.
"""

from __future__ import annotations

import random
import string
from typing import Any, Dict, cast

import pytest

from py.services.model_hash_index import ModelHashIndex
from py.utils.utils import fuzzy_match, calculate_recipe_fingerprint


pytestmark = pytest.mark.performance


class TestHashIndexPerformance:
    """Performance benchmarks for hash index operations."""

    def test_hash_index_lookup_small(self, benchmark):
        """Benchmark hash index lookup with 100 models."""
        index, target_hash = cast(
            tuple[ModelHashIndex, str | None],
            self._create_hash_index_with_n_models(100, return_target=True),
        )
        assert target_hash is not None

        def lookup():
            return index.get_path(target_hash)

        result = benchmark(lookup)
        assert result is not None

    def test_hash_index_lookup_medium(self, benchmark):
        """Benchmark hash index lookup with 1,000 models."""
        index, target_hash = cast(
            tuple[ModelHashIndex, str | None],
            self._create_hash_index_with_n_models(1000, return_target=True),
        )
        assert target_hash is not None

        def lookup():
            return index.get_path(target_hash)

        result = benchmark(lookup)
        assert result is not None

    def test_hash_index_lookup_large(self, benchmark):
        """Benchmark hash index lookup with 10,000 models."""
        index, target_hash = cast(
            tuple[ModelHashIndex, str | None],
            self._create_hash_index_with_n_models(10000, return_target=True),
        )
        assert target_hash is not None

        def lookup():
            return index.get_path(target_hash)

        result = benchmark(lookup)
        assert result is not None

    def test_hash_index_add_entry_small(self, benchmark):
        """Benchmark adding entries to hash index with 100 existing models."""
        index = cast(ModelHashIndex, self._create_hash_index_with_n_models(100))
        new_hash = f"new_hash_{self._random_string(16)}"
        new_path = "/path/to/new_model.safetensors"

        def add_entry():
            index.add_entry(new_hash, new_path)

        benchmark(add_entry)

    def test_hash_index_add_entry_large(self, benchmark):
        """Benchmark adding entries to hash index with 10,000 existing models."""
        index = cast(ModelHashIndex, self._create_hash_index_with_n_models(10000))
        new_hash = f"new_hash_{self._random_string(16)}"
        new_path = "/path/to/new_model.safetensors"

        def add_entry():
            index.add_entry(new_hash, new_path)

        benchmark(add_entry)

    def _create_hash_index_with_n_models(
        self, n: int, return_target: bool = False
    ) -> ModelHashIndex | tuple[ModelHashIndex, str | None]:
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
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


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


class TestFuzzyMatchLibraryScale:
    """Benchmark one search query over a large library (issue #1179).

    Before the prefilters, a non-matching query at this size spent well over
    100ms in ``SequenceMatcher`` because every token of every non-matching
    entry reached the matcher.
    """

    LIBRARY_SIZE = 20_000

    @staticmethod
    def _build_library(size: int) -> list[str]:
        vocabulary = (
            "anime style character realistic portrait detail lineart chinese dark "
            "magic girl pixel art photo cinematic illustration concept fantasy armor "
            "cyberpunk watercolor sketch vintage retro neon glow soft light shadow "
            "chibi cute mecha samurai landscape nature city night flower dragon knight"
        ).split()
        folders = ("", "anime/", "realistic/", "styles/", "characters/")
        rng = random.Random(1179)
        library = []
        for _ in range(size):
            words = rng.sample(vocabulary, k=rng.randint(2, 4))
            library.append(f"{rng.choice(folders)}{'_'.join(words)}.safetensors")
        return library

    def test_non_matching_query(self, benchmark):
        """Worst case: nothing matches, so every entry is fully scanned."""
        library = self._build_library(self.LIBRARY_SIZE)

        def search():
            return sum(1 for name in library if fuzzy_match(name, "zzzqq"))

        assert benchmark(search) == 0

    def test_typo_query(self, benchmark):
        """A typo shares characters with many tokens, so it does the most work."""
        library = self._build_library(self.LIBRARY_SIZE)

        def search():
            return sum(1 for name in library if fuzzy_match(name, "anmei"))

        benchmark(search)


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

    def _create_loras(self, n: int) -> list[Dict[str, Any]]:
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
