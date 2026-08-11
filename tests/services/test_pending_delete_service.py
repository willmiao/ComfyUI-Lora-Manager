"""Tests for :mod:`py.services.pending_delete_service`.

Covers the staging service contract: stage (model + recipe), undo (with
partial-undo retry and occupied-path protection), merge (with rollback and a
fresh purge timer), purge (expired-only, quarantine of malformed batches,
per-file lock tolerance) and the scanner exclusion of the staging directory.

Deterministic time control: no real sleeps - tests rewrite ``expires_at`` in
the manifest or monkeypatch time functions instead.
"""

from __future__ import annotations

import asyncio
import errno
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pytest

from py.services.pending_delete_service import (
    PENDING_DELETE_DIR_NAME,
    PENDING_DELETE_TTL_SECONDS,
    PendingDeleteService,
    _reset_pending_delete_service,
)
from py.services.model_hash_index import ModelHashIndex
from py.services.model_scanner import ModelScanner
from py.services.settings_manager import DEFAULT_SETTINGS, get_settings_manager
from py.utils import settings_paths
from py.utils.models import LoraMetadata


class ScannerForStage:
    """Scanner double exposing the attributes the staging service uses."""

    def __init__(self, roots: Sequence[Path], model_type: str = "lora") -> None:
        self._roots: List[str] = [os.path.abspath(str(r)) for r in roots]
        self.model_type = model_type

    def get_model_roots(self) -> List[str]:
        return list(self._roots)

    def _find_root_for_file(self, file_path: Optional[str]) -> Optional[str]:
        if not file_path:
            return None
        normalized = os.path.abspath(os.path.normpath(file_path))
        for root in self._roots:
            if normalized == root or normalized.startswith(root + os.sep):
                return root
        return None


class CheckpointScannerStub:
    """Minimal double for usage-tracking lookups."""

    def __init__(self, root: Path) -> None:
        self._root = str(root)
        self.file_extensions = {".safetensors", ".ckpt", ".pt", ".gguf"}

    def get_model_roots(self) -> List[str]:
        return [self._root]


@pytest.fixture(autouse=True)
def _reset_service_singleton() -> Iterator[None]:
    """Reset the pending-delete singleton before and after each test."""
    _reset_pending_delete_service()
    yield
    _reset_pending_delete_service()


@pytest.fixture(autouse=True)
def _stub_scanner_registry(monkeypatch) -> None:
    """Prevent purge enumeration from instantiating real scanner singletons."""
    from py.services.service_registry import ServiceRegistry

    async def _none(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _none)
    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _none)
    monkeypatch.setattr(ServiceRegistry, "get_embedding_scanner", _none)


async def _register_model_root(
    monkeypatch: pytest.MonkeyPatch,
    *,
    lora_roots: Sequence[Path] = (),
    checkpoint_roots: Sequence[Path] = (),
    embedding_roots: Sequence[Path] = (),
) -> None:
    """Point the ServiceRegistry scanner getters at tmp-root fakes."""
    from py.services.service_registry import ServiceRegistry

    def _make(roots: Sequence[Path]):
        async def _getter(*_args: Any, **_kwargs: Any) -> Optional[ScannerForStage]:
            return ScannerForStage(roots) if roots else None

        return _getter

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _make(lora_roots))
    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _make(checkpoint_roots))
    monkeypatch.setattr(ServiceRegistry, "get_embedding_scanner", _make(embedding_roots))


def _write_batch_manifest(
    batch_dir: Path,
    *,
    batch_id: str,
    kind: str,
    expires_at: int,
    entries: Sequence[Dict[str, Any]],
    model_type: Optional[str] = None,
    state: str = "staged",
    model_snapshot: Any = None,
    recipe_snapshot: Any = None,
) -> None:
    """Write a manifest.json with the shape the service reads."""
    manifest: Dict[str, Any] = {
        "batch_id": batch_id,
        "kind": kind,
        "model_type": model_type if kind == "model" else None,
        "state": state,
        "expires_at": int(expires_at),
        "entries": list(entries),
        "model_snapshot": model_snapshot if kind == "model" else None,
        "recipe_snapshot": recipe_snapshot if kind == "recipe" else None,
    }
    (batch_dir / "manifest.json").write_text(json.dumps(manifest))


def _spy_purge_timers(monkeypatch: pytest.MonkeyPatch) -> List[Optional[str]]:
    """Replace the timer task factory with a recorder (no real tasks)."""
    created: List[Optional[str]] = []

    class DummyTask:
        def add_done_callback(self, _cb: Any) -> None:  # pragma: no cover - stub
            pass

        def cancel(self) -> None:  # pragma: no cover - stub
            pass

        def done(self) -> bool:  # pragma: no cover - stub
            return False

    def fake_create_task(coro: Any, *args: Any, **kwargs: Any) -> DummyTask:
        created.append(kwargs.get("name"))
        coro.close()  # never awaited - avoid a "coroutine was never awaited" warning
        return DummyTask()

    monkeypatch.setattr("py.services.pending_delete_service._create_task", fake_create_task)
    return created


async def _stage_simple(
    service: PendingDeleteService,
    root: Path,
    file_name: str,
    *,
    model_type: str = "lora",
    cached_entry: Any = None,
) -> str:
    """Stage a single-artifact model delete and return its batch id."""
    model = root / f"{file_name}.safetensors"
    model.write_bytes(f"{file_name}-data".encode())
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root], model_type=model_type),
        target_dir=str(root),
        file_name=file_name,
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=cached_entry,
    )
    assert batch_id is not None
    return batch_id


# ---------------------------------------------------------------------------
# (a) stage_model_delete renames all existing artifact patterns + manifest
# ---------------------------------------------------------------------------
async def test_a_stage_model_renames_artifacts_and_writes_manifest(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"model-bytes")
    metadata = root / "model.metadata.json"
    metadata.write_bytes(b'{"key": "value"}')
    preview = root / "model.preview.webp"
    preview.write_bytes(b"preview-bytes")

    service = await PendingDeleteService.get_instance()
    cached_entry = {"file_path": str(model), "sha256": "abc", "tags": ["a"]}
    before = int(time.time())

    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=cached_entry,
    )

    assert batch_id is not None
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    assert batch_dir.is_dir()

    # Originals are renamed away.
    assert not model.exists()
    assert not metadata.exists()
    assert not preview.exists()

    # Every existing artifact is staged with identical bytes.
    assert (batch_dir / "model.safetensors").read_bytes() == b"model-bytes"
    assert (batch_dir / "model.metadata.json").read_bytes() == b'{"key": "value"}'
    assert (batch_dir / "model.preview.webp").read_bytes() == b"preview-bytes"

    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["batch_id"] == batch_id
    assert manifest["kind"] == "model"
    assert manifest["model_type"] == "loras"
    assert manifest["state"] == "staged"
    assert manifest["model_snapshot"] == cached_entry
    assert manifest["recipe_snapshot"] is None
    assert before + PENDING_DELETE_TTL_SECONDS - 2 <= manifest["expires_at"] <= before + PENDING_DELETE_TTL_SECONDS + 2

    assert len(manifest["entries"]) == 3
    originals = {entry["original"] for entry in manifest["entries"]}
    assert originals == {str(model), str(metadata), str(preview)}
    for entry in manifest["entries"]:
        assert os.path.isabs(entry["staged"])
        assert os.path.isabs(entry["original"])
        assert entry["restored"] is False


# ---------------------------------------------------------------------------
# (b) undo() restores all files to original paths and removes batch dir
# ---------------------------------------------------------------------------
async def test_b_undo_restores_files_and_removes_batch_dir(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"model-bytes")
    metadata = root / "model.metadata.json"
    metadata.write_bytes(b"meta-bytes")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry={"file_path": str(model)},
    )
    assert batch_id is not None
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    assert batch_dir.is_dir()

    result = await service.undo(batch_id)

    assert result["batch_id"] == batch_id
    assert model.read_bytes() == b"model-bytes"
    assert metadata.read_bytes() == b"meta-bytes"
    assert not batch_dir.exists()


