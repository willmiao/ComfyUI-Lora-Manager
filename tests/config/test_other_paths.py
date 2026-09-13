"""Tests for other-model path handling in py/config.py."""

import logging
import os

import pytest

from py import config as config_module
from py.services.settings_manager import get_settings_manager


def _normalize(path: str) -> str:
    return os.path.normpath(path).replace(os.sep, "/")


def _make_config(**overrides) -> config_module.Config:
    """Create a bare Config instance for _prepare_other_paths tests."""
    config = config_module.Config.__new__(config_module.Config)
    config._path_mappings = {}
    config._preview_root_paths = set()
    config._cached_fingerprint = None
    config.base_models_roots = []
    config.embeddings_roots = []
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


@pytest.fixture(autouse=True)
def enable_other_models():
    """Other Models is opt-in; enable it for the enabled-state tests."""
    manager = get_settings_manager()
    manager.set("enable_other_models", True)
    yield


class TestPrepareOtherPaths:
    """Unit tests for Config._prepare_other_paths."""

    def test_maps_each_folder_key_to_sub_type(self, tmp_path):
        roots = {
            "vae": tmp_path / "vae",
            "upscale_models": tmp_path / "upscale_models",
            "text_encoders": tmp_path / "text_encoders",
            "clip": tmp_path / "clip",
            "clip_vision": tmp_path / "clip_vision",
            "controlnet": tmp_path / "controlnet",
        }
        for root in roots.values():
            root.mkdir()

        config = _make_config()
        unique, sub_type_map, per_key = config._prepare_other_paths(
            {key: [str(root)] for key, root in roots.items()}
        )

        assert len(unique) == 6
        assert sub_type_map[_normalize(str(roots["vae"]))] == "vae"
        assert sub_type_map[_normalize(str(roots["upscale_models"]))] == "upscaler"
        assert sub_type_map[_normalize(str(roots["text_encoders"]))] == "text_encoder"
        # Legacy ComfyUI 'clip' key maps to text_encoder as well
        assert sub_type_map[_normalize(str(roots["clip"]))] == "text_encoder"
        assert sub_type_map[_normalize(str(roots["clip_vision"]))] == "clip_vision"
        assert sub_type_map[_normalize(str(roots["controlnet"]))] == "controlnet"
        assert per_key["vae"] == [_normalize(str(roots["vae"]))]
        assert per_key["controlnet"] == [_normalize(str(roots["controlnet"]))]

    def test_missing_or_unknown_keys_are_skipped(self, tmp_path):
        vae_root = tmp_path / "vae"
        vae_root.mkdir()

        config = _make_config()
        unique, sub_type_map, per_key = config._prepare_other_paths(
            {
                "vae": [str(vae_root)],
                "does_not_exist_key": [str(tmp_path / "nope_dir")],
                "upscale_models": [],
            }
        )

        assert unique == [_normalize(str(vae_root))]
        assert set(per_key.keys()) == {"vae"}

    def test_nonexistent_paths_are_filtered(self, tmp_path):
        config = _make_config()
        unique, _, _ = config._prepare_other_paths(
            {"vae": [str(tmp_path / "missing_vae")]}
        )
        assert unique == []

    def test_cross_category_overlap_warns_and_keeps_first(
        self, tmp_path, caplog
    ):
        """The same physical folder under two categories warns; first wins."""
        shared = tmp_path / "shared"
        shared.mkdir()

        config = _make_config()
        with caplog.at_level(logging.WARNING, logger=config_module.logger.name):
            unique, sub_type_map, per_key = config._prepare_other_paths(
                {
                    "vae": [str(shared)],
                    "upscale_models": [str(shared)],
                }
            )

        assert unique == [_normalize(str(shared))]
        assert sub_type_map[_normalize(str(shared))] == "vae"
        assert "upscale_models" not in per_key

        warnings = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING"
            and "multiple other-model categories" in record.message
        ]
        assert len(warnings) == 1

    def test_same_sub_type_duplicate_is_debug_not_warning(self, tmp_path, caplog):
        """A sub_type spanning two folder keys legitimately sees a folder twice.

        ``clip`` and ``text_encoders`` both map to ``text_encoder``, so a folder
        reachable through both is expected and must not tell the user to fix a
        configuration they cannot fix.
        """
        text_encoders_dir = tmp_path / "text_encoders"
        legacy_clip_dir = tmp_path / "clip"
        text_encoders_dir.mkdir()
        legacy_clip_dir.mkdir()

        config = _make_config()
        with caplog.at_level(logging.DEBUG, logger=config_module.logger.name):
            unique, sub_type_map, per_key = config._prepare_other_paths(
                {
                    "text_encoders": [str(text_encoders_dir)],
                    "clip": [str(legacy_clip_dir), str(text_encoders_dir)],
                }
            )

        assert set(unique) == {
            _normalize(str(text_encoders_dir)),
            _normalize(str(legacy_clip_dir)),
        }
        assert sub_type_map[_normalize(str(legacy_clip_dir))] == "text_encoder"
        assert per_key["clip"] == [_normalize(str(legacy_clip_dir))]

        warnings = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING"
            and "multiple other-model categories" in record.message
        ]
        assert warnings == []

        debug_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "DEBUG"
            and "Ignoring duplicate folder" in record.message
        ]
        assert len(debug_messages) == 1

    def test_cross_scanner_overlap_warns_but_keeps_path(self, tmp_path, caplog):
        """An other root overlapping a checkpoint root warns but stays managed."""
        shared = tmp_path / "shared_models"
        shared.mkdir()

        config = _make_config(base_models_roots=[_normalize(str(shared))])
        with caplog.at_level(logging.WARNING, logger=config_module.logger.name):
            unique, sub_type_map, _ = config._prepare_other_paths(
                {"vae": [str(shared)]}
            )

        # Kept on purpose: dropping would silently unmanage the files
        assert unique == [_normalize(str(shared))]
        assert sub_type_map[_normalize(str(shared))] == "vae"

        warnings = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING"
            and "overlaps an existing checkpoints/embeddings root" in record.message
        ]
        assert len(warnings) == 1

    def test_no_warning_for_disjoint_roots(self, tmp_path, caplog):
        checkpoints_root = tmp_path / "checkpoints"
        checkpoints_root.mkdir()
        vae_root = tmp_path / "vae"
        vae_root.mkdir()

        config = _make_config(base_models_roots=[_normalize(str(checkpoints_root))])
        with caplog.at_level(logging.WARNING, logger=config_module.logger.name):
            unique, _, _ = config._prepare_other_paths({"vae": [str(vae_root)]})

        assert unique == [_normalize(str(vae_root))]
        warnings = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING" and "overlap" in record.message.lower()
        ]
        assert warnings == []


