from __future__ import annotations

from pathlib import Path

import pytest

from py.services.example_images_cleanup_service import ExampleImagesCleanupService
from py.services.service_registry import ServiceRegistry
from py.services.settings_manager import get_settings_manager


class StubScanner:
    def __init__(self, valid_hashes: set[str] | None = None) -> None:
        self._valid_hashes = valid_hashes or set()

    def has_hash(self, value: str) -> bool:
        return value in self._valid_hashes


@pytest.mark.asyncio
async def test_cleanup_moves_empty_and_orphaned(tmp_path, monkeypatch):
    service = ExampleImagesCleanupService()

    settings_manager = get_settings_manager()
    previous_path = settings_manager.get('example_images_path')
    settings_manager.settings['example_images_path'] = str(tmp_path)

    try:
        empty_folder = tmp_path / 'empty_folder'
        empty_folder.mkdir()

        orphan_hash = 'a' * 64
        orphan_folder = tmp_path / orphan_hash
        orphan_folder.mkdir()
        (orphan_folder / 'image.png').write_text('data', encoding='utf-8')

        valid_hash = 'b' * 64
        valid_folder = tmp_path / valid_hash
        valid_folder.mkdir()
        (valid_folder / 'image.png').write_text('data', encoding='utf-8')

        matching_scanner = StubScanner({valid_hash})
        empty_scanner = StubScanner()

        async def get_matching_scanner(*_args, **_kwargs):
            return matching_scanner

        async def get_empty_scanner(*_args, **_kwargs):
            return empty_scanner

        monkeypatch.setattr(ServiceRegistry, 'get_lora_scanner', get_matching_scanner)
        monkeypatch.setattr(ServiceRegistry, 'get_checkpoint_scanner', get_empty_scanner)
        monkeypatch.setattr(ServiceRegistry, 'get_embedding_scanner', get_empty_scanner)

        result = await service.cleanup_example_image_folders()

        deleted_bucket = Path(result['deleted_root'])
        assert result['success'] is True
        assert result['moved_total'] == 2
        assert not empty_folder.exists()
        assert not (deleted_bucket / 'empty_folder').exists()
        assert (deleted_bucket / orphan_hash).exists()
        assert not orphan_folder.exists()
        assert valid_folder.exists()

    finally:
        if previous_path is None:
            settings_manager.settings.pop('example_images_path', None)
        else:
            settings_manager.settings['example_images_path'] = previous_path


@pytest.mark.asyncio
async def test_cleanup_handles_missing_path(monkeypatch):
    service = ExampleImagesCleanupService()

    settings_manager = get_settings_manager()
    previous_path = settings_manager.get('example_images_path')
    settings_manager.settings.pop('example_images_path', None)

    try:
        result = await service.cleanup_example_image_folders()
    finally:
        if previous_path is not None:
            settings_manager.settings['example_images_path'] = previous_path

    assert result['success'] is False
    assert result['error_code'] == 'path_not_configured'
