import asyncio
import contextlib
import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from py.metadata_collector.constants import LORAS, MODELS
from py.services.service_registry import ServiceRegistry
from py.utils import usage_stats as usage_stats_module
from py.utils.usage_stats import UsageStats


async def _finalize_usage_stats(tasks):
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    UsageStats._instance = None


def _prepare_usage_stats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, sleep_override=None):
    UsageStats._instance = None
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module, "get_settings_dir", lambda create=True: str(settings_dir))
    loras_root = tmp_path / "loras"
    loras_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module.config, "loras_roots", [str(loras_root)])

    created_tasks = []
    real_create_task = usage_stats_module.asyncio.create_task

    def _track_task(coro):
        task = real_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(usage_stats_module.asyncio, "create_task", _track_task)

    if sleep_override is not None:
        monkeypatch.setattr(usage_stats_module.asyncio, "sleep", sleep_override)

    stats = UsageStats()
    return stats, created_tasks, settings_dir, loras_root


async def test_usage_stats_converts_legacy_format(tmp_path, monkeypatch):
    legacy_stats = {
        "checkpoints": {"hash1": 3},
        "loras": {"hash2": 5},
        "total_executions": 9,
        "last_save_time": 123.0,
    }

    UsageStats._instance = None
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module, "get_settings_dir", lambda create=True: str(settings_dir))
    loras_root = tmp_path / "loras"
    loras_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module.config, "loras_roots", [str(loras_root)])

    old_stats_path = loras_root / UsageStats.STATS_FILENAME
    old_stats_path.write_text(json.dumps(legacy_stats), encoding="utf-8")

    created_tasks = []
    real_create_task = usage_stats_module.asyncio.create_task

    def _track_task(coro):
        task = real_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(usage_stats_module.asyncio, "create_task", _track_task)

    stats = UsageStats()

    today = datetime.now().strftime("%Y-%m-%d")
    converted = stats.stats

    assert converted["total_executions"] == 9
    assert converted["checkpoints"]["hash1"] == {"total": 3, "history": {today: 3}}
    assert converted["loras"]["hash2"] == {"total": 5, "history": {today: 5}}

    new_stats_path = settings_dir / "stats" / UsageStats.STATS_FILENAME
    assert new_stats_path.exists()

    backup_path = new_stats_path.with_suffix(new_stats_path.suffix + UsageStats.BACKUP_SUFFIX)
    assert backup_path.exists()

    await _finalize_usage_stats(created_tasks)


async def test_usage_stats_save_stats_persists_file(tmp_path, monkeypatch):
    stats, tasks, settings_dir, _ = _prepare_usage_stats(tmp_path, monkeypatch)
    stats.stats["total_executions"] = 4

    saved = await stats.save_stats(force=True)
    assert saved is True

    stats_path = settings_dir / "stats" / UsageStats.STATS_FILENAME
    persisted = json.loads(stats_path.read_text(encoding="utf-8"))
    assert persisted["total_executions"] == 4
    assert persisted["last_save_time"] == stats.stats["last_save_time"]

    await _finalize_usage_stats(tasks)


async def test_usage_stats_background_processor_handles_pending_prompts(tmp_path, monkeypatch):
    real_sleep = usage_stats_module.asyncio.sleep

    async def fast_sleep(_seconds):
        await real_sleep(0.01)

    stats, tasks, _, _ = _prepare_usage_stats(tmp_path, monkeypatch, sleep_override=fast_sleep)

    metadata_calls = []
    # Use string literals directly to avoid dependency on conditional imports
    metadata_payload = {
        "models": {
            "1": {"type": "checkpoint", "name": "model.ckpt"},
        },
        "loras": {
            "2": {"lora_list": [{"name": "awesome_lora.safetensors"}]},
        },
    }

    class FakeMetadataRegistry:
        def get_metadata(self, prompt_id):
            metadata_calls.append(prompt_id)
            return metadata_payload

    monkeypatch.setattr(usage_stats_module, "MetadataRegistry", FakeMetadataRegistry, raising=False)

    checkpoint_scanner = SimpleNamespace(get_hash_by_filename=lambda name: {"model": "ckpt-hash"}.get(name))
    lora_scanner = SimpleNamespace(get_hash_by_filename=lambda name: {"awesome_lora.safetensors": "lora-hash"}.get(name))

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", AsyncMock(return_value=checkpoint_scanner))
    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=lora_scanner))

    save_spy = AsyncMock(return_value=True)
    monkeypatch.setattr(stats, "save_stats", save_spy)

    stats.pending_prompt_ids.add("prompt-42")

    await real_sleep(0.05)

    assert metadata_calls == ["prompt-42"]
    assert stats.pending_prompt_ids == set()
    assert stats.stats["total_executions"] == 1

    today = datetime.now().strftime("%Y-%m-%d")
    assert stats.stats["checkpoints"]["ckpt-hash"]["history"][today] == 1
    assert stats.stats["loras"]["lora-hash"]["history"][today] == 1

    await _finalize_usage_stats(tasks)


