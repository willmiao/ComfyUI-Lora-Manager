import os

import pytest

from py.utils.root_paths import normalize_root_identity


def test_folds_windows_and_posix_separators():
    """ComfyUI's normpath output and LoRA Manager's forward slashes agree."""

    assert normalize_root_identity("E:\\StableDiffusion\\cc_models\\loras") == (
        normalize_root_identity("E:/StableDiffusion/cc_models/loras")
    )


def test_folds_drive_letter_case_on_every_platform():
    """A drive letter is case-insensitive even where the filesystem is not."""

    assert normalize_root_identity("E:/models/loras") == normalize_root_identity(
        "e:/models/loras"
    )
    assert normalize_root_identity("E:\\models\\loras") == normalize_root_identity(
        "e:/MODELS/loras"
    )


def test_folds_trailing_and_redundant_separators():
    assert normalize_root_identity("E:/models/loras/") == normalize_root_identity(
        "E:/models/loras"
    )
    assert normalize_root_identity("E:/models/other/../loras") == (
        normalize_root_identity("E:/models/loras")
    )


def test_keeps_posix_case_significant():
    """Only Windows compares whole paths case-insensitively."""

    if os.name == "nt":
        assert normalize_root_identity("C:/Models/Loras") == (
            normalize_root_identity("c:/models/loras")
        )
    else:
        assert normalize_root_identity("/data/Loras") != normalize_root_identity(
            "/data/loras"
        )


def test_folds_whole_path_case_on_windows(monkeypatch):
    """The Windows branch is exercised on every platform."""

    monkeypatch.setattr(os, "name", "nt")

    assert normalize_root_identity("C:/Models/Loras") == normalize_root_identity(
        "c:/models/loras"
    )
    assert normalize_root_identity("C:\\Models\\Loras\\") == "c:/models/loras"


def test_never_resolves_symlinks_or_abspath():
    """Business paths stay business paths: only the spelling is folded."""

    assert normalize_root_identity("./models/loras") == "models/loras"
    assert normalize_root_identity("/srv/link/loras") == "/srv/link/loras"


@pytest.mark.parametrize("value", ["", "   ", None, 42])
def test_blank_inputs_have_no_identity(value):
    assert normalize_root_identity(value) == ""
