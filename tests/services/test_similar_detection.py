"""Tests for 'Find Similar' recipe detection (signature + weight clustering)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from py.utils.utils import (
    calculate_recipe_similarity_signature,
    cluster_recipes_by_weight,
    get_retained_lora_weights,
)


def _loras(*pairs):
    """Build a lora list from (hash, weight) pairs."""
    return [{"hash": h, "strength": w} for h, w in pairs]


# --- Base signature (weight-free) --------------------------------------------

def test_signature_matches_same_lora_set_regardless_of_weight():
    """Signature captures the LoRA set only; weights don't affect it."""
    a = calculate_recipe_similarity_signature(_loras(("aaa", 0.8), ("bbb", 1.0)))
    b = calculate_recipe_similarity_signature(_loras(("bbb", 0.2), ("aaa", 0.5)))
    assert a == b
    assert a != ""


def test_signature_drop_low_weight_is_magnitude_based():
    """Low-weight dropping uses |weight|: -0.1 drops, -0.6 stays."""
    opts = {"drop_low_weight": True, "low_weight_threshold": 0.3}
    a = calculate_recipe_similarity_signature(_loras(("aaa", 0.8)), options=opts)
    # -0.1 is low magnitude -> dropped, so this matches the single-lora recipe.
    b = calculate_recipe_similarity_signature(
        _loras(("aaa", 0.8), ("bbb", -0.1)), options=opts
    )
    assert a == b
    # -0.6 is a strong negative -> kept, so it must NOT match.
    c = calculate_recipe_similarity_signature(
        _loras(("aaa", 0.8), ("bbb", -0.6)), options=opts
    )
    assert a != c


def test_signature_prompt_matching():
    opts = {"match_prompt": True}
    base = calculate_recipe_similarity_signature(
        _loras(("aaa", 1)), {"prompt": "a cat"}, opts
    )
    same = calculate_recipe_similarity_signature(
        _loras(("aaa", 1)), {"prompt": "A  CAT"}, opts
    )
    diff = calculate_recipe_similarity_signature(
        _loras(("aaa", 1)), {"prompt": "a dog"}, opts
    )
    assert base == same  # case + whitespace insensitive
    assert base != diff


def test_signature_config_matching_ignores_seed():
    opts = {"match_config": True}
    a = calculate_recipe_similarity_signature(
        _loras(("aaa", 1)), {"steps": 20, "seed": 1}, opts
    )
    b = calculate_recipe_similarity_signature(
        _loras(("aaa", 1)), {"steps": 20, "seed": 2}, opts
    )
    c = calculate_recipe_similarity_signature(
        _loras(("aaa", 1)), {"steps": 30}, opts
    )
    assert a == b  # seed excluded
    assert a != c  # steps differ


def test_signature_empty():
    assert calculate_recipe_similarity_signature([]) == ""
    assert calculate_recipe_similarity_signature([{"exclude": True, "hash": "x"}]) == ""


def test_get_retained_lora_weights_drops_low_magnitude():
    weights = get_retained_lora_weights(
        _loras(("aaa", 0.8), ("bbb", -0.1)),
        {"drop_low_weight": True, "low_weight_threshold": 0.3},
    )
    assert weights == {"aaa": 0.8}


# --- Weight clustering -------------------------------------------------------

def test_cluster_splits_when_weights_differ_a_lot():
    wmaps = {"r1": {"aaa": 0.80}, "r2": {"aaa": 0.85}, "r3": {"aaa": 1.20}}
    clusters = cluster_recipes_by_weight(["r1", "r2", "r3"], wmaps, 0.2)
    sets = sorted([sorted(c) for c in clusters])
    assert sets == [["r1", "r2"], ["r3"]]


def test_cluster_zero_tolerance_keeps_together():
    wmaps = {"r1": {"aaa": 0.2}, "r2": {"aaa": 1.5}}
    clusters = cluster_recipes_by_weight(["r1", "r2"], wmaps, 0)
    assert clusters == [["r1", "r2"]]


def test_cluster_single_linkage_chains():
    # 0.8 ~ 0.95 ~ 1.1 pairwise within 0.2 -> one connected component.
    wmaps = {"r1": {"aaa": 0.8}, "r2": {"aaa": 0.95}, "r3": {"aaa": 1.1}}
    clusters = cluster_recipes_by_weight(["r1", "r2", "r3"], wmaps, 0.2)
    assert len(clusters) == 1


# --- Scanner integration -----------------------------------------------------

@pytest.mark.asyncio
async def test_find_similar_recipes_groups_and_splits():
    """Same LoRAs across checkpoints group; very different weights split off."""
    from py.services.recipe_scanner import RecipeScanner

    scanner = MagicMock(spec=RecipeScanner)
    scanner.get_cached_data = AsyncMock()

    cache = MagicMock()
    cache.raw_data = [
        {"id": "r1", "loras": _loras(("aaa", 0.80)), "checkpoint": {"name": "cp1"}},
        {"id": "r2", "loras": _loras(("aaa", 0.85)), "checkpoint": {"name": "cp2"}},
        {"id": "r3", "loras": _loras(("aaa", 1.50))},  # weight far off -> splits away
        {"id": "r4", "loras": _loras(("zzz", 0.80))},  # different LoRA set
    ]
    scanner.get_cached_data.return_value = cache

    result = await RecipeScanner.find_similar_recipes(
        scanner, {"weight_tolerance": 0.2}
    )

    assert len(result) == 1
    group = next(iter(result.values()))
    assert set(group) == {"r1", "r2"}
