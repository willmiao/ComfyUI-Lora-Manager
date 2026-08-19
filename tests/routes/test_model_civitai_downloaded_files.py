"""Unit tests for per-file downloaded-state matching (#1058)."""

from py.routes.handlers.model_handlers import ModelCivitaiHandler


VERSION = {
    "id": 42,
    "files": [
        {
            "id": 1001,
            "name": "file-a.safetensors",
            "hashes": {"SHA256": "AAA111"},
        },
        {
            "id": 1002,
            "name": "file-b.safetensors",
            "hashes": {"SHA256": "BBB222"},
        },
    ],
}


def _entry(file_name: str, sha256: str = "", file_path: str | None = None):
    return {
        "file_name": file_name,
        "file_path": file_path or f"/models/{file_name}.safetensors",
        "sha256": sha256,
    }


def test_matches_by_sha256():
    entries = [_entry("renamed-locally", "bbb222")]
    result = ModelCivitaiHandler._match_downloaded_files(VERSION, entries)
    assert result == [
        {
            "fileId": 1002,
            "fileName": "file-b.safetensors",
            "filePath": "/models/renamed-locally.safetensors",
        }
    ]


def test_falls_back_to_name_when_hash_missing():
    entries = [_entry("file-a", "")]
    result = ModelCivitaiHandler._match_downloaded_files(VERSION, entries)
    assert [r["fileId"] for r in result] == [1001]


def test_hash_takes_precedence_over_name():
    # Hash points at file-b while the name points at file-a: hash wins.
    entries = [_entry("file-a", "bbb222")]
    result = ModelCivitaiHandler._match_downloaded_files(VERSION, entries)
    assert [r["fileId"] for r in result] == [1002]


def test_unmatched_entries_are_skipped():
    entries = [
        _entry("unrelated", "ccc333"),
        _entry("file-b", ""),  # name match
    ]
    result = ModelCivitaiHandler._match_downloaded_files(VERSION, entries)
    assert [r["fileId"] for r in result] == [1002]


def test_multiple_files_of_same_version():
    entries = [
        _entry("file-a", "aaa111"),
        _entry("file-b", "bbb222"),
    ]
    result = ModelCivitaiHandler._match_downloaded_files(VERSION, entries)
    assert [r["fileId"] for r in result] == [1001, 1002]


def test_empty_inputs():
    assert ModelCivitaiHandler._match_downloaded_files(VERSION, []) == []
    assert ModelCivitaiHandler._match_downloaded_files({"id": 1}, [_entry("x")]) == []
    assert ModelCivitaiHandler._match_downloaded_files(VERSION, None) == []
