"""Tests for ModelMoveService folder creation."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List

import pytest

from py.services.model_file_service import ModelMoveService


class FakeScanner:
    def __init__(self, roots: List[Path], excluded: List[str] | None = None) -> None:
        self._roots = [str(root) for root in roots]
        self.known_folders: List[str] = []
        self.removed_folders: List[str] = []
        self.removed_folder_paths: List[str | None] = []
        self.renamed_folders: List[tuple] = []
        self._excluded = list(excluded or [])

    def get_model_roots(self) -> List[str]:
        return list(self._roots)

    def get_excluded_models(self) -> List[str]:
        return list(self._excluded)

    async def add_known_folder(self, folder: str) -> None:
        self.known_folders.append(folder)

    async def remove_known_folder(self, folder: str, absolute_path: str | None = None) -> None:
        self.removed_folders.append(folder)
        self.removed_folder_paths.append(absolute_path)

    async def rename_known_folder(self, previous: str, current: str, **kwargs) -> None:
        self.renamed_folders.append((previous, current, kwargs))


class ScannerWithoutExcludedAccessor(FakeScanner):
    """Scanner stand-in predating ``get_excluded_models()``."""

    get_excluded_models = None  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_create_folder_creates_directory_and_registers_it(tmp_path: Path):
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    target = tmp_path / "characters" / "anime"
    result = await service.create_folder(str(target))

    assert result["success"] is True
    assert result["created"] is True
    assert result["folder"] == "characters/anime"
    assert target.is_dir()
    assert scanner.known_folders == ["characters/anime"]


@pytest.mark.asyncio
async def test_create_folder_existing_directory_reports_not_created(tmp_path: Path):
    (tmp_path / "existing").mkdir()
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.create_folder(str(tmp_path / "existing"))

    assert result["success"] is True
    assert result["created"] is False
    assert result["folder"] == "existing"


@pytest.mark.asyncio
async def test_create_folder_rejects_paths_outside_roots(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    scanner = FakeScanner([root])
    service = ModelMoveService(scanner, "lora")

    outside = tmp_path / "outside"
    result = await service.create_folder(str(outside))

    assert result["success"] is False
    assert "error" in result
    assert not outside.exists()
    assert scanner.known_folders == []


@pytest.mark.asyncio
async def test_create_folder_rejects_traversal_outside_roots(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    scanner = FakeScanner([root])
    service = ModelMoveService(scanner, "lora")

    result = await service.create_folder(str(root / ".." / "escape"))

    assert result["success"] is False
    assert not (tmp_path / "escape").exists()
    assert scanner.known_folders == []


@pytest.mark.asyncio
async def test_create_folder_requires_path(tmp_path: Path):
    service = ModelMoveService(FakeScanner([tmp_path]), "lora")

    result = await service.create_folder("")

    assert result["success"] is False


def test_resolve_folder_finds_the_directory_under_the_root_that_holds_it(tmp_path: Path):
    # The reported bug: the tree node lives under the primary root while the
    # configured default root is the extra one. Resolution must answer with the
    # directory that exists, not with a path fabricated from the default root.
    primary = tmp_path / "primary"
    extra = tmp_path / "extra"
    primary.mkdir()
    extra.mkdir()
    (primary / "recipes").mkdir()

    service = ModelMoveService(FakeScanner([primary, extra]), "lora")

    result = service.resolve_folder("recipes")

    assert result["success"] is True
    assert result["folder"] == "recipes"
    assert [Path(candidate["folder_path"]) for candidate in result["candidates"]] == [
        primary / "recipes"
    ]
    assert result["candidates"][0]["root"] == primary.as_posix()
    assert result["candidates"][0]["is_symlink"] is False


def test_resolve_folder_returns_a_candidate_per_root_holding_the_folder(tmp_path: Path):
    primary = tmp_path / "primary"
    extra = tmp_path / "extra"
    (primary / "characters" / "anime").mkdir(parents=True)
    (extra / "characters" / "anime").mkdir(parents=True)

    service = ModelMoveService(FakeScanner([primary, extra]), "lora")

    result = service.resolve_folder("characters/anime")

    # Order follows the scanner's root order so the caller can prefer the
    # default root without losing the rest.
    assert [Path(candidate["folder_path"]) for candidate in result["candidates"]] == [
        primary / "characters" / "anime",
        extra / "characters" / "anime",
    ]
    assert [candidate["root"] for candidate in result["candidates"]] == [
        primary.as_posix(),
        extra.as_posix(),
    ]


def test_resolve_folder_reports_no_candidate_for_a_stale_tree_node(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()

    service = ModelMoveService(FakeScanner([root]), "lora")

    result = service.resolve_folder("gone")

    assert result["success"] is True
    assert result["candidates"] == []


def test_resolve_folder_flags_symlinked_candidates(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    real = tmp_path / "real"
    real.mkdir()
    try:
        (root / "linked").symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform guard
        pytest.skip("symlinks are not supported on this platform")

    service = ModelMoveService(FakeScanner([root]), "lora")

    result = service.resolve_folder("linked")

    assert result["success"] is True
    assert result["candidates"][0]["is_symlink"] is True


def test_resolve_folder_normalizes_the_relative_path(tmp_path: Path):
    root = tmp_path / "library"
    (root / "characters" / "anime").mkdir(parents=True)

    service = ModelMoveService(FakeScanner([root]), "lora")

    result = service.resolve_folder("  characters\\anime/  ")

    assert result["success"] is True
    assert result["folder"] == "characters/anime"
    assert len(result["candidates"]) == 1


@pytest.mark.parametrize(
    "folder",
    ["", "   ", "/library/recipes", "C:/library/recipes", "..", "../outside", "a/../../b"],
)
def test_resolve_folder_rejects_paths_outside_the_relative_namespace(
    tmp_path: Path, folder: str
):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    service = ModelMoveService(FakeScanner([root]), "lora")

    result = service.resolve_folder(folder)

    assert result["success"] is False
    assert "candidates" not in result


def _make_nested(root: Path) -> Path:
    target = root / "characters" / "anime"
    target.mkdir(parents=True)
    return target


@pytest.mark.asyncio
async def test_delete_folder_removes_empty_directory_and_forgets_it(tmp_path: Path):
    target = _make_nested(tmp_path)
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is True
    assert result["folder"] == "characters/anime"
    assert result["model_count"] == 0
    assert result["restorable"] is True
    assert not target.exists()
    assert scanner.removed_folders == ["characters/anime"]
    # The scanner purges by the removed directory: the same relative folder may
    # exist under another root, whose model cards must survive.
    assert scanner.removed_folder_paths == [str(target)]


@pytest.mark.asyncio
async def test_delete_folder_reports_non_model_leftovers_as_not_restorable(tmp_path: Path):
    target = _make_nested(tmp_path)
    (target / "notes.txt").write_text("keep me?", encoding="utf-8")
    (target / "nested").mkdir()
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is True
    assert result["file_count"] == 1
    assert result["dir_count"] == 1
    assert result["restorable"] is False
    assert not target.exists()


@pytest.mark.asyncio
async def test_delete_folder_refuses_when_models_live_below(tmp_path: Path):
    target = _make_nested(tmp_path)
    model_file = target / "model.safetensors"
    model_file.write_text("weights", encoding="utf-8")
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is False
    assert result["code"] == "not_empty"
    assert result["manifest"]["model_count"] == 1
    assert result["manifest"]["excluded_model_count"] == 0
    assert target.exists()
    assert model_file.exists()
    assert scanner.removed_folders == []


@pytest.mark.asyncio
async def test_delete_folder_manifest_marks_models_excluded_from_the_library(tmp_path: Path):
    """Excluded models are invisible to the model lists but still block the
    cascade, so the manifest has to say so — the folder sidebar otherwise shows
    the folder as empty and the refusal reads as a bug."""
    target = _make_nested(tmp_path)
    model_file = target / "hidden.safetensors"
    model_file.write_text("weights", encoding="utf-8")
    scanner = FakeScanner([tmp_path], excluded=[str(model_file)])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is False
    assert result["code"] == "not_empty"
    assert result["manifest"]["model_count"] == 1
    assert result["manifest"]["excluded_model_count"] == 1
    assert "excluded" in result["error"]
    assert model_file.exists()


@pytest.mark.asyncio
async def test_delete_folder_error_splits_excluded_from_visible_models(tmp_path: Path):
    target = _make_nested(tmp_path)
    visible = target / "visible.safetensors"
    hidden = target / "hidden.safetensors"
    visible.write_text("weights", encoding="utf-8")
    hidden.write_text("weights", encoding="utf-8")
    scanner = FakeScanner([tmp_path], excluded=[str(hidden)])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["manifest"]["model_count"] == 2
    assert result["manifest"]["excluded_model_count"] == 1
    assert "1 of them excluded" in result["error"]


@pytest.mark.asyncio
async def test_delete_folder_does_not_claim_excluded_for_visible_models(tmp_path: Path):
    target = _make_nested(tmp_path)
    (target / "model.safetensors").write_text("weights", encoding="utf-8")
    # An excluded model elsewhere in the library must not be attributed here.
    scanner = FakeScanner([tmp_path], excluded=[str(tmp_path / "other" / "other.safetensors")])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["manifest"]["excluded_model_count"] == 0
    assert "excluded" not in result["error"]


@pytest.mark.asyncio
async def test_delete_folder_works_without_the_excluded_accessor(tmp_path: Path):
    target = _make_nested(tmp_path)
    (target / "model.safetensors").write_text("weights", encoding="utf-8")
    scanner = ScannerWithoutExcludedAccessor([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is False
    assert result["manifest"]["excluded_model_count"] == 0


@pytest.mark.asyncio
async def test_delete_folder_success_manifest_carries_excluded_model_count(tmp_path: Path):
    target = _make_nested(tmp_path)
    (target / "leftover.webp").write_text("preview", encoding="utf-8")
    scanner = FakeScanner([tmp_path], excluded=[str(tmp_path / "elsewhere.safetensors")])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target), dry_run=True)

    assert result["success"] is True
    assert result["excluded_model_count"] == 0


@pytest.mark.asyncio
async def test_delete_folder_refuses_while_a_staged_delete_is_pending(tmp_path: Path):
    target = _make_nested(tmp_path)
    batch = target / ".lm-pending-delete" / "batch1"
    batch.mkdir(parents=True)
    (batch / "manifest.json").write_text("{}", encoding="utf-8")
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is False
    assert result["code"] == "busy"
    assert target.exists()


@pytest.mark.asyncio
async def test_delete_folder_ignores_an_empty_staging_container(tmp_path: Path):
    """An empty `.lm-pending-delete` is a leftover, not a pending deletion.

    Every purge, undo and failed staging used to leave the container behind, and
    the name match alone made the folder undeletable for good: "A deletion is
    still pending inside this folder. Wait for the undo window to expire." with
    no window left to wait for (issue #1145 follow-up).
    """
    target = _make_nested(tmp_path)
    (target / ".lm-pending-delete").mkdir()
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is True
    assert not target.exists()


@pytest.mark.asyncio
async def test_delete_folder_refuses_over_a_quarantined_batch(tmp_path: Path):
    """Quarantine preserves the user's staged files, so it still blocks."""
    target = _make_nested(tmp_path)
    quarantined = target / ".lm-pending-delete" / "batch1.orphaned"
    quarantined.mkdir(parents=True)
    (quarantined / "model.safetensors").write_bytes(b"user-data")
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is False
    assert result["code"] == "busy"
    assert (quarantined / "model.safetensors").read_bytes() == b"user-data"


@pytest.mark.asyncio
async def test_delete_folder_refuses_the_library_root_itself(tmp_path: Path):
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(tmp_path))

    assert result["success"] is False
    assert "root" in result["error"].lower()
    assert tmp_path.exists()