# ---------------------------------------------------------------------------
# (c) undo() on expired batch raises ValueError
# ---------------------------------------------------------------------------
async def test_c_undo_expired_raises_value_error(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    service = await PendingDeleteService.get_instance()

    # Isolate the expiry check: keep the opportunistic purge from consuming it.
    async def _no_purge() -> int:
        return 0

    monkeypatch.setattr(service, "purge_expired", _no_purge)

    batch_id = await _stage_simple(service, root, "model")
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    manifest_path = batch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expires_at"] = int(time.time()) - 10
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="expired"):
        await service.undo(batch_id)


# ---------------------------------------------------------------------------
# (d) undo() when original path occupied raises ValueError, batch stays intact
# ---------------------------------------------------------------------------
async def test_d_undo_occupied_path_raises_and_leaves_batch_intact(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"original")
    metadata = root / "model.metadata.json"
    metadata.write_bytes(b"meta")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=None,
    )
    assert batch_id is not None
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    manifest_before = (batch_dir / "manifest.json").read_bytes()

    # Simulate a re-download occupying the original path.
    model.write_bytes(b"new-file")

    with pytest.raises(ValueError, match="occupied"):
        await service.undo(batch_id)

    # Batch dir + manifest untouched, staged file still present, new file safe.
    assert (batch_dir / "manifest.json").read_bytes() == manifest_before
    assert (batch_dir / "model.safetensors").exists()
    assert model.read_bytes() == b"new-file"


# ---------------------------------------------------------------------------
# (e) PARTIAL-UNDO RETRY
# ---------------------------------------------------------------------------
async def test_e_partial_undo_retry_completes_on_second_attempt(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    for name in ("model.safetensors", "model.metadata.json", "model.preview.webp"):
        (root / name).write_bytes(name.encode())

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(root / "model.safetensors"),
        cached_entry=None,
    )
    assert batch_id is not None
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id

    real_rename = os.rename
    calls = {"n": 0}
    fail_next = {"enabled": True}

    def flaky_rename(src: str, dst: str) -> None:
        calls["n"] += 1
        if fail_next["enabled"] and calls["n"] == 2:
            raise OSError("simulated locked file")
        return real_rename(src, dst)

    monkeypatch.setattr("py.services.pending_delete_service.os.rename", flaky_rename)

    with pytest.raises(OSError):
        await service.undo(batch_id)

    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    assert [entry["restored"] for entry in manifest["entries"]] == [True, False, False]
    assert (root / "model.safetensors").exists()

    # Second undo (rename no longer failing) completes the remainder.
    fail_next["enabled"] = False
    await service.undo(batch_id)

    assert (root / "model.metadata.json").read_bytes() == b"model.metadata.json"
    assert (root / "model.preview.webp").read_bytes() == b"model.preview.webp"
    assert not batch_dir.exists()


# ---------------------------------------------------------------------------
# (e2) UNDO SKIPS A STAGED FILE THAT IS ALREADY GONE and finishes the rest
# ---------------------------------------------------------------------------
async def test_e2_undo_skips_missing_staged_file(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    for name in ("model.safetensors", "model.metadata.json", "model.preview.webp"):
        (root / name).write_bytes(name.encode())

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(root / "model.safetensors"),
        cached_entry=None,
    )
    assert batch_id is not None
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id

    # Simulate one staged artifact being removed out-of-band (e.g. an earlier
    # purge/manual cleanup) before undo runs.
    (batch_dir / "model.metadata.json").unlink()

    await service.undo(batch_id)

    assert (root / "model.safetensors").read_bytes() == b"model.safetensors"
    assert (root / "model.preview.webp").read_bytes() == b"model.preview.webp"
    assert not (root / "model.metadata.json").exists()
    assert not batch_dir.exists()


