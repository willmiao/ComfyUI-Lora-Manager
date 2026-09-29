"""Tests for py.utils.sidecar_paths (alongside + centralized storage modes)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils import sidecar_paths
from py.utils.sidecar_paths import (
    METADATA_SUFFIX,
    ROOT_MAP_FILENAME,
    get_configured_sidecar_root,
    get_metadata_path,
    get_preview_dir,
    get_sidecar_dir,
    get_sidecar_root,
    get_storage_mode,
    get_unmatched_sidecar_components,
    is_centralized,
    is_metadata_path,
    relocate_root_map,
    resolve_centralized_dir,
    resolve_centralized_dir_for_dir,
    resolve_metadata_path,
    root_mirror_component,
    sanitize_path_component,
)


def _write_map(root: Path, entries: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ROOT_MAP_FILENAME
    path.write_text(
        json.dumps({"version": 1, "roots": entries}), encoding="utf-8"
    )
    return path


def _normalize(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _legacy_component(root) -> str:
    """Independent reimplementation of the pre-identity-map component name."""

    normalized = os.path.normpath(os.path.abspath(str(root)))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{sanitize_path_component(os.path.basename(normalized))}-{digest}"


@pytest.fixture(autouse=True)
def _reset_root_map_cache():
    """Identities are cached per sidecar root; keep tests order-independent."""

    sidecar_paths.reset_root_map_cache()
    yield
    sidecar_paths.reset_root_map_cache()


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


def _write_sidecar(model_path: Path, payload: dict | None = None) -> Path:
    """Create the model file and its sidecar at the module-resolved path."""

    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(b"weights")
    sidecar = Path(get_metadata_path(str(model_path)))
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(payload or {"favorite": True}), encoding="utf-8")
    return sidecar


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

    def test_alongside_resolution_touches_nothing(
        self, model_roots: dict, tmp_path: Path
    ):
        """The default branch must not load, create, or scan the mirror tree."""

        sidecar_root = tmp_path / "sidecars"
        settings = get_settings_manager()
        settings.set("sidecar_storage_mode", "alongside")
        settings.set("sidecar_storage_path", str(sidecar_root))

        model = model_roots["loras"] / "sub" / "model.safetensors"
        assert get_metadata_path(str(model)) == os.path.join(
            str(model_roots["loras"]), "sub", "model" + METADATA_SUFFIX
        )
        assert get_preview_dir(str(model)) == os.path.join(
            str(model_roots["loras"]), "sub"
        )
        assert not sidecar_root.exists()
        assert sidecar_paths._ROOT_MAPS == {}


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
        root_component = root_mirror_component(str(model_roots["loras"]))

        metadata_path = get_metadata_path(str(model))

        expected = os.path.join(
            str(centralized), root_component, "styles", "anime", "model" + METADATA_SUFFIX
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
        # Same root always maps to the same component (pinned identity).
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

        model = nested / "model.safetensors"
        assert get_metadata_path(str(model)) == os.path.join(
            str(centralized), root_mirror_component(str(nested)), "model" + METADATA_SUFFIX
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
        assert resolve_centralized_dir_for_dir(str(model_roots["loras"])) == os.path.join(
            str(centralized), root_mirror_component(str(model_roots["loras"]))
        )

    def test_empty_path_uses_default_sidecar_root(self, model_roots: dict, tmp_path: Path):
        settings = get_settings_manager()
        settings.set("sidecar_storage_mode", "centralized")
        settings.set("sidecar_storage_path", "")

        root = get_sidecar_root()
        assert root
        assert root.endswith(os.sep + "sidecars")
        assert is_centralized()


class TestRootIdentityMap:
    """The root component is a remembered identity, not a path hash."""

    def test_component_is_pinned_in_the_map_file(
        self, model_roots: dict, centralized: Path
    ):
        model = model_roots["loras"] / "sub" / "model.safetensors"
        first = get_metadata_path(str(model))

        map_path = centralized / ROOT_MAP_FILENAME
        assert map_path.exists()
        payload = json.loads(map_path.read_text(encoding="utf-8"))
        persisted = {entry["component"] for entry in payload["roots"].values()}
        assert root_mirror_component(str(model_roots["loras"])) in persisted

        # Restarting the process must resolve the exact same location.
        sidecar_paths.reset_root_map_cache()
        assert get_metadata_path(str(model)) == first

    def test_component_is_deterministic_and_survives_a_lost_map(
        self, model_roots: dict, centralized: Path
    ):
        """Deleting the map must not strand a mirror whose root has not moved."""

        model = model_roots["loras"] / "sub" / "model.safetensors"
        first = _write_sidecar(model)
        assert Path(get_metadata_path(str(model))) == first

        (centralized / ROOT_MAP_FILENAME).unlink()
        sidecar_paths.reset_root_map_cache()

        assert Path(get_metadata_path(str(model))) == first
        assert root_mirror_component(str(model_roots["loras"])) == _legacy_component(
            model_roots["loras"]
        )

    def test_legacy_path_derived_component_is_adopted(
        self, model_roots: dict, centralized: Path
    ):
        """Upgrading from the hash-named layout keeps existing mirrors usable."""

        legacy = _legacy_component(model_roots["loras"])

        sidecar = centralized / legacy / "sub" / ("model" + METADATA_SUFFIX)
        sidecar.parent.mkdir(parents=True)
        sidecar.write_text(json.dumps({"favorite": True}), encoding="utf-8")

        model = model_roots["loras"] / "sub" / "model.safetensors"
        assert get_metadata_path(str(model)) == str(sidecar)
        assert root_mirror_component(str(model_roots["loras"])) == legacy

    def test_pre_identity_map_library_nested_component_is_adopted(
        self, model_roots: dict, centralized: Path
    ):
        """Mirrors created by the pre-identity-map build nested under a library."""

        legacy = _legacy_component(model_roots["loras"])
        sidecar = (
            centralized / "comfyui" / legacy / "sub" / ("model" + METADATA_SUFFIX)
        )
        sidecar.parent.mkdir(parents=True)
        sidecar.write_text(json.dumps({"favorite": True}), encoding="utf-8")

        model = model_roots["loras"] / "sub" / "model.safetensors"
        assert get_metadata_path(str(model)) == str(sidecar)
        assert root_mirror_component(str(model_roots["loras"])) == f"comfyui/{legacy}"
        # The adopted tree counts as linked, not orphaned.
        assert get_unmatched_sidecar_components() == []

    def test_moved_root_reuses_its_mirror(
        self, model_roots: dict, centralized: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A relocated (and reconfigured) root keeps its remembered identity."""

        from py.config import config

        model = model_roots["loras"] / "sub" / "model.safetensors"
        before = _write_sidecar(model)

        moved_root = tmp_path / "relocated" / "loras"
        shutil.copytree(model_roots["loras"], moved_root)
        monkeypatch.setattr(config, "loras_roots", [str(moved_root)], raising=False)
        sidecar_paths.reset_root_map_cache()

        moved_model = moved_root / "sub" / "model.safetensors"
        after = Path(get_metadata_path(str(moved_model)))

        assert after == before
        assert json.loads(after.read_text(encoding="utf-8")) == {"favorite": True}

    def test_renamed_root_reanchors_via_directory_overlap(
        self, model_roots: dict, centralized: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A rename that changes the basename still re-anchors when the tree matches."""

        from py.config import config

        model = model_roots["loras"] / "sub" / "model.safetensors"
        before = _write_sidecar(model)

        renamed_root = tmp_path / "brand-new-name"
        shutil.copytree(model_roots["loras"], renamed_root)
        monkeypatch.setattr(config, "loras_roots", [str(renamed_root)], raising=False)
        sidecar_paths.reset_root_map_cache()

        renamed_model = renamed_root / "sub" / "model.safetensors"
        assert Path(get_metadata_path(str(renamed_model))) == before

    def test_ambiguous_reanchor_reports_orphans_instead_of_guessing(
        self, model_roots: dict, centralized: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from py.config import config

        model = model_roots["loras"] / "sub" / "model.safetensors"
        before = _write_sidecar(model)
        component = before.parent.parent.name

        # Two equally plausible candidates: never silently pick one.
        candidate_a = tmp_path / "a" / "loras"
        candidate_b = tmp_path / "b" / "loras"
        shutil.copytree(model_roots["loras"], candidate_a)
        shutil.copytree(model_roots["loras"], candidate_b)
        monkeypatch.setattr(
            config, "loras_roots", [str(candidate_a), str(candidate_b)], raising=False
        )
        sidecar_paths.reset_root_map_cache()

        for candidate in (candidate_a, candidate_b):
            resolved = Path(
                get_metadata_path(str(candidate / "sub" / "model.safetensors"))
            )
            assert resolved != before
            assert component not in str(resolved)

        orphans = get_unmatched_sidecar_components()
        assert [item["component"] for item in orphans] == [component]

    def test_removed_root_surfaces_its_component_as_orphan(
        self, model_roots: dict, centralized: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from py.config import config

        model = model_roots["loras"] / "sub" / "model.safetensors"
        sidecar = _write_sidecar(model)
        component = sidecar.parent.parent.name

        monkeypatch.setattr(config, "loras_roots", [], raising=False)
        sidecar_paths.reset_root_map_cache()

        assert [item["component"] for item in get_unmatched_sidecar_components()] == [
            component
        ]

    def test_unmatched_helper_is_empty_in_alongside_mode(
        self, model_roots: dict, tmp_path: Path
    ):
        settings = get_settings_manager()
        settings.set("sidecar_storage_mode", "alongside")
        settings.set("sidecar_storage_path", str(tmp_path / "sidecars"))

        assert get_unmatched_sidecar_components() == []
        assert not (tmp_path / "sidecars").exists()

    def test_relocated_sidecar_root_resolves_after_map_written_first(
        self, model_roots: dict, tmp_path: Path
    ):
        """A resolve before the mirror tree is relocated must not rename it."""

        settings = get_settings_manager()
        old_root = tmp_path / "old-sidecars"
        new_root = tmp_path / "new-sidecars"
        settings.set("sidecar_storage_mode", "centralized")
        settings.set("sidecar_storage_path", str(old_root))

        model = model_roots["loras"] / "sub" / "model.safetensors"
        sidecar = _write_sidecar(model)

        # The path setting changes first, and something resolves against the
        # new root before the user runs the relocation.
        settings.set("sidecar_storage_path", str(new_root))
        sidecar_paths.reset_root_map_cache()
        expected = new_root / sidecar.relative_to(old_root)
        assert Path(get_metadata_path(str(model))) == expected
        assert not expected.exists()

        # Now the mirror tree moves, exactly as migrate_root does.
        for dirpath, _dirnames, filenames in os.walk(old_root):
            rel = os.path.relpath(dirpath, old_root)
            target_dir = new_root if rel == os.curdir else new_root / rel
            target_dir.mkdir(parents=True, exist_ok=True)
            for filename in filenames:
                shutil.move(str(Path(dirpath) / filename), str(target_dir / filename))

        sidecar_paths.reset_root_map_cache()
        assert Path(get_metadata_path(str(model))) == expected
        assert json.loads(expected.read_text(encoding="utf-8")) == {"favorite": True}

    def test_relocate_root_map_prefers_the_source_entries(self, tmp_path: Path):
        """A map written at the destination before a relocation must not win."""

        source = tmp_path / "old-sidecars"
        destination = tmp_path / "new-sidecars"
        _write_map(
            source,
            {
                "aaaa1111": {
                    "component": "loras-pinned",
                    "basename": "loras",
                    "last_path": "/models/loras",
                    "sample_rel_dirs": [],
                }
            },
        )
        _write_map(
            destination,
            {
                "bbbb2222": {
                    "component": "loras-recomputed",
                    "basename": "loras",
                    "last_path": "/models/loras",
                    "sample_rel_dirs": [],
                },
                "cccc3333": {
                    "component": "vae-other",
                    "basename": "vae",
                    "last_path": "/models/vae",
                    "sample_rel_dirs": [],
                },
            },
        )

        assert relocate_root_map(str(source), str(destination)) is True

        merged = json.loads(
            (destination / ROOT_MAP_FILENAME).read_text(encoding="utf-8")
        )["roots"]
        assert merged["aaaa1111"]["component"] == "loras-pinned"
        assert "bbbb2222" not in merged  # superseded for the same root path
        assert merged["cccc3333"]["component"] == "vae-other"
        assert not (source / ROOT_MAP_FILENAME).exists()

    def test_relocate_root_map_without_a_source_map_is_a_noop(self, tmp_path: Path):
        source = tmp_path / "old-sidecars"
        destination = tmp_path / "new-sidecars"
        _write_map(
            destination,
            {
                "bbbb2222": {
                    "component": "loras-keep",
                    "basename": "loras",
                    "last_path": "/models/loras",
                    "sample_rel_dirs": [],
                }
            },
        )

        assert relocate_root_map(str(source), str(destination)) is True

        kept = json.loads(
            (destination / ROOT_MAP_FILENAME).read_text(encoding="utf-8")
        )["roots"]
        assert kept["bbbb2222"]["component"] == "loras-keep"

    def test_corrupt_map_file_is_ignored_and_rebuilt(
        self, model_roots: dict, centralized: Path
    ):
        model = model_roots["loras"] / "model.safetensors"
        map_path = centralized / ROOT_MAP_FILENAME

        get_metadata_path(str(model))
        map_path.write_text("{not json", encoding="utf-8")
        sidecar_paths.reset_root_map_cache()

        path_after = get_metadata_path(str(model))
        assert json.loads(map_path.read_text(encoding="utf-8"))["roots"]
        assert os.path.basename(os.path.dirname(path_after)).startswith("loras-")

    def test_root_map_file_is_not_mistaken_for_a_component(
        self, model_roots: dict, centralized: Path
    ):
        model = model_roots["loras"] / "model.safetensors"
        get_metadata_path(str(model))

        assert (centralized / ROOT_MAP_FILENAME).is_file()
        assert get_unmatched_sidecar_components() == []


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
        settings.set("sidecar_storage_path", str(sidecar_root))

        model_dir = model_roots["loras"] / "sub"
        component = root_mirror_component(
            str(model_roots["loras"]), sidecar_root=str(sidecar_root)
        )

        # Alongside mode: no root resolves without the override.
        assert resolve_centralized_dir_for_dir(str(model_dir)) is None
        assert resolve_centralized_dir_for_dir(
            str(model_dir), sidecar_root=str(sidecar_root)
        ) == os.path.join(str(sidecar_root), component, "sub")


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


class TestDescribeSidecarRoot:
    def test_configured_root(self, tmp_path: Path):
        settings = get_settings_manager()
        root = tmp_path / "sidecars-custom"
        settings.set("sidecar_storage_path", str(root))

        info = sidecar_paths.describe_sidecar_root()

        assert info["root"] == os.path.abspath(str(root))
        assert info["is_default"] is False
        assert info["inside_repo"] is False

    def test_default_root_marks_is_default(self):
        settings = get_settings_manager()
        settings.set("sidecar_storage_path", "")

        info = sidecar_paths.describe_sidecar_root()

        assert info["root"].endswith(os.sep + "sidecars")
        assert info["is_default"] is True

    def test_inside_repo_detection(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            sidecar_paths, "_installation_root", lambda: str(tmp_path / "repo")
        )
        settings = get_settings_manager()
        settings.set(
            "sidecar_storage_path", str(tmp_path / "repo" / "sidecars")
        )

        assert sidecar_paths.describe_sidecar_root()["inside_repo"] is True

        settings.set("sidecar_storage_path", str(tmp_path / "elsewhere"))
        assert sidecar_paths.describe_sidecar_root()["inside_repo"] is False
