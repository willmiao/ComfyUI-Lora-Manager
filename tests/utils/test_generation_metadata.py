import json

import pytest

from py.utils.generation_metadata import (
    GraphReader, MetadataError, extract_generation_metadata, parse_parameters, split_lora_tags,
)


def graph():
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "base.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly monster, (detail:1.2)", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "sunshine", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 768, "height": 1024}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": 18446744073709551615, "steps": 25, "cfg": 6.5, "sampler_name": "euler", "scheduler": "normal", "denoise": 1}},
    }


def test_traces_polarity_without_content_heuristics():
    result = GraphReader(graph()).read("")
    assert result.values["positive"] == "ugly monster, (detail:1.2)"
    assert result.values["negative"] == "sunshine"
    assert result.values["seed"] == 2**64 - 1
    assert result.values["width"] == 768
    assert not result.issues


def test_multiple_samplers_require_selection_and_do_not_mix():
    data = graph()
    data["6"] = {"class_type": "KSampler", "inputs": {**data["5"]["inputs"], "seed": 42}}
    with pytest.raises(MetadataError, match="5, 6"):
        GraphReader(data).read("")
    assert GraphReader(data).read("6").values["seed"] == 42


def test_model_lora_order_repeated_entries_and_clip_strength():
    data = graph()
    data["6"] = {"class_type": "LoraLoader", "inputs": {"model": ["1", 0], "lora_name": "same.safetensors", "strength_model": .7, "strength_clip": .3}}
    data["7"] = {"class_type": "Lora Loader (LoraManager)", "inputs": {"model": ["6", 0], "loras": {"__value__": [{"name": "same", "active": True, "strength": .4, "clipStrength": 0}, {"name": "disabled", "active": False}]}}}
    data["5"]["inputs"]["model"] = ["7", 0]
    result = GraphReader(data).read("")
    assert result.loras == [("same.safetensors", .7, .3), ("same", .4, 0)]


def test_linked_primitive_and_cycle_detection():
    data = graph()
    data["6"] = {"class_type": "PrimitiveInt", "inputs": {"value": 123}}
    data["5"]["inputs"]["seed"] = ["6", 0]
    assert GraphReader(data).read("").values["seed"] == 123
    data["6"]["inputs"]["value"] = ["6", 0]
    assert "Cyclic" in GraphReader(data).read("").issues["seed"]


def test_unsupported_conditioning_is_not_silently_flattened():
    data = graph()
    data["2"]["class_type"] = "ConditioningCombine"
    assert "Unsupported conditioning" in GraphReader(data).read("").issues["positive"]


def test_parameters_sampler_mapping_and_clean_prompts():
    result = parse_parameters('portrait (detail:1.2) <lora:style:0.7:0.2>\nsecond line\nNegative prompt: blur\nmore blur\nSteps: 25, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 123, Size: 512x768, Model: base')
    assert result.values["sampler_name"] == "dpmpp_2m"
    assert result.values["scheduler"] == "karras"
    assert result.values["negative"] == "blur\nmore blur"
    clean, loras = split_lora_tags(result.values["positive"])
    assert clean == "portrait (detail:1.2) \nsecond line"
    assert loras == []
    assert result.loras == [("style", .7, .2)]


def test_unspecified_a1111_scheduler_requires_decision():
    result = parse_parameters("cat\nSteps: 20, Sampler: Euler a, Seed: 1, CFG scale: 7")
    assert result.values["sampler_name"] == "euler_ancestral"
    assert "scheduler" in result.issues


@pytest.mark.parametrize("value", ["<lora:foo:nan>", "<lora:foo:1e999>", "<lora:foo:bad>"])
def test_bad_lora_strength(value):
    with pytest.raises(ValueError):
        split_lora_tags(value)


def test_malformed_and_missing_metadata():
    with pytest.raises(MetadataError, match="Malformed"):
        extract_generation_metadata({"prompt": "{"})
    with pytest.raises(MetadataError, match="no supported"):
        extract_generation_metadata({})
    assert extract_generation_metadata({"comment": json.dumps(graph())}).values["steps"] == 25


