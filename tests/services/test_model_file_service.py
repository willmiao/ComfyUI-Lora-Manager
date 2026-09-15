"""Tests for ModelMoveService folder creation."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from py.services.model_file_service import ModelMoveService


class FakeScanner:
    def __init__(self, roots: List[Path]) -> None:
        self._roots = [str(root) for root in roots]
        self.known_folders: List[str] = []

    def get_model_roots(self) -> List[str]:
        return list(self._roots)

    async def add_known_folder(self, folder: str) -> None:
        self.known_folders.append(folder)


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
