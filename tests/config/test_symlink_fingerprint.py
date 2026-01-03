import os
import pytest
from py import config as config_module

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

def test_fingerprint_match_skips_rescan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)
    
    # Track calls to _scan_symbolic_links
    scan_calls = 0
    original_scan = config_module.Config._scan_symbolic_links
    
    def wrapped_scan(self):
        nonlocal scan_calls
        scan_calls += 1
        return original_scan(self)
    
    monkeypatch.setattr(config_module.Config, "_scan_symbolic_links", wrapped_scan)
    
    # 1. First initialization: should scan and cache
    cfg1 = config_module.Config()
    assert scan_calls == 1
    
    # 2. Second initialization: should load from cache and skip rescan because fingerprint matches
    cfg2 = config_module.Config()
    # scan_calls should still be 1 because it loaded from cache and skipped the rescan
    assert scan_calls == 1

def test_mtime_change_does_not_trigger_rescan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)
    
    # Track calls to _scan_symbolic_links
    scan_calls = 0
    original_scan = config_module.Config._scan_symbolic_links
    
    def wrapped_scan(self):
        nonlocal scan_calls
        scan_calls += 1
        return original_scan(self)
    
    monkeypatch.setattr(config_module.Config, "_scan_symbolic_links", wrapped_scan)
    
    # 1. First initialization: should scan and cache
    cfg1 = config_module.Config()
    assert scan_calls == 1
    
    # 2. Modify a root directory (change mtime) - this should NOT trigger a rescan anymore
    os.utime(loras_dir, (os.path.getatime(loras_dir), os.path.getmtime(loras_dir) + 100))
    
    # 3. Third initialization: should load from cache and skip rescan despite mtime change
    cfg3 = config_module.Config()
    assert scan_calls == 1

def test_root_path_change_triggers_rescan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)
    
    # Track calls to _scan_symbolic_links
    scan_calls = 0
    original_scan = config_module.Config._scan_symbolic_links
    
    def wrapped_scan(self):
        nonlocal scan_calls
        scan_calls += 1
        return original_scan(self)
    
    monkeypatch.setattr(config_module.Config, "_scan_symbolic_links", wrapped_scan)
    
    # 1. First initialization
    config_module.Config()
    assert scan_calls == 1
    
    # 2. Change root paths
    new_lora_dir = tmp_path / "new_loras"
    new_lora_dir.mkdir()
    
    def fake_get_folder_paths_modified(kind: str):
        if kind == "loras":
            return [str(loras_dir), str(new_lora_dir)]
        return []
    
    monkeypatch.setattr(config_module.folder_paths, "get_folder_paths", fake_get_folder_paths_modified)
    
    # 3. Initialization with different roots should trigger rescan
    config_module.Config()
    assert scan_calls == 2

def test_manual_rebuild_symlink_cache(monkeypatch: pytest.MonkeyPatch, tmp_path):
    loras_dir, settings_dir = _setup_paths(monkeypatch, tmp_path)
    
    scan_calls = 0
    original_scan = config_module.Config._scan_symbolic_links
    
    def wrapped_scan(self):
        nonlocal scan_calls
        scan_calls += 1
        return original_scan(self)
    
    monkeypatch.setattr(config_module.Config, "_scan_symbolic_links", wrapped_scan)
    
    cfg = config_module.Config()
    assert scan_calls == 1
    
    # Manual trigger
    cfg.rebuild_symlink_cache()
    assert scan_calls == 2
