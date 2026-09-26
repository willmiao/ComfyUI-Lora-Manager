"""Tests for py.utils.sidecar_paths (alongside + centralized storage modes)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils import sidecar_paths
from py.utils.sidecar_paths import (
    METADATA_SUFFIX,
    get_configured_sidecar_root,
    get_metadata_path,
    get_preview_dir,
    get_sidecar_dir,
    get_sidecar_root,
    get_storage_mode,
    is_centralized,
    is_metadata_path,
    resolve_centralized_dir,
    resolve_centralized_dir_for_dir,
    resolve_metadata_path,
    root_mirror_component,
    sanitize_path_component,
)


def _normalize(path: Path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture
def model_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Point every config model root the sidecar module reads at tmp_path."""

    from py.config import config

    loras = tmp_path / "loras"
    checkpoints = tmp_path / "checkpoints"
    loras.mkdir()
    checkpoints.mkdir()

    for attr, value in (
        ("loras_roots", [str(loras)]),
        ("base_models_roots", [str(checkpoints)]),
        ("embeddings_roots", []),
        ("other_roots", []),
        ("extra_loras_roots", []),
        ("extra_checkpoints_roots", []),
        ("extra_unet_roots", []),
        ("extra_embeddings_roots", []),
    ):
        monkeypatch.setattr(config, attr, value, raising=False)

    return {"loras": loras, "checkpoints": checkpoints}


@pytest.fixture
def centralized(model_roots: dict, tmp_path: Path) -> Path:
    """Enable centralized mode rooted at tmp_path/sidecars; returns the root."""

    sidecar_root = tmp_path / "sidecars"
    settings = get_settings_manager()
    settings.set("sidecar_storage_mode", "centralized")
    settings.set("sidecar_storage_path", str(sidecar_root))
    return sidecar_root


class TestAlongsideMode:
    def test_default_mode_is_alongside(self):
        assert get_storage_mode() == "alongside"
        assert not is_centralized()
        assert get_sidecar_root() == ""

    def test_metadata_path_next_to_model(self, tmp_path: Path):
        model = tmp_path / "sub" / "model.safetensors"
        assert get_metadata_path(str(model)) == os.path.join(
            str(tmp_path), "sub", "model" + METADATA_SUFFIX
        )

    def test_preview_and_sidecar_dir_are_model_dir(self, tmp_path: Path):
        model = tmp_path / "sub" / "model.safetensors"
        expected = os.path.dirname(os.path.abspath(str(model)))
        assert get_sidecar_dir(str(model)) == expected
        assert get_preview_dir(str(model)) == expected


class TestPathPredicates:
    def test_is_metadata_path(self):
        assert is_metadata_path("/x/model.metadata.json")
        assert not is_metadata_path("/x/model.safetensors")
        assert not is_metadata_path("/x/model.metadata.json.bak")

    def test_resolve_metadata_path_passthrough_for_sidecar(self):
        sidecar = "/x/model.metadata.json"
        assert resolve_metadata_path(sidecar) == sidecar

    def test_resolve_metadata_path_derives_for_model(self, tmp_path: Path):
        model = tmp_path / "model.safetensors"
        assert resolve_metadata_path(str(model)) == get_metadata_path(str(model))


class TestSanitizePathComponent:
    def test_special_characters_replaced(self):
        assert sanitize_path_component("foo bar/baz:qux") == "foo_bar_baz_qux"

    def test_safe_characters_kept(self):
        assert sanitize_path_component("Flux-1.dev_v2") == "Flux-1.dev_v2"

    def test_empty_falls_back_to_underscore(self):
        assert sanitize_path_component("") == "_"
        assert sanitize_path_component(None) == "_"


