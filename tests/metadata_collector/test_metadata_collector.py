import sys
import types
from types import SimpleNamespace
from typing import Any, Dict

from py.metadata_collector import metadata_processor
from py.metadata_collector.metadata_hook import MetadataHook
from py.metadata_collector.metadata_processor import MetadataProcessor
from py.metadata_collector.metadata_registry import MetadataRegistry
from py.metadata_collector.constants import LORAS, MODELS, PROMPTS, SAMPLING, SIZE


def test_metadata_hook_installs_and_traces_execution(monkeypatch, metadata_registry):
    """Ensure MetadataHook installs wrappers and records node execution."""
    fake_execution = types.SimpleNamespace()
    def original_map_node_over_list(obj, input_data_all, func, allow_interrupt=False, execution_block_cb=None, pre_execute_cb=None):
        return {"outputs": "result"}

    def original_execute(*args, **kwargs):
        return "executed"

    fake_execution._map_node_over_list = original_map_node_over_list
    fake_execution.execute = original_execute

    monkeypatch.setitem(sys.modules, "execution", fake_execution)

    MetadataHook.install()

    assert fake_execution._map_node_over_list is not original_map_node_over_list
    assert fake_execution.execute is not original_execute

    calls = []

    def record_stub(self, node_id, class_type, inputs, outputs, return_types=None):
        calls.append(("record", node_id, class_type, inputs))

    def update_stub(self, node_id, class_type, outputs, return_types=None):
        calls.append(("update", node_id, class_type, outputs))

    monkeypatch.setattr(MetadataRegistry, "record_node_execution", record_stub)
    monkeypatch.setattr(MetadataRegistry, "update_node_execution", update_stub)

    metadata_registry.start_collection("prompt-1")
    metadata_registry.set_current_prompt(SimpleNamespace(original_prompt={}))

    class FakeNode:
        FUNCTION = "run"
        unique_id: str = ""

    node = FakeNode()
    node.unique_id = "node-1"

    wrapped_map = fake_execution._map_node_over_list
    result = wrapped_map(node, {"input": ["value"]}, node.FUNCTION)

    assert result == {"outputs": "result"}
    assert ("record", "node-1", "FakeNode", {"input": ["value"]}) in calls
    assert any(call[0] == "update" for call in calls)

    metadata_registry.clear_metadata()

    prompt = SimpleNamespace(original_prompt={})
    execute_wrapper = fake_execution.execute
    execute_wrapper("server", prompt, {}, None, None, None, "prompt-2")

    registry = MetadataRegistry()
    assert registry.current_prompt_id == "prompt-2"
    assert registry.get_metadata("prompt-2")["current_prompt"] is prompt


def test_metadata_processor_extracts_generation_params(populated_registry, monkeypatch):
    metadata = populated_registry["metadata"]
    prompt = populated_registry["prompt"]

    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    sampler_id, sampler_data = MetadataProcessor.find_primary_sampler(metadata, downstream_id="vae")
    assert sampler_id == "sampler"
    assert sampler_data["parameters"]["seed"] == 999

    positive_node = MetadataProcessor.trace_node_input(prompt, "cfg_guider", "positive", target_class="CLIPTextEncode")
    assert positive_node == "encode_pos"

    params = MetadataProcessor.extract_generation_params(metadata)
    assert params["prompt"] == "A castle on a hill"
    assert params["negative_prompt"] == "low quality"
    assert params["seed"] == 999
    assert params["steps"] == 20
    assert params["cfg_scale"] == 7.5
    assert params["sampler"] == "Euler"
    assert params["scheduler"] == "karras"
    assert params["checkpoint"] == "model.safetensors"
    assert params["loras"] == "<lora:my-lora:0.6>"
    assert params["size"] == "128x128"

    params_dict = MetadataProcessor.to_dict(metadata)
    assert params_dict["prompt"] == "A castle on a hill"
    for value in params_dict.values():
        if value is not None:
            assert isinstance(value, str)


