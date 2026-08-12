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
