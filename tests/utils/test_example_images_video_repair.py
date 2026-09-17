"""Tests for the one-shot repair of locally imported video dimensions (issue #1115)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from py.utils import example_images_migration as migration_module
from py.utils import example_images_metadata as metadata_module
from tests.utils.test_video_dimension_probe import build_mp4


def _metadata_payload(**civitai: Any) -> Dict[str, Any]:
    return {"model_name": "Example", "civitai": civitai}


def test_repair_backfills_landscape_video_dimensions(tmp_path: Path):
    video = tmp_path / "custom_abc123.mp4"
    video.write_bytes(build_mp4(1280, 720))

    payload = _metadata_payload(
        customImages=[
            {
                "url": "",
                "id": "abc123",
                "type": "video",
                "width": 720,
                "height": 1280,
            }
        ]
    )

    repaired = metadata_module.repair_local_video_dimensions(
        payload, {"abc123": str(video)}
    )

    assert repaired == 1
    entry = payload["civitai"]["customImages"][0]
    assert (entry["width"], entry["height"]) == (1280, 720)


def test_repair_handles_index_marked_images_array(tmp_path: Path):
    video = tmp_path / "image_3.mp4"
    video.write_bytes(build_mp4(1920, 1080))

    payload = _metadata_payload(
        images=[
            {"url": "https://example.com/remote.png", "type": "image"},
            {"url": "", "type": "video", "width": 720, "height": 1280},
            {"url": "", "type": "video", "width": 720, "height": 1280},
            {"url": "", "type": "video", "width": 720, "height": 1280},
        ]
    )

    repaired = metadata_module.repair_local_video_dimensions(
        payload, {"3": str(video)}
    )

    assert repaired == 1
    # Position 3 (index 3) is the one carrying the local file.
    assert payload["civitai"]["images"][3]["width"] == 1920
    assert payload["civitai"]["images"][3]["height"] == 1080
    # The remote entry keeps its API-provided shape.
    assert payload["civitai"]["images"][0].get("width") is None


def test_repair_never_touches_remote_entries(tmp_path: Path):
    """Remote entries keep API-provided dimensions even if a file exists."""

    video = tmp_path / "custom_remote.mp4"
    video.write_bytes(build_mp4(1280, 720))

    payload = _metadata_payload(
        customImages=[
            {
                "url": "https://civitai.com/1234.mp4",
                "id": "remote",
                "type": "video",
                "width": 720,
                "height": 1280,
            }
        ]
    )
    before = json.dumps(payload, sort_keys=True)

    repaired = metadata_module.repair_local_video_dimensions(
        payload, {"remote": str(video)}
    )

    assert repaired == 0
    assert json.dumps(payload, sort_keys=True) == before


def test_repair_is_idempotent(tmp_path: Path):
    video = tmp_path / "custom_abc.mp4"
    video.write_bytes(build_mp4(1280, 720))

    payload = _metadata_payload(
        customImages=[{"url": "", "id": "abc", "type": "video", "width": 720, "height": 1280}]
    )
    files = {"abc": str(video)}

    assert metadata_module.repair_local_video_dimensions(payload, files) == 1
    # Second run finds nothing to do and leaves the entry byte-identical.
    snapshot = json.dumps(payload, sort_keys=True)
    assert metadata_module.repair_local_video_dimensions(payload, files) == 0
    assert json.dumps(payload, sort_keys=True) == snapshot


def test_repair_dry_run_does_not_mutate(tmp_path: Path):
    video = tmp_path / "custom_abc.mp4"
    video.write_bytes(build_mp4(1280, 720))

    payload = _metadata_payload(
        customImages=[{"url": "", "id": "abc", "type": "video", "width": 720, "height": 1280}]
    )
    before = json.dumps(payload, sort_keys=True)

    repaired = metadata_module.repair_local_video_dimensions(
        payload, {"abc": str(video)}, dry_run=True
    )

    assert repaired == 1
    assert json.dumps(payload, sort_keys=True) == before


def test_repair_skips_missing_file(tmp_path: Path):
    payload = _metadata_payload(
        customImages=[{"url": "", "id": "gone", "type": "video", "width": 720, "height": 1280}]
    )

    repaired = metadata_module.repair_local_video_dimensions(
        payload, {"gone": str(tmp_path / "does-not-exist.mp4")}
    )

    assert repaired == 0
    assert payload["civitai"]["customImages"][0]["width"] == 720


def test_repair_leaves_correct_entries_untouched(tmp_path: Path):
    video = tmp_path / "custom_ok.mp4"
    video.write_bytes(build_mp4(1280, 720))

    payload = _metadata_payload(
        customImages=[{"url": "", "id": "ok", "type": "video", "width": 1280, "height": 720}]
    )

    assert metadata_module.repair_local_video_dimensions(payload, {"ok": str(video)}) == 0


def test_local_file_map_keys_strip_naming_prefix(tmp_path: Path):
    (tmp_path / "custom_abc.mp4").write_bytes(build_mp4(1280, 720))
    (tmp_path / "image_2.png").write_bytes(b"not-a-real-image")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

    mapping = migration_module.ExampleImagesMigration._build_local_file_map(str(tmp_path))

    assert set(mapping) == {"abc", "2"}


async def test_migrate_to_v3_repairs_and_syncs_cache(tmp_path: Path, monkeypatch):
    model_hash = "a" * 64
    folder = tmp_path / model_hash
    folder.mkdir()
    (folder / "custom_xyz.mp4").write_bytes(build_mp4(1080, 1920))

    model_file = tmp_path / "model.safetensors"
    model_file.write_text("weights", encoding="utf-8")

    payload = _metadata_payload(
        customImages=[{"url": "", "id": "xyz", "type": "video", "width": 720, "height": 1280}]
    )
    saved: list[tuple[str, Dict[str, Any]]] = []

    async def fake_load(file_path):
        return dict(payload, civitai=dict(payload["civitai"]))

    async def fake_save(file_path, data):
        saved.append((file_path, data))
        return True

    synced: list[tuple[str, Dict[str, Any]]] = []

    async def fake_sync(scanner, file_path, data):
        synced.append((file_path, data))
        return True

    class StubScanner:
        def has_hash(self, _hash):
            return True

        async def get_cached_data(self):
            from types import SimpleNamespace

            return SimpleNamespace(raw_data=[{"sha256": model_hash, "file_path": str(model_file)}])

    monkeypatch.setattr(migration_module.MetadataManager, "load_metadata_payload", fake_load)
    monkeypatch.setattr(migration_module.MetadataManager, "save_metadata", fake_save)
    monkeypatch.setattr(migration_module, "update_cache_from_metadata", fake_sync)

    async def fake_lora():
        return StubScanner()

    async def fake_none():
        return None

    monkeypatch.setattr(migration_module.ServiceRegistry, "get_lora_scanner", fake_lora)
    monkeypatch.setattr(migration_module.ServiceRegistry, "get_checkpoint_scanner", fake_none)
    monkeypatch.setattr(migration_module.ServiceRegistry, "get_embedding_scanner", fake_none)

    await migration_module.ExampleImagesMigration._migrate_to_v3(
        str(tmp_path), [str(folder)]
    )

    assert len(saved) == 1
    saved_entry = saved[0][1]["civitai"]["customImages"][0]
    assert (saved_entry["width"], saved_entry["height"]) == (1080, 1920)
    assert len(synced) == 1
    assert synced[0][1]["civitai"]["customImages"][0]["width"] == 1080


async def test_migrate_to_v3_skips_when_nothing_to_repair(tmp_path: Path, monkeypatch):
    model_hash = "b" * 64
    folder = tmp_path / model_hash
    folder.mkdir()
    (folder / "custom_ok.mp4").write_bytes(build_mp4(1080, 1920))

    model_file = tmp_path / "model.safetensors"
    model_file.write_text("weights", encoding="utf-8")

    payload = _metadata_payload(
        customImages=[{"url": "", "id": "ok", "type": "video", "width": 1080, "height": 1920}]
    )
    saved: list[Any] = []

    async def fake_load(file_path):
        return dict(payload, civitai=dict(payload["civitai"]))

    async def fake_save(file_path, data):
        saved.append(data)
        return True

    class StubScanner:
        def has_hash(self, _hash):
            return True

        async def get_cached_data(self):
            from types import SimpleNamespace

            return SimpleNamespace(raw_data=[{"sha256": model_hash, "file_path": str(model_file)}])

    monkeypatch.setattr(migration_module.MetadataManager, "load_metadata_payload", fake_load)
    monkeypatch.setattr(migration_module.MetadataManager, "save_metadata", fake_save)

    async def fake_lora():
        return StubScanner()

    async def fake_none():
        return None

    monkeypatch.setattr(migration_module.ServiceRegistry, "get_lora_scanner", fake_lora)
    monkeypatch.setattr(migration_module.ServiceRegistry, "get_checkpoint_scanner", fake_none)
    monkeypatch.setattr(migration_module.ServiceRegistry, "get_embedding_scanner", fake_none)

    await migration_module.ExampleImagesMigration._migrate_to_v3(str(tmp_path), [str(folder)])

    # Correctly-sized entries are never rewritten.
    assert saved == []


async def test_migrate_to_v3_skips_unindexed_model(tmp_path: Path, monkeypatch):
    """A folder whose model is absent from every scanner cache is skipped, not fatal."""

    model_hash = "c" * 64
    folder = tmp_path / model_hash
    folder.mkdir()
    (folder / "custom_zzz.mp4").write_bytes(build_mp4(1080, 1920))

    class EmptyScanner:
        def has_hash(self, _hash):
            return False

        async def get_cached_data(self):
            from types import SimpleNamespace

            return SimpleNamespace(raw_data=[])

    async def fake_scanner():
        return EmptyScanner()

    monkeypatch.setattr(migration_module.ServiceRegistry, "get_lora_scanner", fake_scanner)
    monkeypatch.setattr(migration_module.ServiceRegistry, "get_checkpoint_scanner", fake_scanner)
    monkeypatch.setattr(migration_module.ServiceRegistry, "get_embedding_scanner", fake_scanner)

    # Must not raise.
    await migration_module.ExampleImagesMigration._migrate_to_v3(str(tmp_path), [str(folder)])
