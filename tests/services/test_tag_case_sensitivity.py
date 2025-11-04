"""Tests for tag case sensitivity handling to prevent issues on Windows."""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from py.services.tag_update_service import TagUpdateService


class RecordingMetadataManager:
    def __init__(self) -> None:
        self.saved: list[tuple[str, Dict[str, Any]]] = []

    async def save_metadata(self, path: str, metadata: Dict[str, Any]) -> bool:
        self.saved.append((path, json.loads(json.dumps(metadata))))
        return True


class DummyProvider:
    async def __call__(self, path: str) -> Dict[str, Any]:
        return {"tags": []}


@pytest.mark.asyncio
async def test_tag_update_service_handles_case_insensitive_tags(tmp_path: Path) -> None:
    """Test that tag update service treats tags case-insensitively."""
    metadata_path = tmp_path / "model.metadata.json"
    metadata_path.write_text(json.dumps({"tags": ["test"]}))

    async def loader(path: str) -> Dict[str, Any]:
        return json.loads(Path(path).read_text())

    manager = RecordingMetadataManager()
    service = TagUpdateService(metadata_manager=manager)

    cache_updates: list[Dict[str, Any]] = []

    async def update_cache(original: str, new: str, metadata: Dict[str, Any]) -> bool:
        cache_updates.append(metadata)
        return True

    # Try to add "Test" (different case) - should not be added since "test" already exists
    tags = await service.add_tags(
        file_path=str(tmp_path / "model.safetensors"),
        new_tags=["Test"],
        metadata_loader=loader,
        update_cache=update_cache,
    )

    # Should still only have "test" (lowercase) in the tags
    assert tags == ["test"]
    assert len(manager.saved) == 1
    saved_metadata = manager.saved[0][1]
    assert saved_metadata["tags"] == ["test"]


@pytest.mark.asyncio
async def test_tag_update_service_adds_new_tags_in_lowercase(tmp_path: Path) -> None:
    """Test that new tags are stored in lowercase."""
    metadata_path = tmp_path / "model.metadata.json"
    metadata_path.write_text(json.dumps({"tags": ["existing"]}))

    async def loader(path: str) -> Dict[str, Any]:
        return json.loads(Path(path).read_text())

    manager = RecordingMetadataManager()
    service = TagUpdateService(metadata_manager=manager)

    cache_updates: list[Dict[str, Any]] = []

    async def update_cache(original: str, new: str, metadata: Dict[str, Any]) -> bool:
        cache_updates.append(metadata)
        return True

    # Add new tags with mixed case
    tags = await service.add_tags(
        file_path=str(tmp_path / "model.safetensors"),
        new_tags=["NewTag", "ANOTHER_TAG"],
        metadata_loader=loader,
        update_cache=update_cache,
    )

    # New tags should be stored in lowercase
    assert "existing" in tags
    assert "newtag" in tags
    assert "another_tag" in tags
    assert len(manager.saved) == 1
    saved_metadata = manager.saved[0][1]
    assert "newtag" in saved_metadata["tags"]
    assert "another_tag" in saved_metadata["tags"]
    # Ensure all tags are lowercase
    for tag in saved_metadata["tags"]:
        assert tag == tag.lower()