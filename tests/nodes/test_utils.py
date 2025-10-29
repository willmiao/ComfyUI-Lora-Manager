import logging

from py.nodes.utils import nunchaku_load_lora


class _DummyTransformer:
    pass


class _DummyModelConfig:
    def __init__(self):
        self.unet_config = {"in_channels": 4}


class _DummyDiffusionModel:
    def __init__(self):
        self.model = _DummyTransformer()
        self.loras = []


class _DummyModelWrapper:
    def __init__(self):
        self.diffusion_model = _DummyDiffusionModel()
        self.model_config = _DummyModelConfig()


class _DummyModel:
    def __init__(self):
        self.model = _DummyModelWrapper()


def test_nunchaku_load_lora_skips_missing_lora(monkeypatch, caplog):
    import folder_paths

    dummy_model = _DummyModel()

    monkeypatch.setattr(folder_paths, "get_full_path", lambda *_args, **_kwargs: None, raising=False)

    with caplog.at_level(logging.WARNING):
        result_model = nunchaku_load_lora(dummy_model, "missing_lora", 0.5)

    assert result_model is dummy_model
    assert dummy_model.model.diffusion_model.loras == []
    assert "missing_lora" in caplog.text