def test_core_ui_workflow_fallback():
    workflow = {"nodes": [
        {"id": 1, "type": "CheckpointLoaderSimple", "widgets_values": ["base.safetensors"]},
        {"id": 2, "type": "CLIPTextEncode", "widgets_values": ["positive"]},
        {"id": 3, "type": "CLIPTextEncode", "widgets_values": ["negative"]},
        {"id": 4, "type": "KSampler", "widgets_values": [42, "fixed", 20, 7, "euler", "normal", 1], "inputs": [
            {"name": "model", "link": 1}, {"name": "positive", "link": 2}, {"name": "negative", "link": 3}]},
    ], "links": [[1, 1, 0, 4, 0, "MODEL"], [2, 2, 0, 4, 1, "CONDITIONING"], [3, 3, 0, 4, 2, "CONDITIONING"]]}
    result = extract_generation_metadata({"workflow": json.dumps(workflow)})
    assert result.values["positive"] == "positive"
    assert result.values["seed"] == 42
    assert "UI workflow fallback" in result.notes[0]


def test_stack_combiner_uses_numeric_order():
    data = {str(i): {"class_type": "Lora Stacker (LoraManager)", "inputs": {"loras": [{"name": str(i), "strength": 1, "active": True}]}} for i in (1, 2, 10)}
    data["20"] = {"class_type": "Lora Stack Combiner (LoraManager)", "inputs": {"lora_stack10": ["10", 0], "lora_stack2": ["2", 0], "lora_stack1": ["1", 0]}}
    assert [entry[0] for entry in GraphReader(data).stack(["20", 0])] == ["1", "2", "10"]


def test_model_and_clip_lora_mismatch_requires_override():
    data = graph()
    data["6"] = {"class_type": "LoraLoader", "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": "style", "strength_model": .7, "strength_clip": .3}}
    data["5"]["inputs"]["model"] = ["6", 0]
    assert "different LoRAs" in GraphReader(data).read("").issues["loras"]
    data["2"]["inputs"]["clip"] = ["6", 1]
    data["3"]["inputs"]["clip"] = ["6", 1]
    assert not GraphReader(data).read("").issues


def test_malformed_sampler_inputs():
    data = graph()
    data["5"]["inputs"] = None
    with pytest.raises(MetadataError, match="Malformed sampler"):
        GraphReader(data).read("")


@pytest.mark.parametrize("label,sampler,scheduler", [
    ("Euler a SGM Uniform", "euler_ancestral", "sgm_uniform"),
    ("Euler simple", "euler", "simple"),
    ("Euler Normal", "euler", "normal"),
    ("er_sde simple", "er_sde", "simple"),
])
def test_combined_sampler_scheduler_labels(label, sampler, scheduler):
    result = parse_parameters(f"cat\nSteps: 30, Sampler: {label}, Seed: 42, CFG scale: 5")
    assert result.values["sampler_name"] == sampler
    assert result.values["scheduler"] == scheduler
    assert not result.issues


def test_multiline_settings_and_single_resource_weight():
    result = parse_parameters('cat\nNegative prompt: blur\nSteps: 30, Sampler: Euler Normal, Seed: 42, CFG scale: 5, Clip skip: 0, extra text,\nmore text\n, Model: example, Hashes: {"model":"123", "LORA:style, special":"456"}, Civitai resources: [{"air":"urn:model"}, {"air":"urn:lora", "weight":0.74}]')
    assert result.values["checkpoint_name"] == "example"
    assert result.values["negative"] == "blur"
    assert result.loras == [("style, special", .74, .74)]
    assert result.resource_hints[0]["hash"] == "456"


def test_multiple_resource_weights_are_not_paired_by_order():
    result = parse_parameters('cat\nSteps: 20, Sampler: Euler Normal, Hashes: {"LORA:first":"aaa","LORA:second":"bbb"}, Civitai resources: [{"weight":0.5},{"weight":0.8}]')
    assert result.loras == []
    assert "loras" in result.issues
    assert [item["name"] for item in result.resource_hints] == ["first", "second"]



def test_duplicate_tags_with_single_authoritative_resource():
    result = parse_parameters('cat <lora:style:0.45> <lora:style:0.45>\nSteps: 10, Sampler: Euler simple, Hashes: {"LORA:style":"abc"}, Civitai resources: [{"weight":0.45}]')
    assert result.loras == [("style", .45, .45)]
    assert "<lora:" not in result.values["positive"]


