from __future__ import annotations

import json
import zipfile

import pytest

from py.services.wildcard_parser import (
    WildcardParseError,
    parse_wildcard_artifact,
    read_wildcard_source,
    wildcard_reference_problem,
)


def test_parse_zip_preserves_paths_and_flattens_structured_files(tmp_path):
    artifact = tmp_path / "pack.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("wildcards/animals/cat.txt", "tabby\nblack cat\n")
        archive.writestr("palette.yaml", "warm:\n  - red\n  - orange\n")
        archive.writestr("artists.json", json.dumps({"digital": ["alice", "bob"]}))
        archive.writestr("readme.md", "not a wildcard")

    parsed = parse_wildcard_artifact(str(artifact))

    assert [entry.key for entry in parsed.entries] == [
        "digital",
        "warm",
        "wildcards/animals/cat",
    ]
    assert parsed.entries[1].values == ("red", "orange")
    assert parsed.value_count == 6
    assert parsed.unsupported_files == ["readme.md"]
    assert read_wildcard_source(str(artifact), "palette.yaml")["content"] == (
        "warm:\n  - red\n  - orange\n"
    )


def test_parse_zip_reports_duplicate_keys_and_unsafe_members(tmp_path):
    artifact = tmp_path / "pack.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("Color.txt", "red\n")
        archive.writestr("color.txt", "blue\n")
        archive.writestr("../outside.txt", "bad\n")

    parsed = parse_wildcard_artifact(str(artifact))

    assert len(parsed.entries) == 1
    assert parsed.entries[0].values == ("red",)
    assert any("Duplicate wildcard key 'color'" in error for error in parsed.errors)
    assert any("Unsafe archive member" in error for error in parsed.errors)


def test_parse_flags_keys_that_cannot_be_referenced(tmp_path):
    artifact = tmp_path / "edge.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("anime/bang_dream!.txt", "punctuated is fine\n")
        archive.writestr("broken__key.txt", "value\n")
        archive.writestr("option{s}.txt", "value\n")

    parsed = parse_wildcard_artifact(str(artifact))

    summaries = {entry.key: entry.summary() for entry in parsed.entries}
    assert summaries["anime/bang_dream!"]["reference_problem"] is None
    assert "closes the token" in summaries["broken__key"]["reference_problem"]
    assert "option group" in summaries["option{s}"]["reference_problem"]
    assert {item["key"] for item in parsed.unreferenceable} == {
        "broken__key",
        "option{s}",
    }


def test_reference_problem_rejects_line_breaks():
    assert "line break" in wildcard_reference_problem("a\nb")
    assert wildcard_reference_problem("anime/bang_dream!") is None


def test_parse_rejects_artifacts_without_wildcard_entries(tmp_path):
    artifact = tmp_path / "empty.json"
    artifact.write_text('{"not": "a list"}', encoding="utf-8")

    with pytest.raises(WildcardParseError, match="No usable wildcard entries"):
        parse_wildcard_artifact(str(artifact))
