"""Tests for the checkpoint/unet combo-name existence filtering.

Deleted files must drop out of the combo list so ComfyUI flags the node at
queue time via "value not in list" instead of failing at execution time.
"""

import pytest

from py.nodes.checkpoint_loader import CheckpointLoaderLM
from py.nodes.unet_loader import UNETLoaderLM


class _FakeCache:
    def __init__(self, raw_data):
        self.raw_data = raw_data


class _FakeScanner:
    def __init__(self, raw_data, model_roots):
        self._raw_data = raw_data
        self._model_roots = model_roots

    async def get_cached_data(self, force_refresh=False):
        return _FakeCache(self._raw_data)

    def get_model_roots(self):
        return self._model_roots


@pytest.fixture
def checkpoint_library(tmp_path, monkeypatch):
    from py.services.service_registry import ServiceRegistry

    existing = tmp_path / "keep.safetensors"
    existing.write_bytes(b"x")
    deleted = tmp_path / "deleted.safetensors"  # referenced but never created

    raw_data = [
        {"sub_type": "checkpoint", "file_path": str(existing)},
        {"sub_type": "checkpoint", "file_path": str(deleted)},
        # Wrong type must stay excluded by the sub_type filter.
        {"sub_type": "diffusion_model", "file_path": str(existing)},
    ]
    async def _fake_scanner():
        return _FakeScanner(raw_data, [str(tmp_path)])

    monkeypatch.setattr(
        ServiceRegistry, "get_checkpoint_scanner", _fake_scanner
    )
    return tmp_path


def test_checkpoint_names_drop_deleted_files(checkpoint_library):
    assert CheckpointLoaderLM._get_checkpoint_names() == ["keep.safetensors"]


def test_unet_names_drop_deleted_files(tmp_path, monkeypatch):
    from py.services.service_registry import ServiceRegistry

    existing = tmp_path / "keep.safetensors"
    existing.write_bytes(b"x")
    deleted = tmp_path / "deleted.safetensors"

    raw_data = [
        {"sub_type": "diffusion_model", "file_path": str(existing)},
        {"sub_type": "diffusion_model", "file_path": str(deleted)},
        {"sub_type": "checkpoint", "file_path": str(existing)},
    ]
    async def _fake_scanner():
        return _FakeScanner(raw_data, [str(tmp_path)])

    monkeypatch.setattr(
        ServiceRegistry, "get_checkpoint_scanner", _fake_scanner
    )
    assert UNETLoaderLM._get_unet_names() == ["keep.safetensors"]


def test_checkpoint_names_empty_when_scanner_fails(tmp_path, monkeypatch):
    from py.services.service_registry import ServiceRegistry

    def _boom():
        raise RuntimeError("scanner not available")

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _boom)
    assert CheckpointLoaderLM._get_checkpoint_names() == []


@pytest.fixture
def base_model_library(tmp_path, monkeypatch):
    from py.services.service_registry import ServiceRegistry

    illustrious = tmp_path / "illustrious.safetensors"
    illustrious.write_bytes(b"x")
    flux = tmp_path / "flux.safetensors"
    flux.write_bytes(b"x")
    missing = tmp_path / "missing.safetensors"  # referenced but never created

    raw_data = [
        {
            "sub_type": "checkpoint",
            "file_path": str(illustrious),
            "base_model": "Illustrious",
        },
        {"sub_type": "checkpoint", "file_path": str(flux), "base_model": "Flux.1 D"},
        {
            "sub_type": "checkpoint",
            "file_path": str(missing),
            "base_model": "SDXL 1.0",
        },
        {
            "sub_type": "diffusion_model",
            "file_path": str(flux),
            "base_model": "Flux.1 D",
        },
    ]

    async def _fake_scanner():
        return _FakeScanner(raw_data, [str(tmp_path)])

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _fake_scanner)
    return tmp_path


def test_checkpoint_available_base_models(base_model_library):
    # "SDXL 1.0" is excluded because its file no longer exists on disk.
    assert CheckpointLoaderLM._get_available_base_models() == [
        "Any",
        "Flux.1 D",
        "Illustrious",
    ]


def test_checkpoint_names_filtered_by_base_model(base_model_library):
    assert CheckpointLoaderLM._get_checkpoint_names("Illustrious") == [
        "illustrious.safetensors"
    ]
    assert CheckpointLoaderLM._get_checkpoint_names("Any") == [
        "flux.safetensors",
        "illustrious.safetensors",
    ]


def test_unet_available_base_models(base_model_library):
    assert UNETLoaderLM._get_available_base_models() == ["Any", "Flux.1 D"]


def test_load_checkpoint_random_selection_uses_pool(base_model_library, monkeypatch):
    from py.nodes import checkpoint_loader as checkpoint_loader_module

    monkeypatch.setattr(
        checkpoint_loader_module,
        "get_checkpoint_info_absolute",
        lambda name: (str(base_model_library / name), {"file_path": name}),
    )
    monkeypatch.setattr(
        checkpoint_loader_module.comfy.sd,
        "load_checkpoint_guess_config",
        lambda *a, **k: ("MODEL", "CLIP", "VAE", None),
        raising=False,
    )

    node = CheckpointLoaderLM()
    node.load_checkpoint(
        "ignored.safetensors", select_at_random=True, base_model="Illustrious"
    )
    # Only one checkpoint matches "Illustrious", so the random pick is deterministic here.


def test_load_checkpoint_random_selection_raises_when_pool_empty(
    base_model_library, monkeypatch
):
    node = CheckpointLoaderLM()
    with pytest.raises(FileNotFoundError, match="No checkpoints found"):
        node.load_checkpoint(
            "ignored.safetensors", select_at_random=True, base_model="SDXL 1.0"
        )


def test_checkpoint_is_changed_forces_rerun_when_random():
    assert CheckpointLoaderLM.IS_CHANGED(
        "a.safetensors", select_at_random=True, base_model="Any"
    ) != CheckpointLoaderLM.IS_CHANGED(
        "a.safetensors", select_at_random=True, base_model="Any"
    )
    assert CheckpointLoaderLM.IS_CHANGED(
        "a.safetensors", select_at_random=False, base_model="Any"
    ) == CheckpointLoaderLM.IS_CHANGED(
        "a.safetensors", select_at_random=False, base_model="Any"
    )
