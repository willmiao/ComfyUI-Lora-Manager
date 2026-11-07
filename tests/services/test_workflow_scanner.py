"""Tests for WorkflowScanner: opt-in roots, sidecar exclusion, metadata creation."""

import json
import logging
import os

import pytest

from py import config as config_module
from py.services.model_scanner import ModelScanner
from py.services.workflow_scanner import WorkflowScanner
from py.utils.metadata_manager import MetadataManager
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
    scanner.file_extensions = {".json", ".zip", ".png", ".webp"}
    return scanner


def _write_zip_with_embedded_png(scratch_dir, artifact_path, workflow=None):
    """Create an archive whose only workflow carrier is an embedded-metadata PNG."""

    import zipfile

    PIL = pytest.importorskip("PIL.Image")
    from py.utils.exif_utils import ExifUtils

    if workflow is None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["base.safetensors"],
                }
            ],
            "links": [],
        }
    image_path = scratch_dir / "shot.png"
    PIL.new("RGB", (8, 8)).save(image_path, format="PNG")
    ExifUtils.embed_workflow(str(image_path), json.dumps(workflow))
    with zipfile.ZipFile(artifact_path, "w") as archive:
        archive.write(image_path, "images/shot.png")
        archive.writestr("readme.txt", "hello")
    return workflow


@pytest.fixture(autouse=True)
def stub_base_model_resolution(monkeypatch):
    """Keep scanner tests hermetic; resolution itself is covered in
    tests/services/test_workflow_base_model.py."""

    async def _resolve(**kwargs):
        return None

    monkeypatch.setattr(
        "py.services.workflow_base_model.resolve_workflow_base_model", _resolve
    )


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
    # The derived workflow document of a container artifact is also a sidecar.
    assert scanner._is_indexable_filename("flow.workflow.json") is False
    assert scanner._is_indexable_filename("FLOW.WORKFLOW.JSON") is False


def test_filename_filter_rejects_preview_sidecars(enable_workflows):
    """LM preview assets share image-artifact extensions and must not be
    indexed as workflows of their own."""
    scanner = _make_scanner()
    assert scanner._is_indexable_filename("flow.preview.webp") is False
    assert scanner._is_indexable_filename("FLOW.PREVIEW.PNG") is False
    assert scanner._is_indexable_filename("flow.preview.mp4") is False
    # A plain image artifact is still indexable.
    assert scanner._is_indexable_filename("flow.webp") is True
    assert scanner._is_indexable_filename("flow.png") is True


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


async def test_create_default_metadata_from_zip_artifact(workflow_root, enable_workflows):
    import zipfile

    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "base.safetensors"}},
    }
    file_path = workflow_root / "pack.zip"
    with zipfile.ZipFile(file_path, "w") as archive:
        archive.writestr("workflow.json", json.dumps(workflow))
        archive.writestr("readme.txt", "hello")

    scanner = _make_scanner()
    metadata = await scanner._create_default_metadata(str(file_path))

    assert metadata is not None
    assert metadata.file_name == "pack"
    assert metadata.workflow_format == "api"
    assert metadata.node_count == 1
    assert metadata.model_refs == ["base.safetensors"]
    # The artifact is hashed, not the extracted document.
    assert metadata.sha256

    # The derived workflow document is materialized as a sidecar.
    derived = workflow_root / "pack.zip.workflow.json"
    assert derived.exists()
    assert json.loads(derived.read_text(encoding="utf-8")) == workflow


async def test_create_default_metadata_from_zip_with_embedded_png(
    workflow_root, enable_workflows, tmp_path
):
    """A CivitAI archive may bundle only a PNG carrying the workflow."""

    import hashlib

    file_path = workflow_root / "pack.zip"
    workflow = _write_zip_with_embedded_png(tmp_path, file_path)

    scanner = _make_scanner()
    metadata = await scanner._create_default_metadata(str(file_path))

    assert metadata is not None
    assert metadata.workflow_format == "ui"
    assert metadata.node_count == 1
    assert metadata.model_refs == ["base.safetensors"]
    # CivitAI identity stays the zip's hash, never the embedded image's.
    assert metadata.sha256 == hashlib.sha256(file_path.read_bytes()).hexdigest()

    derived = workflow_root / "pack.zip.workflow.json"
    assert derived.exists()
    assert json.loads(derived.read_text(encoding="utf-8")) == workflow


