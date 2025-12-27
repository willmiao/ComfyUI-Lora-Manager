import logging
import sys
import os
import unittest.mock as mock
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
    
    def clone(self):
        # This is what our legacy logic used via copy.deepcopy(model)
        # But in the new logic, copy_with_ctx returns the cloned model
        return self

def test_nunchaku_load_lora_legacy_fallback(monkeypatch, caplog):
    import folder_paths
    import copy
    
    dummy_model = _DummyModel()
    
    # Mock folder_paths and os.path.isfile to "find" the LoRA
    monkeypatch.setattr(folder_paths, "get_full_path", lambda folder, name: f"/fake/path/{name}", raising=False)
    monkeypatch.setattr(os.path, "isfile", lambda path: True if "/fake/path/" in path else False)
    
    # Mock to_diffusers to return a dummy state dict
    monkeypatch.setattr("py.nodes.utils.to_diffusers", lambda path: {})
    
    # Ensure copy_with_ctx is NOT found
    # model_wrapper.__class__.__module__ will be this module
    module_name = _DummyDiffusionModel.__module__
    if module_name in sys.modules:
        module = sys.modules[module_name]
        if hasattr(module, "copy_with_ctx"):
            monkeypatch.delattr(module, "copy_with_ctx")

    with caplog.at_level(logging.WARNING):
        result_model = nunchaku_load_lora(dummy_model, "some_lora", 0.8)
    
    assert "better LoRA support" in caplog.text
    assert len(result_model.model.diffusion_model.loras) == 1
    assert result_model.model.diffusion_model.loras[0][1] == 0.8

def test_nunchaku_load_lora_new_logic(monkeypatch):
    import folder_paths
    import os
    
    dummy_model = _DummyModel()
    model_wrapper = dummy_model.model.diffusion_model
    
    # Mock folder_paths and os.path.isfile
    monkeypatch.setattr(folder_paths, "get_full_path", lambda folder, name: f"/fake/path/{name}", raising=False)
    monkeypatch.setattr(os.path, "isfile", lambda path: True if "/fake/path/" in path else False)
    
    # Mock to_diffusers
    monkeypatch.setattr("py.nodes.utils.to_diffusers", lambda path: {})
    
    # Create the cloned objects that copy_with_ctx would return
    cloned_wrapper = _DummyDiffusionModel()
    cloned_model = _DummyModel()
    cloned_model.model.diffusion_model = cloned_wrapper
    
    # Define copy_with_ctx
    def mock_copy_with_ctx(wrapper):
        return cloned_wrapper, cloned_model
    
    # Inject copy_with_ctx into the module
    module_name = _DummyDiffusionModel.__module__
    module = sys.modules[module_name]
    monkeypatch.setattr(module, "copy_with_ctx", mock_copy_with_ctx, raising=False)
    
    result_model = nunchaku_load_lora(dummy_model, "new_lora", 0.7)
    
    assert result_model is cloned_model
    assert cloned_wrapper.loras == [("/fake/path/new_lora", 0.7)]
