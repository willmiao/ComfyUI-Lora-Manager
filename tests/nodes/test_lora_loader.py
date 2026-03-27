import types

from py.nodes.lora_loader import LoraLoaderLM, LoraTextLoaderLM


class _ModelContainer:
    def __init__(self, diffusion_model):
        self.diffusion_model = diffusion_model


class _Model:
    def __init__(self, diffusion_model):
        self.model = _ModelContainer(diffusion_model)


def test_lora_loader_standard_model_uses_comfy_loader(monkeypatch):
    loader = LoraLoaderLM()
    model = _Model(object())
    clip = object()

    monkeypatch.setattr(
        "py.nodes.lora_loader.get_lora_info_absolute",
        lambda name: (f"/abs/{name}.safetensors", [f"{name}_trigger"]),
    )

    load_calls = []

    def mock_load_torch_file(path, safe_load=True):
        load_calls.append((path, safe_load))
        return {"path": path}

    def mock_load_lora_for_models(model_arg, clip_arg, lora_arg, model_strength, clip_strength):
        return model_arg, clip_arg

    monkeypatch.setattr("comfy.utils.load_torch_file", mock_load_torch_file)
    monkeypatch.setattr("comfy.sd.load_lora_for_models", mock_load_lora_for_models)

    result_model, result_clip, trigger_words, loaded_loras = loader.load_loras(
        model,
        "",
        clip=clip,
        loras={
            "__value__": [
                {"active": True, "name": "demo", "strength": 0.75, "clipStrength": 0.5},
            ]
        },
    )

    assert result_model is model
    assert result_clip is clip
    assert load_calls == [("/abs/demo.safetensors", True)]
    assert trigger_words == "demo_trigger"
    assert loaded_loras == "<lora:demo:0.75:0.5>"


def test_lora_loader_formats_widget_lora_names_with_colons(monkeypatch):
    loader = LoraLoaderLM()
    model = _Model(object())
    clip = object()

    monkeypatch.setattr(
        "py.nodes.lora_loader.get_lora_info_absolute",
        lambda name: (f"/abs/{name}.safetensors", [f"{name}_trigger"]),
    )
    monkeypatch.setattr("comfy.utils.load_torch_file", lambda path, safe_load=True: {"path": path})
    monkeypatch.setattr(
        "comfy.sd.load_lora_for_models",
        lambda model_arg, clip_arg, lora_arg, model_strength, clip_strength: (model_arg, clip_arg),
    )

    _, _, trigger_words, loaded_loras = loader.load_loras(
        model,
        "",
        clip=clip,
        loras={
            "__value__": [
                {"active": True, "name": "demo:variant", "strength": 0.75, "clipStrength": 0.5},
                {"active": True, "name": "demo:single", "strength": 0.3},
            ]
        },
    )

    assert trigger_words == "demo:variant_trigger,, demo:single_trigger"
    assert loaded_loras == "<lora:demo:variant:0.75:0.5> <lora:demo:single:0.3>"


def test_lora_loader_flux_model_uses_flux_helper(monkeypatch):
    flux_model = _Model(type("ComfyFluxWrapper", (), {})())
    loader = LoraLoaderLM()

    monkeypatch.setattr(
        "py.nodes.lora_loader.get_lora_info_absolute",
        lambda name: (f"/abs/{name}.safetensors", [f"{name}_trigger"]),
    )

    calls = []

    def mock_nunchaku_load_lora(model_arg, lora_name, strength):
        calls.append((lora_name, strength))
        return model_arg

    monkeypatch.setattr("py.nodes.lora_loader.nunchaku_load_lora", mock_nunchaku_load_lora)

    _, _, trigger_words, loaded_loras = loader.load_loras(
        flux_model,
        "",
        lora_stack=[("stack_lora.safetensors", 0.4, 0.2)],
        loras={"__value__": [{"active": True, "name": "widget_lora", "strength": 0.8}]},
    )

    assert calls == [("stack_lora.safetensors", 0.4), ("/abs/widget_lora.safetensors", 0.8)]
    assert trigger_words == "stack_lora_trigger,, widget_lora_trigger"
    assert loaded_loras == "<lora:stack_lora:0.4> <lora:widget_lora:0.8>"


def test_lora_loader_qwen_model_batches_loras(monkeypatch):
    qwen_model = _Model(type("NunchakuQwenImageTransformer2DModel", (), {})())
    loader = LoraLoaderLM()

    monkeypatch.setattr(
        "py.nodes.lora_loader.get_lora_info_absolute",
        lambda name: (f"/abs/{name}.safetensors", [f"{name}_trigger"]),
    )

    batched_calls = []

    def mock_nunchaku_load_qwen_loras(model_arg, lora_configs):
        batched_calls.append((model_arg, lora_configs))
        return model_arg

    monkeypatch.setattr("py.nodes.lora_loader.nunchaku_load_qwen_loras", mock_nunchaku_load_qwen_loras)

    _, result_clip, trigger_words, loaded_loras = loader.load_loras(
        qwen_model,
        "",
        clip="clip",
        lora_stack=[("stack_qwen.safetensors", 0.6, 0.1)],
        loras={"__value__": [{"active": True, "name": "widget_qwen", "strength": 0.9, "clipStrength": 0.3}]},
    )

    assert result_clip == "clip"
    assert len(batched_calls) == 1
    assert batched_calls[0][0] is qwen_model
    assert batched_calls[0][1] == [
        ("/abs/stack_qwen.safetensors", 0.6),
        ("/abs/widget_qwen.safetensors", 0.9),
    ]
    assert trigger_words == "stack_qwen_trigger,, widget_qwen_trigger"
    assert loaded_loras == "<lora:stack_qwen:0.6> <lora:widget_qwen:0.9>"


def test_lora_text_loader_qwen_batches_text_and_stack(monkeypatch):
    qwen_model = _Model(type("NunchakuQwenImageTransformer2DModel", (), {})())
    loader = LoraTextLoaderLM()

    monkeypatch.setattr(
        "py.nodes.lora_loader.get_lora_info_absolute",
        lambda name: (f"/abs/{name}.safetensors", [f"{name}_trigger"]),
    )

    batched_calls = []
    monkeypatch.setattr(
        "py.nodes.lora_loader.nunchaku_load_qwen_loras",
        lambda model_arg, lora_configs: batched_calls.append(lora_configs) or model_arg,
    )

    _, _, trigger_words, loaded_loras = loader.load_loras_from_text(
        qwen_model,
        "<lora:text_qwen:1.2:0.4>",
        clip="clip",
        lora_stack=[("stack_qwen.safetensors", 0.6, 0.1)],
    )

    assert batched_calls == [[("/abs/stack_qwen.safetensors", 0.6), ("/abs/text_qwen.safetensors", 1.2)]]
    assert trigger_words == "stack_qwen_trigger,, text_qwen_trigger"
    assert loaded_loras == "<lora:stack_qwen:0.6> <lora:text_qwen:1.2>"
