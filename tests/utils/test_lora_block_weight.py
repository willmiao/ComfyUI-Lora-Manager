from types import SimpleNamespace

import pytest

from py.metadata_collector.node_extractors import (
    LoraLoaderManagerExtractor,
    LoraTextLoaderManagerExtractor,
)
from py.nodes.utils import parse_lora_syntax
from py.utils.lora_block_weight import (
    format_lbw_syntax,
    get_lbw_schema_from_keys,
    has_active_lbw,
    load_lora_with_block_weights,
    normalize_lbw_config,
    parse_lbw_syntax,
)


class PatchRecorder:
    def __init__(self, with_clip=False):
        self.model = SimpleNamespace(diffusion_model=object())
        if with_clip:
            self.cond_stage_model = object()
        self.calls = []
        self.clone_count = 0

    def clone(self):
        self.clone_count += 1
        return self

    def add_patches(self, patches, strength):
        self.calls.append((patches, strength))
        return list(patches)


def test_schema_reads_actual_unet_and_flux_blocks():
    unet = get_lbw_schema_from_keys([
        "lora_unet_input_blocks_04_0.lora_down.weight",
        "lora_unet_middle_block_1.lora_down.weight",
        "lora_unet_output_blocks_03_0.lora_down.weight",
        "lora_te_text_model_encoder_layers_0.lora_down.weight",
    ])
    assert unet == {
        "kind": "unet",
        "groups": ["IN", "MID", "OUT"],
        "blocks": [
            {"id": "IN04", "group": "IN", "index": 4},
            {"id": "MID01", "group": "MID", "index": 1},
            {"id": "OUT03", "group": "OUT", "index": 3},
        ],
    }

    flux = get_lbw_schema_from_keys([
        "diffusion_model.double_blocks.0.img_attn.qkv.lora_A.weight",
        "diffusion_model.single_blocks.37.linear1.lora_A.weight",
    ])
    assert flux["kind"] == "flux"
    assert flux["groups"] == ["DOUBLE", "SINGLE"]
    assert [block["id"] for block in flux["blocks"]] == ["D00", "S37"]


def test_config_and_syntax_round_trip():
    config = normalize_lbw_config({
        "enabled": True,
        "weights": {"IN": 0.5, "OUT03": 0, "BASE": 1},
    })
    assert has_active_lbw(config)
    syntax = format_lbw_syntax(config)
    assert syntax == "LBW=IN=0.5;OUT03=0;BASE=1"
    assert parse_lbw_syntax(syntax) == config
    assert not has_active_lbw({"enabled": True, "weights": {"IN": 1}})
    assert not has_active_lbw({"enabled": False, "weights": {"IN": 0}})

    parsed = parse_lora_syntax(f"<lora:demo:0.8:0.6:{syntax}>")
    assert parsed[0]["model_strength"] == 0.8
    assert parsed[0]["clip_strength"] == 0.6
    assert parsed[0]["lbw"] == config


def test_invalid_config_is_rejected():
    with pytest.raises(ValueError, match="finite number"):
        normalize_lbw_config({"enabled": True, "weights": {"IN": float("nan")}})
    with pytest.raises(ValueError, match="Unknown LoRA block weight ID"):
        normalize_lbw_config({"enabled": True, "weights": {"BOGUS": 0.5}})


def test_block_patches_use_group_specific_and_base_weights(monkeypatch):
    model = PatchRecorder()
    clip = PatchRecorder(with_clip=True)
    loaded = {
        "diffusion_model.input_blocks.4.0.weight": "input",
        "diffusion_model.input_blocks.5.0.weight": "specific",
        "diffusion_model.output_blocks.3.0.weight": "muted",
        "text_encoder.weight": "base",
    }
    monkeypatch.setattr("comfy.lora.model_lora_keys_unet", lambda *_args: {}, raising=False)
    monkeypatch.setattr("comfy.lora.model_lora_keys_clip", lambda *_args: {}, raising=False)
    monkeypatch.setattr("comfy.lora.load_lora", lambda *_args: loaded, raising=False)
    monkeypatch.setattr("comfy.lora_convert.convert_lora", lambda value: value, raising=False)

    result_model, result_clip = load_lora_with_block_weights(
        model,
        clip,
        {},
        0.8,
        0.6,
        {"enabled": True, "weights": {"IN": 0.5, "IN05": 0.25, "OUT": 0, "BASE": 0.75}},
    )

    assert result_model is model
    assert result_clip is clip
    assert model.clone_count == 1
    assert clip.clone_count == 1
    assert model.calls == [
        ({"diffusion_model.input_blocks.4.0.weight": "input"}, 0.4),
        ({"diffusion_model.input_blocks.5.0.weight": "specific"}, 0.2),
        ({"text_encoder.weight": "base"}, pytest.approx(0.6)),
    ]
    assert clip.calls == [
        ({"diffusion_model.input_blocks.4.0.weight": "input"}, 0.3),
        ({"diffusion_model.input_blocks.5.0.weight": "specific"}, 0.15),
        ({"text_encoder.weight": "base"}, pytest.approx(0.45)),
    ]
    assert all("muted" not in patches.values() for patches, _ in model.calls)


def test_unsupported_layout_fails_instead_of_loading_normally(monkeypatch):
    model = PatchRecorder()
    monkeypatch.setattr("comfy.lora.model_lora_keys_unet", lambda *_args: {}, raising=False)
    monkeypatch.setattr("comfy.lora.load_lora", lambda *_args: {"transformer_blocks.0.weight": "patch"}, raising=False)
    monkeypatch.setattr("comfy.lora_convert.convert_lora", lambda value: value, raising=False)

    with pytest.raises(ValueError, match="supports only"):
        load_lora_with_block_weights(
            model,
            None,
            {},
            1,
            0,
            {"enabled": True, "weights": {"BASE": 0.5}},
        )


def test_metadata_extractors_exclude_lbw():
    config = {"enabled": True, "weights": {"IN04": 0.5}}
    metadata = {"loras": {}}
    LoraLoaderManagerExtractor.extract(
        "loader",
        {"loras": [{"active": True, "name": "demo", "strength": 0.8, "lbw": config}]},
        None,
        metadata,
    )
    assert metadata["loras"]["loader"]["lora_list"] == [
        {"name": "demo", "strength": 0.8}
    ]

    text_metadata = {"loras": {}}
    LoraTextLoaderManagerExtractor.extract(
        "text",
        {"lora_syntax": "<lora:demo:0.8:LBW=IN04=0.5>"},
        None,
        text_metadata,
    )
    assert text_metadata["loras"]["text"]["lora_list"] == [
        {"name": "demo", "strength": 0.8}
    ]