def test_attention_bias_clip_text_encode_prompts_are_collected(metadata_registry, monkeypatch):
    import types

    prompt_graph = {
        "encode_pos": {
            "class_type": "CLIPTextEncodeAttentionBias",
            "inputs": {"text": "A <big dog=1.25> on a hill", "clip": ["clip", 0]},
        },
        "encode_neg": {
            "class_type": "CLIPTextEncodeAttentionBias",
            "inputs": {"text": "low quality", "clip": ["clip", 0]},
        },
        "sampler": {
            "class_type": "KSampler",
            "inputs": {
                "seed": types.SimpleNamespace(seed=123),
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "Euler",
                "scheduler": "karras",
                "denoise": 1.0,
                "positive": ["encode_pos", 0],
                "negative": ["encode_neg", 0],
                "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
            },
        },
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)

    pos_conditioning = object()
    neg_conditioning = object()

    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    metadata_registry.start_collection("prompt-attention")
    metadata_registry.set_current_prompt(prompt)

    metadata_registry.record_node_execution(
        "encode_pos",
        "CLIPTextEncodeAttentionBias",
        {"text": "A <big dog=1.25> on a hill"},
        None,
    )
    metadata_registry.update_node_execution(
        "encode_pos", "CLIPTextEncodeAttentionBias", [(pos_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "encode_neg",
        "CLIPTextEncodeAttentionBias",
        {"text": "low quality"},
        None,
    )
    metadata_registry.update_node_execution(
        "encode_neg", "CLIPTextEncodeAttentionBias", [(neg_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "sampler",
        "KSampler",
        {
            "seed": types.SimpleNamespace(seed=123),
            "positive": pos_conditioning,
            "negative": neg_conditioning,
            "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
        },
        None,
    )

    metadata = metadata_registry.get_metadata("prompt-attention")
    sampler_data = metadata[SAMPLING]["sampler"]
    prompt_results = MetadataProcessor.match_conditioning_to_prompts(metadata, "sampler")

    assert metadata[PROMPTS]["encode_pos"]["text"] == "A <big dog=1.25> on a hill"
    assert metadata[PROMPTS]["encode_neg"]["text"] == "low quality"
    assert sampler_data["node_id"] == "sampler"
    assert sampler_data["is_sampler"] is True
    assert prompt_results["prompt"] == "A <big dog=1.25> on a hill"
    assert prompt_results["negative_prompt"] == "low quality"


def test_myoriginalwaifu_text_provider_uses_processed_prompt_outputs(
    metadata_registry, monkeypatch
):
    prompt_graph = {
        "text_provider": {
            "class_type": "TextProvider",
            "inputs": {
                "positive": "raw positive",
                "negative": "raw negative",
            },
        },
        "encode_pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": ["text_provider", 0], "clip": ["clip", 0]},
        },
        "encode_neg": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": ["text_provider", 1], "clip": ["clip", 0]},
        },
        "sampler": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 123,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "Euler",
                "scheduler": "karras",
                "denoise": 1.0,
                "positive": ["encode_pos", 0],
                "negative": ["encode_neg", 0],
                "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
            },
        },
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)

    pos_conditioning = object()
    neg_conditioning = object()

    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    metadata_registry.start_collection("prompt-myoriginalwaifu-text")
    metadata_registry.set_current_prompt(prompt)

    metadata_registry.record_node_execution(
        "text_provider",
        "TextProvider",
        {"positive": "raw positive", "negative": "raw negative"},
        None,
    )
    metadata_registry.update_node_execution(
        "text_provider",
        "TextProvider",
        [("processed positive", "processed negative")],
    )
    metadata_registry.record_node_execution(
        "encode_pos", "CLIPTextEncode", {"text": "processed positive"}, None
    )
    metadata_registry.update_node_execution(
        "encode_pos", "CLIPTextEncode", [(pos_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "encode_neg", "CLIPTextEncode", {"text": "processed negative"}, None
    )
    metadata_registry.update_node_execution(
        "encode_neg", "CLIPTextEncode", [(neg_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "sampler",
        "KSampler",
        {
            "seed": 123,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "Euler",
            "scheduler": "karras",
            "denoise": 1.0,
            "positive": pos_conditioning,
            "negative": neg_conditioning,
            "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
        },
        None,
    )

    metadata = metadata_registry.get_metadata("prompt-myoriginalwaifu-text")
    params = MetadataProcessor.extract_generation_params(metadata)

    assert metadata[PROMPTS]["text_provider"]["positive_text"] == "processed positive"
    assert metadata[PROMPTS]["text_provider"]["negative_text"] == "processed negative"
    assert params["prompt"] == "processed positive"
    assert params["negative_prompt"] == "processed negative"


def test_myoriginalwaifu_clip_provider_prompts_are_collected_without_clip_text_encode(
    metadata_registry, monkeypatch
):
    prompt_graph = {
        "clip_provider": {
            "class_type": "ClipProvider",
            "inputs": {
                "positive": "direct positive",
                "negative": "direct negative",
                "clip": ["clip", 0],
            },
        },
        "sampler": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 123,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "Euler",
                "scheduler": "karras",
                "denoise": 1.0,
                "positive": ["clip_provider", 0],
                "negative": ["clip_provider", 1],
                "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
            },
        },
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)

    pos_conditioning = object()
    neg_conditioning = object()

    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    metadata_registry.start_collection("prompt-myoriginalwaifu-clip")
    metadata_registry.set_current_prompt(prompt)

    metadata_registry.record_node_execution(
        "clip_provider",
        "ClipProvider",
        {"positive": "direct positive", "negative": "direct negative"},
        None,
    )
    metadata_registry.update_node_execution(
        "clip_provider", "ClipProvider", [(pos_conditioning, neg_conditioning)]
    )
    metadata_registry.record_node_execution(
        "sampler",
        "KSampler",
        {
            "seed": 123,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "Euler",
            "scheduler": "karras",
            "denoise": 1.0,
            "positive": pos_conditioning,
            "negative": neg_conditioning,
            "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
        },
        None,
    )

    metadata = metadata_registry.get_metadata("prompt-myoriginalwaifu-clip")
    params = MetadataProcessor.extract_generation_params(metadata)

    assert params["prompt"] == "direct positive"
    assert params["negative_prompt"] == "direct negative"


def test_conditioning_provenance_recovers_combined_controlnet_prompts(
    metadata_registry, monkeypatch
):
    import types

    prompt_graph = {
        "encode_wd": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "wd14 tags", "clip": ["clip", 0]},
        },
        "encode_manual": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "manual tags", "clip": ["clip", 0]},
        },
        "encode_neg": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "low quality", "clip": ["clip", 0]},
        },
        "combine": {
            "class_type": "ConditioningCombine",
            "inputs": {
                "conditioning_1": ["encode_wd", 0],
                "conditioning_2": ["encode_manual", 0],
            },
        },
        "controlnet": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["combine", 0],
                "negative": ["encode_neg", 0],
            },
        },
        "sampler": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 123,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "Euler",
                "scheduler": "karras",
                "denoise": 1.0,
                "positive": ["controlnet", 0],
                "negative": ["controlnet", 1],
                "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
            },
        },
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)

    wd_conditioning = object()
    manual_conditioning = object()
    negative_conditioning = object()
    combined_conditioning = object()
    controlnet_positive = object()
    controlnet_negative = object()

    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    metadata_registry.start_collection("prompt-provenance")
    metadata_registry.set_current_prompt(prompt)

    metadata_registry.record_node_execution(
        "encode_wd", "CLIPTextEncode", {"text": "wd14 tags"}, None
    )
    metadata_registry.update_node_execution(
        "encode_wd", "CLIPTextEncode", [(wd_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "encode_manual", "CLIPTextEncode", {"text": "manual tags"}, None
    )
    metadata_registry.update_node_execution(
        "encode_manual", "CLIPTextEncode", [(manual_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "encode_neg", "CLIPTextEncode", {"text": "low quality"}, None
    )
    metadata_registry.update_node_execution(
        "encode_neg", "CLIPTextEncode", [(negative_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "combine",
        "ConditioningCombine",
        {
            "conditioning_1": wd_conditioning,
            "conditioning_2": manual_conditioning,
        },
        None,
    )
    metadata_registry.update_node_execution(
        "combine", "ConditioningCombine", [(combined_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "controlnet",
        "ControlNetApplyAdvanced",
        {
            "positive": combined_conditioning,
            "negative": negative_conditioning,
        },
        None,
    )
    metadata_registry.update_node_execution(
        "controlnet",
        "ControlNetApplyAdvanced",
        [(controlnet_positive, controlnet_negative)],
    )
    metadata_registry.record_node_execution(
        "sampler",
        "KSampler",
        {
            "seed": 123,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "Euler",
            "scheduler": "karras",
            "denoise": 1.0,
            "positive": controlnet_positive,
            "negative": controlnet_negative,
            "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
        },
        None,
    )

    metadata = metadata_registry.get_metadata("prompt-provenance")
    params = MetadataProcessor.extract_generation_params(metadata)

    assert params["prompt"] == "wd14 tags, manual tags"
    assert params["negative_prompt"] == "low quality"


def test_conditioning_provenance_recovers_transformed_switched_prompts(
    metadata_registry, monkeypatch
):
    prompt_graph = {
        "encode_pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "expected positive", "clip": ["clip", 0]},
        },
        "encode_other_pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "wrong positive", "clip": ["clip", 0]},
        },
        "encode_neg": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "expected negative", "clip": ["clip", 0]},
        },
        "encode_other_neg": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "wrong negative", "clip": ["clip", 0]},
        },
        "enhancer": {
            "class_type": "KreaSeedVarianceEnhancer",
            "inputs": {"conditioning": ["encode_pos", 0]},
        },
        "zero_out": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["encode_neg", 0]},
        },
        "positive_switch": {
            "class_type": "ComfySwitchNode",
            "inputs": {
                "switch": True,
                "on_false": ["encode_other_pos", 0],
                "on_true": ["enhancer", 0],
            },
        },
        "negative_switch": {
            "class_type": "ComfySwitchNode",
            "inputs": {
                "switch": True,
                "on_false": ["encode_other_neg", 0],
                "on_true": ["zero_out", 0],
            },
        },
        "sampler": {
            "class_type": "ClownsharKSampler_Beta",
            "inputs": {
                "seed": 123,
                "steps": 8,
                "cfg": 1.0,
                "sampler_name": "linear/euler",
                "scheduler": "beta57",
                "denoise": 1.0,
                "positive": ["positive_switch", 0],
                "negative": ["negative_switch", 0],
                "latent_image": {
                    "samples": types.SimpleNamespace(shape=(1, 4, 16, 16))
                },
            },
        },
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)

    positive_conditioning = object()
    other_positive_conditioning = object()
    negative_conditioning = object()
    other_negative_conditioning = object()
    enhanced_conditioning = object()
    zeroed_conditioning = object()

    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    metadata_registry.start_collection("prompt-transformed-switch")
    metadata_registry.set_current_prompt(prompt)

    for node_id, text, conditioning in (
        ("encode_pos", "expected positive", positive_conditioning),
        ("encode_other_pos", "wrong positive", other_positive_conditioning),
        ("encode_neg", "expected negative", negative_conditioning),
        ("encode_other_neg", "wrong negative", other_negative_conditioning),
    ):
        metadata_registry.record_node_execution(
            node_id, "CLIPTextEncode", {"text": text}, None
        )
        metadata_registry.update_node_execution(
            node_id, "CLIPTextEncode", [(conditioning,)]
        )

    metadata_registry.record_node_execution(
        "enhancer",
        "KreaSeedVarianceEnhancer",
        {"conditioning": positive_conditioning},
        None,
        return_types=("CONDITIONING", "STRING"),
    )
    metadata_registry.update_node_execution(
        "enhancer",
        "KreaSeedVarianceEnhancer",
        [(enhanced_conditioning, "diagnostics")],
        return_types=("CONDITIONING", "STRING"),
    )
    metadata_registry.record_node_execution(
        "zero_out",
        "ConditioningZeroOut",
        {"conditioning": negative_conditioning},
        None,
        return_types=("CONDITIONING",),
    )
    metadata_registry.update_node_execution(
        "zero_out",
        "ConditioningZeroOut",
        [(zeroed_conditioning,)],
        return_types=("CONDITIONING",),
    )
    metadata_registry.record_node_execution(
        "positive_switch",
        "ComfySwitchNode",
        {
            "switch": True,
            "on_false": other_positive_conditioning,
            "on_true": enhanced_conditioning,
        },
        None,
    )
    metadata_registry.update_node_execution(
        "positive_switch", "ComfySwitchNode", [(enhanced_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "negative_switch",
        "ComfySwitchNode",
        {
            "switch": True,
            "on_false": other_negative_conditioning,
            "on_true": zeroed_conditioning,
        },
        None,
    )
    metadata_registry.update_node_execution(
        "negative_switch", "ComfySwitchNode", [(zeroed_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "sampler",
        "ClownsharKSampler_Beta",
        {
            "seed": 123,
            "steps": 8,
            "cfg": 1.0,
            "sampler_name": "linear/euler",
            "scheduler": "beta57",
            "denoise": 1.0,
            "positive": enhanced_conditioning,
            "negative": zeroed_conditioning,
            "latent_image": {
                "samples": types.SimpleNamespace(shape=(1, 4, 16, 16))
            },
        },
        None,
    )

    metadata = metadata_registry.get_metadata("prompt-transformed-switch")
    params = MetadataProcessor.extract_generation_params(metadata)

    assert params["prompt"] == "expected positive"
    assert params["negative_prompt"] == "expected negative"


def test_conditioning_provenance_identity_switch_between_encoders(
    metadata_registry, monkeypatch
):
    """Lock identity-preserving switches placed directly between encoders.

    A switch returns the selected input conditioning verbatim, so provenance
    must be recovered through object identity without any transform metadata.
    """
    prompt_graph = {
        "encode_pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "chosen positive", "clip": ["clip", 0]},
        },
        "encode_other_pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "unchosen positive", "clip": ["clip", 0]},
        },
        "positive_switch": {
            "class_type": "ComfySwitchNode",
            "inputs": {
                "switch": True,
                "on_false": ["encode_other_pos", 0],
                "on_true": ["encode_pos", 0],
            },
        },
        "sampler": {
            "class_type": "ClownsharKSampler_Beta",
            "inputs": {
                "seed": 123,
                "steps": 8,
                "cfg": 1.0,
                "sampler_name": "linear/euler",
                "scheduler": "beta57",
                "denoise": 1.0,
                "positive": ["positive_switch", 0],
                "negative": ["encode_other_pos", 0],
                "latent_image": {
                    "samples": types.SimpleNamespace(shape=(1, 4, 16, 16))
                },
            },
        },
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)

    chosen_conditioning = object()
    unchosen_conditioning = object()

    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    metadata_registry.start_collection("prompt-identity-switch")
    metadata_registry.set_current_prompt(prompt)

    metadata_registry.record_node_execution(
        "encode_pos", "CLIPTextEncode", {"text": "chosen positive"}, None
    )
    metadata_registry.update_node_execution(
        "encode_pos", "CLIPTextEncode", [(chosen_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "encode_other_pos", "CLIPTextEncode", {"text": "unchosen positive"}, None
    )
    metadata_registry.update_node_execution(
        "encode_other_pos", "CLIPTextEncode", [(unchosen_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "positive_switch",
        "ComfySwitchNode",
        {
            "switch": True,
            "on_false": unchosen_conditioning,
            "on_true": chosen_conditioning,
        },
        None,
    )
    metadata_registry.update_node_execution(
        "positive_switch", "ComfySwitchNode", [(chosen_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "sampler",
        "ClownsharKSampler_Beta",
        {
            "seed": 123,
            "steps": 8,
            "cfg": 1.0,
            "sampler_name": "linear/euler",
            "scheduler": "beta57",
            "denoise": 1.0,
            "positive": chosen_conditioning,
            "negative": unchosen_conditioning,
            "latent_image": {
                "samples": types.SimpleNamespace(shape=(1, 4, 16, 16))
            },
        },
        None,
    )

    metadata = metadata_registry.get_metadata("prompt-identity-switch")
    params = MetadataProcessor.extract_generation_params(metadata)

    assert params["prompt"] == "chosen positive"
    assert params["negative_prompt"] == "unchosen positive"


def test_conditioning_provenance_ignores_scalar_conditioning_fields(
    metadata_registry, monkeypatch
):
    """Scalar fields like ``conditioning_strength`` must not be collected as
    conditioning objects for unregistered transform nodes."""
    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    metadata_registry.start_collection("prompt-scalar-filter")
    metadata_registry.set_current_prompt(SimpleNamespace(original_prompt={}))

    input_conditioning = object()
    metadata_registry.record_node_execution(
        "strength_node",
        "SomeStrengthTransform",
        {"conditioning": input_conditioning, "conditioning_strength": 0.8},
        None,
        return_types=("CONDITIONING",),
    )

    metadata = metadata_registry.get_metadata("prompt-scalar-filter")
    assert metadata[PROMPTS]["strength_node"]["orig_conditionings"] == [
        input_conditioning
    ]


def test_conditioning_provenance_recovers_kj_set_get_prompts(
    metadata_registry, monkeypatch
):
    import types

    prompt_graph = {
        "encode_pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "from set node", "clip": ["clip", 0]},
        },
        "set_positive": {
            "class_type": "SetNode",
            "inputs": {"CONDITIONING": ["encode_pos", 0], "name": "positive"},
        },
        "get_positive": {
            "class_type": "GetNode",
            "inputs": {"name": "positive"},
        },
        "sampler": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 123,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "Euler",
                "scheduler": "karras",
                "denoise": 1.0,
                "positive": ["get_positive", 0],
                "negative": ["encode_pos", 0],
                "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
            },
        },
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)

    original_conditioning = object()
    get_conditioning = object()

    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    metadata_registry.start_collection("prompt-kj-get")
    metadata_registry.set_current_prompt(prompt)

    metadata_registry.record_node_execution(
        "encode_pos", "CLIPTextEncode", {"text": "from set node"}, None
    )
    metadata_registry.update_node_execution(
        "encode_pos", "CLIPTextEncode", [(original_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "set_positive",
        "SetNode",
        {"CONDITIONING": original_conditioning, "name": "positive"},
        None,
    )
    metadata_registry.record_node_execution(
        "get_positive", "GetNode", {"name": "positive"}, None
    )
    metadata_registry.update_node_execution(
        "get_positive", "GetNode", [(get_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "sampler",
        "KSampler",
        {
            "seed": 123,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "Euler",
            "scheduler": "karras",
            "denoise": 1.0,
            "positive": get_conditioning,
            "negative": original_conditioning,
            "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
        },
        None,
    )

    metadata = metadata_registry.get_metadata("prompt-kj-get")
    params = MetadataProcessor.extract_generation_params(metadata)

    assert params["prompt"] == "from set node"
    assert params["negative_prompt"] == "from set node"


def test_sampler_custom_advanced_recovers_prompt_text_through_guidance_nodes(metadata_registry, monkeypatch):
    import types

    prompt_graph = {
        "encode_pos": {
            "class_type": "CLIPTextEncodeAttentionBias",
            "inputs": {
                "text": "A low-angle, medium close-up portrait of her.",
                "clip": ["clip", 0],
            },
        },
        "encode_neg": {
            "class_type": "CLIPTextEncodeAttentionBias",
            "inputs": {
                "text": " This low quality greyscale unfinished sketch is inaccurate and flawed. The image is very blurred and lacks detail with excessive chromatic aberrations and artifacts. The image is overly saturated with excessive bloom. It has a toony aesthetic with bold outlines and flat colors. ",
                "clip": ["clip", 0],
            },
        },
        "scheduled_cfg_guidance": {
            "class_type": "ScheduledCFGGuidance",
            "inputs": {
                "model": ["model", 0],
                "positive": ["encode_pos", 0],
                "negative": ["encode_neg", 0],
                "cfg": 2.6,
                "start_percent": 0.0,
                "end_percent": 0.62,
            },
        },
        "sampler": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": types.SimpleNamespace(seed=174),
                "guider": ["scheduled_cfg_guidance", 0],
                "sampler": ["sampler_select", 0],
                "sigmas": ["scheduler", 0],
                "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 128, 128))},
            },
        },
        "sampler_select": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "multistep/deis_2m"},
        },
        "scheduler": {
            "class_type": "BasicScheduler",
            "inputs": {"steps": 20, "scheduler": "power_shift", "denoise": 1.0},
        },
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)

    pos_conditioning = object()
    neg_conditioning = object()

    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    metadata_registry.start_collection("prompt-guidance")
    metadata_registry.set_current_prompt(prompt)

    metadata_registry.record_node_execution(
        "encode_pos",
        "CLIPTextEncodeAttentionBias",
        {"text": "A low-angle, medium close-up portrait of her."},
        None,
    )
    metadata_registry.update_node_execution(
        "encode_pos", "CLIPTextEncodeAttentionBias", [(pos_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "encode_neg",
        "CLIPTextEncodeAttentionBias",
        {
            "text": " This low quality greyscale unfinished sketch is inaccurate and flawed. The image is very blurred and lacks detail with excessive chromatic aberrations and artifacts. The image is overly saturated with excessive bloom. It has a toony aesthetic with bold outlines and flat colors. ",
        },
        None,
    )
    metadata_registry.update_node_execution(
        "encode_neg", "CLIPTextEncodeAttentionBias", [(neg_conditioning,)]
    )
    metadata_registry.record_node_execution(
        "scheduled_cfg_guidance",
        "ScheduledCFGGuidance",
        {
            "positive": pos_conditioning,
            "negative": neg_conditioning,
            "cfg": 2.6,
        },
        None,
    )
    metadata_registry.record_node_execution(
        "sampler",
        "SamplerCustomAdvanced",
        {
            "noise": types.SimpleNamespace(seed=174),
            "guider": {
                "positive": pos_conditioning,
                "negative": neg_conditioning,
            },
            "sampler": ["sampler_select", 0],
            "sigmas": ["scheduler", 0],
            "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 128, 128))},
        },
        None,
    )

    metadata = metadata_registry.get_metadata("prompt-guidance")
    params = MetadataProcessor.extract_generation_params(metadata)

    assert params["prompt"] == "A low-angle, medium close-up portrait of her."
    assert (
        params["negative_prompt"]
        == " This low quality greyscale unfinished sketch is inaccurate and flawed. The image is very blurred and lacks detail with excessive chromatic aberrations and artifacts. The image is overly saturated with excessive bloom. It has a toony aesthetic with bold outlines and flat colors. "
    )


def test_metadata_registry_caches_and_rehydrates(populated_registry):
    registry = populated_registry["registry"]
    prompt = populated_registry["prompt"]

    assert registry.node_cache  # Cache should contain entries from the first prompt

    new_prompt = SimpleNamespace(original_prompt=prompt.original_prompt)
    registry.start_collection("promptB")
    registry.set_current_prompt(new_prompt)

    cache_entry = registry.node_cache.get("sampler:SamplerCustomAdvanced")
    assert cache_entry is not None

    metadata = registry.get_metadata("promptB")

    assert metadata[MODELS]["loader"]["name"] == "model.safetensors"
    assert metadata[PROMPTS]["loader"]["positive_text"] == "A castle on a hill"
    assert metadata[SAMPLING]["sampler"]["parameters"]["seed"] == 999
    assert metadata[LORAS]["loader"]["lora_list"][0]["name"] == "my-lora"
    assert metadata[SIZE]["sampler"]["width"] == 128

    image = registry.get_first_decoded_image("promptB")
    assert image == "image-data"

    registry.clear_metadata("promptA")
    assert "promptA" not in registry.prompt_metadata


def test_lora_manager_cache_updates_when_loras_removed(metadata_registry):
    import nodes

    class LoraLoaderLM:  # type: ignore[too-many-ancestors]
        __name__ = "LoraLoaderLM"

    nodes.NODE_CLASS_MAPPINGS["LoraLoaderLM"] = LoraLoaderLM  # pyright: ignore[reportAttributeAccessIssue]

    prompt_graph = {
        "lora_node": {"class_type": "LoraLoaderLM", "inputs": {}},
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)
    cache_key = "lora_node:LoraLoaderLM"

    metadata_registry.start_collection("prompt1")
    metadata_registry.set_current_prompt(prompt)
    metadata_registry.record_node_execution(
        "lora_node",
        "LoraLoaderLM",
        {"loras": [[{"name": "foo", "strength": 0.8, "active": True}]]},
        None,
    )
    assert cache_key in metadata_registry.node_cache

    metadata_registry.start_collection("prompt2")
    metadata_registry.set_current_prompt(prompt)
    metadata_registry.record_node_execution("lora_node", "LoraLoaderLM", {"loras": [[]]}, None)

    assert cache_key not in metadata_registry.node_cache

    metadata_registry.start_collection("prompt3")
    metadata_registry.set_current_prompt(prompt)
    metadata = metadata_registry.get_metadata("prompt3")

    assert "lora_node" not in metadata[LORAS]


def test_lora_text_loader_extracts_loras_from_syntax(metadata_registry):
    """LoraTextLoaderLM extractor parses <lora:name:strength> tags from lora_syntax string."""
    metadata_registry.start_collection("prompt1")

    metadata_registry.record_node_execution(
        "text_loader",
        "LoraTextLoaderLM",
        {"lora_syntax": ["<lora:foo:0.8> <lora:bar:1.0>"]},
        None,
    )

    metadata = metadata_registry.get_metadata("prompt1")

    assert "text_loader" in metadata[LORAS]
    lora_list = metadata[LORAS]["text_loader"]["lora_list"]
    assert len(lora_list) == 2
    assert lora_list[0] == {"name": "foo", "strength": 0.8}
    assert lora_list[1] == {"name": "bar", "strength": 1.0}


def test_lora_text_loader_extracts_loras_from_lora_stack(metadata_registry):
    """LoraTextLoaderLM extractor also processes the optional lora_stack input."""
    metadata_registry.start_collection("prompt1")

    metadata_registry.record_node_execution(
        "stack_loader",
        "LoraTextLoaderLM",
        {
            "lora_syntax": [""],
            "lora_stack": (("/models/loras/my-lora.safetensors", 0.6, 0.5),),
        },
        None,
    )

    metadata = metadata_registry.get_metadata("prompt1")

    assert "stack_loader" in metadata[LORAS]
    lora_list = metadata[LORAS]["stack_loader"]["lora_list"]
    assert len(lora_list) == 1
    assert lora_list[0] == {"name": "my-lora", "strength": 0.6}


def test_lora_text_loader_handles_empty_syntax(metadata_registry):
    """LoraTextLoaderLM extractor produces no metadata when no loras are provided."""
    metadata_registry.start_collection("prompt1")

    metadata_registry.record_node_execution(
        "empty_loader",
        "LoraTextLoaderLM",
        {"lora_syntax": [""]},
        None,
    )

    metadata = metadata_registry.get_metadata("prompt1")

    assert "empty_loader" not in metadata[LORAS]



def test_lora_manager_checkpoint_and_unet_loaders_extract_models(metadata_registry):
    metadata_registry.start_collection("prompt1")

    metadata_registry.record_node_execution(
        "checkpoint_node",
        "CheckpointLoaderLM",
        {"ckpt_name": ["models/checkpoint.safetensors"]},
        None,
    )
    metadata_registry.record_node_execution(
        "unet_node",
        "UNETLoaderLM",
        {"unet_name": ["models/diffusion_model.safetensors"], "weight_dtype": ["default"]},
        None,
    )

    metadata = metadata_registry.get_metadata("prompt1")

    assert metadata[MODELS]["checkpoint_node"] == {
        "name": "models/checkpoint.safetensors",
        "type": "checkpoint",
        "node_id": "checkpoint_node",
    }
    assert metadata[MODELS]["unet_node"] == {
        "name": "models/diffusion_model.safetensors",
        "type": "checkpoint",
        "node_id": "unet_node",
    }


# ---------------------------------------------------------------------------
# MetadataOverwriteExtractor & overwrite merge tests
# ---------------------------------------------------------------------------

from py.metadata_collector.constants import OVERWRITE, METADATA_OVERWRITE_FIELDS
from py.metadata_collector.node_extractors import MetadataOverwriteExtractor


def test_metadata_overwrite_extractor_stores_truthy_values(metadata_registry):
    """Extractor should store truthy inputs under the OVERWRITE category."""
    metadata_registry.start_collection("prompt-ow")
    metadata = metadata_registry.prompt_metadata["prompt-ow"]

    inputs = {
        "prompt": "a beautiful landscape",
        "negative_prompt": "",
        "seed": 42,
        "steps": 0,
        "cfg_scale": 7.5,
        "sampler": "",
        "scheduler": "",
        "model": "myModel.safetensors",
        "loras": "<lora:detail:0.8>",
        "size": "1024x768",
        "clip_skip": 0,
        "additional_data": '{"Copyright": "CC0"}',
    }

    MetadataOverwriteExtractor.extract("ow-1", inputs, None, metadata)

    assert OVERWRITE in metadata
    assert "ow-1" in metadata[OVERWRITE]
    params = metadata[OVERWRITE]["ow-1"]["parameters"]

    # Truthy values stored
    assert params["prompt"] == "a beautiful landscape"
    assert params["seed"] == 42
    assert params["cfg_scale"] == 7.5
    assert params["model"] == "myModel.safetensors"
    assert params["loras"] == "<lora:detail:0.8>"
    assert params["size"] == "1024x768"
    assert params["additional_data"] == '{"Copyright": "CC0"}'

    # Falsy values NOT stored
    assert "negative_prompt" not in params
    assert "steps" not in params
    assert "sampler" not in params
    assert "scheduler" not in params
    # clip_skip=0 is now stored (0 != sentinel -25) — wired 0 is valid
    assert params["clip_skip"] == 0

    metadata_registry.clear_metadata()


def test_metadata_overwrite_extractor_empty_inputs(metadata_registry):
    """Extractor with all-falsy inputs should NOT create OVERWRITE category."""
    metadata_registry.start_collection("prompt-ow2")
    metadata = metadata_registry.prompt_metadata["prompt-ow2"]

    from py.metadata_collector.constants import CLIP_SKIP_SENTINEL

    inputs: Dict[str, Any] = {key: "" for key in METADATA_OVERWRITE_FIELDS}
    inputs.update({"seed": 0, "steps": 0, "cfg_scale": 0.0, "clip_skip": CLIP_SKIP_SENTINEL})

    MetadataOverwriteExtractor.extract("ow-2", inputs, None, metadata)

    # start_collection pre-creates empty dicts for all categories,
    # but no node should have populated OVERWRITE with any data
    assert not metadata[OVERWRITE]

    metadata_registry.clear_metadata()


def test_extract_generation_params_applies_overwrite(metadata_registry, populated_registry, monkeypatch):
    """overwrite values should replace inferred params in extract_generation_params."""
    import py.metadata_collector.metadata_processor as mp

    monkeypatch.setattr(mp, "standalone_mode", False)

    metadata = populated_registry["metadata"]
    registry_obj = populated_registry["registry"]

    # Simulate the MetadataOverwriteLM node having been executed with overwrite values
    registry_obj.start_collection("promptA")
    # Re-populate with the same data (start_collection resets)
    registry_obj.set_current_prompt(populated_registry["prompt"])
    metadata2 = registry_obj.prompt_metadata["promptA"]

    # Inject overwrite data into metadata
    metadata2[OVERWRITE] = {
        "ow-1": {
            "parameters": {
                "seed": 777,
                "additional_data": '{"AuthorURL": "https://civitai.com/user/foo"}',
            },
            "node_id": "ow-1",
        }
    }
    # Copy other categories from original populated metadata
    for cat in ("models", "prompts", "sampling", "loras", "size", "images"):
        if cat in metadata:
            metadata2[cat] = metadata[cat]
    metadata2["execution_order"] = metadata["execution_order"]

    params = MetadataProcessor.extract_generation_params(metadata2, id="vae")

    # Overwritten values
    assert params["seed"] == 777
    assert params["additional_data"] == '{"AuthorURL": "https://civitai.com/user/foo"}'

    # Inferred values still present (not overwritten)
    assert params["prompt"] == "A castle on a hill"
    assert params["cfg_scale"] == 7.5
    assert params["checkpoint"] == "model.safetensors"

    registry_obj.clear_metadata()


def test_extract_generation_params_overwrite_falsy_skipped(metadata_registry, populated_registry, monkeypatch):
    """Overwrite entries with falsy values should NOT replace inferred params."""
    import py.metadata_collector.metadata_processor as mp

    monkeypatch.setattr(mp, "standalone_mode", False)

    metadata = populated_registry["metadata"]
    registry_obj = populated_registry["registry"]

    registry_obj.start_collection("promptA")
    registry_obj.set_current_prompt(populated_registry["prompt"])
    metadata2 = registry_obj.prompt_metadata["promptA"]

    # Inject overwrite with falsy values (except clip_skip=0 which is now
    # treated as a valid wired input thanks to the -25 sentinel)
    metadata2[OVERWRITE] = {
        "ow-1": {
            "parameters": {
                "seed": 0,
                "steps": 0,
                "cfg_scale": 0.0,
                "prompt": "",
                "clip_skip": 0,
            },
            "node_id": "ow-1",
        }
    }
    for cat in ("models", "prompts", "sampling", "loras", "size", "images"):
        if cat in metadata:
            metadata2[cat] = metadata[cat]
    metadata2["execution_order"] = metadata["execution_order"]

    params = MetadataProcessor.extract_generation_params(metadata2, id="vae")

    # Falsy overwrites should NOT have replaced inferred values
    assert params["prompt"] == "A castle on a hill"
    assert params["cfg_scale"] == 7.5

    # clip_skip=0 is a valid wired value (not the -25 sentinel) — should be applied
    assert params["clip_skip"] == 0

    registry_obj.clear_metadata()


def test_fill_missing_metadata_skips_overwrite_for_bypassed_node(metadata_registry):
    """Bypassed (mode=4) node should not have OVERWRITE filled from cache."""
    metadata_registry.start_collection("prompt-bypass")

    # Simulate a previous execution that cached overwrite data
    metadata_registry.record_node_execution(
        "ow-1",
        "MetadataOverwriteLM",
        {"seed": 99, "prompt": "test", "steps": 0, "cfg_scale": 0.0,
         "negative_prompt": "", "sampler": "", "scheduler": "", "model": "",
         "loras": "", "size": "", "clip_skip": 0, "additional_data": ""},
        None,
    )

    # Now start a new prompt where the node is bypassed (mode=4)
    metadata_registry.start_collection("prompt-bypass-2")
    original_prompt = {
        "ow-1": {"class_type": "MetadataOverwriteLM", "inputs": {}, "mode": 4},
    }
    metadata_registry.set_current_prompt(
        SimpleNamespace(original_prompt=original_prompt)
    )

    metadata = metadata_registry.get_metadata("prompt-bypass-2")

    # The overwrite data should NOT be present (node was bypassed, not
    # a cache hit — it should not inherit previous execution's overwrite)
    assert "ow-1" not in metadata.get(OVERWRITE, {})

    metadata_registry.clear_metadata()


def test_fill_missing_metadata_fills_overwrite_for_muted_node(metadata_registry):
    """Muted (mode=2) node should also not have OVERWRITE filled from cache."""
    metadata_registry.start_collection("prompt-mute")

    # Simulate a previous execution that cached overwrite data
    metadata_registry.record_node_execution(
        "ow-1",
        "MetadataOverwriteLM",
        {"seed": 88, "prompt": "test2", "steps": 0, "cfg_scale": 0.0,
         "negative_prompt": "", "sampler": "", "scheduler": "", "model": "",
         "loras": "", "size": "", "clip_skip": 0, "additional_data": ""},
        None,
    )

    # Start a new prompt where the node is muted (mode=2)
    metadata_registry.start_collection("prompt-mute-2")
    original_prompt = {
        "ow-1": {"class_type": "MetadataOverwriteLM", "inputs": {}, "mode": 2},
    }
    metadata_registry.set_current_prompt(
        SimpleNamespace(original_prompt=original_prompt)
    )

    metadata = metadata_registry.get_metadata("prompt-mute-2")

    assert "ow-1" not in metadata.get(OVERWRITE, {})

    metadata_registry.clear_metadata()