async def test_usage_stats_calculates_pending_checkpoint_hash_on_demand(tmp_path, monkeypatch):
    stats, tasks, _, _ = _prepare_usage_stats(tmp_path, monkeypatch)

    metadata_payload = {
        "models": {
            "1": {"type": "checkpoint", "name": "pending_model.safetensors"},
        },
        "loras": {},
    }

    checkpoint_cache = SimpleNamespace(
        raw_data=[
            {
                "file_name": "pending_model",
                "model_name": "pending_model",
                "file_path": "/models/pending_model.safetensors",
                "sha256": "",
                "hash_status": "pending",
            }
        ]
    )
    checkpoint_scanner = SimpleNamespace(
        get_hash_by_filename=lambda name: None,
        get_cached_data=AsyncMock(return_value=checkpoint_cache),
        calculate_hash_for_model=AsyncMock(return_value="resolved-hash"),
    )
    lora_scanner = SimpleNamespace(get_hash_by_filename=lambda name: None)

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", AsyncMock(return_value=checkpoint_scanner))
    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=lora_scanner))

    await stats._process_metadata(metadata_payload)

    today = datetime.now().strftime("%Y-%m-%d")
    checkpoint_scanner.calculate_hash_for_model.assert_awaited_once_with("/models/pending_model.safetensors")
    assert stats.stats["checkpoints"]["resolved-hash"]["history"][today] == 1

    await _finalize_usage_stats(tasks)


async def test_usage_stats_skips_failed_checkpoint_hash_retry(tmp_path, monkeypatch):
    stats, tasks, _, _ = _prepare_usage_stats(tmp_path, monkeypatch)

    metadata_payload = {
        "models": {
            "1": {"type": "checkpoint", "name": "failed_model.safetensors"},
        },
        "loras": {},
    }

    checkpoint_cache = SimpleNamespace(
        raw_data=[
            {
                "file_name": "failed_model",
                "model_name": "failed_model",
                "file_path": "/models/failed_model.safetensors",
                "sha256": "",
                "hash_status": "failed",
            }
        ]
    )
    checkpoint_scanner = SimpleNamespace(
        get_hash_by_filename=lambda name: None,
        get_cached_data=AsyncMock(return_value=checkpoint_cache),
        calculate_hash_for_model=AsyncMock(return_value=None),
    )
    lora_scanner = SimpleNamespace(get_hash_by_filename=lambda name: None)

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", AsyncMock(return_value=checkpoint_scanner))
    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=lora_scanner))

    await stats._process_metadata(metadata_payload)

    checkpoint_scanner.calculate_hash_for_model.assert_not_awaited()
    assert stats.stats["checkpoints"] == {}

    await _finalize_usage_stats(tasks)


