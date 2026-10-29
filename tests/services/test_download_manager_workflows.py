"""DownloadManager support for the "workflow" model type.

Covers type routing (Workflows/ComfyWorkflows), the opt-in gate, existence
checks against the workflow scanner, the default save root, file selection
for weight-less workflow versions, and the rule that workflow archives are
kept byte-identical (never extracted).
"""

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from py.services import aria2_transfer_state
from py.services import download_manager
from py.services.download_manager import DownloadManager
from py.services.service_registry import ServiceRegistry
from py.services.settings_manager import SettingsManager, get_settings_manager
from py.utils.models import WorkflowMetadata


@pytest.fixture(autouse=True)
def reset_download_manager():
    """Ensure each test operates on a fresh singleton."""
    DownloadManager._instance = None
    yield
    DownloadManager._instance = None


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch, tmp_path):
    """Point settings writes at a temporary directory to avoid touching real files."""
    manager = get_settings_manager()
    default_settings = manager._get_default_settings()
    default_settings.update(
        {
            "enable_workflows": True,
            "skip_previously_downloaded_model_versions": False,
            "download_skip_base_models": [],
            "download_path_templates": {},
            "download_filename_templates": {},
        }
    )
    monkeypatch.setattr(manager, "settings", default_settings)
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)


@pytest.fixture(autouse=True)
def isolate_aria2_state(monkeypatch, tmp_path):
    state_path = tmp_path / "cache" / "aria2" / "downloads.json"
    monkeypatch.setattr(
        aria2_transfer_state,
        "get_aria2_state_path",
        lambda: str(state_path),
    )


class DummyScanner:
    def __init__(self, exists: bool = False, roots=None):
        self.exists = exists
        self.calls = []
        self._roots = list(roots or [])
        self._cache = SimpleNamespace(raw_data=[])

    async def check_model_version_exists(self, version_id):
        self.calls.append(version_id)
        return self.exists

    async def get_cached_data(self):
        return self._cache

    def get_model_roots(self):
        return list(self._roots)


@pytest.fixture
def scanners(monkeypatch):
    lora_scanner = DummyScanner()
    checkpoint_scanner = DummyScanner()
    embedding_scanner = DummyScanner()
    other_scanner = DummyScanner()
    workflow_scanner = DummyScanner()

    monkeypatch.setattr(
        ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=lora_scanner)
    )
    monkeypatch.setattr(
        ServiceRegistry,
        "get_checkpoint_scanner",
        AsyncMock(return_value=checkpoint_scanner),
    )
    monkeypatch.setattr(
        ServiceRegistry,
        "get_embedding_scanner",
        AsyncMock(return_value=embedding_scanner),
    )
    monkeypatch.setattr(
        ServiceRegistry,
        "get_other_scanner",
        AsyncMock(return_value=other_scanner),
    )
    monkeypatch.setattr(
        ServiceRegistry,
        "get_workflow_scanner",
        AsyncMock(return_value=workflow_scanner),
    )

    return SimpleNamespace(
        lora=lora_scanner,
        checkpoint=checkpoint_scanner,
        embedding=embedding_scanner,
        other=other_scanner,
        workflow=workflow_scanner,
    )


def _workflow_payload(civitai_type: str, *, files=None) -> dict:
    return {
        "id": 42,
        "model": {"type": civitai_type, "tags": ["utility"], "name": "Flow"},
        "baseModel": "SDXL 1.0",
        "creator": {"username": "Author"},
        "files": files
        or [
            {
                "id": 7,
                "type": "Config",
                "primary": True,
                "downloadUrl": "https://example.invalid/flow.json",
                "name": "flow.json",
                "hashes": {"SHA256": "ab" * 32},
            }
        ],
    }


@pytest.fixture
def metadata_provider(monkeypatch):
    class DummyProvider:
        def __init__(self):
            self.calls = []
            self.payload = _workflow_payload("Workflows")

        async def get_model_version(self, model_id, model_version_id):
            self.calls.append((model_id, model_version_id))
            return self.payload

    provider = DummyProvider()
    monkeypatch.setattr(
        download_manager,
        "get_default_metadata_provider",
        AsyncMock(return_value=provider),
    )
    return provider