class TestInitOtherPaths:
    """Config._init_other_paths with mocked folder_paths (plugin + standalone modes).

    Config only depends on ``folder_paths.get_folder_paths(key)``: ComfyUI in
    plugin mode, or MockFolderPaths serving ``settings.json.folder_paths`` in
    standalone mode. A dict-backed stub therefore covers both.
    """

    def _stub_folder_paths(self, monkeypatch, mapping):
        def get_folder_paths(key):
            value = mapping.get(key, [])
            return [value] if isinstance(value, str) else list(value)

        monkeypatch.setattr(
            config_module.folder_paths, "get_folder_paths", get_folder_paths
        )

    def test_default_enabled_keys_exclude_opt_in_types(self, monkeypatch, tmp_path):
        dirs = {}
        for key in (
            "vae",
            "upscale_models",
            "text_encoders",
            "clip",
            "clip_vision",
            "controlnet",
        ):
            path = tmp_path / key
            path.mkdir()
            dirs[key] = str(path)

        self._stub_folder_paths(monkeypatch, dirs)

        config = _make_config()
        roots = config._init_other_paths()

        # clip_vision and controlnet are workflow-driven categories and stay
        # opt-in; only VAE / upscaler / text encoder are managed by default.
        for key in ("clip_vision", "controlnet"):
            assert _normalize(dirs[key]) not in roots
            assert _normalize(dirs[key]) not in config.other_root_subtypes
        # This stub has no map_legacy (standalone-shaped), so the legacy clip
        # key is queried on its own and its folder lands under text_encoder.
        for key in ("vae", "upscale_models", "text_encoders", "clip"):
            assert _normalize(dirs[key]) in roots

    def test_legacy_key_is_not_queried_when_host_aliases_it(
        self, monkeypatch, tmp_path, caplog
    ):
        """ComfyUI resolves clip -> text_encoders, so only the canonical key is
        queried: its folder list already contains the legacy directory."""
        canonical_dir = tmp_path / "text_encoders"
        legacy_dir = tmp_path / "clip"
        canonical_dir.mkdir()
        legacy_dir.mkdir()

        queried = []

        def get_folder_paths(key):
            queried.append(key)
            if key == "text_encoders":
                # Mirrors ComfyUI folder_paths: both directories are registered
                # under the canonical key.
                return [str(canonical_dir), str(legacy_dir)]
            return []

        monkeypatch.setattr(
            config_module.folder_paths, "get_folder_paths", get_folder_paths
        )
        monkeypatch.setattr(
            config_module.folder_paths,
            "map_legacy",
            lambda key: {"clip": "text_encoders"}.get(key, key),
            raising=False,
        )

        config = _make_config()
        with caplog.at_level(logging.DEBUG, logger=config_module.logger.name):
            roots = config._init_other_paths()

        assert "clip" not in queried
        assert _normalize(str(canonical_dir)) in roots
        assert _normalize(str(legacy_dir)) in roots
        assert (
            config.other_root_subtypes[_normalize(str(legacy_dir))]
            == "text_encoder"
        )
        # The reported bug: this layout used to log "please fix your path
        # configuration" twice for aliased keys the user cannot separate.
        assert [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING"
        ] == []

    @pytest.mark.parametrize("opt_in_key", ["controlnet", "clip_vision"])
    def test_opt_in_sub_type_via_setting(self, monkeypatch, tmp_path, opt_in_key):
        opt_in_dir = tmp_path / opt_in_key
        opt_in_dir.mkdir()

        self._stub_folder_paths(monkeypatch, {opt_in_key: str(opt_in_dir)})
        get_settings_manager().set("enabled_other_sub_types", [opt_in_key])

        config = _make_config()
        roots = config._init_other_paths()

        assert _normalize(str(opt_in_dir)) in roots
        assert (
            config.other_root_subtypes[_normalize(str(opt_in_dir))] == opt_in_key
        )

    def test_disabled_sub_type_is_not_scanned(self, monkeypatch, tmp_path):
        vae_dir = tmp_path / "vae"
        upscaler_dir = tmp_path / "upscale_models"
        vae_dir.mkdir()
        upscaler_dir.mkdir()

        self._stub_folder_paths(
            monkeypatch, {"vae": str(vae_dir), "upscale_models": str(upscaler_dir)}
        )
        get_settings_manager().set("enabled_other_sub_types", ["vae"])

        config = _make_config()
        roots = config._init_other_paths()

        assert roots == [_normalize(str(vae_dir))]
        assert _normalize(str(upscaler_dir)) not in config.other_root_subtypes

    def test_feature_disabled_scans_nothing(self, monkeypatch, tmp_path):
        vae_dir = tmp_path / "vae"
        vae_dir.mkdir()

        self._stub_folder_paths(monkeypatch, {"vae": str(vae_dir)})
        get_settings_manager().set("enable_other_models", False)

        config = _make_config()
        roots = config._init_other_paths()

        assert roots == []
        assert config.other_root_subtypes == {}
        assert config.other_folder_roots == {}

    def test_unknown_opt_in_keys_are_ignored(self, monkeypatch, tmp_path):
        vae_dir = tmp_path / "vae"
        vae_dir.mkdir()

        self._stub_folder_paths(monkeypatch, {"vae": str(vae_dir)})
        get_settings_manager().set(
            "enabled_other_sub_types", ["vae", "not_a_real_key", 42]
        )

        config = _make_config()
        roots = config._init_other_paths()

        assert roots == [_normalize(str(vae_dir))]

    def test_apply_library_paths_picks_up_other_keys(self, monkeypatch, tmp_path):
        vae_dir = tmp_path / "vae"
        vae_dir.mkdir()

        config = _make_config()
        monkeypatch.setattr(config, "_initialize_symlink_mappings", lambda: None)

        config._apply_library_paths(
            {
                "loras": [],
                "checkpoints": [],
                "unet": [],
                "embeddings": [],
                "vae": [str(vae_dir)],
            }
        )

        assert config.other_roots == [_normalize(str(vae_dir))]
        assert config.other_root_subtypes == {
            _normalize(str(vae_dir)): "vae"
        }
        assert config.other_folder_roots == {"vae": [_normalize(str(vae_dir))]}


