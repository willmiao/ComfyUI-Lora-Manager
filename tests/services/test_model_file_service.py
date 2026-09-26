"""Tests for ModelMoveService folder creation."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from py.services.model_file_service import ModelMoveService


class FakeScanner:
    def __init__(self, roots: List[Path], excluded: List[str] | None = None) -> None:
        self._roots = [str(root) for root in roots]
        self.known_folders: List[str] = []
        self.removed_folders: List[str] = []
        self.renamed_folders: List[tuple] = []
        self._excluded = list(excluded or [])

    def get_model_roots(self) -> List[str]:
        return list(self._roots)

    def get_excluded_models(self) -> List[str]:
        return list(self._excluded)

    async def add_known_folder(self, folder: str) -> None:
        self.known_folders.append(folder)

    async def remove_known_folder(self, folder: str) -> None:
        self.removed_folders.append(folder)

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
    (target / ".lm-pending-delete").mkdir()
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(target))

    assert result["success"] is False
    assert result["code"] == "busy"
    assert target.exists()


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
async def test_delete_folder_reports_missing_directory(tmp_path: Path):
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.delete_folder(str(tmp_path / "gone"))

    assert result["success"] is False
    assert "no longer exists" in result["error"]


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
    (target / ".lm-pending-delete").mkdir()
    scanner = FakeScanner([tmp_path])
    service = ModelMoveService(scanner, "lora")

    result = await service.rename_folder(str(target), "animation")

    assert result["success"] is False
    assert result["code"] == "busy"
    assert target.is_dir()
    assert scanner.renamed_folders == []


@pytest.mark.asyncio
async def test_rename_folder_requires_path(tmp_path: Path):
    service = ModelMoveService(FakeScanner([tmp_path]), "lora")

    result = await service.rename_folder("", "renamed")

    assert result["success"] is False
