import json
import os

import pytest

from py import config as config_module


def _normalize(path: str) -> str:
    return os.path.normpath(path).replace(os.sep, "/")


def _setup_paths(monkeypatch: pytest.MonkeyPatch, tmp_path):
    settings_dir = tmp_path / "settings"
    loras_dir = tmp_path / "loras"
    loras_dir.mkdir()
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    embedding_dir = tmp_path / "embeddings"
    embedding_dir.mkdir()

    def fake_get_folder_paths(kind: str):
        mapping = {
            "loras": [str(loras_dir)],
            "checkpoints": [str(checkpoint_dir)],
            "unet": [],
            "embeddings": [str(embedding_dir)],
        }
        return mapping.get(kind, [])

    monkeypatch.setattr(config_module.folder_paths, "get_folder_paths", fake_get_folder_paths)
    monkeypatch.setattr(config_module, "standalone_mode", True)
    monkeypatch.setattr(config_module, "get_settings_dir", lambda create=True: str(settings_dir))

    return loras_dir, settings_dir


def test_symlink_scan_skips_file_links(monkeypatch: pytest.MonkeyPatch, tmp_path):
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)

    target_dir = loras_dir / "target"
    target_dir.mkdir()
    dir_link = loras_dir / "dir_link"
    dir_link.symlink_to(target_dir, target_is_directory=True)

    file_target = loras_dir / "model.safetensors"
    file_target.write_text("content", encoding="utf-8")
    file_link = loras_dir / "file_link"
    file_link.symlink_to(file_target)

    cfg = config_module.Config()

    normalized_target_dir = _normalize(os.path.realpath(target_dir))
    normalized_link_dir = _normalize(str(dir_link))
    assert cfg._path_mappings[normalized_target_dir] == normalized_link_dir

    normalized_file_real = _normalize(os.path.realpath(file_target))
    assert normalized_file_real not in cfg._path_mappings

    cache_path = settings_dir / "cache" / "symlink_map.json"
    assert cache_path.exists()


def test_symlink_cache_reuses_previous_scan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)

    target_dir = loras_dir / "target"
    target_dir.mkdir()
    dir_link = loras_dir / "dir_link"
    dir_link.symlink_to(target_dir, target_is_directory=True)

    first_cfg = config_module.Config()
    cached_mappings = dict(first_cfg._path_mappings)
    cache_path = settings_dir / "cache" / "symlink_map.json"
    assert cache_path.exists()

    def fail_scan(self):
        raise AssertionError("Cache should bypass directory scan")

    monkeypatch.setattr(config_module.Config, "_scan_symbolic_links", fail_scan)

    second_cfg = config_module.Config()
    assert second_cfg._path_mappings == cached_mappings
    assert second_cfg.map_path_to_link(str(target_dir)) == _normalize(str(dir_link))


def test_symlink_cache_survives_noise_mtime(monkeypatch: pytest.MonkeyPatch, tmp_path):
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)

    target_dir = loras_dir / "target"
    target_dir.mkdir()
    dir_link = loras_dir / "dir_link"
    dir_link.symlink_to(target_dir, target_is_directory=True)

    recipes_dir = loras_dir / "recipes"
    recipes_dir.mkdir()
    noise_file = recipes_dir / "touchme.txt"

    first_cfg = config_module.Config()
    cache_path = settings_dir / "cache" / "symlink_map.json"
    assert cache_path.exists()

    # Update a noisy path to bump parent directory mtime
    noise_file.write_text("hi", encoding="utf-8")

    def fail_scan(self):
        raise AssertionError("Cache should bypass directory scan despite noise mtime")

    monkeypatch.setattr(config_module.Config, "_scan_symbolic_links", fail_scan)

    second_cfg = config_module.Config()
    assert second_cfg.map_path_to_link(str(target_dir)) == _normalize(str(dir_link))


def test_retargeted_symlink_triggers_rescan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Changing a symlink's target should trigger automatic cache invalidation."""
    loras_dir, _ = _setup_paths(monkeypatch, tmp_path)

    target_dir = loras_dir / "target"
    target_dir.mkdir()
    dir_link = loras_dir / "dir_link"
    dir_link.symlink_to(target_dir, target_is_directory=True)

    # Build initial cache pointing at the first target
    first_cfg = config_module.Config()
    assert first_cfg.map_path_to_link(str(target_dir)) == _normalize(str(dir_link))

    # Retarget the symlink to a new directory
    new_target = loras_dir / "target_v2"
    new_target.mkdir()
    dir_link.unlink()
    dir_link.symlink_to(new_target, target_is_directory=True)

    # Second config should automatically detect the change and rescan
    second_cfg = config_module.Config()
    new_real = _normalize(os.path.realpath(new_target))
    assert second_cfg._path_mappings.get(new_real) == _normalize(str(dir_link))
    assert second_cfg.map_path_to_link(str(new_target)) == _normalize(str(dir_link))


