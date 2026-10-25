"""Tests for the first-run scan gate (FirstRunManager)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import sqlite3

import pytest

from py.services import first_run_manager as first_run_module
from py.services.first_run_manager import FirstRunManager
from py.services.settings_manager import get_settings_manager


class FakeScanner:
    """Minimal scanner double exposing the surface FirstRunManager uses."""

    def __init__(
        self,
        roots: List[str] | None = None,
        extensions: set | None = None,
    ) -> None:
        self._roots = list(roots or [])
        self.file_extensions = extensions or {".safetensors"}
        self._cache = None
        self._name_display_mode = "model_name"

    def get_model_roots(self) -> List[str]:
        return list(self._roots)


class RecordingWSManager:
    def __init__(self) -> None:
        self.init_progress: List[Dict[str, Any]] = []

    async def broadcast_init_progress(self, payload: Dict[str, Any]) -> None:
        self.init_progress.append(dict(payload))


def _make_manager(
    tmp_path,
    *,
    scanner_getters=None,
    scan_launcher=None,
    recipe_scanner=None,
) -> FirstRunManager:
    settings_manager = get_settings_manager()

    async def _recipe_getter():
        return recipe_scanner

    return FirstRunManager(
        settings_manager=settings_manager,
        scanner_getters=scanner_getters or {},
        scan_launcher=scan_launcher,
        recipe_scanner_getter=_recipe_getter,
    )


@pytest.fixture(autouse=True)
def _cache_db_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LORA_MANAGER_CACHE_DB", str(tmp_path / "model.sqlite"))
    monkeypatch.setenv(
        "LORA_MANAGER_RECIPE_CACHE_DB", str(tmp_path / "recipe.sqlite")
    )


@pytest.fixture
def ws_recorder(monkeypatch):
    recorder = RecordingWSManager()
    monkeypatch.setattr(first_run_module, "ws_manager", recorder)
    return recorder


def test_awaiting_first_scan_when_flag_not_set(tmp_path):
    manager = _make_manager(tmp_path)

    assert manager.is_awaiting_first_scan() is True


def test_not_awaiting_once_flag_completed(tmp_path):
    manager = _make_manager(tmp_path)
    get_settings_manager().set("initial_scan_completed", True)

    assert manager.is_awaiting_first_scan() is False


def test_not_awaiting_while_scan_in_progress(tmp_path):
    manager = _make_manager(tmp_path)
    manager._scan_in_progress = True

    assert manager.is_awaiting_first_scan() is False


def _write_snapshot(path, table, rows=1):
    """Create a real SQLite snapshot file with the given row count."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        for i in range(rows):
            conn.execute(f"INSERT INTO {table} (id) VALUES (?)", (i + 1,))
        conn.commit()
    finally:
        conn.close()


def test_check_and_mark_upgrade_with_existing_snapshot(tmp_path):
    _write_snapshot(tmp_path / "model.sqlite", "models")
    manager = _make_manager(tmp_path)

    manager.check_and_mark_upgrade()

    assert get_settings_manager().get("initial_scan_completed") is True
    assert manager.is_awaiting_first_scan() is False


def test_check_and_mark_upgrade_with_recipe_snapshot_only(tmp_path):
    _write_snapshot(tmp_path / "recipe.sqlite", "recipes")
    manager = _make_manager(tmp_path)

    manager.check_and_mark_upgrade()

    assert get_settings_manager().get("initial_scan_completed") is True


def test_check_and_mark_upgrade_with_empty_snapshot_stays_pending(tmp_path):
    # Scanner construction creates an empty snapshot file before the upgrade
    # check runs; a file with no rows must not count as an existing library.
    _write_snapshot(tmp_path / "model.sqlite", "models", rows=0)
    _write_snapshot(tmp_path / "recipe.sqlite", "recipes", rows=0)
    manager = _make_manager(tmp_path)

    manager.check_and_mark_upgrade()

    assert get_settings_manager().get("initial_scan_completed") is False
    assert manager.is_awaiting_first_scan() is True


def test_check_and_mark_upgrade_without_snapshot_stays_pending(tmp_path):
    manager = _make_manager(tmp_path)

    manager.check_and_mark_upgrade()

    assert get_settings_manager().get("initial_scan_completed") is False
    assert manager.is_awaiting_first_scan() is True


async def test_collect_first_run_info_counts_files_and_bytes(tmp_path, monkeypatch):
    # Standalone-mode tests may leak this env var; pin it for a stable assert.
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "0")
    lora_root = tmp_path / "loras"
    nested = lora_root / "sub"
    nested.mkdir(parents=True)
    (lora_root / "a.safetensors").write_bytes(b"x" * 100)
    (nested / "b.safetensors").write_bytes(b"y" * 200)
    (nested / "ignored.txt").write_bytes(b"z")
    missing_root = tmp_path / "missing"

    scanners = {
        "loras": FakeScanner([str(lora_root), str(missing_root)]),
        "checkpoints": FakeScanner([]),
        "embeddings": FakeScanner([]),
    }

    async def _getter(scanner):
        return scanner

    manager = _make_manager(
        tmp_path,
        scanner_getters={
            name: (lambda s=scanner: _getter(s)) for name, scanner in scanners.items()
        },
    )

    info = await manager.collect_first_run_info()

    assert info["loras"]["file_count"] == 2
    assert info["loras"]["total_bytes"] == 300
    roots = info["loras"]["roots"]
    assert roots[0] == {"path": str(lora_root), "exists": True}
    assert roots[1] == {"path": str(missing_root), "exists": False}
    # The opt-in other scanner is dropped while Other Models is disabled.
    assert "other" not in info
    # Recipes are always empty on a fresh install and are not listed.
    assert "recipes" not in info
    assert info["file_count"] == 2
    assert info["total_bytes"] == 300
    assert info["estimated_seconds"] >= 0
    assert info["sidecar_storage_mode"] == "alongside"
    assert info["sidecar_storage_path"] == ""
    assert info["standalone"] is False


