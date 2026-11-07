"""Equivalence tests for the ``fuzzy_match`` prefilters added for #1179.

``fuzzy_match`` now skips ``SequenceMatcher`` when its ratio provably cannot
reach ``threshold``. These tests pin the two properties that make that legal:
the optimised implementation agrees with the pre-optimisation one on every
input, and obvious misses never reach the matcher at all.
"""

from __future__ import annotations

from difflib import SequenceMatcher

import pytest
from hypothesis import given, settings, strategies as st

import py.utils.utils as utils_module
from py.utils.utils import fuzzy_match


def reference_fuzzy_match(text: str, pattern: str, threshold: float = 0.85) -> bool:
    """The implementation from before #1179, kept as the oracle."""
    if not pattern or not text:
        return False

    text = text.lower()
    pattern = pattern.lower()

    for word in pattern.split():
        if word in text:
            continue

        found_match = False
        for text_part in text.split():
            if SequenceMatcher(None, text_part, word).ratio() >= threshold:
                found_match = True
                break

        if not found_match:
            return False

    return True


ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789 -."
TEXT = st.text(alphabet=ALPHABET, max_size=60)
PATTERN = st.text(alphabet=ALPHABET, max_size=24)
THRESHOLDS = st.sampled_from([0.0, 0.5, 0.75, 0.8, 0.85, 0.9, 1.0])


@st.composite
def similar_pairs(draw):
    """Two strings sharing a stem, to exercise the threshold boundary."""
    stem = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=10))
    tail_a = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", max_size=3))
    tail_b = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", max_size=3))
    return stem + tail_a, stem + tail_b


@settings(max_examples=300, deadline=None)
@given(TEXT, PATTERN, THRESHOLDS)
def test_matches_reference_on_arbitrary_input(text, pattern, threshold):
    assert fuzzy_match(text, pattern, threshold) == reference_fuzzy_match(
        text, pattern, threshold
    )


@settings(max_examples=300, deadline=None)
@given(similar_pairs(), THRESHOLDS)
def test_matches_reference_near_threshold(pair, threshold):
    text, pattern = pair
    assert fuzzy_match(text, pattern, threshold) == reference_fuzzy_match(
        text, pattern, threshold
    )
    # Both argument orders: the prefilter is not allowed to be directional.
    assert fuzzy_match(pattern, text, threshold) == reference_fuzzy_match(
        pattern, text, threshold
    )


class _CountingSequenceMatcher(SequenceMatcher):
    """SequenceMatcher that records how often ``ratio()`` is evaluated."""

    calls = 0

    def ratio(self) -> float:
        type(self).calls += 1
        return super().ratio()


@pytest.fixture
def counting_matcher(monkeypatch):
    _CountingSequenceMatcher.calls = 0
    monkeypatch.setattr(utils_module, "SequenceMatcher", _CountingSequenceMatcher)
    return _CountingSequenceMatcher


def test_obvious_miss_never_reaches_sequence_matcher(counting_matcher):
    assert fuzzy_match("photorealistic_anime_v3_fp16", "zzzqq") is False
    assert counting_matcher.calls == 0


def test_length_mismatch_never_reaches_sequence_matcher(counting_matcher):
    # 2 * 3 / (3 + 18) is far below the 0.85 threshold.
    assert fuzzy_match("high_detail_anime_style", "abc") is False
    assert counting_matcher.calls == 0


def test_near_match_still_consults_sequence_matcher(counting_matcher):
    # "animee" is not a substring of "anime", so only the matcher can accept it.
    assert fuzzy_match("anime", "animee") is True
    assert counting_matcher.calls >= 1


@pytest.mark.parametrize(
    ("text", "pattern", "expected"),
    [
        # A leading insertion changes the first character: a prefix/first-char
        # prefilter would wrongly reject this, the applied bounds do not.
        ("anime", "nanime", True),
        ("anime", "animee", True),
        # A transposition scores 0.8, below the default threshold.
        ("anime", "anmei", False),
        ("anime", "animee_", False),
        ("Anime", "anime", True),
        ("anime style", "anime styl", True),
        ("anime", "anime  style", False),
        ("anime_style_v2", "zzzqq", False),
        ("", "anime", False),
        ("anime", "", False),
    ],
)
def test_threshold_boundaries_are_preserved(text, pattern, expected):
    assert fuzzy_match(text, pattern) is expected
