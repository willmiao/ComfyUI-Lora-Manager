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
    stats_root = tmp_path / "loras"
    stats_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module.config, "loras_roots", [str(stats_root)])

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
    return stats, created_tasks, stats_root


async def test_usage_stats_converts_legacy_format(tmp_path, monkeypatch):
    legacy_stats = {
        "checkpoints": {"hash1": 3},
        "loras": {"hash2": 5},
        "total_executions": 9,
        "last_save_time": 123.0,
    }

    UsageStats._instance = None
    stats_root = tmp_path / "loras"
    stats_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(usage_stats_module.config, "loras_roots", [str(stats_root)])

    stats_path = stats_root / UsageStats.STATS_FILENAME
    stats_path.write_text(json.dumps(legacy_stats), encoding="utf-8")

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

    backup_path = stats_path.with_suffix(stats_path.suffix + UsageStats.BACKUP_SUFFIX)
    assert backup_path.exists()

    await _finalize_usage_stats(created_tasks)


async def test_usage_stats_save_stats_persists_file(tmp_path, monkeypatch):
    stats, tasks, stats_root = _prepare_usage_stats(tmp_path, monkeypatch)
    stats.stats["total_executions"] = 4

    saved = await stats.save_stats(force=True)
    assert saved is True

    stats_path = stats_root / UsageStats.STATS_FILENAME
    persisted = json.loads(stats_path.read_text(encoding="utf-8"))
    assert persisted["total_executions"] == 4
    assert persisted["last_save_time"] == stats.stats["last_save_time"]

    await _finalize_usage_stats(tasks)


async def test_usage_stats_background_processor_handles_pending_prompts(tmp_path, monkeypatch):
    real_sleep = usage_stats_module.asyncio.sleep

    async def fast_sleep(_seconds):
        await real_sleep(0.01)

    stats, tasks, _ = _prepare_usage_stats(tmp_path, monkeypatch, sleep_override=fast_sleep)

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
