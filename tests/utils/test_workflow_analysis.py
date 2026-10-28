"""Tests for py.utils.workflow_analysis: sniffing and graph extraction."""

import json

from py.utils.workflow_analysis import (
    WORKFLOW_FORMAT_API,
    WORKFLOW_FORMAT_UI,
    analyze_workflow,
    analyze_workflow_file,
    load_workflow_file,
    sniff_workflow_text,
)


UI_WORKFLOW = {
    "nodes": [
        {"id": 1, "type": "CheckpointLoaderSimple", "widgets_values": ["sd_xl_base_1.0.safetensors"]},
        {"id": 2, "type": "LoraLoader", "widgets_values": ["civitai:12345@67890", 1.0, 1.0]},
        {"id": 3, "type": "KSampler", "widgets_values": [42]},
    ],
    "links": [],
    "groups": [],
    "version": 0.4,
}

API_WORKFLOW = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "v1-5-pruned.safetensors"}},
    "2": {"class_type": "LoraLoader", "inputs": {"lora_name": "civitai:111@222", "strength_model": 1.0}},
    "3": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ComfyUI"}},
}


def test_sniff_ui_format():
    assert sniff_workflow_text(json.dumps(UI_WORKFLOW)) == WORKFLOW_FORMAT_UI


def test_sniff_api_format():
    assert sniff_workflow_text(json.dumps(API_WORKFLOW)) == WORKFLOW_FORMAT_API


def test_sniff_rejects_non_workflow_json():
    assert sniff_workflow_text(json.dumps({"setting": True, "other": 1})) is None
    assert sniff_workflow_text(json.dumps(["a", "b"])) is None
    assert sniff_workflow_text("not json at all") is None
    # A sidecar-shaped document (flat metadata fields) is not a workflow.
    assert sniff_workflow_text(json.dumps({"file_name": "x", "sha256": "abc"})) is None


def test_analyze_ui_format_extracts_classes_and_refs():
    analysis = analyze_workflow(UI_WORKFLOW)
    assert analysis is not None
    assert analysis.workflow_format == WORKFLOW_FORMAT_UI
    assert analysis.node_count == 3
    assert analysis.node_classes == ["CheckpointLoaderSimple", "KSampler", "LoraLoader"]
    assert analysis.model_refs == ["sd_xl_base_1.0.safetensors"]
    assert analysis.civitai_refs == ["civitai:12345@67890"]


def test_analyze_api_format_extracts_classes_and_refs():
    analysis = analyze_workflow(API_WORKFLOW)
    assert analysis is not None
    assert analysis.workflow_format == WORKFLOW_FORMAT_API
    assert analysis.node_count == 3
    assert "SaveImage" in analysis.node_classes
    assert analysis.model_refs == ["v1-5-pruned.safetensors"]
    assert analysis.civitai_refs == ["civitai:111@222"]


def test_analyze_rejects_non_workflow():
    assert analyze_workflow({"foo": "bar"}) is None


def test_analyze_skips_prompt_text_with_extension_like_suffix(tmp_path):
    # Prompt strings contain spaces and must not become model refs.
    workflow = {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "a beautiful landscape, best quality.safetensors style"},
        }
    }
    analysis = analyze_workflow(workflow)
    assert analysis is not None
    assert analysis.model_refs == []


def test_analyze_workflow_file_roundtrip(tmp_path):
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(API_WORKFLOW), encoding="utf-8")
    analysis = analyze_workflow_file(str(path))
    assert analysis is not None
    assert analysis.workflow_format == WORKFLOW_FORMAT_API


def test_load_workflow_file_rejects_sidecar(tmp_path):
    sidecar = tmp_path / "flow.metadata.json"
    sidecar.write_text(json.dumps({"file_name": "flow", "sha256": "x"}), encoding="utf-8")
    assert load_workflow_file(str(sidecar)) is None


def test_load_workflow_file_handles_missing(tmp_path):
    assert load_workflow_file(str(tmp_path / "nope.json")) is None