def test_symlink_roots_are_preserved(monkeypatch: pytest.MonkeyPatch, tmp_path):
    settings_dir = tmp_path / "settings"
    real_loras = tmp_path / "loras_real"
    real_loras.mkdir()
    loras_link = tmp_path / "loras_link"
    loras_link.symlink_to(real_loras, target_is_directory=True)

    checkpoints_dir = tmp_path / "checkpoints"
    checkpoints_dir.mkdir()
    embedding_dir = tmp_path / "embeddings"
    embedding_dir.mkdir()

    def fake_get_folder_paths(kind: str):
        mapping = {
            "loras": [str(loras_link)],
            "checkpoints": [str(checkpoints_dir)],
            "unet": [],
            "embeddings": [str(embedding_dir)],
        }
        return mapping.get(kind, [])

    monkeypatch.setattr(config_module.folder_paths, "get_folder_paths", fake_get_folder_paths)
    monkeypatch.setattr(config_module, "standalone_mode", True)
    monkeypatch.setattr(config_module, "get_settings_dir", lambda create=True: str(settings_dir))

    cfg = config_module.Config()

    normalized_real = _normalize(os.path.realpath(real_loras))
    normalized_link = _normalize(str(loras_link))
    assert cfg._path_mappings[normalized_real] == normalized_link

    cache_path = settings_dir / "cache" / "symlink_map.json"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["path_mappings"][normalized_real] == normalized_link


def test_symlink_subfolder_to_external_location(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Symlink under root pointing outside root should be detected and allowed."""
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)

    # Create external directory (outside loras_dir)
    external_dir = tmp_path / "external_models"
    external_dir.mkdir()
    preview_file = external_dir / "model.preview.png"
    preview_file.write_bytes(b"preview")

    # Create symlink under loras_dir pointing to external location
    symlink = loras_dir / "characters"
    symlink.symlink_to(external_dir, target_is_directory=True)

    cfg = config_module.Config()

    # Verify symlink was detected
    normalized_external = _normalize(str(external_dir))
    normalized_link = _normalize(str(symlink))
    assert cfg._path_mappings[normalized_external] == normalized_link

    # Verify preview path is allowed
    assert cfg.is_preview_path_allowed(str(preview_file))


def test_new_symlink_triggers_rescan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Adding a new symlink should trigger cache invalidation."""
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)

    # Initial scan with no symlinks
    first_cfg = config_module.Config()
    assert len(first_cfg._path_mappings) == 0

    # Create a symlink after initial cache
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    symlink = loras_dir / "new_link"
    symlink.symlink_to(external_dir, target_is_directory=True)

    # Second config should detect the change and rescan
    second_cfg = config_module.Config()
    normalized_external = _normalize(str(external_dir))
    assert normalized_external in second_cfg._path_mappings


def test_removed_deep_symlink_triggers_rescan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Removing a deep symlink should trigger cache invalidation."""
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)

    # Create nested structure with deep symlink
    subdir = loras_dir / "anime"
    subdir.mkdir()
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    deep_symlink = subdir / "styles"
    deep_symlink.symlink_to(external_dir, target_is_directory=True)

    # Initial scan finds the deep symlink
    first_cfg = config_module.Config()
    normalized_external = _normalize(str(external_dir))
    assert normalized_external in first_cfg._path_mappings

    # Remove the deep symlink
    deep_symlink.unlink()

    # Second config should detect invalid cached mapping and rescan
    second_cfg = config_module.Config()
    assert normalized_external not in second_cfg._path_mappings


def test_retargeted_deep_symlink_triggers_rescan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Changing a deep symlink's target should trigger cache invalidation."""
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)

    # Create nested structure
    subdir = loras_dir / "anime"
    subdir.mkdir()
    target_v1 = tmp_path / "external_v1"
    target_v1.mkdir()
    target_v2 = tmp_path / "external_v2"
    target_v2.mkdir()

    deep_symlink = subdir / "styles"
    deep_symlink.symlink_to(target_v1, target_is_directory=True)

    # Initial scan
    first_cfg = config_module.Config()
    assert _normalize(str(target_v1)) in first_cfg._path_mappings

    # Retarget the symlink
    deep_symlink.unlink()
    deep_symlink.symlink_to(target_v2, target_is_directory=True)

    # Second config should detect changed target and rescan
    second_cfg = config_module.Config()
    assert _normalize(str(target_v2)) in second_cfg._path_mappings
    assert _normalize(str(target_v1)) not in second_cfg._path_mappings
