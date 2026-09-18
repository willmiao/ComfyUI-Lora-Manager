import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from py.routes.handlers.misc_handlers import FileSystemHandler


def _make_handler() -> FileSystemHandler:
    # browse_directory/validate_path never touch the settings service
    return FileSystemHandler(settings_service=SimpleNamespace())


class _Request:
    def __init__(self, body: dict) -> None:
        self._body = body

    async def json(self):
        return self._body


async def _browse(handler: FileSystemHandler, path: str):
    response = await handler.browse_directory(_Request({"path": path}))
    return response, json.loads(response.text)


async def _validate(handler: FileSystemHandler, path: str, expect: str = "directory"):
    response = await handler.validate_path(
        _Request({"path": path, "expect": expect})
    )
    return response, json.loads(response.text)


@pytest.mark.asyncio
async def test_browse_directory_empty_path_defaults_to_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    response, payload = await _browse(_make_handler(), "")

    assert response.status == 200
    assert payload["success"] is True
    assert payload["current_path"] == str(tmp_path)


@pytest.mark.asyncio
async def test_browse_directory_lists_subdirs_sorted_and_filters(tmp_path):
    (tmp_path / "zeta").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "__pycache__").mkdir()

    response, payload = await _browse(_make_handler(), str(tmp_path))

    assert response.status == 200
    assert payload["success"] is True
    assert [d["name"] for d in payload["directories"]] == ["alpha", "zeta"]
    assert payload["directory_count"] == 2


@pytest.mark.asyncio
async def test_browse_directory_missing_returns_404(tmp_path):
    response, payload = await _browse(_make_handler(), str(tmp_path / "nope"))

    assert response.status == 404
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_browse_directory_file_path_returns_400(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")

    response, payload = await _browse(_make_handler(), str(file_path))

    assert response.status == 400
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_browse_directory_relative_path_returns_403(monkeypatch):
    # resolve() normally absolutizes relative paths against the cwd; bypass it
    # to exercise the access-denied branch directly.
    monkeypatch.setattr(Path, "resolve", lambda self: self)

    response, payload = await _browse(_make_handler(), "relative/path")

    assert response.status == 403
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_validate_path_existing_directory(tmp_path):
    response, payload = await _validate(_make_handler(), str(tmp_path))

    assert response.status == 200
    assert payload == {
        "success": True,
        "path": os.path.abspath(str(tmp_path)),
        "exists": True,
        "is_directory": True,
        "readable": True,
        "writable": True,
        "error_code": None,
    }


@pytest.mark.asyncio
async def test_validate_path_not_found(tmp_path):
    response, payload = await _validate(_make_handler(), str(tmp_path / "missing"))

    assert response.status == 200
    assert payload["success"] is True
    assert payload["exists"] is False
    assert payload["error_code"] == "path_not_found"


@pytest.mark.asyncio
async def test_validate_path_file_when_directory_expected(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")

    response, payload = await _validate(_make_handler(), str(file_path))

    assert response.status == 200
    assert payload["error_code"] == "not_a_directory"
    assert payload["exists"] is True
    assert payload["is_directory"] is False


@pytest.mark.asyncio
async def test_validate_path_expect_file_on_file(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")

    response, payload = await _validate(_make_handler(), str(file_path), expect="file")

    assert response.status == 200
    assert payload["error_code"] is None
    assert payload["exists"] is True
    assert payload["is_directory"] is False


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="root bypasses permission checks",
)
@pytest.mark.asyncio
async def test_validate_path_unreadable_directory(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        response, payload = await _validate(_make_handler(), str(locked))
    finally:
        locked.chmod(0o755)

    assert response.status == 200
    assert payload["error_code"] == "not_readable"
    assert payload["readable"] is False


@pytest.mark.asyncio
async def test_validate_path_empty_path_returns_400():
    response, payload = await _validate(_make_handler(), "")

    assert response.status == 400
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_validate_path_expands_user(tmp_path, monkeypatch):
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    response, payload = await _validate(_make_handler(), "~/subdir")

    assert response.status == 200
    assert payload["error_code"] is None
    assert payload["path"] == os.path.abspath(str(subdir))