@pytest.mark.asyncio
async def test_delete_folder_rejects_paths_outside_roots(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    scanner = FakeScanner([root])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(outside))

    assert result["success"] is False
    assert "error" in result
    assert outside.exists()
    assert scanner.removed_folders == []


@pytest.mark.asyncio
async def test_delete_folder_forgets_a_directory_that_is_already_gone(tmp_path: Path):
    """There is nothing to delete, but the sidebar node can still be cleared.

    A folder moved with a file manager leaves its records behind; answering
    "Folder no longer exists" left the ghost with no way out of the UI (#1145).
    """
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")
    gone = tmp_path / "gone"

    result = await service.delete_folder(str(gone))

    assert result["success"] is True
    assert result["code"] == "missing"
    assert result["already_missing"] is True
    assert result["folder"] == "gone"
    assert scanner.removed_folders == ["gone"]
    assert scanner.removed_folder_paths == [str(gone)]


@pytest.mark.asyncio
async def test_delete_folder_dry_run_still_reports_a_missing_directory(tmp_path: Path):
    """The probe stays a pure read — it is what makes the dialog offer the removal."""
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(tmp_path / "gone"), dry_run=True)

    assert result["success"] is False
    assert result["code"] == "missing"
    assert scanner.removed_folders == []


@pytest.mark.asyncio
async def test_forget_folder_drops_the_records_of_a_gone_directory(tmp_path: Path):
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.forget_folder("Krea2/Women")

    assert result["success"] is True
    assert result["folder"] == "Krea2/Women"
    # No absolute path: the same relative folder may exist under several roots,
    # and the scanner keeps an entry another root still holds.
    assert scanner.removed_folders == ["Krea2/Women"]
    assert scanner.removed_folder_paths == [None]


