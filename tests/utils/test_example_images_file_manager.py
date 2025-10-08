from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils.example_images_file_manager import ExampleImagesFileManager


class JsonRequest:
    def __init__(self, payload: Dict[str, Any], query: Dict[str, str] | None = None) -> None:
        self._payload = payload
        self.query = query or {}

    async def json(self) -> Dict[str, Any]:
        return self._payload


@pytest.fixture(autouse=True)
def restore_settings() -> None:
    manager = get_settings_manager()
    original = manager.settings.copy()
    try:
        yield
    finally:
        manager.settings.clear()
        manager.settings.update(original)


async def test_open_folder_requires_existing_model_directory(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)
    model_hash = "a" * 64
    model_folder = tmp_path / model_hash
    model_folder.mkdir()
    (model_folder / "image.png").write_text("data", encoding="utf-8")

    popen_calls: list[list[str]] = []
    startfile_calls: list[str] = []

    class DummyPopen:
        def __init__(self, cmd, *_args, **_kwargs):
            popen_calls.append(cmd)

    def dummy_startfile(path):
        startfile_calls.append(path)

    monkeypatch.setattr("subprocess.Popen", DummyPopen)
    monkeypatch.setattr("os.startfile", dummy_startfile, raising=False)

    request = JsonRequest({"model_hash": model_hash})
    response = await ExampleImagesFileManager.open_folder(request)
    body = json.loads(response.text)

    assert body["success"] is True
    # On Windows, os.startfile is used; on other platforms, subprocess.Popen
    if os.name == 'nt':
        assert startfile_calls
        assert model_hash in startfile_calls[0]
    else:
        assert popen_calls
        assert model_hash in popen_calls[0][-1]


async def test_open_folder_rejects_invalid_paths(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)

    def fake_get_model_folder(_hash):
        return str(tmp_path.parent / "outside")

    monkeypatch.setattr("py.utils.example_images_file_manager.get_model_folder", fake_get_model_folder)

    request = JsonRequest({"model_hash": "a" * 64})
    response = await ExampleImagesFileManager.open_folder(request)
    body = json.loads(response.text)

    assert response.status == 400
    assert body["success"] is False


async def test_get_files_lists_supported_media(tmp_path) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)
    model_hash = "b" * 64
    model_folder = tmp_path / model_hash
    model_folder.mkdir()
    (model_folder / "image.png").write_text("data", encoding="utf-8")
    (model_folder / "video.webm").write_text("data", encoding="utf-8")
    (model_folder / "notes.txt").write_text("skip", encoding="utf-8")

    request = JsonRequest({}, {"model_hash": model_hash})
    response = await ExampleImagesFileManager.get_files(request)
    body = json.loads(response.text)

    assert response.status == 200
    names = {entry["name"] for entry in body["files"]}
    assert names == {"image.png", "video.webm"}


async def test_has_images_reports_presence(tmp_path) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)
    model_hash = "c" * 64
    model_folder = tmp_path / model_hash
    model_folder.mkdir()
    (model_folder / "image.png").write_text("data", encoding="utf-8")

    request = JsonRequest({}, {"model_hash": model_hash})
    response = await ExampleImagesFileManager.has_images(request)
    body = json.loads(response.text)

    assert body["has_images"] is True

    empty_request = JsonRequest({}, {"model_hash": "missing"})
    empty_response = await ExampleImagesFileManager.has_images(empty_request)
    empty_body = json.loads(empty_response.text)
    assert empty_body["has_images"] is False


async def test_has_images_requires_model_hash() -> None:
    response = await ExampleImagesFileManager.has_images(JsonRequest({}, {}))
    body = json.loads(response.text)
    assert response.status == 400
    assert body["success"] is False
