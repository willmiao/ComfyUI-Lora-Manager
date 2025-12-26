import pytest
from py.recipes.merger import GenParamsMerger

def test_merge_priority():
    request_params = {"prompt": "from request", "steps": 20}
    civitai_meta = {"prompt": "from civitai", "cfg": 7.0}
    embedded_metadata = {"gen_params": {"prompt": "from embedded", "seed": 123}}
    
    merged = GenParamsMerger.merge(request_params, civitai_meta, embedded_metadata)
    
    assert merged["prompt"] == "from request"
    assert merged["steps"] == 20
    assert merged["cfg"] == 7.0
    assert merged["seed"] == 123

def test_merge_no_request_params():
    civitai_meta = {"prompt": "from civitai", "cfg": 7.0}
    embedded_metadata = {"gen_params": {"prompt": "from embedded", "seed": 123}}
    
    merged = GenParamsMerger.merge(None, civitai_meta, embedded_metadata)
    
    assert merged["prompt"] == "from civitai"
    assert merged["cfg"] == 7.0
    assert merged["seed"] == 123

def test_merge_only_embedded():
    embedded_metadata = {"gen_params": {"prompt": "from embedded", "seed": 123}}
    
    merged = GenParamsMerger.merge(None, None, embedded_metadata)
    
    assert merged["prompt"] == "from embedded"
    assert merged["seed"] == 123

def test_merge_raw_embedded():
    # Test when embedded metadata is just the gen_params themselves
    embedded_metadata = {"prompt": "from raw embedded", "seed": 456}
    
    merged = GenParamsMerger.merge(None, None, embedded_metadata)
    
    assert merged["prompt"] == "from raw embedded"
    assert merged["seed"] == 456

def test_merge_none_values():
    merged = GenParamsMerger.merge(None, None, None)
    assert merged == {}

def test_merge_filters_blacklisted_keys():
    request_params = {"prompt": "test", "id": "should-be-removed", "checkpoint": "should-not-be-here"}
    civitai_meta = {"cfg": 7, "url": "remove-me"}
    embedded_metadata = {"seed": 123, "hash": "remove-also"}
    
    merged = GenParamsMerger.merge(request_params, civitai_meta, embedded_metadata)
    
    assert "prompt" in merged
    assert "cfg" in merged
    assert "seed" in merged
    assert "id" not in merged
    assert "url" not in merged
    assert "hash" not in merged
    assert "checkpoint" not in merged

def test_merge_filters_meta_and_normalizes_keys():
    civitai_meta = {
        "prompt": "masterpiece",
        "cfgScale": 5,
        "clipSkip": 2,
        "negativePrompt": "low quality",
        "meta": {"irrelevant": "data"},
        "Size": "1024x1024",
        "draft": False,
        "workflow": "txt2img",
        "civitaiResources": [{"type": "checkpoint"}]
    }
    request_params = {
        "cfg_scale": 5.0,
        "clip_skip": "2",
        "Steps": 30
    }
    
    merged = GenParamsMerger.merge(request_params, civitai_meta)
    
    assert "meta" not in merged
    assert "cfgScale" not in merged
    assert "clipSkip" not in merged
    assert "negativePrompt" not in merged
    assert "Size" not in merged
    assert "draft" not in merged
    assert "workflow" not in merged
    assert "civitaiResources" not in merged
    
    assert merged["cfg_scale"] == 5.0  # From request_params
    assert merged["clip_skip"] == "2"  # From request_params
    assert merged["negative_prompt"] == "low quality" # Normalized from civitai_meta
    assert merged["size"] == "1024x1024" # Normalized from civitai_meta
    assert merged["steps"] == 30 # Normalized from request_params
