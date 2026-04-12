from py.recipes.merger import GenParamsMerger


def test_merge_priority_and_normalization():
    request_params = {"prompt": "from request", "Steps": 20, "cfg": 7.5}
    civitai_meta = {"prompt": "from civitai", "cfgScale": 6.5, "negativePrompt": "bad"}
    embedded_metadata = {"gen_params": {"prompt": "from embedded", "seed": 123}}

    merged = GenParamsMerger.merge(request_params, civitai_meta, embedded_metadata)

    assert merged == {
        "prompt": "from request",
        "steps": 20,
        "cfg_scale": 7.5,
        "negative_prompt": "bad",
        "seed": 123,
    }


def test_merge_accepts_raw_embedded_metadata():
    embedded_metadata = {"prompt": "from raw embedded", "seed": 456, "scheduler": "karras"}

    merged = GenParamsMerger.merge(None, None, embedded_metadata)

    assert merged == {
        "prompt": "from raw embedded",
        "seed": 456,
        "sampler": "karras",
    }


def test_merge_filters_unknown_and_blacklisted_keys():
    request_params = {
        "prompt": "test",
        "id": "should-be-removed",
        "checkpoint": "should-not-be-here",
        "raw_metadata": {"prompt": "remove"},
    }
    civitai_meta = {
        "Version": "ComfyUI",
        "RNG": "cpu",
        "cfgScale": 7,
        "url": "remove-me",
    }
    embedded_metadata = {
        "seed": 123,
        "hash": "remove-also",
        "Discard penultimate sigma": True,
        "eps_scaling_factor": 0.1,
    }

    merged = GenParamsMerger.merge(request_params, civitai_meta, embedded_metadata)

    assert merged == {
        "prompt": "test",
        "cfg_scale": 7,
        "seed": 123,
    }


def test_merge_does_not_keep_original_key_variants():
    civitai_meta = {
        "cfgScale": 5,
        "clipSkip": 2,
        "negativePrompt": "low quality",
        "Size": "1024x1024",
        "Denoising strength": 0.35,
    }
    request_params = {
        "cfg_scale": 5.0,
        "clip_skip": "2",
    }

    merged = GenParamsMerger.merge(request_params, civitai_meta)

    assert merged == {
        "cfg_scale": 5.0,
        "clip_skip": "2",
        "negative_prompt": "low quality",
        "size": "1024x1024",
        "denoising_strength": 0.35,
    }


def test_merge_none_values():
    assert GenParamsMerger.merge(None, None, None) == {}
