"""Tests for workflow document extraction from library artifacts."""

import json
import os
import zipfile

import pytest

from py.utils.workflow_extraction import (
    WORKFLOW_DOCUMENT_SUFFIX,
    extract_workflow_document,
    get_workflow_document_path,
    load_artifact_workflow_document,
    materialize_workflow_document,
)

API_WORKFLOW = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "base.safetensors"}},
    "2": {"class_type": "LoraLoader", "inputs": {"lora_name": "lora.safetensors"}},
}

UI_WORKFLOW = {
    "nodes": [{"id": 1, "type": "CheckpointLoaderSimple", "widgets_values": ["base.safetensors"]}],
    "links": [],
}


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_zip(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def _write_png_with_workflow(path, workflow):
    PIL = pytest.importorskip("PIL.Image")
    from py.utils.exif_utils import ExifUtils

    img = PIL.new("RGB", (8, 8), color=(0, 0, 0))
    img.save(path, format="PNG")
    ExifUtils.embed_workflow(str(path), json.dumps(workflow))


def _write_webp_with_workflow(path, workflow):
    PIL = pytest.importorskip("PIL.Image")
    from py.utils.exif_utils import ExifUtils

    img = PIL.new("RGB", (8, 8), color=(0, 0, 0))
    img.save(path, format="WEBP")
    ExifUtils.embed_workflow(str(path), json.dumps(workflow))


def _zip_with_image_member(tmp_path, workflow, extension=".png"):
    """Build an image carrying *workflow* and bundle it into a zip."""

    image_path = tmp_path / f"member{extension}"
    if extension == ".png":
        _write_png_with_workflow(image_path, workflow)
    else:
        _write_webp_with_workflow(image_path, workflow)
    artifact = tmp_path / "pack.zip"
    _write_zip(
        artifact,
        {"images/member" + extension: image_path.read_bytes()},
    )
    return artifact


def test_document_path_identity_for_json(tmp_path):
    artifact = tmp_path / "flow.json"
    assert get_workflow_document_path(str(artifact)) == str(artifact)


def test_document_path_derived_for_containers(tmp_path):
    artifact = tmp_path / "flow.zip"
    derived = get_workflow_document_path(str(artifact))
    assert derived == str(tmp_path / f"flow{WORKFLOW_DOCUMENT_SUFFIX}")

    image = tmp_path / "flow.png"
    assert get_workflow_document_path(str(image)) == str(
        tmp_path / f"flow{WORKFLOW_DOCUMENT_SUFFIX}"
    )


def test_extract_json_artifact(tmp_path):
    artifact = tmp_path / "flow.json"
    _write_json(artifact, API_WORKFLOW)
    document = extract_workflow_document(str(artifact))
    assert document == API_WORKFLOW


def test_extract_rejects_non_workflow_json(tmp_path):
    artifact = tmp_path / "settings.json"
    _write_json(artifact, {"some": "config"})
    assert extract_workflow_document(str(artifact)) is None
    assert materialize_workflow_document(str(artifact)) is None


def test_extract_from_zip_top_level(tmp_path):
    artifact = tmp_path / "pack.zip"
    _write_zip(
        artifact,
        {
            "workflow.json": json.dumps(UI_WORKFLOW),
            "readme.txt": "hello",
        },
    )
    document = extract_workflow_document(str(artifact))
    assert document == UI_WORKFLOW


def test_extract_from_zip_prefers_shallow_candidates(tmp_path):
    artifact = tmp_path / "pack.zip"
    _write_zip(
        artifact,
        {
            "nested/deep/config.json": json.dumps(API_WORKFLOW),
            "top.json": json.dumps(UI_WORKFLOW),
        },
    )
    document = extract_workflow_document(str(artifact))
    assert document == UI_WORKFLOW


def test_extract_from_zip_skips_macosx_and_hidden(tmp_path):
    artifact = tmp_path / "pack.zip"
    _write_zip(
        artifact,
        {
            "__MACOSX/workflow.json": json.dumps(UI_WORKFLOW),
            ".hidden/workflow.json": json.dumps(UI_WORKFLOW),
            "real.json": json.dumps(API_WORKFLOW),
        },
    )
    document = extract_workflow_document(str(artifact))
    assert document == API_WORKFLOW


def test_extract_from_zip_without_workflow_returns_none(tmp_path):
    artifact = tmp_path / "images.zip"
    _write_zip(artifact, {"note.txt": "no graphs here", "config.json": "{}"})
    assert extract_workflow_document(str(artifact)) is None


def test_extract_from_zip_png_with_embedded_workflow(tmp_path):
    artifact = _zip_with_image_member(tmp_path, UI_WORKFLOW)
    assert extract_workflow_document(str(artifact)) == UI_WORKFLOW


def test_extract_from_zip_webp_with_embedded_workflow(tmp_path):
    artifact = _zip_with_image_member(tmp_path, UI_WORKFLOW, extension=".webp")
    assert extract_workflow_document(str(artifact)) == UI_WORKFLOW


def test_extract_from_zip_prefers_json_over_image(tmp_path):
    image_path = tmp_path / "shot.png"
    _write_png_with_workflow(image_path, UI_WORKFLOW)
    artifact = tmp_path / "pack.zip"
    _write_zip(
        artifact,
        {
            "workflow.json": json.dumps(API_WORKFLOW),
            "shot.png": image_path.read_bytes(),
        },
    )
    assert extract_workflow_document(str(artifact)) == API_WORKFLOW


def test_extract_from_zip_plain_image_returns_none(tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "plain.png"
    PIL.new("RGB", (8, 8)).save(image_path, format="PNG")
    artifact = tmp_path / "images.zip"
    _write_zip(
        artifact,
        {"plain.png": image_path.read_bytes(), "note.txt": "no graphs here"},
    )
    assert extract_workflow_document(str(artifact)) is None


def test_extract_from_zip_continues_after_bad_image_member(tmp_path):
    image_path = tmp_path / "good.png"
    _write_png_with_workflow(image_path, UI_WORKFLOW)
    artifact = tmp_path / "pack.zip"
    # The corrupt member is larger, so the "full-size first" ordering tries
    # it before the valid screenshot; the loop must move on to the next one.
    _write_zip(
        artifact,
        {
            "a_broken.png": b"not an image" * 512,
            "b_good.png": image_path.read_bytes(),
        },
    )
    assert extract_workflow_document(str(artifact)) == UI_WORKFLOW


def test_extract_from_zip_skips_oversized_image_member(tmp_path, monkeypatch):
    from py.utils import workflow_extraction

    artifact = _zip_with_image_member(tmp_path, UI_WORKFLOW)
    monkeypatch.setattr(workflow_extraction, "_MAX_ZIP_IMAGE_BYTES", 1)
    assert extract_workflow_document(str(artifact)) is None


def test_materialize_from_zip_image_member(tmp_path):
    artifact = _zip_with_image_member(tmp_path, UI_WORKFLOW)
    derived = materialize_workflow_document(str(artifact))
    assert derived == str(tmp_path / f"pack{WORKFLOW_DOCUMENT_SUFFIX}")
    with open(derived, "r", encoding="utf-8") as handle:
        assert json.load(handle) == UI_WORKFLOW


def test_extract_from_corrupt_zip_returns_none(tmp_path):
    artifact = tmp_path / "broken.zip"
    artifact.write_bytes(b"not a zip at all")
    assert extract_workflow_document(str(artifact)) is None


def test_extract_from_png_with_embedded_workflow(tmp_path):
    artifact = tmp_path / "flow.png"
    _write_png_with_workflow(artifact, UI_WORKFLOW)
    document = extract_workflow_document(str(artifact))
    assert document == UI_WORKFLOW


def test_extract_from_webp_with_embedded_workflow(tmp_path):
    artifact = tmp_path / "flow.webp"
    _write_webp_with_workflow(artifact, UI_WORKFLOW)
    document = extract_workflow_document(str(artifact))
    assert document == UI_WORKFLOW


def test_extract_from_plain_image_returns_none(tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    artifact = tmp_path / "plain.png"
    PIL.new("RGB", (8, 8)).save(artifact, format="PNG")
    assert extract_workflow_document(str(artifact)) is None
    assert materialize_workflow_document(str(artifact)) is None


def test_materialize_writes_derived_document_once(tmp_path):
    artifact = tmp_path / "pack.zip"
    _write_zip(artifact, {"workflow.json": json.dumps(API_WORKFLOW)})

    derived = materialize_workflow_document(str(artifact))
    assert derived == str(tmp_path / f"pack{WORKFLOW_DOCUMENT_SUFFIX}")
    with open(derived, "r", encoding="utf-8") as handle:
        assert json.load(handle) == API_WORKFLOW

    # A fresh derived file is reused without re-extracting: corrupt the zip
    # and confirm the cached document is still returned.
    artifact_mtime = os.path.getmtime(artifact)
    os.utime(derived, (artifact_mtime + 1, artifact_mtime + 1))
    artifact.write_bytes(b"corrupted")
    assert materialize_workflow_document(str(artifact)) == derived


def test_materialize_reextracts_when_artifact_is_newer(tmp_path):
    artifact = tmp_path / "pack.zip"
    _write_zip(artifact, {"workflow.json": json.dumps(API_WORKFLOW)})

    derived = materialize_workflow_document(str(artifact))

    # Replace the artifact with a newer mtime than the derived document.
    _write_zip(artifact, {"workflow.json": json.dumps(UI_WORKFLOW)})
    artifact_mtime = os.path.getmtime(artifact)
    os.utime(artifact, (artifact_mtime + 10, artifact_mtime + 10))

    assert materialize_workflow_document(str(artifact)) == derived
    with open(derived, "r", encoding="utf-8") as handle:
        assert json.load(handle) == UI_WORKFLOW


def test_load_artifact_workflow_document_round_trip(tmp_path):
    artifact = tmp_path / "pack.zip"
    _write_zip(artifact, {"workflow.json": json.dumps(API_WORKFLOW)})
    assert load_artifact_workflow_document(str(artifact)) == API_WORKFLOW

    bare = tmp_path / "bare.json"
    _write_json(bare, UI_WORKFLOW)
    assert load_artifact_workflow_document(str(bare)) == UI_WORKFLOW
