from py.nodes.anima_remap import (
    find_block_indices,
    get_block_count,
    maybe_remap_lora,
    remap_lora_keys,
    resolve_mapping,
)
from py.nodes.lora_loader import LoraLoaderLM, LoraTextLoaderLM


class _ModelContainer:
    def __init__(self, diffusion_model):
        self.diffusion_model = diffusion_model


class _Model:
    def __init__(self, diffusion_model):
        self.model = _ModelContainer(diffusion_model)


def _lora_keys(count, prefix="net.blocks."):
    return [f"{prefix}{i}.self_attn.q_proj.lora_A.weight" for i in range(count)]


def _lora_sd(count):
    return {key: object() for key in _lora_keys(count)}


# ---------------------------------------------------------------------------
# Manifest / mapping resolution
# ---------------------------------------------------------------------------

def test_manifest_28_40_is_the_official_layout():
    mapping = resolve_mapping(28, 40)
    assert mapping is not None
    # Blocks 0 and 1 keep their indices; everything after shifts.
    assert mapping[0] == 0
    assert mapping[1] == 1
    assert mapping[2] == 3
    assert mapping[27] == 39
    assert len(mapping) == 28


def test_manifest_40_52_covers_all_source_blocks():
    mapping = resolve_mapping(40, 52)
    assert mapping is not None
    assert len(mapping) == 40
    assert sorted(mapping.values()) == [i for i in range(52) if i not in {3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47}]


def test_composed_28_52_chains_through_40():
    direct = resolve_mapping(28, 52)
    assert direct is not None
    step_a = resolve_mapping(28, 40)
    step_b = resolve_mapping(40, 52)
    assert step_a is not None and step_b is not None
    composed = {src: step_b[mid] for src, mid in step_a.items()}
    assert direct == composed


def test_resolve_mapping_returns_none_when_counts_match_or_unknown():
    assert resolve_mapping(40, 40) is None
    assert resolve_mapping(12, 40) is None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_find_block_indices_ignores_llm_adapter_and_connector_keys():
    keys = [
        "net.blocks.5.self_attn.q_proj.lora_A.weight",
        "llm_adapter.blocks.0.attn.weight",
        "semantic_attentions.connector.blocks.9.weight",
        "lora_unet_blocks_12_self_attn_q_proj.lora_down.weight",
    ]
    assert find_block_indices(keys) == {5, 12}


def test_get_block_count_returns_highest_index_plus_one():
    assert get_block_count(_lora_keys(28)) == 28
    assert get_block_count(["final_layer.weight", "net.embed.weight"]) is None


# ---------------------------------------------------------------------------
# Key rewriting
# ---------------------------------------------------------------------------

def test_remap_lora_keys_rewrites_dot_and_kohya_styles():
    mapping = {0: 0, 1: 3}
    sd = {
        "diffusion_model.blocks.1.self_attn.q_proj.lora_A.weight": "t1",
        "lora_unet_blocks_1_self_attn_q_proj.lora_down.weight": "t2",
        "llm_adapter.blocks.1.attn.weight": "t3",
        "net.embed.weight": "t4",
    }
    result = remap_lora_keys(sd, mapping)
    assert "diffusion_model.blocks.3.self_attn.q_proj.lora_A.weight" in result
    assert "lora_unet_blocks_3_self_attn_q_proj.lora_down.weight" in result
    # Skipped sub-structures and non-block keys pass through unchanged.
    assert result["llm_adapter.blocks.1.attn.weight"] == "t3"
    assert result["net.embed.weight"] == "t4"


def test_remap_lora_keys_drops_unmapped_block_indices():
    result = remap_lora_keys({"net.blocks.9.x.weight": "t"}, {0: 0})
    assert result == {}


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------

def test_maybe_remap_lora_noop_cases():
    sd = _lora_sd(28)
    assert maybe_remap_lora(sd, None) is sd
    assert maybe_remap_lora(sd, 28) is sd
    # LoRA already at/above model size passes through untouched.
    assert maybe_remap_lora(_lora_sd(52), 40) is not None


def test_maybe_remap_lora_applies_28_to_52_chain():
    sd = _lora_sd(28)
    remapped = maybe_remap_lora(sd, 52)
    assert get_block_count(remapped.keys()) == 52
    assert len(remapped) == 28
    expected = resolve_mapping(28, 52)
    assert expected is not None
    for src, tgt in expected.items():
        assert f"net.blocks.{tgt}.self_attn.q_proj.lora_A.weight" in remapped


def test_maybe_remap_lora_unknown_pair_returns_unchanged():
    sd = _lora_sd(12)
    assert maybe_remap_lora(sd, 40) is sd


# ---------------------------------------------------------------------------
# Loader integration (regression: anima_remap flag must exist on both nodes)
# ---------------------------------------------------------------------------

def _patch_common(monkeypatch, lora_sd):
    monkeypatch.setattr(
        "py.nodes.lora_loader.get_lora_info_absolute",
        lambda name: (f"/abs/{name}.safetensors", [f"{name}_trigger"]),
    )
    monkeypatch.setattr("comfy.utils.load_torch_file", lambda path, safe_load=True: dict(lora_sd))
    applied = []

    def mock_load_lora_for_models(model_arg, clip_arg, lora_arg, model_strength, clip_strength):
        applied.append(lora_arg)
        return model_arg, clip_arg

    monkeypatch.setattr("comfy.sd.load_lora_for_models", mock_load_lora_for_models)
    return applied


def test_lora_loader_load_loras_honours_anima_remap_flag(monkeypatch):
    lora_sd = _lora_sd(28)
    applied = _patch_common(monkeypatch, lora_sd)
    loader = LoraLoaderLM()
    model = _Model(object())

    loader.load_loras(
        model,
        "",
        {"__value__": [{"active": True, "name": "demo", "strength": 1.0}]},
        anima_remap=True,
    )
    assert len(applied) == 1

    # anima_remap=False must skip remapping entirely.
    applied.clear()
    loader.load_loras(
        model,
        "",
        {"__value__": [{"active": True, "name": "demo", "strength": 1.0}]},
        anima_remap=False,
    )
    assert applied[0].keys() == lora_sd.keys()


def test_lora_text_loader_anima_remap_default_on(monkeypatch):
    lora_sd = _lora_sd(28)
    applied = _patch_common(monkeypatch, lora_sd)
    loader = LoraTextLoaderLM()
    model = _Model(object())

    loader.load_loras_from_text(model, "<lora:demo:1.0>")
    # No block count detectable on the bare object() model -> pass-through.
    assert len(applied) == 1