@pytest.mark.parametrize("selector", ["outer:inner:5", "outer/inner/5", "outer:inner", "5", ""])
def test_qualified_subgraph_sampler_selection(selector):
    original = graph()
    expanded = {}
    for key, node in original.items():
        inputs = {name: ["outer:inner:" + value[0], value[1]] if isinstance(value, list) else value for name, value in node["inputs"].items()}
        expanded["outer:inner:" + key] = {**node, "inputs": inputs}
    result = GraphReader(expanded).read(selector)
    assert result.values["seed"] == 2**64 - 1
    assert "outer:inner:5" in result.notes[0]
    assert not result.issues


def test_subgraph_leaf_selection_rejects_ambiguity():
    reader = GraphReader({
        "10:5": {"class_type": "KSampler", "inputs": {}},
        "20:5": {"class_type": "KSampler", "inputs": {}},
    })
    with pytest.raises(MetadataError, match="10:5, 20:5"):
        reader.read("5")
    assert reader.select_sampler("20") == "20:5"


def test_standard_custom_sampler_pipeline():
    data = graph()
    old = data["5"]["inputs"]
    data["noise"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": 123}}
    data["guider"] = {"class_type": "CFGGuider", "inputs": {key: old[key] for key in ("model", "positive", "negative", "cfg")}}
    data["schedule"] = {"class_type": "BasicScheduler", "inputs": {"steps": 28, "scheduler": "karras", "denoise": .6}}
    data["sampler"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
    data["5"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["noise", 0], "guider": ["guider", 0], "sigmas": ["schedule", 0], "sampler": ["sampler", 0], "latent_image": old["latent_image"]}}
    result = GraphReader(data).read("5")
    assert not result.issues
    assert result.values["seed"] == 123
    assert result.values["steps"] == 28
    assert result.values["denoise"] == .6
    assert result.values["positive"] == "ugly monster, (detail:1.2)"


def test_saved_metadata_is_preferred_and_workflow_can_be_selected():
    fields = {
        "prompt": json.dumps(graph()),
        "parameters": "saved prompt\nSteps: 12, Sampler: Euler Normal, CFG scale: 4, Seed: 42, Model: saved",
    }
    result = extract_generation_metadata(fields, "not-a-node")
    assert result.values["seed"] == "42"
    assert result.values["positive"] == "saved prompt"
    assert any("ignored" in note for note in result.notes)
    result = extract_generation_metadata(fields, "5", prefer_saved_image_metadata=False)
    assert result.values["seed"] == 2**64 - 1


@pytest.mark.parametrize("mode", [2, 4])
def test_muted_or_bypassed_api_sampler_is_not_selected(mode):
    data = graph()
    data["6"] = {"class_type": "KSampler", "mode": mode, "inputs": {**data["5"]["inputs"], "seed": 123}}
    reader = GraphReader(data)
    assert reader.read("").values["seed"] == 2**64 - 1
    with pytest.raises(MetadataError, match="muted, bypassed"):
        reader.read("6")


@pytest.mark.parametrize("mode", [2, 4])
@pytest.mark.parametrize("inactive_parent", [False, True])
def test_workflow_modes_exclude_nested_api_sampler(mode, inactive_parent):
    data = graph()
    sampler = data.pop("5")
    data["10:20:5"] = sampler
    data["30:5"] = {**sampler, "inputs": {**sampler["inputs"], "seed": 123}}
    workflow = {
        "nodes": [{"id": 10, "type": "outer", "mode": mode if inactive_parent else 0}, {"id": 30, "type": "active"}],
        "definitions": {"subgraphs": [
            {"id": "outer", "nodes": [{"id": 20, "type": "inner"}]},
            {"id": "inner", "nodes": [{"id": 5, "type": "KSampler", "mode": 0 if inactive_parent else mode}]},
            {"id": "active", "nodes": [{"id": 5, "type": "KSampler"}]},
        ]},
    }
    fields = {"prompt": json.dumps(data), "workflow": json.dumps(workflow)}
    assert extract_generation_metadata(fields, prefer_saved_image_metadata=False).values["seed"] == 123
    with pytest.raises(MetadataError, match="muted, bypassed"):
        extract_generation_metadata(fields, "10:20:5", prefer_saved_image_metadata=False)


def test_invalid_preferred_parameters_recover_workflow():
    result = extract_generation_metadata({"parameters": "invalid", "prompt": json.dumps(graph())})
    assert result.values["seed"] == 2**64 - 1
    assert any("ERROR: Saved image metadata" in note for note in result.notes)
