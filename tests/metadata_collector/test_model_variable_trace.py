"""Tests for MODEL variable tracing (KJNodes Set/Get) and stale checkpoint
cache-fill validation in the metadata collector."""

import types
from types import SimpleNamespace

from py.metadata_collector import metadata_processor
from py.metadata_collector.constants import MODELS
from py.metadata_collector.metadata_processor import MetadataProcessor
from py.metadata_collector.metadata_registry import (
    MetadataRegistry,
    _checkpoint_name_candidates,
)


def _ksampler_inputs():
    return {
        "seed": 123,
        "steps": 8,
        "cfg": 1.0,
        "sampler_name": "er_sde",
        "scheduler": "simple",
        "denoise": 1.0,
        "latent_image": {"samples": types.SimpleNamespace(shape=(1, 4, 16, 16))},
    }


def test_primary_checkpoint_follows_kj_set_get_model_chain(
    metadata_registry, monkeypatch
):
    """Sampler <- GetNode <- (virtual) <- SetNode <- UNETLoader must resolve to
    the UNETLoader even though the Set/Get links do not exist in the API prompt."""
    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    unet_name = "Krea 2/base model/krea2_turbo_int8_convrot.safetensors"
    prompt_graph = {
        "54": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "32": {
            "class_type": "SetNode",
            "inputs": {"MODEL": ["54", 0], "name": "MODEL"},
        },
        "57": {"class_type": "GetNode", "inputs": {"name": "MODEL"}},
        "9": {
            "class_type": "KSampler",
            "inputs": {**_ksampler_inputs(), "model": ["57", 0]},
        },
    }
    prompt = SimpleNamespace(original_prompt=prompt_graph)

    metadata_registry.start_collection("prompt-set-get-model")
    metadata_registry.set_current_prompt(prompt)
    metadata_registry.record_node_execution(
        "54", "UNETLoader", {"unet_name": unet_name, "weight_dtype": "default"}, None
    )
    metadata_registry.record_node_execution(
        "32", "SetNode", {"MODEL": object(), "name": "MODEL"}, None
    )
    metadata_registry.record_node_execution("57", "GetNode", {"name": "MODEL"}, None)
    metadata_registry.record_node_execution("9", "KSampler", _ksampler_inputs(), None)

    metadata = metadata_registry.get_metadata("prompt-set-get-model")

    # The SetNode recorded a variable reference, not a checkpoint entry.
    set_entry = metadata[MODELS]["32"]
    assert set_entry["type"] == "model_variable"
    assert set_entry["variable_name"] == "MODEL"
    assert set_entry["source_node_id"] == "54"

    params = MetadataProcessor.extract_generation_params(metadata)
    assert params["checkpoint"] == unet_name


def test_stale_checkpoint_cache_fill_rebuilt_from_current_inputs(
    metadata_registry, monkeypatch
):
    """A loader cached with model A, then switched to model B but not
    re-executed (ComfyUI served its output from cache), must not resurrect
    model A's name into the new prompt's metadata."""
    monkeypatch.setattr(metadata_processor, "standalone_mode", False)

    # Run A: loader executes with the old model.
    prompt_a = SimpleNamespace(
        original_prompt={
            "54": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "old/myKrea2.safetensors"},
            },
        }
    )
    metadata_registry.start_collection("prompt-old")
    metadata_registry.set_current_prompt(prompt_a)
    metadata_registry.record_node_execution(
        "54", "UNETLoader", {"unet_name": "old/myKrea2.safetensors"}, None
    )
    metadata_registry.get_metadata("prompt-old")

    # Run B: widget switched to a new model; the loader itself does not
    # execute (its output comes from ComfyUI's execution cache).
    prompt_b = SimpleNamespace(
        original_prompt={
            "54": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "new/krea2_turbo_int8_convrot.safetensors"},
            },
            "9": {"class_type": "KSampler", "inputs": {"model": ["54", 0]}},
        }
    )
    metadata_registry.start_collection("prompt-new")
    metadata_registry.set_current_prompt(prompt_b)
    metadata_registry.record_node_execution("9", "KSampler", _ksampler_inputs(), None)

    metadata = metadata_registry.get_metadata("prompt-new")
    assert (
        metadata[MODELS]["54"]["name"] == "new/krea2_turbo_int8_convrot.safetensors"
    )

    params = MetadataProcessor.extract_generation_params(metadata)
    assert params["checkpoint"] == "new/krea2_turbo_int8_convrot.safetensors"


def test_checkpoint_cache_fill_trusted_when_inputs_match(metadata_registry):
    """Unchanged inputs: the cached entry is filled unchanged."""
    prompt = SimpleNamespace(
        original_prompt={
            "54": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "models/flux.safetensors"},
            },
        }
    )
    metadata_registry.start_collection("prompt-one")
    metadata_registry.set_current_prompt(prompt)
    metadata_registry.record_node_execution(
        "54", "UNETLoader", {"unet_name": "models/flux.safetensors"}, None
    )
    metadata_registry.get_metadata("prompt-one")

    # Identical re-run: nothing executes, everything fills from cache.
    metadata_registry.start_collection("prompt-two")
    metadata_registry.set_current_prompt(prompt)
    metadata = metadata_registry.get_metadata("prompt-two")
    assert metadata[MODELS]["54"]["name"] == "models/flux.safetensors"


def test_validated_checkpoint_fill_trust_cases():
    """Direct checks of the trust/rebuild/drop rules."""
    node_data = {"inputs": {"unet_name": "a/model_b.safetensors"}}

    # Not a checkpoint entry — passed through.
    assert MetadataRegistry._validated_checkpoint_fill(
        {"type": "model_variable"}, node_data
    ) == {"type": "model_variable"}

    # Extension-less cached name (e.g. set from runtime attachments) — trusted.
    entry = {"type": "checkpoint", "name": "flux1-dev"}
    assert MetadataRegistry._validated_checkpoint_fill(entry, node_data) is entry

    # Matching name — trusted unchanged.
    entry = {"type": "checkpoint", "name": "a/model_b.safetensors"}
    assert MetadataRegistry._validated_checkpoint_fill(entry, node_data) is entry

    # Stale name — rebuilt from current inputs.
    entry = {"type": "checkpoint", "name": "a/model_a.safetensors"}
    rebuilt = MetadataRegistry._validated_checkpoint_fill(entry, node_data)
    assert rebuilt["name"] == "a/model_b.safetensors"
    assert rebuilt["type"] == "checkpoint"

    # Unparseable model field (no recognizable value) — cache trusted as-is.
    entry = {"type": "checkpoint", "name": "a/model_a.safetensors"}
    assert (
        MetadataRegistry._validated_checkpoint_fill(entry, {"inputs": {"unet_name": 123}})
        is entry
    )


def test_checkpoint_name_candidates_derivations():
    candidates = _checkpoint_name_candidates(
        {"unet_name": "dir/sub/model_$fp16_00001_.engine"}
    )
    assert "dir/sub/model_$fp16_00001_.engine" in candidates
    assert "model_$fp16_00001_" in candidates
    assert "model" in candidates  # TensorRT-style derivation

    assert _checkpoint_name_candidates({"unet_name": "not-a-model"}) == set()
    assert _checkpoint_name_candidates({}) == set()