async def test_usage_stats_resolves_manually_copied_checkpoint_from_disk(tmp_path, monkeypatch):
    stats, tasks, _, _ = _prepare_usage_stats(tmp_path, monkeypatch)

    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()
    checkpoint_file = checkpoints_root / "Chroma1-HD-Q8_0.gguf"
    checkpoint_file.write_text("manual checkpoint content", encoding="utf-8")

    metadata_payload = {
        "models": {
            "1": {"type": "checkpoint", "name": "Chroma1-HD-Q8_0"},
        },
        "loras": {},
    }

    checkpoint_cache = SimpleNamespace(raw_data=[])
    checkpoint_scanner = SimpleNamespace(
        get_hash_by_filename=lambda name: None,
        get_cached_data=AsyncMock(return_value=checkpoint_cache),
        get_model_roots=lambda: [str(checkpoints_root)],
        file_extensions={".ckpt", ".pt", ".pt2", ".bin", ".pth", ".safetensors", ".pkl", ".sft", ".gguf"},
        calculate_hash_for_model=AsyncMock(return_value="resolved-hash"),
    )

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", AsyncMock(return_value=checkpoint_scanner))
    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=None))

    await stats._process_metadata(metadata_payload)

    checkpoint_scanner.calculate_hash_for_model.assert_awaited_once_with(
        str(checkpoint_file).replace(os.sep, "/")
    )

    today = datetime.now().strftime("%Y-%m-%d")
    assert stats.stats["checkpoints"]["resolved-hash"]["history"][today] == 1

    await _finalize_usage_stats(tasks)


async def test_usage_stats_skips_name_fallback_for_missing_lora_hash(tmp_path, monkeypatch):
    stats, tasks, _, _ = _prepare_usage_stats(tmp_path, monkeypatch)

    metadata_payload = {
        "models": {},
        "loras": {
            "2": {"lora_list": [{"name": "missing_lora"}]},
        },
    }

    checkpoint_scanner = SimpleNamespace(get_hash_by_filename=lambda name: None)
    lora_scanner = SimpleNamespace(get_hash_by_filename=lambda name: None)

    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", AsyncMock(return_value=checkpoint_scanner))
    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=lora_scanner))

    await stats._process_metadata(metadata_payload)

    assert stats.stats["loras"] == {}
    assert not any(key.startswith("name:") for key in stats.stats["loras"])

    await _finalize_usage_stats(tasks)


async def test_usage_stats_migrates_from_old_location(tmp_path, monkeypatch):
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module, "get_settings_dir", lambda create=True: str(settings_dir))
    loras_root = tmp_path / "loras"
    loras_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module.config, "loras_roots", [str(loras_root)])

    old_data = {
        "checkpoints": {},
        "loras": {"lora-hash": {"total": 3, "history": {"2025-01-01": 3}}},
        "embeddings": {},
        "total_executions": 3,
        "last_save_time": 100.0,
    }
    old_path = loras_root / UsageStats.STATS_FILENAME
    old_path.write_text(json.dumps(old_data), encoding="utf-8")

    created_tasks = []
    real_create_task = usage_stats_module.asyncio.create_task

    def _track_task(coro):
        task = real_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(usage_stats_module.asyncio, "create_task", _track_task)

    stats = UsageStats()

    new_path = settings_dir / "stats" / UsageStats.STATS_FILENAME
    assert new_path.exists(), "Stats file should be migrated to new location"
    assert not old_path.exists(), "Old stats file should be removed after migration"
    assert stats.stats["total_executions"] == 3
    assert stats.stats["loras"]["lora-hash"]["total"] == 3

    await _finalize_usage_stats(created_tasks)


async def test_usage_stats_uses_new_location_directly(tmp_path, monkeypatch):
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module, "get_settings_dir", lambda create=True: str(settings_dir))
    loras_root = tmp_path / "loras"
    loras_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module.config, "loras_roots", [str(loras_root)])

    new_data = {
        "checkpoints": {},
        "loras": {},
        "embeddings": {},
        "total_executions": 7,
        "last_save_time": 200.0,
    }
    new_path = settings_dir / "stats" / UsageStats.STATS_FILENAME
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(json.dumps(new_data), encoding="utf-8")

    created_tasks = []
    real_create_task = usage_stats_module.asyncio.create_task

    def _track_task(coro):
        task = real_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(usage_stats_module.asyncio, "create_task", _track_task)

    stats = UsageStats()

    assert stats.stats["total_executions"] == 7
    assert not loras_root.joinpath(UsageStats.STATS_FILENAME).exists()

    await _finalize_usage_stats(created_tasks)
