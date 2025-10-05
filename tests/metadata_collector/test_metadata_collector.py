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