@pytest.mark.asyncio
async def test_forget_folder_refuses_while_the_directory_still_exists(tmp_path: Path):
    """Then the caller wants a delete, not a cleanup."""
    (tmp_path / "Krea2" / "Women").mkdir(parents=True)
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.forget_folder("Krea2/Women")

    assert result["success"] is False
    assert result["code"] == "exists"
    assert scanner.removed_folders == []


@pytest.mark.asyncio
async def test_forget_folder_requires_a_folder(tmp_path: Path):
    service = ModelMoveService(FakeScanner([tmp_path]), "lora")

    assert (await service.forget_folder(""))["success"] is False
    assert (await service.forget_folder("../outside"))["success"] is False


@pytest.mark.asyncio
async def test_delete_folder_requires_path(tmp_path: Path):
    service = ModelMoveService(FakeScanner([tmp_path]), "lora")

    result = await service.delete_folder("")

    assert result["success"] is False


@pytest.mark.asyncio
async def test_delete_folder_dry_run_reports_without_removing(tmp_path: Path):
    target = _make_nested(tmp_path)
    (target / "leftover.webp").write_text("preview", encoding="utf-8")
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target), dry_run=True)

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["file_count"] == 1
    assert target.exists()
    assert scanner.removed_folders == []


@pytest.mark.asyncio
async def test_delete_folder_refuses_symlinked_directory(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform guard
        pytest.skip("symlinks are not supported on this platform")

    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(link))

    assert result["success"] is False
    assert "symlink" in result["error"].lower()
    assert link.is_symlink()
    assert real.is_dir()