# ---------------------------------------------------------------------------
# (f) purge_expired() removes only expired batches
# ---------------------------------------------------------------------------
async def test_f_purge_expired_removes_only_expired(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    await _register_model_root(monkeypatch, lora_roots=[root])

    service = await PendingDeleteService.get_instance()
    expired_id = await _stage_simple(service, root, "expired")
    fresh_id = await _stage_simple(service, root, "fresh")

    expired_manifest_path = root / PENDING_DELETE_DIR_NAME / expired_id / "manifest.json"
    expired_manifest = json.loads(expired_manifest_path.read_text(encoding="utf-8"))
    expired_manifest["expires_at"] = int(time.time()) - 10
    expired_manifest_path.write_text(json.dumps(expired_manifest))

    await service.purge_expired()

    assert not (root / PENDING_DELETE_DIR_NAME / expired_id).exists()
    assert (root / PENDING_DELETE_DIR_NAME / fresh_id).exists()
    assert not (root / "expired.safetensors").exists()
    assert not (root / "fresh.safetensors").exists()


# ---------------------------------------------------------------------------
# (g) MANIFEST-LESS dir -> quarantined, files kept
# ---------------------------------------------------------------------------
async def test_g_manifestless_dir_quarantined(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    staging = root / PENDING_DELETE_DIR_NAME
    batch_dir = staging / "batch1"
    batch_dir.mkdir(parents=True)
    (batch_dir / "model.safetensors").write_bytes(b"user-data")
    await _register_model_root(monkeypatch, lora_roots=[root])

    service = await PendingDeleteService.get_instance()
    # The batch is hand-created (unregistered): the reconciliation pass is
    # required for the default registry-only purge to discover it.
    await service.purge_expired(scan_roots=True)

    orphaned = staging / "batch1.orphaned"
    assert orphaned.is_dir()
    assert not batch_dir.exists()
    assert (orphaned / "model.safetensors").read_bytes() == b"user-data"


# ---------------------------------------------------------------------------
# (h) CORRUPTED manifest -> quarantined, sweep completes
# ---------------------------------------------------------------------------
async def test_h_corrupted_manifest_quarantined(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    staging = root / PENDING_DELETE_DIR_NAME
    batch_dir = staging / "batch2"
    batch_dir.mkdir(parents=True)
    (batch_dir / "model.safetensors").write_bytes(b"data")
    (batch_dir / "manifest.json").write_text("{ not valid json !!!")

    await _register_model_root(monkeypatch, lora_roots=[root])
    service = await PendingDeleteService.get_instance()

    # Hand-created (unregistered) batch: reconciliation discovers it.
    await service.purge_expired(scan_roots=True)  # must not crash

    orphaned = staging / "batch2.orphaned"
    assert orphaned.is_dir()
    assert (orphaned / "model.safetensors").read_bytes() == b"data"


# ---------------------------------------------------------------------------
# (i) PURGE LOCKED FILE -> skip file, keep batch dir, no exception
# ---------------------------------------------------------------------------
async def test_i_purge_locked_file_skips_and_keeps_batch_dir(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")

    service = await PendingDeleteService.get_instance()
    batch_id = await _stage_simple(service, root, "model")
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    manifest_path = batch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expires_at"] = int(time.time()) - 10
    manifest_path.write_text(json.dumps(manifest))

    await _register_model_root(monkeypatch, lora_roots=[root])

    real_remove = os.remove

    def flaky_remove(path: str, *args: Any, **kwargs: Any) -> None:
        if str(path).endswith("model.safetensors"):
            raise OSError("simulated locked file")
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr("py.services.pending_delete_service.os.remove", flaky_remove)

    await service.purge_expired()  # no exception

    assert batch_dir.is_dir()
    assert (batch_dir / "model.safetensors").exists()
    assert (batch_dir / "manifest.json").exists()


# ---------------------------------------------------------------------------
# (j) STALE TIMER -> purge_batch on missing/undone ids is a silent no-op
# ---------------------------------------------------------------------------
async def test_j_stale_timer_purge_batch_noop(tmp_path: Path, monkeypatch) -> None:
    await _register_model_root(monkeypatch, lora_roots=[tmp_path / "nonexistent"])

    service = await PendingDeleteService.get_instance()
    await service.purge_batch("does-not-exist")  # silent no-op

    root = tmp_path / "loras"
    root.mkdir()
    batch_id = await _stage_simple(service, root, "model")
    await service.undo(batch_id)

    await service.purge_batch(batch_id)  # undone -> silent no-op
    assert (root / "model.safetensors").read_bytes() == b"model-data"


# ---------------------------------------------------------------------------
# (k) MERGE -> single manifest, re-anchored expiry, all files under winner
# ---------------------------------------------------------------------------
async def test_k_merge_produces_single_manifest_and_moves_all_files(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    _spy_purge_timers(monkeypatch)

    service = await PendingDeleteService.get_instance()
    a1 = root / "alpha.safetensors"
    a1.write_bytes(b"alpha-data")
    a2 = root / "alpha.metadata.json"
    a2.write_bytes(b"alpha-meta")
    bid_a = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="alpha",
        main_extension=".safetensors",
        original_file_path=str(a1),
        cached_entry={"file_path": str(a1)},
    )
    assert bid_a is not None
    b1 = root / "beta.safetensors"
    b1.write_bytes(b"beta-data")
    bid_b = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="beta",
        main_extension=".safetensors",
        original_file_path=str(b1),
        cached_entry=None,
    )
    assert bid_b is not None

    before_merge = int(time.time())
    merged = await service.merge_batches([bid_a, bid_b])
    assert merged == bid_a

    winner_dir = root / PENDING_DELETE_DIR_NAME / bid_a
    loser_dir = root / PENDING_DELETE_DIR_NAME / bid_b
    manifest = json.loads((winner_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["batch_id"] == bid_a
    assert len(manifest["entries"]) == 3
    assert before_merge + PENDING_DELETE_TTL_SECONDS - 2 <= manifest["expires_at"] <= before_merge + PENDING_DELETE_TTL_SECONDS + 2

    staged_paths = [entry["staged"] for entry in manifest["entries"]]
    assert len(staged_paths) == 3
    for staged in staged_paths:
        assert str(staged).startswith(str(winner_dir))
        assert os.path.exists(staged)

    # Byte-compare: no file dropped.
    assert (winner_dir / "alpha.safetensors").read_bytes() == b"alpha-data"
    assert (winner_dir / "alpha.metadata.json").read_bytes() == b"alpha-meta"
    assert (winner_dir / "beta.safetensors").read_bytes() == b"beta-data"

    # Loser batch dir removed (after being empty).
    assert not loser_dir.exists()


# ---------------------------------------------------------------------------
# (k2) MERGE THEN UNDO -> every file restored to its ORIGINAL path
# ---------------------------------------------------------------------------
async def test_k2_merge_then_undo_restores_every_file(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    _spy_purge_timers(monkeypatch)

    service = await PendingDeleteService.get_instance()
    a1 = root / "alpha.safetensors"
    a1.write_bytes(b"alpha-data")
    a2 = root / "alpha.metadata.json"
    a2.write_bytes(b"alpha-meta")
    bid_a = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="alpha",
        main_extension=".safetensors",
        original_file_path=str(a1),
        cached_entry=None,
    )
    assert bid_a is not None
    b1 = root / "beta.safetensors"
    b1.write_bytes(b"beta-data")
    bid_b = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="beta",
        main_extension=".safetensors",
        original_file_path=str(b1),
        cached_entry=None,
    )
    assert bid_b is not None

    assert await service.merge_batches([bid_a, bid_b]) == bid_a
    await service.undo(bid_a)

    assert a1.read_bytes() == b"alpha-data"
    assert a2.read_bytes() == b"alpha-meta"
    assert b1.read_bytes() == b"beta-data"
    assert not (root / PENDING_DELETE_DIR_NAME / bid_a).exists()
    assert not (root / PENDING_DELETE_DIR_NAME / bid_b).exists()


# ---------------------------------------------------------------------------
# (k3) MERGE THEN PURGE -> merged batch fully purged
# ---------------------------------------------------------------------------
async def test_k3_merge_then_purge_empties_and_removes_winner_dir(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    _spy_purge_timers(monkeypatch)

    service = await PendingDeleteService.get_instance()
    a1 = root / "alpha.safetensors"
    a1.write_bytes(b"alpha-data")
    bid_a = await _stage_simple(service, root, "alpha", cached_entry=None)
    bid_b = await _stage_simple(service, root, "beta")
    assert await service.merge_batches([bid_a, bid_b]) == bid_a

    winner_dir = root / PENDING_DELETE_DIR_NAME / bid_a
    manifest_path = winner_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expires_at"] = int(time.time()) - 10
    manifest_path.write_text(json.dumps(manifest))

    await _register_model_root(monkeypatch, lora_roots=[root])
    await service.purge_expired()

    assert not winner_dir.exists()
    assert not (root / "alpha.safetensors").exists()
    assert not (root / "beta.safetensors").exists()


# ---------------------------------------------------------------------------
# (l) MERGE MOVE FAILURE -> rollback, all batches intact, sequential undo works
# ---------------------------------------------------------------------------
async def test_l_merge_move_failure_rolls_back(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    _spy_purge_timers(monkeypatch)

    service = await PendingDeleteService.get_instance()
    a1 = root / "alpha.safetensors"
    a1.write_bytes(b"alpha-data")
    bid_a = await _stage_simple(service, root, "alpha")
    # Loser has TWO files so a move fails after the first was already moved.
    b1 = root / "beta.safetensors"
    b1.write_bytes(b"beta-data")
    b2 = root / "beta.metadata.json"
    b2.write_bytes(b"beta-meta")
    bid_b = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="beta",
        main_extension=".safetensors",
        original_file_path=str(b1),
        cached_entry=None,
    )
    assert bid_b is not None

    real_rename = os.rename
    calls = {"n": 0}
    fail_next = {"enabled": True}

    def flaky_rename(src: str, dst: str) -> None:
        calls["n"] += 1
        if fail_next["enabled"] and calls["n"] == 2:
            raise OSError("simulated move failure")
        return real_rename(src, dst)

    monkeypatch.setattr("py.services.pending_delete_service.os.rename", flaky_rename)

    result = await service.merge_batches([bid_a, bid_b])
    assert result is None

    # Already-moved file moved back; both batch dirs + manifests + files intact.
    winner_dir = root / PENDING_DELETE_DIR_NAME / bid_a
    loser_dir = root / PENDING_DELETE_DIR_NAME / bid_b
    assert winner_dir.is_dir()
    assert loser_dir.is_dir()
    assert (winner_dir / "manifest.json").exists()
    assert (loser_dir / "manifest.json").exists()
    assert (loser_dir / "beta.safetensors").read_bytes() == b"beta-data"
    assert (loser_dir / "beta.metadata.json").read_bytes() == b"beta-meta"
    assert (winner_dir / "alpha.safetensors").read_bytes() == b"alpha-data"

    # Sequential undo of each constituent batch restores every file.
    fail_next["enabled"] = False
    await service.undo(bid_a)
    await service.undo(bid_b)
    assert a1.read_bytes() == b"alpha-data"
    assert b1.read_bytes() == b"beta-data"
    assert b2.read_bytes() == b"beta-meta"


# ---------------------------------------------------------------------------
# (l2) MERGE SAME-BASENAME COLLISION -> abort + rollback, never overwrite
# ---------------------------------------------------------------------------
async def test_l2_merge_basename_collision_aborts_without_dropping_files(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    _spy_purge_timers(monkeypatch)

    service = await PendingDeleteService.get_instance()
    sub_a = root / "a"
    sub_a.mkdir()
    sub_b = root / "b"
    sub_b.mkdir()
    # Two distinct files that share the same basename after staging.
    bid_a = await _stage_simple(service, sub_a, "model")
    bid_b = await _stage_simple(service, sub_b, "model")

    result = await service.merge_batches([bid_a, bid_b])
    assert result is None

    # No file dropped: both staged files exist in their own batch dirs.
    a_dir = sub_a / PENDING_DELETE_DIR_NAME / bid_a
    b_dir = sub_b / PENDING_DELETE_DIR_NAME / bid_b
    assert (a_dir / "model.safetensors").read_bytes() == b"model-data"
    assert (b_dir / "model.safetensors").read_bytes() == b"model-data"
    assert a_dir.is_dir() and b_dir.is_dir()
    assert (a_dir / "manifest.json").exists()
    assert (b_dir / "manifest.json").exists()

    # Sequential undo of each constituent batch restores every original.
    await service.undo(bid_a)
    await service.undo(bid_b)
    assert (sub_a / "model.safetensors").read_bytes() == b"model-data"
    assert (sub_b / "model.safetensors").read_bytes() == b"model-data"


# ---------------------------------------------------------------------------
# (m) delete_undo_enabled=false -> stage returns None, nothing created
# ---------------------------------------------------------------------------
async def test_m_undo_disabled_returns_none(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")

    get_settings_manager().settings["delete_undo_enabled"] = False

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=None,
    )

    assert batch_id is None
    assert model.exists()
    assert not (root / PENDING_DELETE_DIR_NAME).exists()


# ---------------------------------------------------------------------------
# (n) simulated OSError during staging -> rollback, no orphaned batch dir
# ---------------------------------------------------------------------------
async def test_n_staging_oserror_rolls_back(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    a = root / "model.safetensors"
    a.write_bytes(b"a-bytes")
    b = root / "model.metadata.json"
    b.write_bytes(b"b-bytes")

    service = await PendingDeleteService.get_instance()

    real_rename = os.rename
    calls = {"n": 0}

    def flaky_rename(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated staging failure")
        return real_rename(src, dst)

    monkeypatch.setattr("py.services.pending_delete_service.os.rename", flaky_rename)

    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(a),
        cached_entry=None,
    )

    assert batch_id is None
    # First file renamed back; nothing orphaned.
    assert a.read_bytes() == b"a-bytes"
    assert b.read_bytes() == b"b-bytes"
    staging = root / PENDING_DELETE_DIR_NAME
    if staging.exists():
        assert not any(staging.iterdir())


# ---------------------------------------------------------------------------
# (o) DEFAULT_SETTINGS contains delete_undo_enabled=True
# ---------------------------------------------------------------------------
def test_o_default_settings_contains_undo_enabled() -> None:
    assert DEFAULT_SETTINGS.get("delete_undo_enabled") is True


# ---------------------------------------------------------------------------
# (p) SCANNER EXCLUSION
# ---------------------------------------------------------------------------
class DummyScannerForWalk(ModelScanner):
    """Real ModelScanner subclass exercising the real directory walks."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            model_type="lora",
            model_class=LoraMetadata,
            file_extensions={".safetensors"},
            hash_index=ModelHashIndex(),
        )
        self._roots = [str(root)]

    def get_model_roots(self) -> List[str]:
        return list(self._roots)

    async def _process_model_file(
        self,
        file_path: str,
        root_path: str,
        *,
        hash_index: Any = None,
        excluded_models: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        rel_path = os.path.relpath(file_path, root_path)
        name = os.path.splitext(os.path.basename(file_path))[0]
        return {
            "file_path": file_path.replace(os.sep, "/"),
            "folder": os.path.dirname(rel_path).replace(os.sep, "/"),
            "sha256": f"hash-{name}",
            "tags": ["alpha"],
            "model_name": name,
            "size": 1,
            "modified": 1.0,
        }


async def test_p_model_walk_excludes_staging_dir(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    (root / "normal.safetensors").write_bytes(b"normal")
    staging = root / PENDING_DELETE_DIR_NAME / "x"
    staging.mkdir(parents=True)
    (staging / "model.safetensors").write_bytes(b"ghost")
    (staging / "model.metadata.json").write_bytes(b'{"hash_status": "pending"}')

    # Stub the registration side effects the scanner constructor triggers.
    from py.services import model_scanner as model_scanner_module

    async def _noop_register(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(model_scanner_module.ServiceRegistry, "register_service", _noop_register)
    monkeypatch.setenv("LORA_MANAGER_DISABLE_PERSISTENT_CACHE", "1")

    scanner = DummyScannerForWalk(root)

    # Full walk produces NO entry whose path contains the staging dir.
    result = await scanner._gather_model_data()
    paths = [entry["file_path"] for entry in result.raw_data]
    assert any(PENDING_DELETE_DIR_NAME not in p for p in paths)
    assert not any(PENDING_DELETE_DIR_NAME in p for p in paths)

    # The file-count walk also excludes it.
    assert scanner._count_model_files() == 1


async def test_p_checkpoint_pending_discovery_excludes_staging(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "checkpoints"
    root.mkdir()
    (root / "real.safetensors").write_bytes(b"real")
    (root / "real.metadata.json").write_text('{"hash_status": "pending"}')

    staging = root / PENDING_DELETE_DIR_NAME / "x"
    staging.mkdir(parents=True)
    (staging / "model.safetensors").write_bytes(b"ghost")
    (staging / "model.metadata.json").write_text('{"hash_status": "pending"}')

    from py.services import checkpoint_scanner as checkpoint_scanner_module
    from py.services import model_scanner as model_scanner_module

    async def _noop_register(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(model_scanner_module.ServiceRegistry, "register_service", _noop_register)
    monkeypatch.setenv("LORA_MANAGER_DISABLE_PERSISTENT_CACHE", "1")

    scanner = checkpoint_scanner_module.CheckpointScanner()
    monkeypatch.setattr(scanner, "get_model_roots", lambda: [str(root)])

    pending = await scanner._find_pending_models_from_filesystem()
    paths = [entry["file_path"] for entry in pending]
    assert str(root / "real.safetensors") in paths
    assert not any(PENDING_DELETE_DIR_NAME in p for p in paths)


async def test_p_usage_stats_lookup_excludes_staging(tmp_path: Path) -> None:
    root = tmp_path / "checkpoints"
    root.mkdir()
    (root / "mycheckpoint.safetensors").write_bytes(b"real")
    staging = root / PENDING_DELETE_DIR_NAME / "x"
    staging.mkdir(parents=True)
    (staging / "mycheckpoint.safetensors").write_bytes(b"ghost")

    from py.utils.usage_stats import UsageStats

    stats = object.__new__(UsageStats)  # avoid singleton side effects (bg task)
    result = await stats._find_checkpoint_file_on_disk(
        CheckpointScannerStub(root), "mycheckpoint"
    )

    # Staged file is not matched; only the real one is returned.
    assert result == str(root / "mycheckpoint.safetensors")


# ---------------------------------------------------------------------------
# (q) MERGE TIMER -> fresh task for winner; fire-time expiry re-read purges
# ---------------------------------------------------------------------------
async def test_q_merge_arms_fresh_timer_and_purges_at_expiry(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    created = _spy_purge_timers(monkeypatch)

    service = await PendingDeleteService.get_instance()
    bid_a = await _stage_simple(service, root, "alpha")
    bid_b = await _stage_simple(service, root, "beta")

    merged = await service.merge_batches([bid_a, bid_b])
    assert merged == bid_a
    # Staging arms one timer per batch; merge arms a FRESH timer for the winner
    # with the re-anchored expiry (the original winner timer would no-op after
    # re-reading the later expiry).
    assert created == [
        f"pending_delete_purge_{bid_a}",
        f"pending_delete_purge_{bid_b}",
        f"pending_delete_purge_{bid_a}",
    ]

    # Simulate the re-anchored expiry passing, then fire a purge.
    winner_dir = root / PENDING_DELETE_DIR_NAME / bid_a
    manifest_path = winner_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expires_at"] = int(time.time()) - 5
    manifest_path.write_text(json.dumps(manifest))

    await _register_model_root(monkeypatch, lora_roots=[root])
    await service.purge_batch(bid_a)

    assert not winner_dir.exists()
    assert not (root / "alpha.safetensors").exists()
    assert not (root / "beta.safetensors").exists()


# ---------------------------------------------------------------------------
# (r) CROSS-TYPE PURGE ENUMERATION
# ---------------------------------------------------------------------------
async def test_r_purge_expired_enumerates_all_scanner_types_and_recipe_dir(
    tmp_path: Path, monkeypatch
) -> None:
    lora_root = tmp_path / "loras"
    lora_root.mkdir()
    ckpt_root = tmp_path / "checkpoints"
    ckpt_root.mkdir()
    emb_root = tmp_path / "embeddings"
    emb_root.mkdir()

    for tag, root in (("lora", lora_root), ("ckpt", ckpt_root), ("emb", emb_root)):
        batch_dir = root / PENDING_DELETE_DIR_NAME / f"{tag}-batch"
        batch_dir.mkdir(parents=True)
        (batch_dir / f"{tag}.safetensors").write_bytes(tag.encode())
        _write_batch_manifest(
            batch_dir,
            batch_id=f"{tag}-batch",
            kind="model",
            model_type=f"{tag}s",
            expires_at=int(time.time()) - 10,
            entries=[
                {
                    "staged": str(batch_dir / f"{tag}.safetensors"),
                    "original": str(root / f"{tag}.safetensors"),
                    "restored": False,
                }
            ],
        )

    recipe_batch = Path(settings_paths.get_settings_dir()) / PENDING_DELETE_DIR_NAME / "recipe-batch"
    recipe_batch.mkdir(parents=True)
    (recipe_batch / "recipe.json").write_bytes(b"{}")
    _write_batch_manifest(
        recipe_batch,
        batch_id="recipe-batch",
        kind="recipe",
        expires_at=int(time.time()) - 10,
        entries=[
            {
                "staged": str(recipe_batch / "recipe.json"),
                "original": str(tmp_path / "recipe.json"),
                "restored": False,
            }
        ],
        recipe_snapshot={"id": "r1"},
    )

    await _register_model_root(
        monkeypatch,
        lora_roots=[lora_root],
        checkpoint_roots=[ckpt_root],
        embedding_roots=[emb_root],
    )

    service = await PendingDeleteService.get_instance()
    # Hand-created (unregistered) batches: reconciliation pass discovers them.
    purged = await service.purge_expired(scan_roots=True)

    assert purged >= 4
    for root in (lora_root, ckpt_root, emb_root):
        staging = root / PENDING_DELETE_DIR_NAME
        assert not staging.exists() or not any(staging.iterdir())
    assert not recipe_batch.exists()


# ---------------------------------------------------------------------------
# (s) PARTIALLY-RESTORED PURGE -> missing staged file treated as already-purged
# ---------------------------------------------------------------------------
async def test_s_partially_restored_purge_removes_remaining(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    batch_dir = root / PENDING_DELETE_DIR_NAME / "partial"
    batch_dir.mkdir(parents=True)
    # Entry 1 restored:true and its staged file is absent.
    (batch_dir / "entry2.safetensors").write_bytes(b"present")
    _write_batch_manifest(
        batch_dir,
        batch_id="partial",
        kind="model",
        model_type="loras",
        expires_at=int(time.time()) - 10,
        entries=[
            {
                "staged": str(batch_dir / "entry1.safetensors"),
                "original": str(root / "entry1.safetensors"),
                "restored": True,
            },
            {
                "staged": str(batch_dir / "entry2.safetensors"),
                "original": str(root / "entry2.safetensors"),
                "restored": False,
            },
        ],
    )

    await _register_model_root(monkeypatch, lora_roots=[root])
    service = await PendingDeleteService.get_instance()

    await service.purge_batch("partial")  # no exception

    assert not batch_dir.exists()
    assert not (root / "entry2.safetensors").exists()


# ---------------------------------------------------------------------------
# (t) QUARANTINE IS TERMINAL
# ---------------------------------------------------------------------------
async def test_t_quarantine_is_terminal(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    staging = root / PENDING_DELETE_DIR_NAME
    batch_dir = staging / "qbatch"
    batch_dir.mkdir(parents=True)
    (batch_dir / "model.safetensors").write_bytes(b"data")

    await _register_model_root(monkeypatch, lora_roots=[root])
    service = await PendingDeleteService.get_instance()

    # Hand-created (unregistered) batch: reconciliation discovers it.
    await service.purge_expired(scan_roots=True)
    orphaned = staging / "qbatch.orphaned"
    assert orphaned.is_dir()

    # Second sweep must NOT re-rename or delete the quarantined dir.
    await service.purge_expired(scan_roots=True)
    assert orphaned.is_dir()
    assert (orphaned / "model.safetensors").read_bytes() == b"data"
    assert not batch_dir.exists()


# ---------------------------------------------------------------------------
# (u) LOCK NO-DEADLOCK: stage/undo interleaved with purge
# ---------------------------------------------------------------------------
async def test_u_lock_no_deadlock_with_concurrent_purge(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()

    expired_batch = root / PENDING_DELETE_DIR_NAME / "expired"
    expired_batch.mkdir(parents=True)
    (expired_batch / "old.safetensors").write_bytes(b"old")
    _write_batch_manifest(
        expired_batch,
        batch_id="expired",
        kind="model",
        model_type="loras",
        expires_at=int(time.time()) - 10,
        entries=[
            {
                "staged": str(expired_batch / "old.safetensors"),
                "original": str(root / "old.safetensors"),
                "restored": False,
            }
        ],
    )
    await _register_model_root(monkeypatch, lora_roots=[root])

    service = await PendingDeleteService.get_instance()

    new_model = root / "new.safetensors"
    new_model.write_bytes(b"new")

    async def do_stage() -> Optional[str]:
        return await service.stage_model_delete(
            scanner=ScannerForStage([root]),
            target_dir=str(root),
            file_name="new",
            main_extension=".safetensors",
            original_file_path=str(new_model),
            cached_entry=None,
        )

    # Hand-created (unregistered) "expired" batch: the purge task must run the
    # reconciliation pass to discover it alongside the staged "new" batch.
    purge_task = asyncio.create_task(service.purge_expired(scan_roots=True))
    stage_task = asyncio.create_task(do_stage())
    results = await asyncio.gather(purge_task, stage_task, return_exceptions=True)

    assert not isinstance(results[0], BaseException)
    assert not isinstance(results[1], BaseException)
    assert results[1] is not None

    # Expired batch fully purged (never partially), new batch staged intact.
    assert not expired_batch.exists()
    new_batch_dir = root / PENDING_DELETE_DIR_NAME / results[1]
    assert new_batch_dir.is_dir()
    assert (new_batch_dir / "new.safetensors").read_bytes() == b"new"


# ---------------------------------------------------------------------------
# Extra: recipe staging happy path + missing-image skip + undo
# ---------------------------------------------------------------------------
async def test_recipe_stage_copies_json_and_image_then_undo_restores(tmp_path: Path) -> None:
    settings_dir = Path(settings_paths.get_settings_dir())
    recipe_json = tmp_path / "my_recipe.recipe.json"
    recipe_json.write_text('{"id": "r1"}')
    image = tmp_path / "preview.png"
    image.write_bytes(b"img")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=str(image),
        recipe_data={"id": "r1", "name": "Recipe One"},
    )
    assert batch_id is not None
    batch_dir = settings_dir / PENDING_DELETE_DIR_NAME / batch_id
    assert batch_dir.is_dir()
    assert (batch_dir / "my_recipe.recipe.json").read_text() == '{"id": "r1"}'
    assert (batch_dir / "preview.png").read_bytes() == b"img"

    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "recipe"
    assert manifest["model_type"] is None
    assert manifest["model_snapshot"] is None
    assert manifest["recipe_snapshot"] == {"id": "r1", "name": "Recipe One"}
    assert len(manifest["entries"]) == 2

    # The caller removes the originals after staging (see plan todo 4).
    recipe_json.unlink()
    image.unlink()

    await service.undo(batch_id)
    assert recipe_json.read_text() == '{"id": "r1"}'
    assert image.read_bytes() == b"img"
    assert not batch_dir.exists()


async def test_recipe_stage_skips_missing_image(tmp_path: Path) -> None:
    settings_dir = Path(settings_paths.get_settings_dir())
    recipe_json = tmp_path / "r2.recipe.json"
    recipe_json.write_text("{}")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=str(tmp_path / "missing.png"),
        recipe_data={"id": "r2"},
    )
    assert batch_id is not None

    batch_dir = settings_dir / PENDING_DELETE_DIR_NAME / batch_id
    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["entries"]) == 1
    assert (batch_dir / "r2.recipe.json").exists()


# ---------------------------------------------------------------------------
# Task 6 (a) STAGING ARMS A PURGE TIMER -> task named pending_delete_purge_*
# ---------------------------------------------------------------------------
async def test_t6_stage_model_arms_purge_timer(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    created = _spy_purge_timers(monkeypatch)

    service = await PendingDeleteService.get_instance()
    batch_id = await _stage_simple(service, root, "model")

    # Exactly one timer task armed, with the house naming prefix.
    assert created == [f"pending_delete_purge_{batch_id}"]


async def test_t6_stage_recipe_arms_purge_timer(tmp_path: Path, monkeypatch) -> None:
    created = _spy_purge_timers(monkeypatch)
    recipe_json = tmp_path / "r_t6.recipe.json"
    recipe_json.write_text("{}")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=None,
        recipe_data={"id": "r_t6"},
    )

    assert batch_id is not None
    assert created == [f"pending_delete_purge_{batch_id}"]


# ---------------------------------------------------------------------------
# Task 6 (b) OPPORTUNISTIC PURGE -> awaited at stage/undo entry (lock-free)
# ---------------------------------------------------------------------------
async def test_t6_purge_expired_awaited_at_stage_and_undo_entries(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    service = await PendingDeleteService.get_instance()

    calls: List[str] = []

    async def counting_purge() -> int:
        calls.append("purge")
        return 0

    monkeypatch.setattr(service, "purge_expired", counting_purge)

    batch_id = await _stage_simple(service, root, "model")
    assert calls == ["purge"]

    recipe_json = tmp_path / "r_t6b.recipe.json"
    recipe_json.write_text("{}")
    await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=None,
        recipe_data=None,
    )
    assert calls == ["purge", "purge"]

    await service.undo(batch_id)
    assert calls == ["purge", "purge", "purge"]


# ---------------------------------------------------------------------------
# Task 6 NON-EXPIRED BATCH SURVIVES THE STARTUP SWEEP
# ---------------------------------------------------------------------------
async def test_t6_non_expired_batch_survives_startup_sweep(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    await _register_model_root(monkeypatch, lora_roots=[root])

    service = await PendingDeleteService.get_instance()
    batch_id = await _stage_simple(service, root, "model")
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    assert batch_dir.is_dir()

    # Startup sweep must skip the not-yet-expired batch (undo survives restart).
    await service.purge_expired()

    assert batch_dir.is_dir()
    assert (batch_dir / "model.safetensors").exists()
    assert (batch_dir / "manifest.json").exists()
    assert not (root / "model.safetensors").exists()


# ---------------------------------------------------------------------------
# F3 EXDEV-1: undo() survives a cross-device staging parent (copy fallback)
# ---------------------------------------------------------------------------
async def test_exdev1_recipe_undo_falls_back_to_copy_across_devices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recipe staging copies into ``{settings_dir}/.lm-pending-delete`` which
    can live on a DIFFERENT filesystem than the recipes dir. undo() must NOT
    die with EXDEV: fall back to copy2+remove so bytes are restored and the
    staged copies are gone (no data loss)."""
    settings_dir = Path(settings_paths.get_settings_dir())
    recipe_json = tmp_path / "exdev_recipe.recipe.json"
    recipe_json.write_text('{"id": "exdev"}')
    image = tmp_path / "exdev_preview.png"
    image.write_bytes(b"img-bytes")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=str(image),
        recipe_data={"id": "exdev"},
    )
    assert batch_id is not None
    batch_dir = settings_dir / PENDING_DELETE_DIR_NAME / batch_id
    assert batch_dir.is_dir()

    # The todo-4 caller removes the originals after staging.
    recipe_json.unlink()
    image.unlink()

    real_rename = os.rename

    def exdev_rename(src: str, dst: str) -> None:
        if PENDING_DELETE_DIR_NAME in str(src):
            raise OSError(errno.EXDEV, "Invalid cross-device link", str(src), str(dst))
        return real_rename(src, dst)

    monkeypatch.setattr("py.services.pending_delete_service.os.rename", exdev_rename)

    await service.undo(batch_id)

    # Byte-identical content restored; staged copies + batch dir gone.
    assert recipe_json.read_text(encoding="utf-8") == '{"id": "exdev"}'
    assert image.read_bytes() == b"img-bytes"
    assert not batch_dir.exists()
    staging = settings_dir / PENDING_DELETE_DIR_NAME
    assert not staging.exists() or not any(staging.iterdir())


# ---------------------------------------------------------------------------
# F3 EXDEV-2: partial EXDEV completes within ONE undo (copy fallback inline)
# ---------------------------------------------------------------------------
async def test_exdev2_partial_exdev_completes_within_one_undo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the SECOND restore hits EXDEV, the first entry is restored via
    rename, the second via the copy fallback, and the whole batch finishes in a
    single undo call (no retry needed): both originals byte-identical, staged
    copies gone, batch dir removed."""
    settings_dir = Path(settings_paths.get_settings_dir())
    recipe_json = tmp_path / "exdev2_recipe.recipe.json"
    recipe_json.write_text('{"id": "exdev2"}')
    image = tmp_path / "exdev2_preview.png"
    image.write_bytes(b"img2-bytes")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=str(image),
        recipe_data={"id": "exdev2"},
    )
    assert batch_id is not None
    batch_dir = settings_dir / PENDING_DELETE_DIR_NAME / batch_id
    assert batch_dir.is_dir()

    recipe_json.unlink()
    image.unlink()

    real_rename = os.rename
    calls = {"n": 0}

    def exdev_on_second_rename(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(errno.EXDEV, "Invalid cross-device link", str(src), str(dst))
        return real_rename(src, dst)

    monkeypatch.setattr(
        "py.services.pending_delete_service.os.rename", exdev_on_second_rename
    )

    await service.undo(batch_id)

    assert recipe_json.read_text(encoding="utf-8") == '{"id": "exdev2"}'
    assert image.read_bytes() == b"img2-bytes"
    assert not batch_dir.exists()
    assert calls["n"] >= 2


# ---------------------------------------------------------------------------
# F3 SNAP-1: stage_model_delete attaches the snapshot to the MAIN-file entry
# ---------------------------------------------------------------------------
async def test_snap1_stage_model_writes_snapshot_on_main_file_entry(
    tmp_path: Path,
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")
    metadata = root / "model.metadata.json"
    metadata.write_bytes(b"{}")

    cached_entry = {"file_path": str(model), "sha256": "abc", "tags": ["t"]}

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=cached_entry,
    )
    assert batch_id is not None
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))

    entries = manifest["entries"]
    assert len(entries) == 2
    main_entry = next(e for e in entries if e["original"] == str(model))
    meta_entry = next(e for e in entries if e["original"] == str(metadata))
    assert main_entry["snapshot"] == cached_entry
    assert "snapshot" not in meta_entry
    # Top-level snapshot kept for backward compat / single-delete path.
    assert manifest["model_snapshot"] == cached_entry


async def test_snap1_none_snapshot_is_fine(tmp_path: Path) -> None:
    """cached_entry=None still attaches a (None) snapshot on the main entry."""
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=None,
    )
    assert batch_id is not None
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    main_entry = next(iter(manifest["entries"]))
    assert "snapshot" in main_entry
    assert main_entry["snapshot"] is None


# ---------------------------------------------------------------------------
# F3 SNAP-2: merged manifest entries carry BOTH snapshots
# ---------------------------------------------------------------------------
async def test_snap2_merge_keeps_both_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    _spy_purge_timers(monkeypatch)

    service = await PendingDeleteService.get_instance()
    a1 = root / "alpha.safetensors"
    a1.write_bytes(b"alpha-data")
    b1 = root / "beta.safetensors"
    b1.write_bytes(b"beta-data")
    bid_a = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="alpha",
        main_extension=".safetensors",
        original_file_path=str(a1),
        cached_entry={"file_path": str(a1), "tags": ["alpha"]},
    )
    bid_b = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="beta",
        main_extension=".safetensors",
        original_file_path=str(b1),
        cached_entry={"file_path": str(b1), "tags": ["beta"]},
    )
    assert bid_a is not None
    assert bid_b is not None

    assert await service.merge_batches([bid_a, bid_b]) == bid_a
    winner_dir = root / PENDING_DELETE_DIR_NAME / bid_a
    manifest = json.loads((winner_dir / "manifest.json").read_text(encoding="utf-8"))

    snap_entries = [e for e in manifest["entries"] if e.get("snapshot")]
    assert len(snap_entries) == 2
    assert {e["snapshot"]["file_path"] for e in snap_entries} == {str(a1), str(b1)}


# ---------------------------------------------------------------------------
# Batch-registry lifecycle (todo 1: in-process _known_batch_dirs)
# ---------------------------------------------------------------------------

# (a) stage_model_delete registers in _known_batch_dirs
async def test_reg_a_stage_model_registers_batch(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    service = await PendingDeleteService.get_instance()
    batch_id = await _stage_simple(service, root, "model")

    assert service._known_batch_dirs.get(batch_id) == str(
        root / PENDING_DELETE_DIR_NAME / batch_id
    )


# (b) undo success removes the entry
async def test_reg_b_undo_success_removes_registry_entry(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    service = await PendingDeleteService.get_instance()
    batch_id = await _stage_simple(service, root, "model")
    assert batch_id in service._known_batch_dirs

    await service.undo(batch_id)

    assert batch_id not in service._known_batch_dirs


# (c) purge_batch removes the entry after a real purge
async def test_reg_c_purge_batch_removes_registry_entry(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    service = await PendingDeleteService.get_instance()
    batch_id = await _stage_simple(service, root, "model")
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    manifest_path = batch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expires_at"] = int(time.time()) - 10
    manifest_path.write_text(json.dumps(manifest))

    await service.purge_batch(batch_id)

    assert batch_id not in service._known_batch_dirs
    assert not batch_dir.exists()


# (d) quarantine (corrupted manifest) removes the entry
async def test_reg_d_quarantine_removes_registry_entry(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    service = await PendingDeleteService.get_instance()
    batch_id = await _stage_simple(service, root, "model")
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    assert batch_id in service._known_batch_dirs

    # Corrupt the manifest: purge_batch quarantines the dir (returns True).
    (batch_dir / "manifest.json").write_text("{ not valid json !!!")

    await service.purge_batch(batch_id)

    assert batch_id not in service._known_batch_dirs
    assert not batch_dir.exists()
    assert (batch_dir.with_name(f"{batch_id}.orphaned")).is_dir()


# (e) merge success: winner present + losers removed; EXDEV-abort: unchanged
async def test_reg_e_merge_registry_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    _spy_purge_timers(monkeypatch)
    service = await PendingDeleteService.get_instance()
    bid_a = await _stage_simple(service, root, "alpha")
    bid_b = await _stage_simple(service, root, "beta")
    bid_c = await _stage_simple(service, root, "gamma")
    assert set(service._known_batch_dirs) == {bid_a, bid_b, bid_c}

    # Merge success: winner stays, processed loser forgotten, untouched batch stays.
    assert await service.merge_batches([bid_a, bid_b]) == bid_a
    assert bid_a in service._known_batch_dirs
    assert bid_b not in service._known_batch_dirs
    assert bid_c in service._known_batch_dirs

    # EXDEV-abort: registry untouched.
    def exdev_rename(src: str, dst: str) -> None:
        raise OSError(errno.EXDEV, "Invalid cross-device link", src, dst)

    monkeypatch.setattr("py.services.pending_delete_service.os.rename", exdev_rename)
    before = dict(service._known_batch_dirs)
    assert await service.merge_batches([bid_a, bid_c]) is None
    assert dict(service._known_batch_dirs) == before


# (f) _reset_pending_delete_service clears the registry
async def test_reg_f_reset_clears_registry(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    service = await PendingDeleteService.get_instance()
    batch_id = await _stage_simple(service, root, "model")
    assert service._known_batch_dirs

    _reset_pending_delete_service()

    fresh = await PendingDeleteService.get_instance()
    assert fresh is not service
    assert fresh._known_batch_dirs == {}


# (g) scan_roots=True reconciles externally created batches (expired purged,
#     non-expired registered); the registry-only default does NOT find them
async def test_reg_g_reconciliation_finds_external_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    await _register_model_root(monkeypatch, lora_roots=[root])

    expired_dir = root / PENDING_DELETE_DIR_NAME / "ext-expired"
    expired_dir.mkdir(parents=True)
    (expired_dir / "old.safetensors").write_bytes(b"old")
    _write_batch_manifest(
        expired_dir,
        batch_id="ext-expired",
        kind="model",
        model_type="loras",
        expires_at=int(time.time()) - 10,
        entries=[
            {
                "staged": str(expired_dir / "old.safetensors"),
                "original": str(root / "old.safetensors"),
                "restored": False,
            }
        ],
    )
    fresh_dir = root / PENDING_DELETE_DIR_NAME / "ext-fresh"
    fresh_dir.mkdir(parents=True)
    (fresh_dir / "new.safetensors").write_bytes(b"new")
    _write_batch_manifest(
        fresh_dir,
        batch_id="ext-fresh",
        kind="model",
        model_type="loras",
        expires_at=int(time.time()) + 100,
        entries=[
            {
                "staged": str(fresh_dir / "new.safetensors"),
                "original": str(root / "new.safetensors"),
                "restored": False,
            }
        ],
    )

    service = await PendingDeleteService.get_instance()

    # Registry-only default: the externally created batches are invisible.
    await service.purge_expired()
    assert expired_dir.is_dir()
    assert fresh_dir.is_dir()
    assert "ext-expired" not in service._known_batch_dirs
    assert "ext-fresh" not in service._known_batch_dirs

    # Reconciliation pass: expired one purged, non-expired one registered.
    await service.purge_expired(scan_roots=True)

    assert not expired_dir.exists()
    assert not (root / "old.safetensors").exists()
    assert fresh_dir.is_dir()
    assert (fresh_dir / "new.safetensors").exists()
    assert "ext-expired" not in service._known_batch_dirs
    assert service._known_batch_dirs.get("ext-fresh") == str(fresh_dir)


# (h) _find_batch_dir with cleared registry locates + registers (restart sim)
async def test_reg_h_find_batch_dir_restart_simulation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    await _register_model_root(monkeypatch, lora_roots=[root])
    service = await PendingDeleteService.get_instance()
    batch_id = await _stage_simple(service, root, "model")
    assert batch_id in service._known_batch_dirs

    # Simulate a restart: the in-process registry is empty but the batch dir
    # is still on disk.
    service._known_batch_dirs.clear()

    found = await service._find_batch_dir(batch_id)

    assert found == str(root / PENDING_DELETE_DIR_NAME / batch_id)
    assert service._known_batch_dirs.get(batch_id) == found

    # Undo works after the restart simulation.
    await service.undo(batch_id)
    assert (root / "model.safetensors").read_bytes() == b"model-data"
    assert batch_id not in service._known_batch_dirs


# (i) purge iteration uses a snapshot: no dict-changed-size when entries are
#     removed mid-iteration
async def test_reg_i_purge_iteration_uses_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    await _register_model_root(monkeypatch, lora_roots=[root])
    service = await PendingDeleteService.get_instance()
    ids = [await _stage_simple(service, root, f"m{i}") for i in range(5)]

    for batch_id in ids:
        manifest_path = root / PENDING_DELETE_DIR_NAME / batch_id / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["expires_at"] = int(time.time()) - 10
        manifest_path.write_text(json.dumps(manifest))

    # Every purge removes its registry entry mid-loop; the snapshot makes this
    # safe (iterating the dict directly would raise RuntimeError).
    await service.purge_expired()

    assert service._known_batch_dirs == {}
    for batch_id in ids:
        assert not (root / PENDING_DELETE_DIR_NAME / batch_id).exists()


# (j) STARTUP SWEEP PIN: the startup sweep task passes scan_roots=True
async def test_reg_j_startup_sweep_passes_scan_roots_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from py import lora_manager

    sweep_calls: List[Dict[str, Any]] = []

    class _SpySweepService:
        async def purge_expired(self, scan_roots: bool = False) -> int:
            sweep_calls.append({"scan_roots": scan_roots})
            return 0

    async def _fake_get_service() -> _SpySweepService:
        return _SpySweepService()

    monkeypatch.setattr(lora_manager, "get_pending_delete_service", _fake_get_service)

    async def _stub(*args: Any, **_kwargs: Any) -> Any:
        return args[0] if args else None

    class _DummyScanner:
        async def initialize_in_background(self) -> None:
            return None

    dummy = _DummyScanner()
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_civitai_client", lambda: _stub())
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_download_manager", lambda: _stub())
    monkeypatch.setattr(
        lora_manager.ServiceRegistry, "get_download_queue_service", lambda: _stub()
    )
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_backup_service", lambda: _stub())
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_websocket_manager", lambda: _stub())
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_lora_scanner", lambda: _stub(dummy))
    monkeypatch.setattr(
        lora_manager.ServiceRegistry, "get_checkpoint_scanner", lambda: _stub(dummy)
    )
    monkeypatch.setattr(
        lora_manager.ServiceRegistry, "get_embedding_scanner", lambda: _stub(dummy)
    )
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_recipe_scanner", lambda: _stub(dummy))

    from py.services import metadata_service as metadata_service_module

    monkeypatch.setattr(
        metadata_service_module,
        "initialize_metadata_providers",
        _stub,
    )

    from py.services.llm_service import LLMService

    monkeypatch.setattr(LLMService, "get_instance", _stub)

    async def _fake_migration() -> None:
        return None

    monkeypatch.setattr(
        lora_manager.ExampleImagesMigration,
        "check_and_run_migrations",
        staticmethod(_fake_migration),
    )

    captured: List[Any] = []

    class _DummyTask:
        def add_done_callback(self, _cb: Any) -> None:  # pragma: no cover - stub
            pass

        def done(self) -> bool:  # pragma: no cover - stub
            return False

    def _capture_task(coro: Any, *args: Any, **kwargs: Any) -> _DummyTask:
        captured.append(coro)
        return _DummyTask()

    monkeypatch.setattr(asyncio, "create_task", _capture_task)

    try:
        await lora_manager.LoraManager._initialize_services()
    finally:
        sweep_coro: Any = None
        for coro in captured:
            qualname = getattr(coro.cr_code, "co_qualname", "")
            if "_SpySweepService.purge_expired" in qualname:
                sweep_coro = coro
            else:
                coro.close()
        if sweep_coro is not None:
            # The sweep task body only runs when awaited; execute just the
            # spy's purge_expired so it records its invocation arguments.
            await sweep_coro

    # The startup sweep must invoke purge_expired with scan_roots=True (the
    # reconciliation flag) - forgetting it would break restart cleanup.
    assert sweep_calls == [{"scan_roots": True}]


# ---------------------------------------------------------------------------
# Todo 2: SIBLING-OF-MODEL STAGING (model file in a SUBDIR of the scanner root)
# ---------------------------------------------------------------------------

# (a) staging lands in <model_dir>/.lm-pending-delete/<batch_id>, NOT under the
#     scanner root - manifest entries' staged paths live under the sibling dir.
async def test_sibling1_stage_model_in_subdir_uses_sibling_dir(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    sub = root / "nested"
    sub.mkdir()
    model = sub / "model.safetensors"
    model.write_bytes(b"sibling-data")
    metadata = sub / "model.metadata.json"
    metadata.write_bytes(b"{}")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(sub),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=None,
    )
    assert batch_id is not None

    sibling_dir = sub / PENDING_DELETE_DIR_NAME / batch_id
    assert sibling_dir.is_dir()
    # The OLD location (under the scanner root) must NOT be created.
    assert not (root / PENDING_DELETE_DIR_NAME).exists()

    manifest = json.loads((sibling_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["entries"]) == 2
    for entry in manifest["entries"]:
        assert str(entry["staged"]).startswith(str(sibling_dir))
    assert (sibling_dir / "model.safetensors").read_bytes() == b"sibling-data"
    assert (sibling_dir / "model.metadata.json").exists()
    assert not model.exists()
    assert not metadata.exists()


# (b) undo of a sibling-staged batch restores the files byte-identically.
async def test_sibling2_undo_restores_byte_identically(tmp_path: Path) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    sub = root / "nested"
    sub.mkdir()
    model = sub / "model.safetensors"
    model.write_bytes(b"payload-1")
    preview = sub / "model.preview.png"
    preview.write_bytes(b"payload-2")

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(sub),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=None,
    )
    assert batch_id is not None
    sibling_dir = sub / PENDING_DELETE_DIR_NAME / batch_id
    assert sibling_dir.is_dir()
    assert not model.exists()
    assert not preview.exists()

    await service.undo(batch_id)

    assert model.read_bytes() == b"payload-1"
    assert preview.read_bytes() == b"payload-2"
    assert not sibling_dir.exists()
    assert batch_id not in service._known_batch_dirs


# (c) ROOT GATING: _find_model_root -> None skips staging entirely.
async def test_sibling3_root_gating_skips_staging(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"keep-me")

    service = await PendingDeleteService.get_instance()
    monkeypatch.setattr(service, "_find_model_root", lambda _scanner, _path: None)

    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=None,
    )

    assert batch_id is None
    assert model.read_bytes() == b"keep-me"
    assert not (root / PENDING_DELETE_DIR_NAME).exists()


# QA scenario: simulated OSError on the 2nd artifact during sibling staging ->
# rollback renames the 1st back, returns None, and leaves no orphaned sibling
# batch dir behind.
async def test_sibling4_staging_oserror_rolls_back_sibling_dir(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    sub = root / "nested"
    sub.mkdir()
    a = sub / "model.safetensors"
    a.write_bytes(b"a-bytes")
    b = sub / "model.metadata.json"
    b.write_bytes(b"b-bytes")

    service = await PendingDeleteService.get_instance()

    real_rename = os.rename
    calls = {"n": 0}

    def flaky_rename(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated sibling staging failure")
        return real_rename(src, dst)

    monkeypatch.setattr("py.services.pending_delete_service.os.rename", flaky_rename)

    batch_id = await service.stage_model_delete(
        scanner=ScannerForStage([root]),
        target_dir=str(sub),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(a),
        cached_entry=None,
    )

    assert batch_id is None
    # Both artifacts rolled back; no orphaned sibling batch dir holds data.
    assert a.read_bytes() == b"a-bytes"
    assert b.read_bytes() == b"b-bytes"
    sibling = sub / PENDING_DELETE_DIR_NAME
    if sibling.exists():
        assert not any(sibling.iterdir())


# (d) SCANNER EXCLUSION at a NESTED staging dir: a model staged into
#     <root>/sub/.lm-pending-delete is excluded from the walk just like the
#     root-level one (depth independence).
async def test_p_model_walk_excludes_nested_staging_dir(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    (root / "normal.safetensors").write_bytes(b"normal")
    sub = root / "sub"
    sub.mkdir()
    (sub / "real.safetensors").write_bytes(b"real")
    nested_staging = sub / PENDING_DELETE_DIR_NAME / "x"
    nested_staging.mkdir(parents=True)
    (nested_staging / "model.safetensors").write_bytes(b"ghost")
    (nested_staging / "model.metadata.json").write_bytes(b'{"hash_status": "pending"}')
    # Root-level staging dir for comparison.
    root_staging = root / PENDING_DELETE_DIR_NAME / "y"
    root_staging.mkdir(parents=True)
    (root_staging / "ghost2.safetensors").write_bytes(b"ghost2")

    from py.services import model_scanner as model_scanner_module

    async def _noop_register(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(model_scanner_module.ServiceRegistry, "register_service", _noop_register)
    monkeypatch.setenv("LORA_MANAGER_DISABLE_PERSISTENT_CACHE", "1")

    scanner = DummyScannerForWalk(root)

    result = await scanner._gather_model_data()
    paths = [entry["file_path"] for entry in result.raw_data]
    assert not any(PENDING_DELETE_DIR_NAME in p for p in paths)
    # Real files at both depths are still discovered.
    assert any(p.endswith("normal.safetensors") for p in paths)
    assert any(p.endswith("sub/real.safetensors") for p in paths)

    assert scanner._count_model_files() == 2
