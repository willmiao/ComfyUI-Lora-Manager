"""Regression tests for issue #1112.

Dotted model file names (``lora-sd1.5-backlight_slider_v10.safetensors``) must
not be truncated when metadata is built from a CivitAI payload. The builder has
to strip at most one *known* model extension: API filenames keep their
extension, while migration paths (``.civitai.info``) pass the local stem.
"""

import pytest

from py.utils.models import (
    CheckpointMetadata,
    EmbeddingMetadata,
    LoraMetadata,
    OtherModelMetadata,
    strip_model_extension,
)

DOTTED_STEM = "lora-sd1.5-backlight_slider_v10"

MODEL_CLASSES = [
    LoraMetadata,
    CheckpointMetadata,
    EmbeddingMetadata,
    OtherModelMetadata,
]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Dotted stems are not extensions.
        (DOTTED_STEM, DOTTED_STEM),
        (f"{DOTTED_STEM}.safetensors", DOTTED_STEM),
        ("model.v1.5.safetensors", "model.v1.5"),
        ("a.b.c", "a.b.c"),
        # Every scanner extension is recognized, case-insensitively.
        ("weights.GGUF", "weights"),
        ("weights.pt2", "weights"),
        ("weights.ckpt", "weights"),
        # Extension-free plain names are unchanged.
        ("plain_name", "plain_name"),
        ("", ""),
    ],
)
def test_strip_model_extension_strips_only_known_extensions(raw, expected):
    assert strip_model_extension(raw) == expected


@pytest.mark.parametrize("model_cls", MODEL_CLASSES)
@pytest.mark.parametrize(
    "file_name",
    [
        f"{DOTTED_STEM}.safetensors",  # CivitAI API / download shape
        DOTTED_STEM,  # .civitai.info migration shape (already extension-free)
    ],
)
def test_from_civitai_info_keeps_dotted_stem(model_cls, file_name):
    version_info = {
        "baseModel": "SD 1.5",
        "name": "v1.0",
        "model": {"name": "Light Control", "description": "", "tags": []},
    }
    file_info = {"name": file_name, "sizeKB": 1024, "hashes": {"SHA256": "a" * 64}}

    metadata = model_cls.from_civitai_info(
        version_info, file_info, f"/models/{DOTTED_STEM}.safetensors"
    )

    assert metadata.file_name == DOTTED_STEM
    assert metadata.model_name == "Light Control"


@pytest.mark.parametrize("model_cls", MODEL_CLASSES)
def test_from_civitai_info_model_name_fallback_uses_full_stem(model_cls):
    """A sidecar without ``model.name`` must fall back to the full local stem."""
    version_info = {"baseModel": "SD 1.5", "model": {"description": "", "tags": []}}
    file_info = {"name": DOTTED_STEM, "sizeKB": 1024, "hashes": {}}

    metadata = model_cls.from_civitai_info(
        version_info, file_info, f"/models/{DOTTED_STEM}.safetensors"
    )

    assert metadata.file_name == DOTTED_STEM
    assert metadata.model_name == DOTTED_STEM


@pytest.mark.parametrize("model_cls", MODEL_CLASSES)
def test_from_civitai_info_model_name_still_wins_over_stem(model_cls):
    """The CivitAI model name stays authoritative when present."""
    version_info = {
        "baseModel": "SDXL",
        "model": {"name": "Chiaroscuro Light", "description": "", "tags": ["light"]},
    }
    file_info = {
        "name": f"{DOTTED_STEM}.safetensors",
        "sizeKB": 1024,
        "hashes": {},
    }

    metadata = model_cls.from_civitai_info(
        version_info, file_info, f"/models/{DOTTED_STEM}.safetensors"
    )

    assert metadata.file_name == DOTTED_STEM
    assert metadata.model_name == "Chiaroscuro Light"
