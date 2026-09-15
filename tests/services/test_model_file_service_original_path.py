from types import SimpleNamespace

import pytest

from py.services.model_file_service import ModelFileService, ModelMoveService
from py.services.settings_manager import SettingsManager, get_settings_manager


class _Scanner:
    def __init__(self, roots, models):
        self._roots = [str(root) for root in roots]
        self._cache = SimpleNamespace(raw_data=models)
        self.target_path = None

    def get_model_roots(self):
        return self._roots

    async def get_cached_data(self):
        return self._cache

    async def move_model(self, source_path, target_path):
        self.target_path = target_path
        return {
            "new_path": f"{target_path}/model.safetensors",
            "cache_entry": {},
        }


@pytest.fixture
def original_path_settings(monkeypatch):
    manager = get_settings_manager()
    settings = manager._get_default_settings()
    settings["download_path_templates"]["lora"] = (
        "{base_model}/{original_path}"
    )
    monkeypatch.setattr(manager, "settings", settings)
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)


@pytest.mark.asyncio
async def test_auto_organize_preserves_folder_below_source_root(
    original_path_settings, tmp_path
):
    source_root = tmp_path / "source"
    model = {
        "file_path": str(
            source_root / "People" / "Portraits" / "model.safetensors"
        ),
        "base_model": "SDXL",
        "tags": [],
    }
    scanner = _Scanner([source_root], [model])
    service = ModelFileService(scanner, "lora")

    target = await service._calculate_target_directory(
        model, str(source_root), is_flat_structure=False
    )

    assert target.replace("\\", "/").endswith("source/SDXL/People/Portraits")


@pytest.mark.asyncio
async def test_default_path_move_preserves_folder_across_roots(
    original_path_settings, tmp_path
):
    source_root = tmp_path / "source"
    target_root = tmp_path / "archive"
    source_path = str(
        source_root / "People" / "Portraits" / "model.safetensors"
    )
    model = {
        "file_path": source_path,
        "base_model": "SDXL",
        "tags": [],
    }
    scanner = _Scanner([source_root, target_root], [model])
    service = ModelMoveService(scanner, "lora")

    result = await service.move_model(
        source_path, str(target_root), use_default_paths=True
    )

    assert result["success"] is True
    assert scanner.target_path.replace("\\", "/").endswith(
        "archive/SDXL/People/Portraits"
    )
