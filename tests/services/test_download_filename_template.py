"""Tests for the post-download filename template rename phase."""

import json
from pathlib import Path

import pytest

from py.services.download_manager import DownloadManager
from py.services.service_registry import ServiceRegistry
from py.services.settings_manager import get_settings_manager


class DummyScanner:
    def __init__(self, root: Path):
        self._root = root
        self.model_type = "lora"
        self.updates = []

    def get_model_roots(self):
        return [str(self._root)]

    async def update_single_model_cache(self, original_path, new_path, metadata):
        self.updates.append((original_path, new_path, metadata))
        return True


@pytest.fixture
def download_manager() -> DownloadManager:
    return DownloadManager()


@pytest.fixture(autouse=True)
def no_recipe_scanner(monkeypatch: pytest.MonkeyPatch):
    async def _no_scanner():
        return None

    monkeypatch.setattr(ServiceRegistry, "get_recipe_scanner", _no_scanner)


def _set_template(template: str, model_type: str = "lora") -> None:
    manager = get_settings_manager()
    templates = dict(manager.settings.get("download_filename_templates") or {})
    templates[model_type] = template
    manager.settings["download_filename_templates"] = templates


def _write_model(root: Path, stem: str, model_name: str, sha256: str) -> Path:
    model_path = root / f"{stem}.safetensors"
    model_path.write_bytes(b"model")
    metadata_path = root / f"{stem}.metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "file_name": stem,
                "file_path": model_path.as_posix(),
                "model_name": model_name,
                "sha256": sha256,
                "civitai": {"id": 1},
            }
        )
    )
    return model_path


async def test_download_rename_applies_filename_template(
    tmp_path: Path, download_manager: DownloadManager
):
    _set_template("{model_name}-{hash_short}")
    model_path = _write_model(tmp_path, "V1", "My Model", "abcdef0123456789")
    download_manager._active_downloads["dl1"] = {"file_path": model_path.as_posix()}

    downloaded_metadata = [
        {
            "file_path": model_path.as_posix(),
            "file_name": "V1",
            "model_name": "My Model",
            "sha256": "abcdef0123456789",
            "civitai": {"id": 1},
        }
    ]

    await download_manager._apply_download_filename_template(
        scanner=DummyScanner(tmp_path),
        model_type="lora",
        downloaded_metadata=downloaded_metadata,
        download_id="dl1",
    )

    new_path = tmp_path / "My Model-abcdef0123.safetensors"
    assert new_path.exists()
    assert not model_path.exists()

    new_metadata = json.loads(
        (tmp_path / "My Model-abcdef0123.metadata.json").read_text()
    )
    assert new_metadata["original_file_name"] == "V1"

    assert (
        download_manager._active_downloads["dl1"]["file_path"]
        == new_path.as_posix()
    )


async def test_download_rename_keeps_original_on_conflict(
    tmp_path: Path, download_manager: DownloadManager
):
    _set_template("{model_name}-{hash_short}")
    model_path = _write_model(tmp_path, "V1", "My Model", "abcdef0123456789")
    # Conflicting target already exists.
    (tmp_path / "My Model-abcdef0123.safetensors").write_bytes(b"other")

    downloaded_metadata = [
        {
            "file_path": model_path.as_posix(),
            "file_name": "V1",
            "model_name": "My Model",
            "sha256": "abcdef0123456789",
            "civitai": {"id": 1},
        }
    ]

    # Must not raise: a rename conflict never fails the download.
    await download_manager._apply_download_filename_template(
        scanner=DummyScanner(tmp_path),
        model_type="lora",
        downloaded_metadata=downloaded_metadata,
        download_id=None,
    )

    assert model_path.exists()


async def test_download_rename_noop_without_template(
    tmp_path: Path, download_manager: DownloadManager
):
    _set_template("")
    model_path = _write_model(tmp_path, "V1", "My Model", "abcdef0123456789")

    await download_manager._apply_download_filename_template(
        scanner=DummyScanner(tmp_path),
        model_type="lora",
        downloaded_metadata=[{"file_path": model_path.as_posix()}],
        download_id=None,
    )

    assert model_path.exists()
    assert (tmp_path / "V1.metadata.json").exists()
