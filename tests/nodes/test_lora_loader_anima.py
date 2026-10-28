from __future__ import annotations

import pytest

from py.nodes.lora_loader import LoraLoaderLM, LoraTextLoaderLM
from py.utils.lora_compat import LoraCompatibilityError


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


def _lora(count: int) -> dict[str, object]:
    return {
        f"lora_unet_blocks_{index}_self_attn_q_proj.lora_down.weight": object()
        for index in range(count)
    }


def _patch_loader(monkeypatch, lora: dict[str, object], enabled: bool = True):
    applied: list[dict[str, object]] = []

    monkeypatch.setattr(
        "py.nodes.lora_loader.get_lora_info_absolute",
        lambda name: (f"/abs/{name}.safetensors", []),
    )
    monkeypatch.setattr(
        "py.nodes.lora_loader.apply_lora_syntax_format",
        lambda name: name,
    )
    monkeypatch.setattr(
        "py.nodes.lora_loader.get_anima_lora_remap_enabled",
        lambda: enabled,
    )
    monkeypatch.setattr(
        "comfy.utils.load_torch_file",
        lambda path, safe_load=True: dict(lora),
    )

    def mock_load_lora_for_models(model_arg, clip_arg, lora_arg, model_strength, clip_strength):
        applied.append(lora_arg)
        return model_arg, clip_arg

    monkeypatch.setattr("comfy.sd.load_lora_for_models", mock_load_lora_for_models)
    return applied


def _widget_loras():
    return {"__value__": [{"active": True, "name": "demo", "strength": 1.0}]}


def test_loader_auto_remaps_28_block_anima_lora(monkeypatch):
    model = _Model(40)
    lora = _lora(28)
    applied = _patch_loader(monkeypatch, lora)

    LoraLoaderLM().load_loras(model, "", loras=_widget_loras())

    assert len(applied) == 1
    assert "lora_unet_blocks_3_self_attn_q_proj.lora_down.weight" in applied[0]
    assert "lora_unet_blocks_2_self_attn_q_proj.lora_down.weight" not in applied[0]


def test_text_loader_auto_remaps_28_block_anima_lora(monkeypatch):
    model = _Model(52)
    lora = _lora(28)
    applied = _patch_loader(monkeypatch, lora)

    LoraTextLoaderLM().load_loras_from_text(model, "<lora:demo:1.0>")

    assert len(applied) == 1
    assert "lora_unet_blocks_4_self_attn_q_proj.lora_down.weight" in applied[0]
    assert "lora_unet_blocks_51_self_attn_q_proj.lora_down.weight" in applied[0]


def test_loader_can_disable_anima_remap(monkeypatch):
    model = _Model(40)
    lora = _lora(28)
    applied = _patch_loader(monkeypatch, lora, enabled=False)

    LoraLoaderLM().load_loras(model, "", loras=_widget_loras())

    assert len(applied) == 1
    assert set(applied[0]) == set(lora)


def test_loader_rejects_newer_anima_lora(monkeypatch):
    model = _Model(40)
    applied = _patch_loader(monkeypatch, _lora(52))

    with pytest.raises(LoraCompatibilityError, match="cannot be remapped down"):
        LoraLoaderLM().load_loras(model, "", loras=_widget_loras())

    assert applied == []


def test_loader_leaves_non_anima_models_alone(monkeypatch):
    model = _Model(40, image_model="sdxl")
    lora = _lora(28)
    applied = _patch_loader(monkeypatch, lora)

    LoraLoaderLM().load_loras(model, "", loras=_widget_loras())

    assert len(applied) == 1
    assert set(applied[0]) == set(lora)


def test_loader_does_not_expose_anima_specific_toggle():
    for node_cls in (LoraLoaderLM, LoraTextLoaderLM):
        required = node_cls.INPUT_TYPES()["required"]
        assert "anima_remap" not in required
        assert "auto_remap" not in required
