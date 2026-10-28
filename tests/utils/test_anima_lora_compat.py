from __future__ import annotations

import pytest

from py.utils.lora_compat import LoraCompatibilityError, prepare_lora
from py.utils.lora_compat import anima


class _Config:
    def __init__(self, blocks: int, image_model: str = "anima"):
        self.unet_config = {"image_model": image_model, "num_blocks": blocks}


class _DiffusionModel:
    def __init__(self, blocks: int):
        self.blocks = [object() for _ in range(blocks)]


class _InnerModel:
    def __init__(self, blocks: int, image_model: str = "anima"):
        self.model_config = _Config(blocks, image_model)
        self.diffusion_model = _DiffusionModel(blocks)


class _Model:
    def __init__(self, blocks: int, image_model: str = "anima"):
        self.model = _InnerModel(blocks, image_model)


def _lora(count: int, style: str = "kohya") -> dict[str, object]:
    if style == "generic":
        return {
            f"diffusion_model.blocks.{index}.self_attn.q_proj.lora_A.weight": object()
            for index in range(count)
        }
    return {
        f"lora_unet_blocks_{index}_self_attn_q_proj.lora_down.weight": object()
        for index in range(count)
    }


def test_resolve_mapping_28_to_40():
    mapping = anima.resolve_mapping(28, 40)

    assert mapping is not None
    assert mapping[0] == 0
    assert mapping[1] == 1
    assert mapping[2] == 3
    assert mapping[13] == 19
    assert mapping[27] == 39
    assert len(mapping) == 28


def test_resolve_mapping_40_to_52():
    mapping = anima.resolve_mapping(40, 52)

    assert mapping is not None
    assert mapping[0] == 0
    assert mapping[3] == 4
    assert mapping[39] == 51
    assert len(mapping) == 40


def test_resolve_mapping_28_to_52_is_composed():
    mapping = anima.resolve_mapping(28, 52)

    assert mapping is not None
    assert mapping[2] == 4
    assert mapping[27] == 51
    assert len(mapping) == 28


def test_resolve_mapping_same_layout_is_a_noop():
    assert anima.resolve_mapping(40, 40) is None


def test_resolve_mapping_rejects_newer_lora_on_older_model():
    with pytest.raises(LoraCompatibilityError, match="cannot be remapped down"):
        anima.resolve_mapping(52, 40)


def test_detect_block_count_for_known_layouts():
    assert anima.detect_lora_block_count(_lora(28).keys()) == 28
    assert anima.detect_lora_block_count(_lora(40, "generic").keys()) == 40
    assert anima.detect_lora_block_count(_lora(52).keys()) == 52


def test_detect_block_count_supports_net_prefixed_kohya_and_transformer_keys():
    net_prefixed = [f"lora_unet_net_blocks_{index}_x" for index in range(28)]
    transformer = [f"transformer.blocks.{index}.x" for index in range(40)]

    assert anima.detect_lora_block_count(net_prefixed) == 28
    assert anima.detect_lora_block_count(transformer) == 40


def test_detect_block_count_buckets_partial_loras():
    assert anima.detect_lora_block_count(_lora(26).keys()) == 28
    assert anima.detect_lora_block_count(_lora(35).keys()) == 40
    assert anima.detect_lora_block_count(_lora(45).keys()) == 52


def test_detect_block_count_ignores_non_dit_keys():
    assert anima.detect_lora_block_count([]) is None
    assert anima.detect_lora_block_count(["lora_te_blocks_2_self_attn.weight"]) is None
    assert anima.detect_lora_block_count(["llm_adapter.blocks.2.cross_attn.weight"]) is None
    assert anima.detect_lora_block_count(["semantic_attentions.connector.blocks.2.weight"]) is None


def test_detect_block_count_rejects_unknown_block_index():
    with pytest.raises(LoraCompatibilityError, match="Unsupported Anima LoRA block index"):
        anima.detect_lora_block_count(_lora(53).keys())


