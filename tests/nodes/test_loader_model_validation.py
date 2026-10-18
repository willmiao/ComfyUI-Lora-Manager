"""Tests for queue-time loader model name validation (validate_loader_model_name)."""

import inspect

import pytest

from py.nodes.utils import validate_loader_model_name


class _FakeCache:
    def __init__(self, raw_data):
        self.raw_data = raw_data


class _FakeScanner:
    def __init__(self, raw_data, roots):
        self._raw_data = raw_data
        self._roots = roots

    async def get_cached_data(self, force_refresh=False):
        return _FakeCache(self._raw_data)

    def get_model_roots(self):
        return self._roots


@pytest.fixture
def mock_checkpoint_scanner(tmp_path, monkeypatch):
    from py.services.service_registry import ServiceRegistry

    model = tmp_path / "sub" / "model.safetensors"
    model.parent.mkdir()
    model.write_bytes(b"m")

    raw_data = [
        {
            "file_name": "model.safetensors",
            "folder": "sub",
            "file_path": str(model),
            "sub_type": "checkpoint",
        }
    ]

    async def _fake_scanner():
        return _FakeScanner(raw_data, [str(tmp_path)])

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _fake_scanner)
    return str(model)


def test_validate_forward_slash_name(mock_checkpoint_scanner):
    assert validate_loader_model_name("sub/model.safetensors") is None


def test_validate_backslash_name_from_old_windows_workflow(mock_checkpoint_scanner):
    # Workflows saved before the forward-slash paths fix carry "sub\model..."
    # while the combo list is forward-slashed; validation must accept both.
    assert validate_loader_model_name("sub\\model.safetensors") is None


def test_validate_unknown_name_reported(mock_checkpoint_scanner):
    result = validate_loader_model_name("sub\\unknown.safetensors")
    assert result is not None
    assert "sub\\unknown.safetensors" in result


def test_validate_wired_input_is_lenient(mock_checkpoint_scanner):
    # A linked input arrives as [node_id, slot], not a string.
    assert validate_loader_model_name(["1", 0]) is None


def test_validate_empty_or_missing_name_is_lenient(mock_checkpoint_scanner):
    assert validate_loader_model_name(None) is None
    assert validate_loader_model_name("") is None


def test_validate_scanner_failure_is_lenient(monkeypatch):
    from py.services.service_registry import ServiceRegistry

    def _boom():
        raise RuntimeError("scanner not initialized")

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _boom)
    assert validate_loader_model_name("sub/model.safetensors") is None


def test_loader_nodes_declare_validate_inputs(mock_checkpoint_scanner):
    """VALIDATE_INPUTS must declare the model name input without **kwargs so
    ComfyUI skips its strict "value not in list" check for that input only,
    and must accept backslash-spelled names from old Windows workflows."""
    from py.nodes.checkpoint_loader import CheckpointLoaderLM
    from py.nodes.unet_loader import UNETLoaderLM

    spec = inspect.getfullargspec(CheckpointLoaderLM.VALIDATE_INPUTS)
    assert spec.varkw is None
    assert "ckpt_name" in spec.args

    spec = inspect.getfullargspec(UNETLoaderLM.VALIDATE_INPUTS)
    assert spec.varkw is None
    assert "unet_name" in spec.args

    assert CheckpointLoaderLM.VALIDATE_INPUTS(ckpt_name="sub\\model.safetensors") is True
    assert UNETLoaderLM.VALIDATE_INPUTS(unet_name="sub\\model.safetensors") is True

    result = CheckpointLoaderLM.VALIDATE_INPUTS(ckpt_name="sub\\unknown.safetensors")
    assert result is not True
    assert "sub\\unknown.safetensors" in result

    assert CheckpointLoaderLM.VALIDATE_INPUTS() is True
    assert UNETLoaderLM.VALIDATE_INPUTS() is True
