import json
import os
import sqlite3
from pathlib import Path

import pytest

import py.services.backup_service as backup_service
from py.services.model_update_service import ModelUpdateService
from py.utils.cache_paths import CacheType


class DummySettings:
    def __init__(self, settings_file: Path, *, library_name: str = "main", values=None):
        self.settings_file = str(settings_file)
        self._library_name = library_name
        self._values = values or {}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def get_active_library_name(self):
        return self._library_name


def _configure_backup_paths(monkeypatch, root: Path):
    settings_dir = root / "settings"
    cache_dir = settings_dir / "cache"

    def fake_get_settings_dir(create: bool = True):
        if create:
            settings_dir.mkdir(parents=True, exist_ok=True)
        return str(settings_dir)

    def fake_get_cache_base_dir(create: bool = True):
        if create:
            cache_dir.mkdir(parents=True, exist_ok=True)
        return str(cache_dir)

    def fake_get_cache_file_path(cache_type, library_name=None, create_dir=True):
        if cache_type == CacheType.SYMLINK:
            path = cache_dir / "symlink" / "symlink_map.json"
        elif cache_type == CacheType.MODEL_UPDATE:
            name = library_name or "default"
            path = cache_dir / "model_update" / f"{name}.sqlite"
        else:  # pragma: no cover - the test only covers the backup targets
            raise AssertionError(f"Unexpected cache type: {cache_type}")

        if create_dir:
            path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    monkeypatch.setattr(backup_service, "get_settings_dir", fake_get_settings_dir)
    monkeypatch.setattr(backup_service, "get_cache_base_dir", fake_get_cache_base_dir)
    monkeypatch.setattr(backup_service, "get_cache_file_path", fake_get_cache_file_path)

    return settings_dir, cache_dir


@pytest.mark.asyncio
async def test_backup_round_trip_restores_user_state(tmp_path, monkeypatch):
    settings_dir, cache_dir = _configure_backup_paths(monkeypatch, tmp_path)

    settings_file = settings_dir / "settings.json"
    download_history = cache_dir / "download_history" / "downloaded_versions.sqlite"
    symlink_map = cache_dir / "symlink" / "symlink_map.json"
    model_update_db = cache_dir / "model_update" / "main.sqlite"

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    download_history.parent.mkdir(parents=True, exist_ok=True)
    symlink_map.parent.mkdir(parents=True, exist_ok=True)
    model_update_db.parent.mkdir(parents=True, exist_ok=True)

    settings_file.write_text(json.dumps({"backup_auto_enabled": True}), encoding="utf-8")
    download_history.write_bytes(b"download-history-v1")
    symlink_map.write_text(json.dumps({"a": "/tmp/a"}), encoding="utf-8")
    model_update_db.write_bytes(b"model-update-v1")

    service = backup_service.BackupService(
        settings_manager=DummySettings(settings_file),
        backup_dir=str(tmp_path / "backups"),
    )

    snapshot = await service.create_snapshot(snapshot_type="manual", persist=False)
    archive_path = tmp_path / snapshot["archive_name"]
    archive_path.write_bytes(snapshot["archive_bytes"])

    settings_file.write_text(json.dumps({"backup_auto_enabled": False}), encoding="utf-8")
    download_history.write_bytes(b"download-history-v2")
    symlink_map.write_text(json.dumps({"a": "/tmp/b"}), encoding="utf-8")
    model_update_db.write_bytes(b"model-update-v2")

    result = await service.restore_snapshot(str(archive_path))

    assert result["success"] is True
    assert settings_file.read_text(encoding="utf-8") == json.dumps({"backup_auto_enabled": True})
    assert download_history.read_bytes() == b"download-history-v1"
    assert symlink_map.read_text(encoding="utf-8") == json.dumps({"a": "/tmp/a"})
    assert model_update_db.read_bytes() == b"model-update-v1"