async def test_process_model_file_creates_entry_for_zip_with_embedded_png(
    workflow_root, enable_workflows, tmp_path
):
    """A plain Refresh scan indexes the archive (the user-reported case)."""

    import hashlib

    from py.services.model_hash_index import ModelHashIndex

    file_path = workflow_root / "pack.zip"
    _write_zip_with_embedded_png(tmp_path, file_path)

    scanner = _make_scanner()
    scanner._hash_index = ModelHashIndex()
    scanner._excluded_models = []

    entry = await scanner._process_model_file(str(file_path), str(workflow_root))

    assert entry is not None
    assert entry["workflow_format"] == "ui"
    assert entry["sha256"] == hashlib.sha256(file_path.read_bytes()).hexdigest()
    assert (workflow_root / "pack.zip.workflow.json").exists()


async def test_adjust_metadata_fills_analysis_from_zip_embedded_png(
    workflow_root, enable_workflows, tmp_path
):
    """An entry downloaded before the fix heals on the next scan."""

    file_path = workflow_root / "downloaded.zip"
    _write_zip_with_embedded_png(
        tmp_path,
        file_path,
        {"nodes": [{"id": 1, "type": "CheckpointLoaderSimple"}], "links": []},
    )

    metadata = WorkflowMetadata(
        file_name="downloaded",
        model_name="downloaded",
        file_path=_normalize(file_path),
        size=file_path.stat().st_size,
        modified=0,
        sha256="abc",
        base_model="Unknown",
        preview_url="",
        from_civitai=True,
    )

    scanner = _make_scanner()
    adjusted = scanner.adjust_metadata(metadata, str(file_path), None)

    assert adjusted.workflow_format == "ui"
    assert adjusted.node_count == 1
    assert (workflow_root / "downloaded.zip.workflow.json").exists()


async def test_create_default_metadata_skips_zip_without_workflow(workflow_root, enable_workflows):
    import zipfile

    file_path = workflow_root / "images.zip"
    with zipfile.ZipFile(file_path, "w") as archive:
        archive.writestr("note.txt", "no graphs here")

    scanner = _make_scanner()
    assert await scanner._create_default_metadata(str(file_path)) is None
    assert not (workflow_root / "images.workflow.json").exists()


async def test_non_workflow_zip_is_reported_as_expected_skip(
    workflow_root, enable_workflows, caplog
):
    import zipfile

    from py.services.model_hash_index import ModelHashIndex

    file_path = workflow_root / "wildcards.zip"
    with zipfile.ZipFile(file_path, "w") as archive:
        archive.writestr("wildcards.json", json.dumps({"characters": []}))

    scanner = _make_scanner()
    scanner._hash_index = ModelHashIndex()
    scanner._excluded_models = []

    caplog.set_level(logging.INFO)
    result = await scanner._process_model_file(str(file_path), str(workflow_root))

    assert result is None
    assert any(
        record.name == "py.services.workflow_scanner"
        and record.levelno == logging.INFO
        and "Skipping non-workflow artifact" in record.message
        for record in caplog.records
    )
    assert not any(
        "metadata could not be created" in record.message
        for record in caplog.records
    )


async def test_create_default_metadata_image_artifact_self_preview(workflow_root, enable_workflows):
    PIL = pytest.importorskip("PIL.Image")
    from py.utils.exif_utils import ExifUtils

    workflow = {
        "nodes": [{"id": 1, "type": "CheckpointLoaderSimple"}],
        "links": [],
    }
    file_path = workflow_root / "flow.png"
    PIL.new("RGB", (8, 8)).save(file_path, format="PNG")
    ExifUtils.embed_workflow(str(file_path), json.dumps(workflow))

    scanner = _make_scanner()
    metadata = await scanner._create_default_metadata(str(file_path))

    assert metadata is not None
    assert metadata.workflow_format == "ui"
    # The image artifact doubles as its own preview.
    assert metadata.preview_url.replace(os.sep, "/").endswith("flow.png")


async def test_create_default_metadata_plain_image_skipped(workflow_root, enable_workflows):
    PIL = pytest.importorskip("PIL.Image")

    file_path = workflow_root / "preview.png"
    PIL.new("RGB", (8, 8)).save(file_path, format="PNG")

    scanner = _make_scanner()
    assert await scanner._create_default_metadata(str(file_path)) is None


