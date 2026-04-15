from __future__ import annotations

import json

from py.services.wildcard_service import WildcardService


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
