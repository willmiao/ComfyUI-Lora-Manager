import sys
import types
from types import SimpleNamespace

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

    def record_stub(self, node_id, class_type, inputs, outputs):
        calls.append(("record", node_id, class_type, inputs))

    def update_stub(self, node_id, class_type, outputs):
        calls.append(("update", node_id, class_type, outputs))

    monkeypatch.setattr(MetadataRegistry, "record_node_execution", record_stub)
    monkeypatch.setattr(MetadataRegistry, "update_node_execution", update_stub)

    metadata_registry.start_collection("prompt-1")
    metadata_registry.set_current_prompt(SimpleNamespace(original_prompt={}))

    class FakeNode:
        FUNCTION = "run"

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

    nodes.NODE_CLASS_MAPPINGS["LoraLoaderLM"] = LoraLoaderLM

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