@pytest.mark.asyncio
async def test_delete_folder_counts_nested_symlinks_without_following_them(tmp_path: Path):
    target = _make_nested(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    (real / "model.safetensors").write_text("weights", encoding="utf-8")
    try:
        (target / "linked").symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform guard
        pytest.skip("symlinks are not supported on this platform")

    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is True
    assert result["symlink_count"] == 1
    # The linked model is not part of the subtree being deleted
    assert result["model_count"] == 0
    assert (real / "model.safetensors").exists()


@pytest.mark.asyncio
async def test_rename_folder_moves_directory_and_forwards_rekey(tmp_path: Path):
    target = _make_nested(tmp_path)
    (target / "model.safetensors").write_text("weights", encoding="utf-8")
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(target), "animation")

    renamed = tmp_path / "characters" / "animation"
    assert result["success"] is True
    assert result["renamed"] is True
    assert result["folder"] == "characters/animation"
    assert result["previous_folder"] == "characters/anime"
    assert renamed.is_dir()
    assert (renamed / "model.safetensors").exists()
    assert not target.exists()

    previous, current, kwargs = scanner.renamed_folders[0]
    assert previous == "characters/anime"
    assert current == "characters/animation"
    assert kwargs["previous_path"] == target.as_posix()
    assert kwargs["new_path"] == renamed.as_posix()


@pytest.mark.asyncio
async def test_rename_folder_noop_when_name_is_unchanged(tmp_path: Path):
    target = _make_nested(tmp_path)
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(target), "anime")

    assert result["success"] is True
    assert result["renamed"] is False
    assert target.is_dir()
    assert scanner.renamed_folders == []


@pytest.mark.asyncio
async def test_rename_folder_refuses_existing_target(tmp_path: Path):
    target = _make_nested(tmp_path)
    (tmp_path / "characters" / "animation").mkdir()
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(target), "animation")

    assert result["success"] is False
    assert result["code"] == "target_exists"
    assert target.is_dir()
    assert scanner.renamed_folders == []


@pytest.mark.parametrize("new_name", ["", "   ", "a/b", "..", ".", "bad:name", "back\\slash"])
@pytest.mark.asyncio
async def test_rename_folder_rejects_invalid_names(tmp_path: Path, new_name: str):
    target = _make_nested(tmp_path)
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(target), new_name)

    assert result["success"] is False
    assert target.is_dir()
    assert scanner.renamed_folders == []


@pytest.mark.asyncio
async def test_rename_folder_refuses_the_library_root_itself(tmp_path: Path):
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(tmp_path), "renamed-root")

    assert result["success"] is False
    assert "root" in result["error"].lower()
    assert tmp_path.is_dir()


@pytest.mark.asyncio
async def test_rename_folder_rejects_paths_outside_roots(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    scanner = FakeScanner([root])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(outside), "renamed")

    assert result["success"] is False
    assert outside.is_dir()
    assert scanner.renamed_folders == []


@pytest.mark.asyncio
async def test_rename_folder_reports_missing_directory(tmp_path: Path):
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(tmp_path / "gone"), "renamed")

    assert result["success"] is False
    assert "no longer exists" in result["error"]


@pytest.mark.asyncio
async def test_rename_folder_refuses_symlinked_directory(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform guard
        pytest.skip("symlinks are not supported on this platform")

    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(link), "renamed")

    assert result["success"] is False
    assert "symlink" in result["error"].lower()
    assert link.is_symlink()


@pytest.mark.asyncio
async def test_rename_folder_refuses_while_a_staged_delete_is_pending(tmp_path: Path):
    target = _make_nested(tmp_path)
    batch = target / ".lm-pending-delete" / "batch1"
    batch.mkdir(parents=True)
    (batch / "manifest.json").write_text("{}", encoding="utf-8")
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(target), "animation")

    assert result["success"] is False
    assert result["code"] == "busy"
    assert target.is_dir()
    assert scanner.renamed_folders == []


@pytest.mark.asyncio
async def test_rename_folder_ignores_an_empty_staging_container(tmp_path: Path):
    """The leftover container must not block a rename either."""
    target = _make_nested(tmp_path)
    (target / ".lm-pending-delete").mkdir()
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(target), "animation")

    assert result["success"] is True
    assert scanner.renamed_folders