def test_prepare_28_to_40_rewrites_kohya_keys():
    lora = _lora(28)
    remapped, report = prepare_lora(lora, _Model(40), name="demo")

    assert report is not None
    assert "28 -> 40" in report
    assert "lora_unet_blocks_3_self_attn_q_proj.lora_down.weight" in remapped
    assert "lora_unet_blocks_2_self_attn_q_proj.lora_down.weight" not in remapped
    assert "lora_unet_blocks_39_self_attn_q_proj.lora_down.weight" in remapped
    assert len(remapped) == len(lora)


def test_prepare_40_to_52_rewrites_generic_keys():
    lora = _lora(40, "generic")
    remapped, report = prepare_lora(lora, _Model(52), name="demo")

    assert report is not None
    assert "40 -> 52" in report
    assert "diffusion_model.blocks.4.self_attn.q_proj.lora_A.weight" in remapped
    assert "diffusion_model.blocks.51.self_attn.q_proj.lora_A.weight" in remapped


def test_prepare_28_to_52_composes_mappings():
    lora = _lora(28)
    remapped, report = prepare_lora(lora, _Model(52), name="demo")

    assert report is not None
    assert "28 -> 52" in report
    assert "lora_unet_blocks_4_self_attn_q_proj.lora_down.weight" in remapped
    assert "lora_unet_blocks_51_self_attn_q_proj.lora_down.weight" in remapped


def test_prepare_same_layout_is_a_noop():
    lora = _lora(40)
    remapped, report = prepare_lora(lora, _Model(40), name="demo")

    assert report is None
    assert set(remapped) == set(lora)


def test_prepare_non_anima_model_is_a_noop():
    lora = _lora(28)
    remapped, report = prepare_lora(lora, _Model(40, image_model="sdxl"), name="demo")

    assert report is None
    assert set(remapped) == set(lora)


def test_prepare_rejects_newer_lora_on_older_model():
    with pytest.raises(LoraCompatibilityError, match="cannot be remapped down"):
        prepare_lora(_lora(52), _Model(40), name="demo")


def test_prepare_can_detect_llm_adapter_when_image_model_is_missing():
    model = _Model(40, image_model="cosmos_predict2")
    model.model.diffusion_model.llm_adapter = object()

    assert anima.matches(model) is True
    remapped, report = prepare_lora(_lora(28), model, name="demo")

    assert report is not None
    assert "28 -> 40" in report
    assert "lora_unet_blocks_3_self_attn_q_proj.lora_down.weight" in remapped


def test_prepare_uses_blocks_length_when_num_blocks_is_missing():
    model = _Model(40)
    model.model.model_config.unet_config = {"image_model": "anima"}

    assert anima.get_model_block_count(model) == 40


def test_remap_leaves_text_encoder_and_llm_adapter_keys_alone():
    lora = _lora(28)
    lora["lora_te_blocks_2_self_attn.weight"] = object()
    lora["llm_adapter.blocks.2.cross_attn.weight"] = object()

    remapped, _ = prepare_lora(lora, _Model(40), name="demo")

    assert remapped["lora_te_blocks_2_self_attn.weight"] is lora["lora_te_blocks_2_self_attn.weight"]
    assert remapped["llm_adapter.blocks.2.cross_attn.weight"] is lora["llm_adapter.blocks.2.cross_attn.weight"]


def test_remap_rejects_collisions():
    lora = {
        "lora_unet_blocks_2_self_attn_q_proj.lora_down.weight": object(),
        "lora_unet_blocks_3_self_attn_q_proj.lora_down.weight": object(),
    }

    with pytest.raises(LoraCompatibilityError, match="collision"):
        anima.remap_lora_state_dict(lora, {2: 3, 3: 3})


def test_remap_rejects_unmapped_source_blocks():
    with pytest.raises(LoraCompatibilityError, match="no counterpart"):
        anima.remap_lora_state_dict(
            {"lora_unet_blocks_2_self_attn_q_proj.lora_down.weight": object()},
            {0: 0},
        )


def test_setting_default_enables_remap():
    from py.services.settings_manager import DEFAULT_SETTINGS

    assert DEFAULT_SETTINGS["anima_lora_block_remap"] is True
