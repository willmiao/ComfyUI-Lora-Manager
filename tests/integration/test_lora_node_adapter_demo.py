import importlib.util
import json
from pathlib import Path

import pytest


DEMO_ROOT = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "lora-node-adapter-demo"
)
SPEC = importlib.util.spec_from_file_location(
    "lora_node_adapter_demo",
    DEMO_ROOT / "__init__.py",
    submodule_search_locations=[str(DEMO_ROOT)],
)
assert SPEC is not None and SPEC.loader is not None
DEMO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEMO)


def test_demo_loader_loads_syntax_and_returns_loaded_loras(monkeypatch):
    model = object()
    clip = object()
    load_calls = []

    monkeypatch.setattr(
        "folder_paths.get_full_path",
        lambda collection, name: f"/models/{name}.safetensors",
        raising=False,
    )
    monkeypatch.setattr(
        "comfy.utils.load_torch_file",
        lambda path, safe_load=True: {"path": path},
    )

    def load_lora(model_arg, clip_arg, lora, model_strength, clip_strength):
        load_calls.append((lora["path"], model_strength, clip_strength))
        return model_arg, clip_arg

    monkeypatch.setattr("comfy.sd.load_lora_for_models", load_lora)

    result_model, result_clip, loaded_loras = DEMO.LoraNodeAdapterDemoLoader().load_loras(
        model,
        "<lora:folder/alpha:0.8:0.6> <lora:beta:0.5>",
        clip,
    )

    assert result_model is model
    assert result_clip is clip
    assert load_calls == [
        ("/models/folder/alpha.safetensors", 0.8, 0.6),
        ("/models/beta.safetensors", 0.5, 0.5),
    ]
    assert loaded_loras == "<lora:folder/alpha:0.8:0.6> <lora:beta:0.5>"


def test_demo_loader_accepts_empty_or_unmatched_text():
    model = object()
    clip = object()

    assert DEMO.LoraNodeAdapterDemoLoader().load_loras(model, "", clip) == (
        model,
        clip,
        "",
    )
    assert DEMO.LoraNodeAdapterDemoLoader().load_loras(model, "plain text", clip) == (
        model,
        clip,
        "",
    )


def test_demo_loader_reports_missing_lora(monkeypatch):
    monkeypatch.setattr(
        "folder_paths.get_full_path", lambda _collection, _name: None, raising=False
    )

    with pytest.raises(FileNotFoundError, match="LoRA not found: missing"):
        DEMO.LoraNodeAdapterDemoLoader().load_loras(
            object(),
            "<lora:missing:1>",
        )


def test_demo_workflow_references_the_demo_and_resolver_nodes():
    workflow = json.loads((DEMO_ROOT / "example_workflow.json").read_text())
    node_types = {node["type"] for node in workflow["nodes"]}
    node_ids = {node["id"] for node in workflow["nodes"]}

    assert DEMO.LoraNodeAdapterDemoLoader.NAME in node_types
    assert "LoRA Trigger Words (LoraManager)" in node_types
    assert "TriggerWord Toggle (LoraManager)" in node_types
    for _link_id, source_id, _source_slot, target_id, _target_slot, _type in workflow["links"]:
        assert source_id in node_ids
        assert target_id in node_ids