def test_adjust_metadata_fills_missing_analysis(workflow_root, enable_workflows):
    """Downloaded entries carry CivitAI metadata but no analysis fields yet."""
    import zipfile

    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "base.safetensors"}},
    }
    file_path = workflow_root / "downloaded.zip"
    with zipfile.ZipFile(file_path, "w") as archive:
        archive.writestr("workflow.json", json.dumps(workflow))

    metadata = WorkflowMetadata(
        file_name="downloaded",
        model_name="downloaded",
        file_path=_normalize(file_path),
        size=file_path.stat().st_size,
        modified=0,
        sha256="abc",
        base_model="Unknown",
        preview_url="",
        from_civitai=True,
    )

    scanner = _make_scanner()
    adjusted = scanner.adjust_metadata(metadata, str(file_path), None)

    assert adjusted.workflow_format == "api"
    assert adjusted.node_count == 1
    assert adjusted.model_refs == ["base.safetensors"]
    assert (workflow_root / "downloaded.zip.workflow.json").exists()


def test_adjust_metadata_keeps_populated_analysis(workflow_root, enable_workflows):
    metadata = WorkflowMetadata(
        file_name="flow",
        model_name="flow",
        file_path=_normalize(workflow_root / "flow.json"),
        size=1,
        modified=0,
        sha256="abc",
        base_model="Unknown",
        preview_url="",
        workflow_format="ui",
        node_count=7,
    )

    scanner = _make_scanner()
    adjusted = scanner.adjust_metadata(metadata, str(workflow_root / "flow.json"), None)

    assert adjusted.node_count == 7  # untouched: no re-extraction


async def test_register_local_artifact_builds_metadata_and_syncs_cache(
    workflow_root, enable_workflows, monkeypatch
):
    """The create flow reuses the scanner's metadata builder and cache sync."""
    workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
    file_path = workflow_root / "created_flow.json"
    file_path.write_text(json.dumps(workflow), encoding="utf-8")

    scanner = _make_scanner()
    synced = []

    async def fake_sync(path, metadata_dict):
        synced.append((path, metadata_dict))
        return True

    monkeypatch.setattr(scanner, "sync_cache_from_metadata", fake_sync)

    metadata = await scanner.register_local_artifact(str(file_path))

    assert metadata is not None
    assert metadata.file_name == "created_flow"
    assert len(synced) == 1
    assert synced[0][0] == str(file_path)
    assert synced[0][1]["file_path"] == metadata.file_path
    assert synced[0][1]["sha256"] == metadata.sha256


async def test_register_local_artifact_returns_none_for_non_workflow(
    workflow_root, enable_workflows, monkeypatch
):
    file_path = workflow_root / "not_a_flow.json"
    file_path.write_text(json.dumps({"some": "config"}), encoding="utf-8")

    scanner = _make_scanner()
    synced = []
    monkeypatch.setattr(
        scanner,
        "sync_cache_from_metadata",
        lambda *args: synced.append(args),
    )

    assert await scanner.register_local_artifact(str(file_path)) is None
    assert synced == []


async def test_create_default_metadata_resolves_base_model(
    workflow_root, enable_workflows, monkeypatch
):
    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "base.safetensors"},
        },
    }
    file_path = workflow_root / "flow.json"
    file_path.write_text(json.dumps(workflow), encoding="utf-8")

    captured = {}

    async def fake_resolve(**kwargs):
        captured.update(kwargs)
        return "SDXL 1.0"

    monkeypatch.setattr(
        "py.services.workflow_base_model.resolve_workflow_base_model", fake_resolve
    )

    scanner = _make_scanner()
    metadata = await scanner._create_default_metadata(str(file_path))

    assert metadata is not None
    assert metadata.base_model == "SDXL 1.0"
    assert metadata.primary_model_refs == ["base.safetensors"]
    assert captured["primary_model_refs"] == ["base.safetensors"]
    # Scan-time metadata creation never hits remote providers.
    assert captured["include_remote"] is False


async def test_create_default_metadata_falls_back_to_unknown(
    workflow_root, enable_workflows
):
    """The stubbed resolver returns None; the stored label stays "Unknown"."""
    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "not-in-library.safetensors"},
        },
    }
    file_path = workflow_root / "flow.json"
    file_path.write_text(json.dumps(workflow), encoding="utf-8")

    scanner = _make_scanner()
    metadata = await scanner._create_default_metadata(str(file_path))

    assert metadata is not None
    assert metadata.base_model == "Unknown"


async def test_register_local_artifact_forwards_checkpoint_name_hint(
    workflow_root, enable_workflows, monkeypatch
):
    """The create flow passes the generation-time checkpoint hint through."""
    workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
    file_path = workflow_root / "created_flow.json"
    file_path.write_text(json.dumps(workflow), encoding="utf-8")

    captured = {}

    async def fake_resolve(**kwargs):
        captured.update(kwargs)
        return "Illustrious"

    monkeypatch.setattr(
        "py.services.workflow_base_model.resolve_workflow_base_model", fake_resolve
    )

    scanner = _make_scanner()

    async def fake_sync(path, metadata_dict):
        return True

    monkeypatch.setattr(scanner, "sync_cache_from_metadata", fake_sync)

    metadata = await scanner.register_local_artifact(
        str(file_path), checkpoint_name_hint="primary.safetensors"
    )

    assert metadata is not None
    assert metadata.base_model == "Illustrious"
    assert captured["checkpoint_name_hint"] == "primary.safetensors"


