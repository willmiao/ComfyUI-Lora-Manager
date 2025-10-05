import logging
from typing import Dict, Iterable, List

import pytest

from py import config as config_module
from py.services import settings_manager as settings_manager_module


def _setup_config_environment(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Dict[str, List[str]]:
    loras_dir = tmp_path / "loras"
    checkpoints_dir = tmp_path / "checkpoints"
    embeddings_dir = tmp_path / "embeddings"

    for directory in (loras_dir, checkpoints_dir, embeddings_dir):
        directory.mkdir()

    folder_paths: Dict[str, List[str]] = {
        "loras": [str(loras_dir)],
        "checkpoints": [str(checkpoints_dir)],
        "unet": [],
        "embeddings": [str(embeddings_dir)],
    }

    def fake_get_folder_paths(kind: str) -> Iterable[str]:
        return folder_paths.get(kind, [])

    monkeypatch.setattr(config_module.folder_paths, "get_folder_paths", fake_get_folder_paths)
    monkeypatch.setattr(config_module, "standalone_mode", False)
    monkeypatch.setattr(
        config_module,
        "ensure_settings_file",
        lambda logger=None: str(tmp_path / "settings.json"),
    )

    return folder_paths


def test_save_paths_renames_default_library(monkeypatch: pytest.MonkeyPatch, tmp_path):
    folder_paths = _setup_config_environment(monkeypatch, tmp_path)

    class FakeSettingsService:
        def __init__(self, default_paths: Dict[str, List[str]]):
            self._default_paths = default_paths
            self.rename_calls = []
            self.upsert_calls = []
            self._renamed = False

        def get_libraries(self):
            if self._renamed:
                return {"comfyui": {}}
            return {
                "default": {
                    "folder_paths": {key: list(value) for key, value in self._default_paths.items()},
                    "default_lora_root": "",
                    "default_checkpoint_root": "",
                    "default_embedding_root": "",
                }
            }

        def rename_library(self, old_name: str, new_name: str):
            self.rename_calls.append((old_name, new_name))
            self._renamed = True

        def upsert_library(self, name: str, **payload):
            self.upsert_calls.append((name, payload))

    fake_settings = FakeSettingsService(folder_paths)
    monkeypatch.setattr(settings_manager_module, "settings", fake_settings)

    config_instance = config_module.Config()

    assert isinstance(config_instance, config_module.Config)
    assert fake_settings.rename_calls == [("default", "comfyui")]
    assert len(fake_settings.upsert_calls) == 1

    name, payload = fake_settings.upsert_calls[0]
    assert name == "comfyui"
    
    # The Config class normalizes paths to use forward slashes for cross-platform compatibility
    # Convert expected paths to the same format for comparison
    expected_folder_paths = {
        key: [path.replace("\\", "/") for path in paths]
        for key, paths in folder_paths.items()
    }
    assert payload["folder_paths"] == expected_folder_paths
    assert payload["default_lora_root"] == folder_paths["loras"][0].replace("\\", "/")
    assert payload["default_checkpoint_root"] == folder_paths["checkpoints"][0].replace("\\", "/")
    assert payload["default_embedding_root"] == folder_paths["embeddings"][0].replace("\\", "/")
    assert payload["metadata"] == {"display_name": "ComfyUI", "source": "comfyui"}
    assert payload["activate"] is True


def test_save_paths_logs_warning_when_upsert_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
):
    folder_paths = _setup_config_environment(monkeypatch, tmp_path)

    class RaisingSettingsService:
        def __init__(self):
            self.upsert_attempts = []

        def get_libraries(self):
            return {
                "comfyui": {
                    "folder_paths": {key: list(value) for key, value in folder_paths.items()},
                    "default_lora_root": "existing",
                }
            }

        def rename_library(self, *_):
            raise AssertionError("rename_library should not be invoked")

        def upsert_library(self, name: str, **payload):
            self.upsert_attempts.append((name, payload))
            raise RuntimeError("boom")

    fake_settings = RaisingSettingsService()
    monkeypatch.setattr(settings_manager_module, "settings", fake_settings)

    with caplog.at_level(logging.WARNING, logger=config_module.logger.name):
        config_instance = config_module.Config()

    assert isinstance(config_instance, config_module.Config)
    assert fake_settings.upsert_attempts and fake_settings.upsert_attempts[0][0] == "comfyui"
    assert "Failed to save folder paths: boom" in caplog.text