@pytest.mark.asyncio
async def test_rename_folder_requires_path(tmp_path: Path):
    service = ModelMoveService(FakeScanner([tmp_path]), "lora")

    result = await service.rename_folder("", "renamed")

    assert result["success"] is False


@pytest.mark.asyncio
async def test_delete_folder_refuses_the_recipes_dir(tmp_path: Path, monkeypatch):
    """The default recipes dir lives in the first lora root and holds no model
    weight files, so the model_count check alone would let it be wiped."""
    from py.config import config

    monkeypatch.setattr(config, "loras_roots", [str(tmp_path)])
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    target = tmp_path / "recipes"
    target.mkdir()
    recipe_file = target / "abc123.recipe.json"
    recipe_file.write_text("{}", encoding="utf-8")

    result = await service.delete_folder(str(target))

    assert result["success"] is False
    assert result["code"] == "protected"
    assert recipe_file.exists()


@pytest.mark.asyncio
async def test_delete_folder_refuses_an_ancestor_of_the_recipes_dir(
    tmp_path: Path, monkeypatch
):
    """Deleting a parent of the recipes dir wipes the library just the same."""
    from py.services.settings_manager import get_settings_manager

    recipes_dir = tmp_path / "data" / "recipes"
    recipes_dir.mkdir(parents=True)
    manager = get_settings_manager()
    monkeypatch.setitem(manager.settings, "recipes_path", str(recipes_dir))

    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(tmp_path / "data"))

    assert result["success"] is False
    assert result["code"] == "protected"
    assert recipes_dir.is_dir()


@pytest.mark.asyncio
async def test_delete_folder_allows_normal_folders_next_to_the_recipes_dir(
    tmp_path: Path, monkeypatch
):
    from py.config import config

    monkeypatch.setattr(config, "loras_roots", [str(tmp_path)])
    (tmp_path / "recipes").mkdir()
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    target = tmp_path / "recipes_backup"
    target.mkdir()

    result = await service.delete_folder(str(target))

    assert result["success"] is True
    assert not target.exists()


@pytest.mark.asyncio
async def test_rename_folder_refuses_the_recipes_dir(tmp_path: Path, monkeypatch):
    from py.config import config

    monkeypatch.setattr(config, "loras_roots", [str(tmp_path)])
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    target = tmp_path / "recipes"
    target.mkdir()

    result = await service.rename_folder(str(target), "recipes2")

    assert result["success"] is False
    assert result["code"] == "protected"
    assert target.is_dir()
    assert scanner.renamed_folders == []


class AutoOrganizeScanner:
    """Minimal scanner stand-in for auto-organize path-budget tests."""

    def __init__(self, root: Path, models: List[dict]) -> None:
        self._root = str(root)
        from types import SimpleNamespace

        self._cache = SimpleNamespace(raw_data=models)
        self.moves: List[tuple] = []

    def get_model_roots(self) -> List[str]:
        return [self._root]

    def reset_cancellation(self) -> None:
        pass

    def is_cancelled(self) -> bool:
        return False

    async def get_cached_data(self):
        return self._cache

    async def move_model(self, file_path: str, target_dir: str) -> bool:
        self.moves.append((file_path, target_dir))
        return True


def _organize_setup(tmp_path: Path):
    from py.services.model_file_service import ModelFileService
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    templates = dict(manager.settings.get("download_path_templates") or {})
    templates["lora"] = "{base_model}"
    manager.settings["download_path_templates"] = templates

    model_path = tmp_path / "mymodel.safetensors"
    model_path.write_bytes(b"model")
    models = [
        {
            "file_path": model_path.as_posix(),
            "model_name": "mymodel",
            "base_model": "SDXL",
            "tags": [],
            "civitai": {"id": 1},
        }
    ]
    scanner = AutoOrganizeScanner(tmp_path, models)
    return ModelFileService(scanner, "lora"), scanner, model_path


@pytest.mark.asyncio
async def test_auto_organize_moves_model_within_path_budget(tmp_path: Path):
    service, scanner, model_path = _organize_setup(tmp_path)

    result = await service.auto_organize_models()

    assert result.success_count == 1
    assert scanner.moves == [
        (model_path.as_posix(), str(tmp_path / "SDXL").replace(os.sep, "/"))
    ]


@pytest.mark.asyncio
async def test_auto_organize_skips_model_when_target_path_exceeds_budget(
    tmp_path: Path, monkeypatch
):
    """Organize cannot trim names, so an over-long target is skipped (#1142)."""
    monkeypatch.setattr("py.utils.utils.MAX_FULL_PATH_LENGTH", 40)
    service, scanner, _model_path = _organize_setup(tmp_path)

    result = await service.auto_organize_models()

    assert result.skipped_count == 1
    assert scanner.moves == []
    assert "path length limit" in result.results[0]["message"]