def _capture_execute(monkeypatch, captured):
    async def fake_execute_download(self, **kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(
        DownloadManager, "_execute_download", fake_execute_download, raising=False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("civitai_type", ["Workflows", "ComfyWorkflows"])
async def test_download_accepts_workflow_model_types(
    monkeypatch, scanners, metadata_provider, tmp_path, civitai_type
):
    metadata_provider.payload = _workflow_payload(civitai_type)

    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, save_dir=str(tmp_path)
    )

    assert result["success"] is True
    assert captured["model_type"] == "workflow"
    assert isinstance(captured["metadata"], WorkflowMetadata)
    assert captured["metadata"].file_name == "flow"


@pytest.mark.asyncio
async def test_download_rejects_workflows_when_feature_disabled(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    manager_settings = get_settings_manager()
    manager_settings.settings["enable_workflows"] = False

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, save_dir=str(tmp_path)
    )

    assert result["success"] is False
    assert result["reason"] == "workflows_disabled"


@pytest.mark.asyncio
async def test_early_gate_checks_workflow_scanner(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    scanners.workflow.exists = True

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, save_dir=str(tmp_path)
    )

    assert result["success"] is False
    assert "workflow library" in result["error"]
    assert 99 in scanners.workflow.calls


@pytest.mark.asyncio
async def test_early_gate_skips_workflow_scanner_when_disabled(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    get_settings_manager().settings["enable_workflows"] = False
    # Route the download to a non-workflow type so the run proceeds.
    metadata_provider.payload = {
        "id": 42,
        "model": {"type": "LORA", "tags": []},
        "baseModel": "SDXL 1.0",
        "files": [
            {
                "type": "Model",
                "primary": True,
                "downloadUrl": "https://example.invalid/file.safetensors",
                "name": "file.safetensors",
            }
        ],
    }

    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, save_dir=str(tmp_path)
    )

    assert result["success"] is True
    assert scanners.workflow.calls == []


@pytest.mark.asyncio
async def test_default_paths_use_first_workflow_root(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    workflow_root = tmp_path / "workflows"
    workflow_root.mkdir()
    scanners.workflow._roots = [str(workflow_root)]

    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )

    assert result["success"] is True
    assert captured["save_dir"] == str(workflow_root)


@pytest.mark.asyncio
async def test_default_paths_error_without_workflow_root(
    monkeypatch, scanners, metadata_provider
):
    scanners.workflow._roots = []

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )

    assert result["success"] is False
    assert "workflow folder" in result["error"]


@pytest.mark.asyncio
async def test_scanner_dispatch_resolves_workflow(monkeypatch, scanners):
    manager = DownloadManager()
    scanner = await manager._get_scanner_for_model_type("workflow")
    assert scanner is scanners.workflow


def test_select_workflow_download_file_ranking():
    files = [
        {"id": 1, "type": "Other", "name": "notes.txt"},
        {"id": 2, "type": "Archive", "name": "pack.zip"},
        {"id": 3, "type": "Config", "name": "flow.json"},
    ]
    selected = DownloadManager._select_workflow_download_file(files)
    assert selected["name"] == "flow.json"

    # Without a JSON the archive wins; a primary flag breaks ties.
    files = files[:2]
    assert DownloadManager._select_workflow_download_file(files)["name"] == "pack.zip"
    files[0]["primary"] = True
    assert DownloadManager._select_workflow_download_file(files)["name"] == "notes.txt"

    assert DownloadManager._select_workflow_download_file([]) is None


def test_build_metadata_for_resume_uses_workflow_metadata():
    manager = DownloadManager()
    metadata = manager._build_metadata_for_resume(
        model_type="workflow",
        version_info=_workflow_payload("Workflows"),
        file_info={"name": "flow.zip", "hashes": {}},
        save_path="/tmp/flow.zip",
    )
    assert isinstance(metadata, WorkflowMetadata)
    assert metadata.file_name == "flow"


@pytest.mark.asyncio
async def test_workflow_download_keeps_zip_archive_intact(
    monkeypatch, scanners, tmp_path
):
    """A downloaded workflow zip is the library artifact: never extracted."""
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
    }
    zip_path = tmp_path / "pack.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("workflow.json", json.dumps(workflow))
    zip_bytes = zip_path.read_bytes()

    async def fake_download_file(self, url, save_path, **kwargs):
        with open(save_path, "wb") as handle:
            handle.write(zip_bytes)
        return True, ""

    monkeypatch.setattr(
        DownloadManager, "_download_model_file", fake_download_file, raising=False
    )

    added = []

    class PipelineScanner:
        def _find_root_for_file(self, file_path):
            return None

        def adjust_metadata(self, metadata, file_path, root_path):
            return metadata

        async def add_model_to_cache(self, metadata_dict, relative_path):
            added.append(metadata_dict)

    monkeypatch.setattr(
        ServiceRegistry,
        "get_workflow_scanner",
        AsyncMock(return_value=PipelineScanner()),
    )

    save_path = tmp_path / "pack_downloaded.zip"
    metadata = WorkflowMetadata(
        file_name="pack_downloaded",
        model_name="pack_downloaded",
        file_path=str(save_path),
        size=0,
        modified=0,
        sha256="",
        base_model="Unknown",
        preview_url="",
    )

    manager = DownloadManager()
    result = await manager._execute_download(
        download_urls=["https://example.invalid/pack.zip"],
        save_dir=str(tmp_path),
        metadata=metadata,
        version_info={"id": 42, "model": {"type": "Workflows"}, "images": []},
        relative_path="",
        model_type="workflow",
    )

    assert result["success"] is True
    # The archive is still there, unextracted, and no member files appeared.
    assert save_path.exists()
    assert save_path.read_bytes() == zip_bytes
    assert not (tmp_path / "workflow.json").exists()
    assert added and added[0]["file_path"].endswith("pack_downloaded.zip")
