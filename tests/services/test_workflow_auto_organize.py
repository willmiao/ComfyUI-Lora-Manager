"""Auto-Organize for the workflow library (issue #1177).

The workflow page reuses the shared auto-organize endpoint; these tests pin
the workflow-specific pieces: the default path template and the fact that a
move carries the workflow sidecars (derived document, metadata, preview)
along with the artifact itself.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from py import config as config_module
from py.services.model_cache import ModelCache
from py.services.model_file_service import ModelFileService
from py.services.model_hash_index import ModelHashIndex
from py.services.settings_manager import get_settings_manager
from py.services.workflow_scanner import WorkflowScanner
from py.utils.models import WorkflowMetadata


def _normalize(path) -> str:
    return str(path).replace(os.sep, "/")


def _make_workflow_scanner(root: Path) -> WorkflowScanner:
    """Wire a WorkflowScanner for a move without async initialization."""
    scanner = object.__new__(WorkflowScanner)
    scanner.model_type = "workflow"
    scanner.model_class = WorkflowMetadata
    scanner.file_extensions = {".json", ".zip", ".png", ".webp"}
    scanner._cache = None
    scanner._cache_version = 0
    scanner._hash_index = ModelHashIndex()
    scanner._tags_count = {}
    scanner._excluded_models = []
    scanner._is_initializing = False
    scanner._persistent_cache = MagicMock()
    scanner._name_display_mode = "model_name"
    scanner._cancel_requested = False
    scanner._move_locks = {}
    scanner._all_folders_backfill_running = False
    scanner.get_model_roots = lambda: [_normalize(root)]
    return scanner


def _cache_entry(file_path: str, folder: str) -> dict:
    return {
        "file_path": _normalize(file_path),
        "file_name": "portrait",
        "model_name": "portrait",
        "folder": folder,
        "sha256": "abc123",
        "base_model": "SDXL 1.0",
        "tags": [],
        "civitai": {},
    }


@pytest.fixture
def workflow_library(tmp_path, monkeypatch):
    root = tmp_path / "workflows"
    (root / "old").mkdir(parents=True)
    monkeypatch.setattr(config_module.config, "workflows_roots", [_normalize(root)])
    monkeypatch.setattr(
        get_settings_manager(), "is_workflows_enabled", lambda: True
    )
    # Pin the workflow template so the test does not depend on the default.
    monkeypatch.setitem(
        get_settings_manager().settings,
        "download_path_templates",
        {"workflow": "{base_model}"},
    )
    return root


@pytest.mark.asyncio
async def test_auto_organize_moves_workflow_with_its_sidecars(workflow_library: Path):
    old_dir = workflow_library / "old"
    workflow_path = old_dir / "portrait.json"
    workflow_path.write_text(
        json.dumps({"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}),
        encoding="utf-8",
    )
    (old_dir / "portrait.workflow.json").write_text(
        json.dumps({"1": {"class_type": "CheckpointLoaderSimple"}}),
        encoding="utf-8",
    )
    (old_dir / "portrait.preview.webp").write_bytes(b"preview")
    (old_dir / "portrait.metadata.json").write_text(
        json.dumps(
            {
                "file_path": _normalize(workflow_path),
                "file_name": "portrait",
                "model_name": "portrait",
                "sha256": "abc123",
                "sub_type": "workflow",
                "base_model": "SDXL 1.0",
                "tags": [],
            }
        ),
        encoding="utf-8",
    )

    scanner = _make_workflow_scanner(workflow_library)
    scanner._cache = ModelCache(
        raw_data=[_cache_entry(workflow_path, "old")], folders=["old"]
    )
    service = ModelFileService(scanner, "workflow")

    result = await service.auto_organize_models(
        file_paths=[_normalize(workflow_path)]
    )

    target_dir = workflow_library / "SDXL 1.0"
    assert result.operation_type == "bulk"
    assert result.success_count == 1
    assert (target_dir / "portrait.json").is_file()
    assert (target_dir / "portrait.workflow.json").is_file()
    assert (target_dir / "portrait.preview.webp").read_bytes() == b"preview"
    # The metadata sidecar follows the artifact and records the new path.
    moved_metadata = json.loads(
        (target_dir / "portrait.metadata.json").read_text(encoding="utf-8")
    )
    assert moved_metadata["file_path"] == _normalize(target_dir / "portrait.json")

    # The empty source folder is cleaned up after a bulk run.
    assert not (old_dir / "portrait.json").exists()
    assert not old_dir.exists()


@pytest.mark.asyncio
async def test_auto_organize_skips_workflow_already_in_place(workflow_library: Path):
    target_dir = workflow_library / "SDXL 1.0"
    target_dir.mkdir()
    workflow_path = target_dir / "portrait.json"
    workflow_path.write_text("{}", encoding="utf-8")

    scanner = _make_workflow_scanner(workflow_library)
    scanner._cache = ModelCache(
        raw_data=[_cache_entry(workflow_path, "SDXL 1.0")],
        folders=["SDXL 1.0"],
    )
    service = ModelFileService(scanner, "workflow")

    result = await service.auto_organize_models(
        file_paths=[_normalize(workflow_path)]
    )

    assert result.success_count == 0
    assert result.skipped_count == 1
    assert (target_dir / "portrait.json").is_file()
