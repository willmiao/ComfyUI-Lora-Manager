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


@pytest.mark.parametrize("base_model", ["SVD XT", "Boogu", "Wan Video 3.0", "Flux 3 Video"])
def test_new_diffusion_families_route_to_unet(base_model):
    """DiT families from CivitAI's official baseModel list that plain
    "Model"-typed files must not strand on the checkpoint roots."""
    assert is_diffusion_model_download(
        "checkpoint", file_types=["Model"], base_model=base_model
    )


def test_minimax_h3_routes_to_unet():
    """CivitAI model 2877206: type "Checkpoint", baseModel "MiniMax H3",
    all file entries typed "Model"."""
    assert is_diffusion_model_download(
        "checkpoint", file_types=["Model"], base_model="MiniMax H3"
    )


@pytest.mark.parametrize(
    "base_model",
    [
        "SDXL 1.0",
        "Illustrious",
        "SD 1.5",
        "SD 2.1 768",
        "SD 3.5 Large",
        "SDXL Turbo",
        "Playground v2",
        "Stable Cascade",
    ],
)
def test_known_checkpoint_base_models_stay_on_checkpoint_roots(base_model):
    """CHECKPOINT_BASE_MODELS members never route to unet, even when the
    unknown-base-model default is diffusion."""
    assert not is_diffusion_model_download(
        "checkpoint", file_types=["Model"], base_model=base_model
    )


def test_unknown_base_model_defaults_to_unet():
    """New DiT families appear faster than the allowlist can track them, so
    unknown baseModels route to unet by default."""
    assert is_diffusion_model_download(
        "checkpoint", file_types=["Model"], base_model="Brand New Arch"
    )


def test_unknown_base_model_honors_checkpoint_setting():
    assert not is_diffusion_model_download(
        "checkpoint",
        file_types=["Model"],
        base_model="Brand New Arch",
        unknown_base_model_default="checkpoint",
    )


def test_unknown_base_model_checkpoint_setting_still_loses_to_file_type():
    """The file-type signal stays first regardless of the setting."""
    assert is_diffusion_model_download(
        "checkpoint",
        file_types=["Diffusion Model"],
        base_model="SDXL 1.0",
        unknown_base_model_default="checkpoint",
    )


def test_non_checkpoint_types_never_route_to_unet():
    assert not is_diffusion_model_download(
        "lora", file_types=["UNet"], base_model="Anima"
    )
    assert not is_diffusion_model_download(
        "embedding", file_types=["Diffusion Model"], base_model="Anima"
    )


def test_empty_base_model_follows_unknown_default():
    assert is_diffusion_model_download("checkpoint")
    assert is_diffusion_model_download("checkpoint", file_types=[], base_model="")
    assert not is_diffusion_model_download(
        "checkpoint",
        file_types=[],
        base_model="",
        unknown_base_model_default="checkpoint",
    )


from py.services.download_routing import resolve_other_download_sub_type


class TestResolveOtherDownloadSubType:
    """Fixed priority: explicit file pick > model.type > file.type fallback."""

    def test_explicit_file_pick_wins_over_model_type(self):
        """User explicitly picked a VAE component file of a Checkpoint model —
        the picked file type wins."""
        assert (
            resolve_other_download_sub_type(
                "Checkpoint", file_types=["Model", "VAE"], selected_file_type="VAE"
            )
            == "vae"
        )

    @pytest.mark.parametrize(
        "selected,expected",
        [
            ("VAE", "vae"),
            ("Upscaler", "upscaler"),
            ("Text Encoder", "text_encoder"),
            ("Vision Encoder", "clip_vision"),
            ("CLIPVision", "clip_vision"),
            ("ControlNet", "controlnet"),
        ],
    )
    def test_explicit_file_pick_maps_all_known_types(self, selected, expected):
        assert (
            resolve_other_download_sub_type("Other", selected_file_type=selected)
            == expected
        )

    @pytest.mark.parametrize(
        "model_type,expected",
        [
            ("VAE", "vae"),
            ("Upscaler", "upscaler"),
            ("TextEncoder", "text_encoder"),
            ("CLIP", "text_encoder"),
            ("CLIPVision", "clip_vision"),
            ("Controlnet", "controlnet"),
        ],
    )
    def test_model_type_mapping(self, model_type, expected):
        assert resolve_other_download_sub_type(model_type) == expected

    def test_model_type_beats_unmappable_file_pick(self):
        """An explicit pick whose file type does not map (e.g. plain 'Model')
        falls through to model.type."""
        assert (
            resolve_other_download_sub_type(
                "TextEncoder", selected_file_type="Model"
            )
            == "text_encoder"
        )

    def test_bundled_component_files_never_override_model_type(self):
        """Anti-misrouting: a TextEncoder model bundling a VAE component file
        must stay text_encoder — file types are a fallback, not an override."""
        assert (
            resolve_other_download_sub_type(
                "TextEncoder", file_types=["Model", "VAE"]
            )
            == "text_encoder"
        )
        assert (
            resolve_other_download_sub_type(
                "Controlnet", file_types=["Model", "Text Encoder"]
            )
            == "controlnet"
        )

    def test_file_type_fallback_when_model_type_unmapped(self):
        """model.type 'Other' (or retired values) maps to nothing, so the
        first mappable file type decides."""
        assert (
            resolve_other_download_sub_type("Other", file_types=["Model", "Upscaler"])
            == "upscaler"
        )

    def test_file_type_fallback_for_civarchive_payload(self):
        """CivArchive-shaped payload: same fields, same decision path."""
        assert (
            resolve_other_download_sub_type(
                "Other",
                file_types=["Config", "Text Encoder"],
            )
            == "text_encoder"
        )

    @pytest.mark.parametrize("model_type", ["Other", "", "SomethingNew"])
    def test_undecidable_returns_none(self, model_type):
        assert (
            resolve_other_download_sub_type(model_type, file_types=["Model"]) is None
        )
        assert resolve_other_download_sub_type(model_type) is None

    def test_model_type_matching_is_case_insensitive(self):
        assert resolve_other_download_sub_type("vAe") == "vae"
