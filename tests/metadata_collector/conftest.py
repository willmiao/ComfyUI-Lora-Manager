import types
from types import SimpleNamespace

import pytest

from py.metadata_collector.metadata_registry import MetadataRegistry


@pytest.fixture
def metadata_registry():
    """Provide a clean MetadataRegistry singleton for each test."""
    registry = MetadataRegistry()
    registry.clear_metadata()
    yield registry
    registry.clear_metadata()


@pytest.fixture
def populated_registry(metadata_registry):
    """Populate the registry with a simulated ComfyUI node graph."""
    import nodes

    # Ensure node mappings exist for extractor lookups
    class TSC_EfficientLoader:  # type: ignore[too-many-ancestors]
        __name__ = "TSC_EfficientLoader"

    class SamplerCustomAdvanced:  # type: ignore[too-many-ancestors]
        __name__ = "SamplerCustomAdvanced"

    class BasicScheduler:  # type: ignore[too-many-ancestors]
        __name__ = "BasicScheduler"

    class KSamplerSelect:  # type: ignore[too-many-ancestors]
        __name__ = "KSamplerSelect"

    class CFGGuider:  # type: ignore[too-many-ancestors]
        __name__ = "CFGGuider"

    class CLIPTextEncode:  # type: ignore[too-many-ancestors]
        __name__ = "CLIPTextEncode"

    class VAEDecode:  # type: ignore[too-many-ancestors]
        __name__ = "VAEDecode"

    nodes.NODE_CLASS_MAPPINGS.update(
        {
            "TSC_EfficientLoader": TSC_EfficientLoader,
            "SamplerCustomAdvanced": SamplerCustomAdvanced,
            "BasicScheduler": BasicScheduler,
            "KSamplerSelect": KSamplerSelect,
            "CFGGuider": CFGGuider,
            "CLIPTextEncode": CLIPTextEncode,
            "VAEDecode": VAEDecode,
        }
    )

    prompt_graph = {
        "loader": {"class_type": "TSC_EfficientLoader", "inputs": {}},
        "encode_pos": {"class_type": "CLIPTextEncode", "inputs": {"text": "A castle on a hill"}},
        "encode_neg": {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality"}},
        "cfg_guider": {
            "class_type": "CFGGuider",
            "inputs": {
                "cfg": 7.5,
                "positive": ["encode_pos", 0],
                "negative": ["encode_neg", 0],
            },
        },
        "scheduler": {
            "class_type": "BasicScheduler",
            "inputs": {
                "steps": 20,
                "scheduler": "karras",
            },
        },
        "sampler_select": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "Euler"},
        },
        "sampler": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "sigmas": ["scheduler", 0],
                "sampler": ["sampler_select", 0],
                "guider": ["cfg_guider", 0],
                "positive": ["cfg_guider", 0],
                "negative": ["cfg_guider", 0],
            },
        },
        "vae": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["sampler", 0]},
        },
    }

    prompt = SimpleNamespace(original_prompt=prompt_graph)

    pos_conditioning = object()
    neg_conditioning = object()
    latent_samples = types.SimpleNamespace(shape=(1, 4, 16, 16))

    metadata_registry.start_collection("promptA")
    metadata_registry.set_current_prompt(prompt)

    # Loader node populates checkpoint, loras, and prompt text metadata
    loader_inputs = {
        "ckpt_name": "model.safetensors",
        "lora_stack": (("/loras/my-lora.safetensors", 0.6, 0.5),),
        "positive": "A castle on a hill",
        "negative": "low quality",
    }
    metadata_registry.record_node_execution("loader", "TSC_EfficientLoader", loader_inputs, None)
    loader_outputs = [
        (
            None,
            pos_conditioning,
            neg_conditioning,
            {"samples": latent_samples},
            None,
            None,
            {},
        )
    ]
    metadata_registry.update_node_execution("loader", "TSC_EfficientLoader", loader_outputs)

    # Positive and negative prompt encoders
    metadata_registry.record_node_execution("encode_pos", "CLIPTextEncode", {"text": "A castle on a hill"}, None)
    metadata_registry.update_node_execution("encode_pos", "CLIPTextEncode", [(pos_conditioning,)])
    metadata_registry.record_node_execution("encode_neg", "CLIPTextEncode", {"text": "low quality"}, None)
    metadata_registry.update_node_execution("encode_neg", "CLIPTextEncode", [(neg_conditioning,)])

    # CFG guider and scheduler nodes
    metadata_registry.record_node_execution("cfg_guider", "CFGGuider", {"cfg": 7.5}, None)
    metadata_registry.record_node_execution(
        "scheduler",
        "BasicScheduler",
        {"steps": 20, "scheduler": "karras"},
        None,
    )
    metadata_registry.record_node_execution(
        "sampler_select", "KSamplerSelect", {"sampler_name": "Euler"}, None
    )

    # Sampler execution populates sampling metadata and links conditioning
    sampler_inputs = {
        "noise": types.SimpleNamespace(seed=999),
        "positive": pos_conditioning,
        "negative": neg_conditioning,
        "latent_image": {"samples": latent_samples},
    }
    metadata_registry.record_node_execution("sampler", "SamplerCustomAdvanced", sampler_inputs, None)

    # VAEDecode outputs image data
    metadata_registry.record_node_execution("vae", "VAEDecode", {}, None)
    metadata_registry.update_node_execution("vae", "VAEDecode", ["image-data"])

    metadata = metadata_registry.get_metadata("promptA")

    return {
        "registry": metadata_registry,
        "prompt": prompt,
        "metadata": metadata,
        "pos_conditioning": pos_conditioning,
        "neg_conditioning": neg_conditioning,
    }