async def test_create_default_metadata_defaults_hint_to_none(
    workflow_root, enable_workflows, monkeypatch
):
    """Scan-time metadata creation carries no generation-time hint."""
    workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
    file_path = workflow_root / "flow.json"
    file_path.write_text(json.dumps(workflow), encoding="utf-8")

    captured = {}

    async def fake_resolve(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(
        "py.services.workflow_base_model.resolve_workflow_base_model", fake_resolve
    )

    scanner = _make_scanner()
    metadata = await scanner._create_default_metadata(str(file_path))

    assert metadata is not None
    assert captured["checkpoint_name_hint"] is None


async def test_register_local_artifact_allows_remote_resolution(
    workflow_root, enable_workflows, monkeypatch
):
    """The create flow is a one-off user action, so CivitAI URNs may be used."""
    workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
    file_path = workflow_root / "created_flow.json"
    file_path.write_text(json.dumps(workflow), encoding="utf-8")

    captured = {}

    async def fake_resolve(**kwargs):
        captured.update(kwargs)
        return "SD 1.5"

    monkeypatch.setattr(
        "py.services.workflow_base_model.resolve_workflow_base_model", fake_resolve
    )

    scanner = _make_scanner()

    async def fake_sync(path, metadata_dict):
        return True

    monkeypatch.setattr(scanner, "sync_cache_from_metadata", fake_sync)

    metadata = await scanner.register_local_artifact(str(file_path))

    assert metadata is not None
    assert metadata.base_model == "SD 1.5"
    assert captured["include_remote"] is True


async def test_same_stem_artifacts_recover_independent_hashes_from_legacy_sidecar(
    workflow_root, enable_workflows
):
    import hashlib
    import zipfile

    from py.utils.sidecar_paths import get_metadata_path

    workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
    json_path = workflow_root / "same.json"
    zip_path = workflow_root / "same.zip"
    json_path.write_text(json.dumps(workflow), encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("workflow.json", json.dumps(workflow))

    (workflow_root / "same.metadata.json").write_text(
        json.dumps(
            {
                "file_name": "same",
                "model_name": "same",
                "file_path": _normalize(json_path),
                "size": 1,
                "modified": 0,
                "sha256": "polluted-shared-hash",
                "base_model": "Unknown",
                "preview_url": "",
                "workflow_format": "",
            }
        ),
        encoding="utf-8",
    )

    from py.services.model_hash_index import ModelHashIndex

    scanner = _make_scanner()
    scanner._hash_index = ModelHashIndex()
    scanner._excluded_models = []
    json_entry = await scanner._process_model_file(str(json_path), str(workflow_root))
    zip_entry = await scanner._process_model_file(str(zip_path), str(workflow_root))

    assert json_entry["sha256"] == hashlib.sha256(json_path.read_bytes()).hexdigest()
    assert zip_entry["sha256"] == hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert json_entry["sha256"] != zip_entry["sha256"]
    assert (workflow_root / "same.json.metadata.json").is_file()
    assert (workflow_root / "same.zip.metadata.json").is_file()
    assert get_metadata_path(str(json_path)) != get_metadata_path(str(zip_path))
    assert (workflow_root / "same.zip.workflow.json").is_file()


async def test_scan_skips_legacy_preview_referenced_by_sibling_metadata(
    workflow_root, enable_workflows
):
    import zipfile

    PIL = pytest.importorskip("PIL.Image")
    from py.utils.exif_utils import ExifUtils

    workflow = {"nodes": [{"id": 1, "type": "KSampler"}], "links": []}
    zip_path = workflow_root / "same.zip"
    preview_path = workflow_root / "same.webp"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("workflow.json", json.dumps(workflow))
    PIL.new("RGB", (8, 8)).save(preview_path, format="WEBP")
    ExifUtils.embed_workflow(str(preview_path), json.dumps(workflow))

    scanner = _make_scanner()
    metadata = await scanner._create_default_metadata(str(zip_path))
    metadata.preview_url = _normalize(preview_path)
    await MetadataManager.save_metadata(str(zip_path), metadata)

    assert await scanner._process_model_file(str(preview_path), str(workflow_root)) is None
