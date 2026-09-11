import json
import logging
import os
from pathlib import Path

import pytest

from py.routes.handlers.recipe_handlers import BatchImportHandler


def _make_handler() -> BatchImportHandler:
    return BatchImportHandler(
        ensure_dependencies_ready=None,  # browse_directory never calls it
        recipe_scanner_getter=lambda: None,
        civitai_client_getter=lambda: None,
        logger=logging.getLogger(__name__),
        batch_import_service=None,
    )


class _Request:
    def __init__(self, path: str) -> None:
        self._path = path

    async def json(self):
        return {"path": self._path}


async def _browse(handler: BatchImportHandler, path: str):
    response = await handler.browse_directory(_Request(path))
    return response, json.loads(response.text)


@pytest.mark.asyncio
async def test_browse_directory_lists_subdirs_and_images(tmp_path):
    (tmp_path / "subdir").mkdir()
    (tmp_path / "photo.png").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("not an image")

    response, payload = await _browse(_make_handler(), str(tmp_path))

    assert response.status == 200
    assert payload["success"] is True
    assert payload["current_path"] == str(tmp_path)
    assert [d["name"] for d in payload["directories"]] == ["subdir"]
    assert [f["name"] for f in payload["image_files"]] == ["photo.png"]
    assert payload["parent_path"] == str(tmp_path.parent)


@pytest.mark.asyncio
async def test_browse_directory_empty_path_defaults_to_home(tmp_path, monkeypatch):
    # The frontend no longer sends the POSIX-only "/" as the initial path; an
    # empty path must resolve to the user's home directory (#1106).
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    response, payload = await _browse(_make_handler(), "")

    assert response.status == 200
    assert payload["success"] is True
    assert payload["current_path"] == str(tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX root semantics")
@pytest.mark.asyncio
async def test_browse_directory_root_has_no_parent():
    _, payload = await _browse(_make_handler(), os.path.abspath(os.sep))

    assert payload["success"] is True
    assert payload["parent_path"] is None


@pytest.mark.asyncio
async def test_browse_directory_windows_drives_token(monkeypatch):
    # The token branch returns before any pathlib use, so faking os.name is
    # enough to exercise it on POSIX (#1106).
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os, "listdrives", lambda: ["C:\\", "D:\\"], raising=False)

    response, payload = await _browse(
        _make_handler(), BatchImportHandler.WINDOWS_DRIVES_TOKEN
    )

    assert response.status == 200
    assert payload["success"] is True
    assert payload["current_path"] == ""
    assert payload["parent_path"] is None
    assert [d["name"] for d in payload["directories"]] == ["C:\\", "D:\\"]


@pytest.mark.asyncio
async def test_browse_directory_missing_directory_returns_404(tmp_path):
    response, payload = await _browse(
        _make_handler(), str(tmp_path / "does-not-exist")
    )

    assert response.status == 404
    assert payload["success"] is False