class TestOtherRootsWiring:
    """other_roots participates in symlink and preview root bookkeeping."""

    def test_symlink_roots_include_other_roots(self):
        config = _make_config()
        config.loras_roots = ["/loras"]
        config.embeddings_roots = ["/embeddings"]
        config.other_roots = ["/vae"]
        config.extra_loras_roots = []
        config.extra_checkpoints_roots = []
        config.extra_unet_roots = []
        config.extra_embeddings_roots = []

        assert "/vae" in config._symlink_roots()

    def test_preview_roots_include_other_roots(self, tmp_path):
        vae_dir = tmp_path / "vae"
        vae_dir.mkdir()

        config = _make_config()
        config.loras_roots = []
        config.embeddings_roots = []
        config.other_roots = [_normalize(str(vae_dir))]
        config.extra_loras_roots = []
        config.extra_checkpoints_roots = []
        config.extra_unet_roots = []
        config.extra_embeddings_roots = []
        config.recipes_path = ""

        config._rebuild_preview_roots()

        assert config.is_preview_path_allowed(str(vae_dir / "model.preview.png"))


class TestOtherModelsAvailability:
    """Config.get_other_models_availability ignores the opt-in toggle.

    It answers "could Other Models work here at all?", which the settings
    payload and the announcement banner use to avoid promising a page that
    cannot list anything.
    """

    def _stub_folder_paths(self, monkeypatch, mapping):
        def get_folder_paths(key):
            value = mapping.get(key, [])
            return [value] if isinstance(value, str) else list(value)

        monkeypatch.setattr(
            config_module.folder_paths, "get_folder_paths", get_folder_paths
        )
        # No host alias rewriting: every key stays independently queryable,
        # which is what the standalone mock does.
        monkeypatch.delattr(config_module.folder_paths, "map_legacy", raising=False)

    def test_reports_available_when_a_folder_exists(self, monkeypatch, tmp_path):
        vae_dir = tmp_path / "vae"
        vae_dir.mkdir()
        self._stub_folder_paths(monkeypatch, {"vae": str(vae_dir)})

        # The feature stays off on purpose: availability must not depend on it.
        get_settings_manager().set("enable_other_models", False)

        availability = _make_config().get_other_models_availability()

        assert availability["available"] is True
        assert availability["sub_types"] == {"vae": [_normalize(str(vae_dir))]}

    def test_counts_an_empty_but_existing_folder(self, monkeypatch, tmp_path):
        vae_dir = tmp_path / "vae"
        vae_dir.mkdir()
        self._stub_folder_paths(monkeypatch, {"vae": str(vae_dir)})

        availability = _make_config().get_other_models_availability()

        assert availability["available"] is True

    def test_ignores_missing_folders(self, monkeypatch, tmp_path):
        self._stub_folder_paths(
            monkeypatch, {"vae": str(tmp_path / "does-not-exist")}
        )

        availability = _make_config().get_other_models_availability()

        assert availability == {"available": False, "sub_types": {}}

    def test_reports_unavailable_without_any_configuration(self, monkeypatch):
        self._stub_folder_paths(monkeypatch, {})

        availability = _make_config().get_other_models_availability()

        assert availability == {"available": False, "sub_types": {}}

    def test_merges_legacy_clip_key_into_text_encoder(self, monkeypatch, tmp_path):
        clip_dir = tmp_path / "clip"
        clip_dir.mkdir()
        self._stub_folder_paths(monkeypatch, {"clip": [str(clip_dir)]})

        availability = _make_config().get_other_models_availability()

        assert availability["available"] is True
        assert availability["sub_types"] == {
            "text_encoder": [_normalize(str(clip_dir))]
        }