def test_prune_snapshots_keeps_latest_auto_only(tmp_path, monkeypatch):
    settings_dir, _ = _configure_backup_paths(monkeypatch, tmp_path)
    settings_file = settings_dir / "settings.json"
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps({"backup_retention_count": 2}), encoding="utf-8")

    service = backup_service.BackupService(
        settings_manager=DummySettings(settings_file, values={"backup_retention_count": 2}),
        backup_dir=str(tmp_path / "backups"),
    )

    backup_dir = Path(service.get_backup_dir())
    backup_dir.mkdir(parents=True, exist_ok=True)

    files = [
        backup_dir / "lora-manager-backup-20240101T000000Z-auto.zip",
        backup_dir / "lora-manager-backup-20240102T000000Z-auto.zip",
        backup_dir / "lora-manager-backup-20240103T000000Z-auto.zip",
        backup_dir / "lora-manager-backup-20240104T000000Z-manual.zip",
    ]
    for index, path in enumerate(files):
        path.write_bytes(b"zip")
        os.utime(path, (1000 + index, 1000 + index))

    service._prune_snapshots()

    remaining = sorted(p.name for p in backup_dir.glob("*.zip"))
    assert remaining == [
        "lora-manager-backup-20240102T000000Z-auto.zip",
        "lora-manager-backup-20240103T000000Z-auto.zip",
        "lora-manager-backup-20240104T000000Z-manual.zip",
    ]


def test_backup_status_includes_backup_dir(tmp_path, monkeypatch):
    settings_dir, _ = _configure_backup_paths(monkeypatch, tmp_path)
    settings_file = settings_dir / "settings.json"
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text("{}", encoding="utf-8")

    service = backup_service.BackupService(
        settings_manager=DummySettings(settings_file),
        backup_dir=str(tmp_path / "backups"),
    )

    status = service.get_status()

    assert status["backupDir"] == str(tmp_path / "backups")


@pytest.mark.asyncio
async def test_model_update_service_migrates_legacy_snapshot_db(tmp_path, monkeypatch):
    legacy_db = tmp_path / "legacy" / "main.sqlite"
    new_db = tmp_path / "cache" / "model_update" / "main.sqlite"
    legacy_db.parent.mkdir(parents=True, exist_ok=True)
    new_db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(legacy_db) as conn:
        conn.executescript(
            """
            CREATE TABLE model_update_status (
                model_id INTEGER PRIMARY KEY,
                model_type TEXT NOT NULL,
                last_checked_at REAL,
                should_ignore_model INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE model_update_versions (
                model_id INTEGER NOT NULL,
                version_id INTEGER NOT NULL,
                sort_index INTEGER NOT NULL DEFAULT 0,
                name TEXT,
                base_model TEXT,
                released_at TEXT,
                size_bytes INTEGER,
                preview_url TEXT,
                is_in_library INTEGER NOT NULL DEFAULT 0,
                should_ignore INTEGER NOT NULL DEFAULT 0,
                early_access_ends_at TEXT,
                is_early_access INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (model_id, version_id)
            );
            INSERT INTO model_update_status (
                model_id, model_type, last_checked_at, should_ignore_model
            ) VALUES (1, 'lora', 123.0, 1);
            INSERT INTO model_update_versions (
                model_id, version_id, sort_index, name, base_model, released_at,
                size_bytes, preview_url, is_in_library, should_ignore,
                early_access_ends_at, is_early_access
            ) VALUES (
                1, 11, 0, 'v1', 'SD15', '2024-01-01T00:00:00Z',
                1024, 'https://example.com/v1.png', 1, 0, NULL, 0
            );
            """
        )
        conn.commit()

    class DummySettingsManager:
        def get_active_library_name(self):
            return "main"

    monkeypatch.setattr(
        "py.services.model_update_service.resolve_cache_path_with_migration",
        lambda *args, **kwargs: str(new_db),
    )

    class LegacyCache:
        def get_database_path(self):
            return str(legacy_db)

    monkeypatch.setattr(
        "py.services.persistent_model_cache.get_persistent_cache",
        lambda *_args, **_kwargs: LegacyCache(),
    )

    service = ModelUpdateService(settings_manager=DummySettingsManager())

    with sqlite3.connect(new_db) as conn:
        row = conn.execute(
            "SELECT model_id, model_type, last_checked_at, should_ignore_model FROM model_update_status"
        ).fetchone()
        version_row = conn.execute(
            "SELECT model_id, version_id, name, base_model, is_in_library FROM model_update_versions"
        ).fetchone()

    assert row == (1, "lora", 123.0, 1)
    assert version_row == (1, 11, "v1", "SD15", 1)
    assert service._db_path == str(new_db)
