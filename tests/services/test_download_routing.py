"""Tests for the shared download routing decision."""

import pytest

from py.services.download_routing import is_diffusion_model_download


@pytest.mark.parametrize("file_type", ["UNet", "Diffusion Model"])
def test_file_type_signal_routes_to_unet(file_type):
    assert is_diffusion_model_download(
        "checkpoint", file_types=[file_type], base_model="SDXL 1.0"
    )


def test_base_model_fallback_routes_to_unet():
    """The reported Anima case: file type is plain "Model", but the
    baseModel is a known diffusion model."""
    assert is_diffusion_model_download(
        "checkpoint", file_types=["Model"], base_model="Anima"
    )


def test_regular_checkpoint_stays_on_checkpoint_roots():
    assert not is_diffusion_model_download(
        "checkpoint", file_types=["Model"], base_model="SDXL 1.0"
    )


def test_non_checkpoint_types_never_route_to_unet():
    assert not is_diffusion_model_download(
        "lora", file_types=["UNet"], base_model="Anima"
    )
    assert not is_diffusion_model_download(
        "embedding", file_types=["Diffusion Model"], base_model="Anima"
    )


def test_empty_inputs_stay_on_checkpoint_roots():
    assert not is_diffusion_model_download("checkpoint")
    assert not is_diffusion_model_download("checkpoint", file_types=[], base_model="")