async def test_collect_first_run_info_includes_other_when_enabled(tmp_path):
    other_root = tmp_path / "other"
    other_root.mkdir()
    (other_root / "upscaler.pth").write_bytes(b"q" * 10)

    get_settings_manager().set("enable_other_models", True)

    async def _getter(scanner):
        return scanner

    manager = _make_manager(
        tmp_path,
        scanner_getters={
            "loras": lambda: _getter(FakeScanner([])),
            "other": lambda: _getter(
                FakeScanner([str(other_root)], extensions={".pth"})
            ),
        },
    )

    info = await manager.collect_first_run_info()

    assert info["other"]["file_count"] == 1
    assert info["other"]["total_bytes"] == 10


async def test_start_initial_scan_launches_scanners_and_broadcasts(
    tmp_path, ws_recorder
):
    launcher = AsyncMock(return_value=["task1", "task2"])
    manager = _make_manager(tmp_path, scan_launcher=launcher)

    result = await manager.start_initial_scan()

    assert result["status"] == "scanning"
    assert result["tasks"] == 2
    launcher.assert_awaited_once()
    assert get_settings_manager().get("initial_scan_completed") is True
    assert get_settings_manager().get("bulk_fetch_prompt_pending") is True
    assert manager.is_awaiting_first_scan() is False
    assert ws_recorder.init_progress
    broadcast = ws_recorder.init_progress[-1]
    assert broadcast["stage"] == "scan_started"
    assert "pageType" not in broadcast


async def test_start_initial_scan_is_idempotent(tmp_path, ws_recorder):
    launcher = AsyncMock(return_value=[])
    manager = _make_manager(tmp_path, scan_launcher=launcher)

    first = await manager.start_initial_scan()
    second = await manager.start_initial_scan()

    assert first["status"] == "scanning"
    # Same-session repeat while the launched scan is still tracked as running.
    assert second["status"] == "already_running"
    launcher.assert_awaited_once()


async def test_start_initial_scan_reports_completed_when_flag_set(tmp_path):
    get_settings_manager().set("initial_scan_completed", True)
    launcher = AsyncMock()
    manager = _make_manager(tmp_path, scan_launcher=launcher)

    result = await manager.start_initial_scan()

    assert result["status"] == "completed"
    launcher.assert_not_awaited()


async def test_start_initial_scan_reports_already_running(tmp_path):
    manager = _make_manager(tmp_path)
    manager._scan_in_progress = True

    result = await manager.start_initial_scan()

    assert result["status"] == "already_running"


async def test_start_initial_scan_defer_presets_empty_caches(tmp_path, ws_recorder):
    lora_scanner = FakeScanner()
    recipe_scanner = SimpleNamespace(_cache=None)
    launcher = AsyncMock()

    async def _getter(scanner):
        return scanner

    manager = _make_manager(
        tmp_path,
        scanner_getters={"loras": lambda: _getter(lora_scanner)},
        scan_launcher=launcher,
        recipe_scanner=recipe_scanner,
    )

    result = await manager.start_initial_scan(defer=True)

    assert result["status"] == "deferred"
    launcher.assert_not_awaited()
    assert get_settings_manager().get("initial_scan_completed") is True
    # The defer path has no fresh scan to anchor the fetch prompt to.
    assert get_settings_manager().get("bulk_fetch_prompt_pending") is False
    # Pages render an empty library instead of the initialization screen.
    assert lora_scanner._cache is not None
    assert lora_scanner._cache.raw_data == []
    assert recipe_scanner._cache is not None
    assert recipe_scanner._cache.raw_data == []
    assert ws_recorder.init_progress == []


async def test_start_initial_scan_launch_failure_allows_retry(tmp_path):
    launcher = AsyncMock(side_effect=RuntimeError("boom"))
    manager = _make_manager(tmp_path, scan_launcher=launcher)

    with pytest.raises(RuntimeError):
        await manager.start_initial_scan()

    # The flag is still set (user confirmed), but the in-progress marker is
    # cleared so is_awaiting_first_scan reflects the persisted flag.
    assert manager._scan_in_progress is False
    assert get_settings_manager().get("initial_scan_completed") is True


async def test_start_initial_scan_rejects_invalid_sidecar_mode(tmp_path):
    manager = _make_manager(tmp_path)

    with pytest.raises(ValueError):
        await manager.start_initial_scan(sidecar_storage_mode="sideways")

    # A rejected request must not flip the gate flag.
    assert get_settings_manager().get("initial_scan_completed") is False


async def test_start_initial_scan_rejects_centralized_without_path(tmp_path):
    manager = _make_manager(tmp_path)

    with pytest.raises(ValueError, match="sidecar_storage_path"):
        await manager.start_initial_scan(sidecar_storage_mode="centralized")

    assert get_settings_manager().get("initial_scan_completed") is False


async def test_start_initial_scan_persists_sidecar_settings(tmp_path, ws_recorder):
    launcher = AsyncMock(return_value=[])
    manager = _make_manager(tmp_path, scan_launcher=launcher)

    result = await manager.start_initial_scan(
        sidecar_storage_mode="centralized",
        sidecar_storage_path=str(tmp_path / "sidecars"),
    )

    assert result["status"] == "scanning"
    settings = get_settings_manager()
    assert settings.get("sidecar_storage_mode") == "centralized"
    assert settings.get("sidecar_storage_path") == str(tmp_path / "sidecars")
