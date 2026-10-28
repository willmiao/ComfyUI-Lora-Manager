"""Tests for WorkflowScanner: opt-in roots, sidecar exclusion, metadata creation."""

import json
import os

import pytest

from py import config as config_module
from py.services.model_scanner import ModelScanner
from py.services.workflow_scanner import WorkflowScanner
from py.utils.models import WorkflowMetadata


def _normalize(path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


@pytest.fixture
def workflow_root(tmp_path, monkeypatch):
    root = tmp_path / "workflows"
    root.mkdir()
    monkeypatch.setattr(config_module.config, "workflows_roots", [_normalize(root)])
    monkeypatch.setattr(config_module.config, "extra_workflows_roots", [])
    return root


@pytest.fixture
def enable_workflows(monkeypatch):
    """Enable the feature without set() side effects (root refresh, rescan)."""
    from py.services.settings_manager import get_settings_manager

    monkeypatch.setattr(
        get_settings_manager(), "is_workflows_enabled", lambda: True
    )


def _make_scanner() -> WorkflowScanner:
    """Create a scanner without __init__ to avoid async initialization."""
    scanner = object.__new__(WorkflowScanner)
    scanner.model_type = "workflow"
    scanner.model_class = WorkflowMetadata
    scanner.file_extensions = {".json"}
    return scanner


def test_roots_empty_while_feature_disabled(workflow_root, monkeypatch):
    from py.services.settings_manager import get_settings_manager

    monkeypatch.setattr(
        get_settings_manager(), "is_workflows_enabled", lambda: False
    )
    scanner = _make_scanner()
    assert scanner.get_model_roots() == []


def test_roots_listed_while_feature_enabled(workflow_root, enable_workflows):
    scanner = _make_scanner()
    assert scanner.get_model_roots() == [_normalize(workflow_root)]


def test_filename_filter_rejects_sidecars(enable_workflows):
    scanner = _make_scanner()
    assert scanner._is_indexable_filename("flow.json") is True
    assert scanner._is_indexable_filename("flow.metadata.json") is False
    assert scanner._is_indexable_filename("FLOW.METADATA.JSON") is False


async def test_create_default_metadata_parses_workflow(workflow_root, enable_workflows, tmp_path):
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "base.safetensors"}},
        "2": {"class_type": "LoraLoader", "inputs": {"lora_name": "civitai:1@2"}},
    }
    file_path = workflow_root / "my_flow.json"
    file_path.write_text(json.dumps(workflow), encoding="utf-8")

    scanner = _make_scanner()
    metadata = await scanner._create_default_metadata(str(file_path))

    assert metadata is not None
    assert metadata.file_name == "my_flow"
    assert metadata.sub_type == "workflow"
    assert metadata.workflow_format == "api"
    assert metadata.node_count == 2
    assert metadata.sha256
    assert metadata.model_refs == ["base.safetensors"]
    assert metadata.civitai_refs == ["civitai:1@2"]
    assert metadata.from_civitai is False


async def test_create_default_metadata_skips_non_workflow_json(workflow_root, enable_workflows):
    file_path = workflow_root / "settings.json"
    file_path.write_text(json.dumps({"some": "config"}), encoding="utf-8")

    scanner = _make_scanner()
    assert await scanner._create_default_metadata(str(file_path)) is None


async def test_create_default_metadata_skips_sidecar(workflow_root, enable_workflows):
    file_path = workflow_root / "my_flow.metadata.json"
    file_path.write_text(json.dumps({"file_name": "my_flow"}), encoding="utf-8")

    scanner = _make_scanner()
    assert await scanner._create_default_metadata(str(file_path)) is None
