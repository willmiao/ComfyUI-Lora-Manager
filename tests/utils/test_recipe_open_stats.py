import asyncio
import contextlib
import json
from pathlib import Path

import pytest

from py.utils import recipe_open_stats as stats_module
from py.utils.recipe_open_stats import RecipeOpenStats


async def _finalize(tasks) -> None:
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    RecipeOpenStats._instance = None


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    RecipeOpenStats._instance = None
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        stats_module, "get_settings_dir", lambda create=True: str(settings_dir)
    )
    created_tasks = []
    real_create_task = stats_module.asyncio.create_task

    def _track_task(coro):
        task = real_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(stats_module.asyncio, "create_task", _track_task)
    return RecipeOpenStats(), created_tasks, settings_dir


async def _wait_for_save(stats_file: Path) -> None:
    for _ in range(100):
        if stats_file.exists():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Recipe open stats file was never written")


@pytest.mark.asyncio
async def test_record_open_persists_timestamp(tmp_path, monkeypatch):
    stats, tasks, settings_dir = _prepare(tmp_path, monkeypatch)
    stats_file = settings_dir / "stats" / RecipeOpenStats.STATS_FILENAME

    stats.record_open("abc-123")
    await _wait_for_save(stats_file)

    data = json.loads(stats_file.read_text(encoding="utf-8"))
    assert isinstance(data["abc-123"], float)
    await _finalize(tasks)


@pytest.mark.asyncio
async def test_record_open_updates_existing_entry(tmp_path, monkeypatch):
    stats, tasks, settings_dir = _prepare(tmp_path, monkeypatch)
    stats_file = settings_dir / "stats" / RecipeOpenStats.STATS_FILENAME

    stats.record_open("r1")
    await _wait_for_save(stats_file)
    first = json.loads(stats_file.read_text(encoding="utf-8"))["r1"]

    await asyncio.sleep(0.01)
    stats.record_open("r1")
    await stats.save_stats(force=True)

    second = json.loads(stats_file.read_text(encoding="utf-8"))["r1"]
    assert second > first
    await _finalize(tasks)


@pytest.mark.asyncio
async def test_get_opened_map_reloads_on_file_change(tmp_path, monkeypatch):
    stats, tasks, settings_dir = _prepare(tmp_path, monkeypatch)
    stats_file = settings_dir / "stats" / RecipeOpenStats.STATS_FILENAME

    stats.record_open("r1")
    await _wait_for_save(stats_file)

    stats_file.write_text(json.dumps({"r2": 500.0}), encoding="utf-8")
    opened_map = stats.get_opened_map()
    assert opened_map == {"r2": 500.0}
    await _finalize(tasks)


@pytest.mark.asyncio
async def test_save_merges_entries_written_by_another_process(tmp_path, monkeypatch):
    stats, tasks, settings_dir = _prepare(tmp_path, monkeypatch)
    stats_file = settings_dir / "stats" / RecipeOpenStats.STATS_FILENAME

    stats.record_open("r1")
    await _wait_for_save(stats_file)
    first_ts = json.loads(stats_file.read_text(encoding="utf-8"))["r1"]

    # Another process writes its own entry plus a newer timestamp for r1
    stats_file.write_text(
        json.dumps({"r1": first_ts + 100000.0, "r2": 500.0}), encoding="utf-8"
    )

    stats.record_open("r3")
    await stats.save_stats(force=True)

    data = json.loads(stats_file.read_text(encoding="utf-8"))
    # r2 from the other process survives; r1 keeps the newer disk timestamp;
    # r3 from this process is added
    assert data["r1"] == first_ts + 100000.0
    assert data["r2"] == 500.0
    assert isinstance(data["r3"], float)
    await _finalize(tasks)


@pytest.mark.asyncio
async def test_get_opened_map_returns_copy(tmp_path, monkeypatch):
    stats, tasks, _ = _prepare(tmp_path, monkeypatch)
    stats.record_open("r1")

    opened_map = stats.get_opened_map()
    opened_map["injected"] = 1.0
    assert "injected" not in stats.get_opened_map()
    await _finalize(tasks)


@pytest.mark.asyncio
async def test_missing_stats_file_returns_empty_map(tmp_path, monkeypatch):
    stats, tasks, _ = _prepare(tmp_path, monkeypatch)
    assert stats.get_opened_map() == {}
    await _finalize(tasks)


@pytest.mark.asyncio
async def test_save_stats_skips_when_not_dirty(tmp_path, monkeypatch):
    stats, tasks, settings_dir = _prepare(tmp_path, monkeypatch)
    stats_file = settings_dir / "stats" / RecipeOpenStats.STATS_FILENAME

    assert await stats.save_stats() is False
    assert not stats_file.exists()
    await _finalize(tasks)


@pytest.mark.asyncio
async def test_load_ignores_corrupt_file(tmp_path, monkeypatch):
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    stats_file = settings_dir / "stats" / RecipeOpenStats.STATS_FILENAME
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats_file.write_text("{not valid json", encoding="utf-8")

    monkeypatch.setattr(
        stats_module, "get_settings_dir", lambda create=True: str(settings_dir)
    )
    RecipeOpenStats._instance = None
    stats = RecipeOpenStats()
    assert stats.get_opened_map() == {}