@pytest.mark.asyncio
async def test_auto_organize_dry_run_reports_moves_without_moving(tmp_path: Path):
    """A dry run lists each planned move and leaves the files where they are."""
    service, scanner, model_path = _organize_setup(tmp_path)

    result = await service.auto_organize_models(dry_run=True)

    assert scanner.moves == []
    assert model_path.exists()
    assert result.success_count == 1
    payload = result.to_dict()
    assert payload["dry_run"] is True
    assert payload["summary"]["path_template"] == "{base_model}"
    assert payload["planned_moves"] == [
        {
            "model": "mymodel",
            "from": model_path.as_posix(),
            "to": (tmp_path / "SDXL" / "mymodel.safetensors").as_posix(),
            "status": "planned_move",
            "reason": "path_template",
        }
    ]
    assert "would move" in payload["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("template", ["{base_model}", ""])
async def test_auto_organize_dry_run_reports_already_organized_entries(
    tmp_path: Path, template: str
):
    service, scanner, model_path = _organize_setup(tmp_path)
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    templates = dict(manager.settings.get("download_path_templates") or {})
    templates["lora"] = template
    manager.settings["download_path_templates"] = templates
    if template:
        organized_path = tmp_path / "SDXL" / model_path.name
        organized_path.parent.mkdir()
        model_path.rename(organized_path)
        scanner._cache.raw_data[0]["file_path"] = organized_path.as_posix()
    else:
        organized_path = model_path

    result = await service.auto_organize_models(dry_run=True)

    assert result.success_count == 0
    assert result.skipped_count == 1
    assert result.failure_count == 0
    assert result.results == [
        {
            "model": "mymodel",
            "success": False,
            "status": "skipped",
            "message": "Already in the correct location",
            "reason": "already_organized",
            "from": organized_path.as_posix(),
            "to": organized_path.as_posix(),
        }
    ]


@pytest.mark.asyncio
async def test_auto_organize_dry_run_marks_flat_structure_move_reason(tmp_path: Path):
    service, scanner, model_path = _organize_setup(tmp_path)
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    templates = dict(manager.settings.get("download_path_templates") or {})
    templates["lora"] = ""
    manager.settings["download_path_templates"] = templates
    nested_path = tmp_path / "nested" / model_path.name
    nested_path.parent.mkdir()
    model_path.rename(nested_path)
    scanner._cache.raw_data[0]["file_path"] = nested_path.as_posix()

    result = await service.auto_organize_models(dry_run=True)

    assert result.planned_moves[0]["status"] == "planned_move"
    assert result.planned_moves[0]["reason"] == "flat_structure"
    assert result.to_dict()["summary"]["path_template"] == ""


@pytest.mark.asyncio
async def test_auto_organize_dry_run_flags_two_models_bound_for_one_path(
    tmp_path: Path,
):
    """A real run fails the second of two same-named models aimed at one
    folder; the dry run must report that instead of planning both moves."""
    service, scanner, model_path = _organize_setup(tmp_path)
    twin_dir = tmp_path / "other"
    twin_dir.mkdir()
    twin = twin_dir / "mymodel.safetensors"
    twin.write_bytes(b"model")
    scanner._cache.raw_data.append(
        {
            "file_path": twin.as_posix(),
            "model_name": "mymodel-twin",
            "base_model": "SDXL",
            "tags": [],
            "civitai": {"id": 2},
        }
    )

    result = await service.auto_organize_models(dry_run=True)

    assert scanner.moves == []
    assert result.success_count == 1
    assert result.failure_count == 1
    assert len(result.to_dict()["planned_moves"]) == 1
    assert "would collide" in result.results[0]["message"]


@pytest.mark.asyncio
async def test_auto_organize_dry_run_frees_target_vacated_by_earlier_move(
    tmp_path: Path,
):
    """A real run moves models in cache order, so a target freed by an
    earlier move is free; the dry run must not report a false conflict."""
    service, scanner, _model_path = _organize_setup(tmp_path)
    sdxl_dir = tmp_path / "SDXL"
    sdxl_dir.mkdir()
    occupant = sdxl_dir / "mymodel.safetensors"
    occupant.write_bytes(b"model")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    newcomer = other_dir / "mymodel.safetensors"
    newcomer.write_bytes(b"model")
    scanner._cache.raw_data[:] = [
        {
            "file_path": occupant.as_posix(),
            "model_name": "occupant",
            "base_model": "Flux.1 D",
            "tags": [],
            "civitai": {"id": 1},
        },
        {
            "file_path": newcomer.as_posix(),
            "model_name": "newcomer",
            "base_model": "SDXL",
            "tags": [],
            "civitai": {"id": 2},
        },
    ]

    result = await service.auto_organize_models(dry_run=True)

    assert scanner.moves == []
    assert result.failure_count == 0
    assert result.success_count == 2
    planned = result.to_dict()["planned_moves"]
    assert [move["model"] for move in planned] == ["occupant", "newcomer"]
    assert planned[1]["to"] == occupant.as_posix()


@pytest.mark.asyncio
async def test_auto_organize_dry_run_names_the_planned_collision(tmp_path: Path):
    """When the target is only claimed by a planned move (not on disk yet),
    the message says so instead of claiming the file already exists."""
    service, scanner, _model_path = _organize_setup(tmp_path)
    twin_dir = tmp_path / "other"
    twin_dir.mkdir()
    twin = twin_dir / "mymodel.safetensors"
    twin.write_bytes(b"model")
    scanner._cache.raw_data.append(
        {
            "file_path": twin.as_posix(),
            "model_name": "mymodel-twin",
            "base_model": "SDXL",
            "tags": [],
            "civitai": {"id": 2},
        }
    )

    result = await service.auto_organize_models(dry_run=True)

    message = result.results[0]["message"]
    assert "planned move of mymodel" in message
    assert "already exists" not in message


@pytest.mark.asyncio
async def test_auto_organize_dry_run_collides_targets_case_insensitively(
    tmp_path: Path, monkeypatch
):
    """On a case-insensitive filesystem Foo.st and foo.st are one file."""
    service, scanner, model_path = _organize_setup(tmp_path)
    twin_dir = tmp_path / "other"
    twin_dir.mkdir()
    twin = twin_dir / "MyModel.safetensors"
    twin.write_bytes(b"model")
    scanner._cache.raw_data.append(
        {
            "file_path": twin.as_posix(),
            "model_name": "twin",
            "base_model": "SDXL",
            "tags": [],
            "civitai": {"id": 2},
        }
    )
    monkeypatch.setattr(os.path, "normcase", lambda path: path.lower())

    result = await service.auto_organize_models(dry_run=True)

    assert result.success_count == 1
    assert result.failure_count == 1


@pytest.mark.asyncio
async def test_auto_organize_dry_run_honours_file_paths(tmp_path: Path):
    service, scanner, model_path = _organize_setup(tmp_path)
    other = tmp_path / "other.safetensors"
    other.write_bytes(b"model")
    scanner._cache.raw_data.append(
        {
            "file_path": other.as_posix(),
            "model_name": "other",
            "base_model": "SDXL",
            "tags": [],
            "civitai": {"id": 2},
        }
    )

    result = await service.auto_organize_models(
        file_paths=[other.as_posix()], dry_run=True
    )

    assert result.operation_type == "bulk"
    assert result.total == 1
    assert [m["model"] for m in result.to_dict()["planned_moves"]] == ["other"]


@pytest.mark.asyncio
async def test_auto_organize_dry_run_does_not_pace_batches(
    tmp_path: Path, monkeypatch
):
    """A dry run does no I/O, so the inter-batch pacing sleep is skipped."""
    import py.services.model_file_service as module

    service, scanner, _model_path = _organize_setup(tmp_path)
    scanner._cache.raw_data[:] = [
        {
            "file_path": (tmp_path / f"m{i}.safetensors").as_posix(),
            "model_name": f"m{i}",
            "base_model": "",
            "tags": [],
            "civitai": {},
        }
        for i in range(120)
    ]
    delays: List[float] = []
    real_sleep = asyncio.sleep

    async def recording_sleep(delay, *args, **kwargs):
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(module.asyncio, "sleep", recording_sleep)

    await service.auto_organize_models(dry_run=True)

    assert delays and all(delay == 0 for delay in delays)


@pytest.mark.asyncio
async def test_auto_organize_dry_run_skips_empty_folder_cleanup(
    tmp_path: Path, monkeypatch
):
    service, _scanner, _model_path = _organize_setup(tmp_path)
    (tmp_path / "empty").mkdir()

    result = await service.auto_organize_models(dry_run=True)

    assert (tmp_path / "empty").is_dir()
    assert result.cleanup_counts == {}


@pytest.mark.asyncio
async def test_auto_organize_dry_run_keeps_every_result(tmp_path: Path):
    """A real run trims per-model results after 100; a dry run is the report,
    so a would-be failure must not be hidden behind a pile of skips."""
    service, scanner, _model_path = _organize_setup(tmp_path)
    scanner._cache.raw_data[:] = [
        {
            "file_path": (tmp_path / f"m{i}.safetensors").as_posix(),
            "model_name": f"m{i}",
            "base_model": "",
            "tags": [],
            "civitai": {},
        }
        for i in range(150)
    ]

    result = await service.auto_organize_models(dry_run=True)
    payload = result.to_dict()

    assert result.skipped_count == 150
    assert "results_truncated" not in payload
    assert len(payload["results"]) == 150


@pytest.mark.asyncio
async def test_auto_organize_results_carry_reason_codes(tmp_path: Path):
    """Skips and failures expose a stable code, so a preview UI can group them
    without string-matching the human-readable message."""
    from py.services.model_file_service import (
        REASON_MISSING_METADATA,
        REASON_PLANNED_COLLISION,
        REASON_TARGET_EXISTS,
    )

    service, scanner, model_path = _organize_setup(tmp_path)
    twin_dir = tmp_path / "other"
    twin_dir.mkdir()
    (twin_dir / "mymodel.safetensors").write_bytes(b"model")
    metadata_less = tmp_path / "nometa.safetensors"
    metadata_less.write_bytes(b"model")
    blocked = tmp_path / "taken.safetensors"
    blocked.write_bytes(b"model")
    # A stray file occupies the target without being a cache model, so nothing
    # in this run would move it away: the target really is taken.
    blocked_dir = tmp_path / "SD1.5"
    blocked_dir.mkdir()
    (blocked_dir / "taken.safetensors").write_bytes(b"model")
    scanner._cache.raw_data[:] = [
        {
            "file_path": model_path.as_posix(),
            "model_name": "mymodel",
            "base_model": "SDXL",
            "tags": [],
            "civitai": {"id": 1},
        },
        {
            "file_path": (twin_dir / "mymodel.safetensors").as_posix(),
            "model_name": "twin",
            "base_model": "SDXL",
            "tags": [],
            "civitai": {"id": 2},
        },
        {
            "file_path": metadata_less.as_posix(),
            "model_name": "nometa",
            "base_model": "",
            "tags": [],
            "civitai": {},
        },
        {
            "file_path": blocked.as_posix(),
            "model_name": "taken",
            "base_model": "SD1.5",
            "tags": [],
            "civitai": {"id": 3},
        },
    ]

    result = await service.auto_organize_models(dry_run=True)

    reasons = {entry["model"]: entry["reason"] for entry in result.results}
    statuses = {entry["model"]: entry["status"] for entry in result.results}
    assert reasons["twin"] == REASON_PLANNED_COLLISION
    assert reasons["nometa"] == REASON_MISSING_METADATA
    assert reasons["taken"] == REASON_TARGET_EXISTS
    assert statuses == {
        "twin": "issue",
        "nometa": "skipped",
        "taken": "issue",
    }
    assert all(entry["success"] is False for entry in result.results)


@pytest.mark.asyncio
async def test_auto_organize_real_run_results_carry_reason_codes(tmp_path: Path):
    from py.services.model_file_service import REASON_MOVE_FAILED

    service, scanner, _model_path = _organize_setup(tmp_path)

    async def failing_move(file_path: str, target_dir: str) -> bool:
        return False

    scanner.move_model = failing_move  # type: ignore[method-assign]

    result = await service.auto_organize_models()

    assert result.failure_count == 1
    assert result.results[0]["reason"] == REASON_MOVE_FAILED


def _workflow_organize_setup(
    tmp_path: Path, *, template: str | None = None
) -> tuple:
    """Build a workflow ModelFileService over a fake scanner.

    ``template=None`` leaves the workflow entry out of the settings so the
    default in DEFAULT_DOWNLOAD_PATH_TEMPLATES applies; pass a string to pin
    the template.
    """
    from py.services.model_file_service import ModelFileService
    from py.services.settings_manager import get_settings_manager

    manager = get_settings_manager()
    templates = dict(manager.settings.get("download_path_templates") or {})
    if template is None:
        templates.pop("workflow", None)
    else:
        templates["workflow"] = template
    manager.settings["download_path_templates"] = templates

    nested_dir = tmp_path / "old"
    nested_dir.mkdir()
    workflow_path = nested_dir / "portrait.workflow.json"
    workflow_path.write_text("{}", encoding="utf-8")
    models = [
        {
            "file_path": workflow_path.as_posix(),
            "model_name": "portrait",
            "file_name": "portrait",
            "base_model": "SDXL 1.0",
            "tags": [],
            "civitai": {},
        }
    ]
    scanner = AutoOrganizeScanner(tmp_path, models)
    return ModelFileService(scanner, "workflow"), scanner, workflow_path


@pytest.mark.asyncio
async def test_auto_organize_workflows_uses_the_workflow_template(tmp_path: Path):
    """Auto-Organize on the Workflows page routes by the workflow template."""
    service, scanner, workflow_path = _workflow_organize_setup(tmp_path)

    result = await service.auto_organize_models(
        file_paths=[workflow_path.as_posix()]
    )

    assert result.operation_type == "bulk"
    assert result.success_count == 1
    assert scanner.moves == [
        (
            workflow_path.as_posix(),
            str(tmp_path / "SDXL 1.0").replace(os.sep, "/"),
        )
    ]


@pytest.mark.asyncio
async def test_auto_organize_workflows_flattens_when_template_is_empty(
    tmp_path: Path,
):
    """An empty workflow template keeps the historical flat layout: selected
    files are moved back to the workflow root, not into a tag folder."""
    service, scanner, workflow_path = _workflow_organize_setup(
        tmp_path, template=""
    )

    result = await service.auto_organize_models(
        file_paths=[workflow_path.as_posix()]
    )

    assert result.success_count == 1
    assert scanner.moves == [
        (workflow_path.as_posix(), str(tmp_path).replace(os.sep, "/"))
    ]