class TestCentralizedMode:
    def test_mirror_layout(self, model_roots: dict, centralized: Path):
        model = model_roots["loras"] / "styles" / "anime" / "model.safetensors"
        library = get_settings_manager().get_active_library_name()
        root_component = root_mirror_component(str(model_roots["loras"]))

        metadata_path = get_metadata_path(str(model))

        expected = os.path.join(
            str(centralized), library, root_component, "styles", "anime", "model" + METADATA_SUFFIX
        )
        assert metadata_path == expected
        assert get_preview_dir(str(model)) == os.path.dirname(expected)
        assert is_centralized()

    def test_same_basename_roots_get_distinct_mirrors(
        self, model_roots: dict, centralized: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from py.config import config

        # Two roots sharing the basename "loras" must not share a mirror dir.
        other_parent = tmp_path / "elsewhere"
        other_root = other_parent / "loras"
        other_root.mkdir(parents=True)
        monkeypatch.setattr(
            config,
            "loras_roots",
            [str(model_roots["loras"]), str(other_root)],
            raising=False,
        )

        model_a = model_roots["loras"] / "model.safetensors"
        model_b = other_root / "model.safetensors"

        dir_a = resolve_centralized_dir(str(model_a))
        dir_b = resolve_centralized_dir(str(model_b))
        assert dir_a is not None and dir_b is not None
        assert dir_a != dir_b
        assert root_mirror_component(str(model_roots["loras"])) != root_mirror_component(
            str(other_root)
        )
        # Same root always maps to the same component (stable hash).
        assert root_mirror_component(str(model_roots["loras"])) == root_mirror_component(
            str(model_roots["loras"]) + os.sep
        )

    def test_longest_root_wins(self, model_roots: dict, centralized: Path, monkeypatch: pytest.MonkeyPatch):
        from py.config import config

        nested = model_roots["loras"] / "nested"
        nested.mkdir()
        monkeypatch.setattr(
            config,
            "loras_roots",
            [str(model_roots["loras"]), str(nested)],
            raising=False,
        )
        library = get_settings_manager().get_active_library_name()

        model = nested / "model.safetensors"
        assert get_metadata_path(str(model)) == os.path.join(
            str(centralized), library, root_mirror_component(str(nested)), "model" + METADATA_SUFFIX
        )

    def test_outside_roots_falls_back_to_alongside(
        self, model_roots: dict, centralized: Path, tmp_path: Path
    ):
        outside = tmp_path / "elsewhere" / "model.safetensors"

        assert resolve_centralized_dir(str(outside)) is None
        assert get_sidecar_dir(str(outside)) == os.path.dirname(
            os.path.abspath(str(outside))
        )
        assert get_metadata_path(str(outside)) == os.path.join(
            str(tmp_path), "elsewhere", "model" + METADATA_SUFFIX
        )

    def test_resolve_centralized_dir_for_dir_matches_model_resolution(
        self, model_roots: dict, centralized: Path
    ):
        model_dir = model_roots["checkpoints"] / "sub"
        model = model_dir / "model.safetensors"

        assert resolve_centralized_dir_for_dir(str(model_dir)) == resolve_centralized_dir(
            str(model)
        )

    def test_resolve_centralized_dir_for_dir_root_maps_to_mirror_base(
        self, model_roots: dict, centralized: Path
    ):
        library = get_settings_manager().get_active_library_name()

        assert resolve_centralized_dir_for_dir(str(model_roots["loras"])) == os.path.join(
            str(centralized), library, root_mirror_component(str(model_roots["loras"]))
        )

    def test_empty_path_uses_default_sidecar_root(self, model_roots: dict, tmp_path: Path):
        settings = get_settings_manager()
        settings.set("sidecar_storage_mode", "centralized")
        settings.set("sidecar_storage_path", "")

        root = get_sidecar_root()
        assert root
        assert root.endswith(os.sep + "sidecars")
        assert is_centralized()


class TestModeIndependentResolution:
    """Migration tooling resolves the mirror layout regardless of active mode."""

    def test_configured_root_resolves_in_alongside_mode(self, tmp_path: Path):
        sidecar_root = tmp_path / "sidecars"
        settings = get_settings_manager()
        settings.set("sidecar_storage_mode", "alongside")
        settings.set("sidecar_storage_path", str(sidecar_root))

        assert get_sidecar_root() == ""
        assert get_configured_sidecar_root() == os.path.abspath(str(sidecar_root))

    def test_configured_root_defaults_to_settings_dir(self):
        settings = get_settings_manager()
        settings.set("sidecar_storage_mode", "alongside")
        settings.set("sidecar_storage_path", "")

        root = get_configured_sidecar_root()
        assert root
        assert root.endswith(os.sep + "sidecars")

    def test_resolve_centralized_dir_for_dir_with_explicit_root(
        self, model_roots: dict, tmp_path: Path
    ):
        sidecar_root = tmp_path / "sidecars"
        settings = get_settings_manager()
        settings.set("sidecar_storage_mode", "alongside")
        library = settings.get_active_library_name()

        model_dir = model_roots["loras"] / "sub"

        # Alongside mode: no root resolves without the override.
        assert resolve_centralized_dir_for_dir(str(model_dir)) is None
        assert resolve_centralized_dir_for_dir(
            str(model_dir), sidecar_root=str(sidecar_root)
        ) == os.path.join(
            str(sidecar_root), library, root_mirror_component(str(model_roots["loras"])), "sub"
        )


class TestSettingsValidation:
    def test_invalid_mode_falls_back_to_alongside(self):
        settings = get_settings_manager()
        settings.set("sidecar_storage_mode", "bogus")
        assert settings.get("sidecar_storage_mode") == "alongside"

    def test_mode_is_normalized(self):
        settings = get_settings_manager()
        settings.set("sidecar_storage_mode", " Centralized ")
        assert settings.get("sidecar_storage_mode") == "centralized"

    def test_path_is_normalized_to_absolute(self, tmp_path: Path):
        settings = get_settings_manager()
        settings.set("sidecar_storage_path", str(tmp_path / "sidecars"))
        assert settings.get("sidecar_storage_path") == os.path.abspath(
            str(tmp_path / "sidecars")
        )

    def test_non_string_path_becomes_empty(self):
        settings = get_settings_manager()
        settings.set("sidecar_storage_path", None)
        assert settings.get("sidecar_storage_path") == ""
