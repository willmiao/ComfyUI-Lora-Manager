"""Wave 6: configured roots that are unavailable must be reportable and
re-admitted append-only, never dropped from the live lists."""

import os

import pytest

from py import config as config_module


def _make_config(**overrides) -> config_module.Config:
    config = config_module.Config.__new__(config_module.Config)
    config._path_mappings = {}
    config._preview_root_paths = set()
    config._cached_fingerprint = None
    config.loras_roots = []
    config.extra_loras_roots = []
    config.base_models_roots = []
    config.checkpoints_roots = []
    config.unet_roots = []
    config.embeddings_roots = []
    config.extra_checkpoints_roots = []
    config.extra_unet_roots = []
    config.extra_embeddings_roots = []
    config.other_roots = []
    config.recipes_path = ""
    config.other_root_subtypes = {}
    config.other_folder_roots = {}
    config._configured_root_paths = {}
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _normalize(path) -> str:
    return os.path.normpath(str(path)).replace(os.sep, "/")


class TestAppendNewPaths:
    def test_appends_without_reordering_or_duplicating(self):
        merged = config_module._append_new_paths(
            ["/b/loras", "/a/loras"], ["/a/loras", "/c/loras", "", None]
        )
        # Existing order is preserved (it derives *_roots[0] consumers) and the
        # new root lands at the end.
        assert merged == ["/b/loras", "/a/loras", "/c/loras"]

    def test_matches_case_insensitively(self):
        merged = config_module._append_new_paths(["C:/Loras"], ["c:/loras"])
        assert merged == ["C:/Loras"]


class TestAdmitConfiguredRoots:
    def test_admits_a_root_that_became_readable(self, tmp_path):
        primary = tmp_path / "primary"
        primary.mkdir()
        drive = tmp_path / "drive-Z" / "loras"

        config = _make_config(
            loras_roots=[str(primary)],
            _configured_root_paths={"lora": [str(primary), str(drive)]},
        )
        assert config.configured_roots_for("lora") == [str(primary), str(drive)]

        # Still switched off: nothing to admit.
        assert config.admit_configured_roots() == []
        assert config.loras_roots == [str(primary)]

        drive.mkdir(parents=True)
        admitted = config.admit_configured_roots()

        assert admitted == [str(drive)]
        assert config.loras_roots == [str(primary), str(drive)]
        # Idempotent: a second call adds nothing.
        assert config.admit_configured_roots() == []

    def test_never_removes_a_root_that_disappeared(self, tmp_path):
        primary = tmp_path / "primary"
        primary.mkdir()
        drive = tmp_path / "drive-Z" / "loras"
        drive.mkdir(parents=True)

        config = _make_config(
            loras_roots=[str(primary), str(drive)],
            _configured_root_paths={"lora": [str(drive), str(primary)]},
        )

        # The drive is switched off after the lists were built: the live list
        # keeps it (reporting and pruning decide separately) and admission must
        # not "clean it up" — a later settings save would persist the loss.
        drive.rmdir()
        config.admit_configured_roots()

        assert config.loras_roots == [str(primary), str(drive)]

    def test_admits_every_model_type_and_its_side_maps(self, tmp_path):
        checkpoint_dir = tmp_path / "checkpoints"
        unet_dir = tmp_path / "unet"
        embedding_dir = tmp_path / "embeddings"
        other_dir = tmp_path / "vae"
        for directory in (checkpoint_dir, unet_dir, embedding_dir, other_dir):
            directory.mkdir()

        config = _make_config(
            _configured_root_paths={
                "checkpoint": [str(checkpoint_dir)],
                "unet": [str(unet_dir)],
                "embedding": [str(embedding_dir)],
                "other": [str(other_dir)],
            },
        )
        config._get_enabled_other_folder_keys = lambda: ["vae"]
        config._configured_other_paths_for_key = lambda key: [str(other_dir)]

        admitted = config.admit_configured_roots()

        assert set(admitted) == {
            _normalize(checkpoint_dir),
            _normalize(unet_dir),
            _normalize(embedding_dir),
            _normalize(other_dir),
        }
        assert config.base_models_roots == [
            _normalize(checkpoint_dir),
            _normalize(unet_dir),
        ]
        assert config.checkpoints_roots == [_normalize(checkpoint_dir)]
        assert config.unet_roots == [_normalize(unet_dir)]
        assert config.embeddings_roots == [_normalize(embedding_dir)]
        assert config.other_roots == [_normalize(other_dir)]
        assert config.other_root_subtypes[_normalize(other_dir)] == "vae"
        assert config.other_folder_roots["vae"] == [_normalize(other_dir)]
