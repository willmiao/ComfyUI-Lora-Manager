from __future__ import annotations

import json

from py.services.wildcard_service import WildcardService, contains_dynamic_syntax


def _make_service(monkeypatch, tmp_path):
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    monkeypatch.setattr(
        "py.services.wildcard_service.get_settings_dir",
        lambda create=True: str(settings_dir),
    )
    service = WildcardService()
    service._cached_signature = None
    service._wildcard_dict = {}
    return service, settings_dir / "wildcards"


def test_search_keys_returns_empty_when_directory_missing(monkeypatch, tmp_path):
    service, _wildcards_dir = _make_service(monkeypatch, tmp_path)

    assert service.search_keys("cat") == []


def test_search_keys_loads_txt_yaml_and_json(monkeypatch, tmp_path):
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)
    wildcards_dir.mkdir()

    (wildcards_dir / "animals").mkdir()
    (wildcards_dir / "animals" / "cat.txt").write_text("tabby\nblack cat\n", encoding="utf-8")
    (wildcards_dir / "colors.yaml").write_text(
        "palette:\n  warm:\n    - red\n    - orange\n",
        encoding="utf-8",
    )
    (wildcards_dir / "artists.json").write_text(
        json.dumps({"illustrators/digital": ["alice", "bob"]}),
        encoding="utf-8",
    )

    assert service.search_keys("cat") == ["animals/cat"]
    assert service.search_keys("warm") == ["palette/warm"]
    assert service.search_keys("digital") == ["illustrators/digital"]


def test_search_keys_prefers_exact_and_prefix_matches(monkeypatch, tmp_path):
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)
    wildcards_dir.mkdir()

    (wildcards_dir / "animals").mkdir()
    (wildcards_dir / "animals" / "cat.txt").write_text("tabby\n", encoding="utf-8")
    (wildcards_dir / "animals" / "catgirl.txt").write_text("heroine\n", encoding="utf-8")
    (wildcards_dir / "fantasy_cat.txt").write_text("beast\n", encoding="utf-8")

    results = service.search_keys("cat")

    assert results == ["animals/cat", "animals/catgirl", "fantasy_cat"]


def test_search_keys_supports_offset_and_limit(monkeypatch, tmp_path):
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)
    wildcards_dir.mkdir()

    for name in ("cat", "catgirl", "catmaid"):
        (wildcards_dir / f"{name}.txt").write_text("x\n", encoding="utf-8")

    assert service.search_keys("cat", limit=1, offset=1) == ["catgirl"]


def test_get_metadata_creates_directory_and_reports_formats(monkeypatch, tmp_path):
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)

    metadata = service.get_metadata(create_dir=True)

    assert metadata.has_wildcards is False
    assert metadata.wildcards_dir == str(wildcards_dir)
    assert metadata.supported_formats == (".txt", ".yaml", ".yml", ".json")
    assert wildcards_dir.is_dir()


def test_expand_text_resolves_nested_wildcards(monkeypatch, tmp_path):
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)
    wildcards_dir.mkdir()

    (wildcards_dir / "flower.txt").write_text("rose\n__color__ lily\n", encoding="utf-8")
    (wildcards_dir / "color.txt").write_text("red\nblue\n", encoding="utf-8")

    expanded = service.expand_text("__flower__", seed=7)

    assert expanded in {"rose", "red lily", "blue lily"}
    assert "__" not in expanded


def test_expand_text_resolves_dynamic_prompt_and_multi_select(monkeypatch, tmp_path):
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)
    wildcards_dir.mkdir()

    expanded = service.expand_text("{2$$, $$red|blue|green}", seed=3)

    assert expanded.count(", ") == 1
    assert set(expanded.split(", ")).issubset({"red", "blue", "green"})


def test_expand_text_resolves_wildcard_glob(monkeypatch, tmp_path):
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)
    wildcards_dir.mkdir()

    (wildcards_dir / "animals").mkdir()
    (wildcards_dir / "animals" / "cat.txt").write_text("tabby\n", encoding="utf-8")
    (wildcards_dir / "animals" / "dog.txt").write_text("retriever\n", encoding="utf-8")

    expanded = service.expand_text("__animals/*__", seed=1)

    assert expanded in {"tabby", "retriever"}


def test_expand_text_is_deterministic_with_seed(monkeypatch, tmp_path):
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)
    wildcards_dir.mkdir()

    (wildcards_dir / "color.txt").write_text("red\nblue\ngreen\n", encoding="utf-8")

    first = service.expand_text("__color__", seed=123)
    second = service.expand_text("__color__", seed=123)

    assert first == second


def test_expand_text_leaves_unresolved_reference_visible(monkeypatch, tmp_path):
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)
    wildcards_dir.mkdir()

    assert service.expand_text("__missing__", seed=1) == "__missing__"


def test_contains_dynamic_syntax_detects_wildcards_and_options():
    assert contains_dynamic_syntax("plain text") is False
    assert contains_dynamic_syntax("__flower__") is True
    assert contains_dynamic_syntax("{red|blue}") is True
    assert contains_dynamic_syntax("{2$$, $$red|blue|green}") is True


