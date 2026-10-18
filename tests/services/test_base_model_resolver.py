"""Tests for the deterministic site base-model resolver.

The resolver exists so the enrichment pipeline can skip the LLM when the model
site already supplies everything; it must therefore be strictly conservative —
returning nothing is always better than returning the wrong canonical name.
"""

from __future__ import annotations

import pytest

from py.services.agent.base_model_resolver import resolve_base_model

KNOWN = [
    "Krea 2",
    "Flux.1 Krea",
    "Flux.1 D",
    "Flux.1 S",
    "SDXL 1.0",
    "Pony",
    "Illustrious",
]


class TestExactNormalisedMatch:
    @pytest.mark.parametrize(
        "hint",
        ["Krea 2", "krea 2", "KREA_2", "krea-2", "krea.2", "  Krea2  "],
    )
    def test_separators_and_casing_are_ignored(self, hint):
        assert resolve_base_model([hint], KNOWN) == "Krea 2"

    def test_returns_the_canonical_spelling_not_the_hint(self):
        assert resolve_base_model(["kreA_2"], KNOWN) == "Krea 2"

    def test_does_not_match_a_longer_prefixed_name_by_accident(self):
        # "Flux.1 Krea" must not be resolved to "Krea 2".
        assert resolve_base_model(["Flux.1 Krea"], KNOWN) == "Flux.1 Krea"

    def test_first_matching_hint_wins(self):
        assert (
            resolve_base_model(["totally-unknown", "KREA_2"], KNOWN) == "Krea 2"
        )


class TestVariantSuffixStripping:
    @pytest.mark.parametrize(
        "hint",
        [
            "KREA_2_TURBO",
            "Krea-2-Turbo",
            "krea2turbo",
            "Krea 2 Turbo",
            "krea-2-dev",
            "krea2-schnell",
            "krea2-lightning",
        ],
    )
    def test_common_published_suffixes_are_stripped(self, hint):
        assert resolve_base_model([hint], KNOWN) == "Krea 2"

    def test_suffix_only_hint_never_matches(self):
        # "turbo" on its own strips to nothing and must not resolve.
        assert resolve_base_model(["turbo"], KNOWN) == ""


class TestConservativeFailures:
    @pytest.mark.parametrize(
        "hints",
        [
            [],
            [""],
            ["totally-unknown-model"],
            ["flux1dev"],  # "Flux.1 D" normalises to "flux1d", not "flux1"
            ["sd"],
            ["ponyxl"],
        ],
    )
    def test_returns_empty_when_not_exactly_sure(self, hints):
        assert resolve_base_model(hints, KNOWN) == ""

    def test_returns_empty_without_a_vocabulary(self):
        assert resolve_base_model(["KREA_2"], []) == ""

    def test_only_ever_returns_a_known_name(self):
        for name in ["KREA_2", "KREA_2_TURBO", "krea-2-turbo", "unknown"]:
            result = resolve_base_model([name], KNOWN)
            assert result == "" or result in KNOWN

    def test_real_world_modelscope_hints(self):
        """The hints ModelScope actually publishes for a Krea 2 LoRA."""
        assert (
            resolve_base_model(
                ["KREA_2", "KREA_2_TURBO", "Krea-2-Turbo"], KNOWN
            )
            == "Krea 2"
        )