# ---------------------------------------------------------------------------
# _pick_weighted_or_plain
# ---------------------------------------------------------------------------


def test_pick_weighted_or_plain_plain_values(monkeypatch, tmp_path):
    """Plain values without :: are picked via rng.choice (fast path)."""
    service, _ = _make_service(monkeypatch, tmp_path)

    import random
    rng = random.Random(42)

    result = service._pick_weighted_or_plain(["red", "green", "blue"], rng)
    assert result in {"red", "green", "blue"}
    assert "::" not in result


def test_pick_weighted_or_plain_deterministic_with_seed(monkeypatch, tmp_path):
    """Same seed produces the same result for plain values."""
    service, _ = _make_service(monkeypatch, tmp_path)

    import random
    first = service._pick_weighted_or_plain(["a", "b", "c"], random.Random(99))
    second = service._pick_weighted_or_plain(["a", "b", "c"], random.Random(99))
    assert first == second


def test_pick_weighted_or_plain_weighted_values(monkeypatch, tmp_path):
    """Weighted values use weighted selection and strip the N:: prefix."""
    service, _ = _make_service(monkeypatch, tmp_path)

    import random
    values = ["3::apple", "1::banana"]
    results = {"apple": 0, "banana": 0}
    for seed in range(4000):
        result = service._pick_weighted_or_plain(values, random.Random(seed))
        assert result in results, f"Unexpected result: {result!r}"
        assert "::" not in result
        results[result] += 1

    total = results["apple"] + results["banana"]
    # 3:1 weight → apple ≈ 75%, banana ≈ 25%
    assert 2700 < results["apple"] < 3300, f"apple count out of range: {results['apple']}"
    assert 700 < results["banana"] < 1300, f"banana count out of range: {results['banana']}"


def test_pick_weighted_or_plain_weight_one_values(monkeypatch, tmp_path):
    """Values with explicit 1:: prefix have prefix stripped but are not weighted."""
    service, _ = _make_service(monkeypatch, tmp_path)

    import random
    # All weights are 1.0 → no actual weighting, but :: prefix is stripped
    values = ["1::foo", "1::bar"]
    rng = random.Random(42)
    results = {service._pick_weighted_or_plain(values, rng) for _ in range(200)}
    assert results == {"foo", "bar"}
    # Ensure the prefix is always stripped
    for result in results:
        assert "::" not in result


def test_pick_weighted_or_plain_mixed_weighted_and_plain(monkeypatch, tmp_path):
    """Mixed list with some weighted and some unweighted values."""
    service, _ = _make_service(monkeypatch, tmp_path)

    import random
    values = ["5::x", "y", "z"]  # x has weight 5, y/z have default weight 1
    results = {"x": 0, "y": 0, "z": 0}
    for seed in range(4000):
        result = service._pick_weighted_or_plain(values, random.Random(seed))
        assert result in results
        assert "::" not in result
        results[result] += 1

    # x (5) vs combined y+z (1+1=2) → ~71% / ~29%
    x_pct = results["x"] / sum(results.values())
    assert 0.65 < x_pct < 0.78, f"x proportion out of range: {x_pct:.3f}"


def test_pick_weighted_or_plain_invalid_weight_prefix(monkeypatch, tmp_path):
    """Invalid numeric prefix (e.g. 1.2.3) is NOT treated as a weight and
    the prefix is NOT stripped, matching the updated strict regex."""
    service, _ = _make_service(monkeypatch, tmp_path)

    import random
    rng = random.Random(42)

    # "1.2.3::a" is not a valid number → treated as plain text value
    result = service._pick_weighted_or_plain(["1.2.3::a", "b"], rng)
    # It should keep the full text including :: because the prefix isn't a
    # valid numeric weight according to the strict regex
    assert result == "1.2.3::a" or result == "b"


def test_pick_weighted_or_plain_glob_aggregation(monkeypatch, tmp_path):
    """Weighted wildcard resolution through glob aggregation (__*__)."""
    service, wildcards_dir = _make_service(monkeypatch, tmp_path)
    wildcards_dir.mkdir()

    (wildcards_dir / "animals").mkdir()
    (wildcards_dir / "animals" / "cat.txt").write_text("3::tabby\n1::persian\n", encoding="utf-8")
    (wildcards_dir / "animals" / "dog.txt").write_text("retriever\npoodle\n", encoding="utf-8")

    # __animals/*__ aggregates all values across both files
    # Weighted values should have :: stripped
    results = {"tabby": 0, "persian": 0, "retriever": 0, "poodle": 0}
    for seed in range(4000):
        expanded = service.expand_text("__animals/*__", seed=seed)
        assert expanded in results, f"Unexpected result: {expanded!r}"
        assert "::" not in expanded
        results[expanded] += 1

    # tabby (3) vs persian (1) → ~75% / ~25% within the cat subset
    cat_total = results["tabby"] + results["persian"]
    if cat_total > 0:
        tabby_pct = results["tabby"] / cat_total
        assert 0.65 < tabby_pct < 0.85, f"tabby proportion out of range: {tabby_pct:.3f}"
