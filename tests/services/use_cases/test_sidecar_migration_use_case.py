"""Sidecar migration use case: layout moves, conflicts, guards."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

from py.config import config
from py.services.settings_manager import get_settings_manager
from py.services.use_cases.sidecar_migration_use_case import SidecarMigrationUseCase
from py.utils.sidecar_paths import root_mirror_component


def _normalize(path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture
def library_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Single lora root under tmp_path; every other root emptied."""

    root = tmp_path / "loras"
    root.mkdir()
    for attr, value in (
        ("loras_roots", [str(root)]),
        ("base_models_roots", []),
        ("checkpoints_roots", []),
        ("embeddings_roots", []),
        ("other_roots", []),
        ("extra_loras_roots", []),
        ("extra_checkpoints_roots", []),
        ("extra_unet_roots", []),
        ("extra_embeddings_roots", []),
    ):
        monkeypatch.setattr(config, attr, value, raising=False)
    return root


@pytest.fixture
def sidecar_root(tmp_path: Path) -> Path:
    """Configured centralized root (mode-independent for migration)."""

    root = tmp_path / "sidecars"
    get_settings_manager().set("sidecar_storage_path", str(root))
    return root


def _set_mode(mode: str) -> None:
    get_settings_manager().set("sidecar_storage_mode", mode)


def _mirror_dir(library_root: Path, sidecar_root: Path, *rel: str) -> Path:
    """Expected mirror directory for a library-relative path."""

    library = get_settings_manager().get_active_library_name()
    component = root_mirror_component(str(library_root))
    return sidecar_root.joinpath(library, component, *rel)


def _write_model(directory: Path, stem: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    model = directory / f"{stem}.safetensors"
    model.write_bytes(b"weights")
    return model


def _write_sidecar(directory: Path, stem: str, model: Path, *, preview_ext: str | None = ".preview.webp") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "file_name": stem,
        "file_path": _normalize(model),
    }
    if preview_ext:
        payload["preview_url"] = _normalize(directory / f"{stem}{preview_ext}")
    sidecar = directory / f"{stem}.metadata.json"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    return sidecar


class _FakeCache:
    def __init__(self, raw_data: List[Dict[str, Any]]) -> None:
        self.raw_data = raw_data

    async def update_preview_url(
        self, file_path: str, preview_url: str, preview_nsfw_level: int
    ) -> bool:
        for item in self.raw_data:
            if item["file_path"] == file_path:
                item["preview_url"] = preview_url
                item["preview_nsfw_level"] = preview_nsfw_level
                return True
        return False


class _FakeScanner:
    def __init__(self, raw_data: List[Dict[str, Any]]) -> None:
        self._cache = _FakeCache(raw_data)
        self.persist_calls = 0

    async def get_cached_data(self) -> _FakeCache:
        return self._cache

    async def _persist_current_cache(self) -> None:
        self.persist_calls += 1


def _make_use_case(model_paths: List[str]) -> SidecarMigrationUseCase:
    scanner = _FakeScanner([{"file_path": path} for path in model_paths])

    async def scanner_factory() -> _FakeScanner:
        return scanner

    use_case = SidecarMigrationUseCase(
        scanner_factories=(("lora", scanner_factory),),
        settings_service=get_settings_manager(),
    )
    use_case._test_scanner = scanner  # expose for cache-reconcile assertions
    return use_case


class _ProgressRecorder:
    def __init__(self) -> None:
        self.payloads: List[Dict[str, Any]] = []

    async def on_progress(self, payload: Dict[str, Any]) -> None:
        self.payloads.append(payload)


@pytest.mark.asyncio
async def test_migrate_to_centralized_moves_sidecar_and_previews(
    library_root: Path, sidecar_root: Path
):
    _set_mode("centralized")
    model = _write_model(library_root / "sub", "model")
    sidecar = _write_sidecar(library_root / "sub", "model", model)
    preview = library_root / "sub" / "model.preview.webp"
    preview.write_bytes(b"preview")
    extra_preview = library_root / "sub" / "model.png"
    extra_preview.write_bytes(b"extra")

    recorder = _ProgressRecorder()
    use_case = _make_use_case([str(model)])
    summary = await use_case.migrate_to_centralized(recorder, force=True)

    assert summary["success"] is True
    assert summary["direction"] == "to_centralized"
    assert summary["moved"] == 3
    assert summary["models_moved"] == 1
    assert summary["skipped"] == 0
    assert summary["conflicts"] == 0
    assert summary["errors"] == []

    mirror = _mirror_dir(library_root, sidecar_root, "sub")
    assert not sidecar.exists()
    assert not preview.exists()
    assert not extra_preview.exists()
    moved_sidecar = mirror / "model.metadata.json"
    assert moved_sidecar.exists()
    assert (mirror / "model.preview.webp").exists()
    assert (mirror / "model.png").exists()
    # Model files never move.
    assert model.exists()

    metadata = json.loads(moved_sidecar.read_text(encoding="utf-8"))
    assert metadata["file_path"] == _normalize(model)
    assert metadata["file_name"] == "model"
    # Recorded extension wins when rewriting preview_url.
    assert metadata["preview_url"] == _normalize(mirror / "model.preview.webp")

    statuses = [payload["status"] for payload in recorder.payloads]
    assert statuses[0] == "started"
    assert statuses[-1] == "completed"
    assert all(p["type"] == "sidecar_migration_progress" for p in recorder.payloads)

    # Scanner cache was reconciled to the mirror preview and persisted.
    entry = use_case._test_scanner._cache.raw_data[0]
    assert entry["preview_url"] == _normalize(mirror / "model.preview.webp")
    assert use_case._test_scanner.persist_calls == 1


@pytest.mark.asyncio
async def test_migrate_to_alongside_reverses_layout(
    library_root: Path, sidecar_root: Path
):
    _set_mode("alongside")
    model = _write_model(library_root / "sub", "model")
    mirror = _mirror_dir(library_root, sidecar_root, "sub")
    sidecar = _write_sidecar(mirror, "model", model)
    preview = mirror / "model.preview.webp"
    preview.write_bytes(b"preview")

    use_case = _make_use_case([str(model)])
    summary = await use_case.migrate_to_alongside(force=True)

    assert summary["success"] is True
    assert summary["moved"] == 2

    assert not sidecar.exists()
    assert not preview.exists()
    moved_sidecar = library_root / "sub" / "model.metadata.json"
    assert moved_sidecar.exists()
    assert (library_root / "sub" / "model.preview.webp").exists()

    metadata = json.loads(moved_sidecar.read_text(encoding="utf-8"))
    assert metadata["file_path"] == _normalize(model)
    assert metadata["preview_url"] == _normalize(
        library_root / "sub" / "model.preview.webp"
    )

    entry = use_case._test_scanner._cache.raw_data[0]
    assert entry["preview_url"] == _normalize(
        library_root / "sub" / "model.preview.webp"
    )
    assert use_case._test_scanner.persist_calls == 1


@pytest.mark.asyncio
async def test_migrate_conflict_keeps_newer_file(
    library_root: Path, sidecar_root: Path
):
    _set_mode("centralized")
    mirror = _mirror_dir(library_root, sidecar_root)

    # Model A: destination (mirror) sidecar is newer -> destination wins.
    model_a = _write_model(library_root, "model_a")
    src_a = _write_sidecar(library_root, "model_a", model_a, preview_ext=None)
    dst_a = _write_sidecar(mirror, "model_a", model_a, preview_ext=None)
    os.utime(src_a, (1000, 1000))
    os.utime(dst_a, (2000, 2000))

    # Model B: source (alongside) sidecar is newer -> source replaces.
    model_b = _write_model(library_root, "model_b")
    src_b = _write_sidecar(library_root, "model_b", model_b, preview_ext=None)
    dst_b = _write_sidecar(mirror, "model_b", model_b, preview_ext=None)
    (mirror / "model_b.metadata.json").write_text(
        json.dumps({"stale": True}), encoding="utf-8"
    )
    os.utime(src_b, (3000, 3000))
    os.utime(dst_b, (2000, 2000))

    use_case = _make_use_case([str(model_a), str(model_b)])
    summary = await use_case.migrate_to_centralized(force=True)

    assert summary["conflicts"] == 2
    assert summary["moved"] == 1

    # A: destination kept, source deleted, content untouched.
    assert not src_a.exists()
    metadata_a = json.loads(dst_a.read_text(encoding="utf-8"))
    assert metadata_a["file_name"] == "model_a"

    # B: newer source replaced the stale destination.
    assert not src_b.exists()
    metadata_b = json.loads(dst_b.read_text(encoding="utf-8"))
    assert metadata_b.get("stale") is None
    assert metadata_b["file_name"] == "model_b"


@pytest.mark.asyncio
async def test_migrate_missing_model_file_is_skipped(
    library_root: Path, sidecar_root: Path
):
    _set_mode("centralized")
    missing_model = library_root / "ghost.safetensors"
    sidecar = _write_sidecar(library_root, "ghost", missing_model, preview_ext=None)

    use_case = _make_use_case([str(missing_model)])
    summary = await use_case.migrate_to_centralized(force=True)

    assert summary["success"] is True
    assert summary["skipped"] == 1
    assert summary["moved"] == 0
    # Sidecar stays put when the model file is gone.
    assert sidecar.exists()


@pytest.mark.asyncio
async def test_migrate_empty_library_is_noop(
    library_root: Path, sidecar_root: Path
):
    _set_mode("centralized")
    recorder = _ProgressRecorder()
    use_case = _make_use_case([])

    summary = await use_case.migrate_to_centralized(recorder, force=True)

    assert summary["success"] is True
    assert summary["models_total"] == 0
    assert summary["moved"] == 0
    statuses = [payload["status"] for payload in recorder.payloads]
    assert statuses == ["started", "completed"]


@pytest.mark.asyncio
async def test_migrate_to_centralized_refuses_when_already_centralized(
    library_root: Path, sidecar_root: Path
):
    _set_mode("centralized")
    use_case = _make_use_case([])

    summary = await use_case.migrate_to_centralized()

    assert summary["success"] is False
    assert "already centralized" in summary["error"]
    assert summary["moved"] == 0


@pytest.mark.asyncio
async def test_migrate_to_alongside_refuses_when_already_alongside(
    library_root: Path, sidecar_root: Path
):
    _set_mode("alongside")
    use_case = _make_use_case([])

    summary = await use_case.migrate_to_alongside()

    assert summary["success"] is False
    assert "already alongside" in summary["error"]
    assert summary["moved"] == 0


def _make_use_case_with_entries(entries: List[Dict[str, Any]]) -> SidecarMigrationUseCase:
    scanner = _FakeScanner(entries)

    async def scanner_factory() -> _FakeScanner:
        return scanner

    use_case = SidecarMigrationUseCase(
        scanner_factories=(("lora", scanner_factory),),
        settings_service=get_settings_manager(),
    )
    use_case._test_scanner = scanner
    return use_case


@pytest.mark.asyncio
async def test_migrate_reconcile_clears_stale_preview_when_none_remains(
    library_root: Path, sidecar_root: Path
):
    _set_mode("centralized")
    model = _write_model(library_root, "model")
    _write_sidecar(library_root, "model", model, preview_ext=None)

    stale_url = _normalize(library_root / "model.preview.webp")
    entries = [
        {"file_path": str(model), "preview_url": stale_url, "preview_nsfw_level": 4}
    ]
    use_case = _make_use_case_with_entries(entries)
    summary = await use_case.migrate_to_centralized(force=True)

    assert summary["success"] is True
    entry = use_case._test_scanner._cache.raw_data[0]
    # No preview exists in either layout: the stale reference is cleared.
    assert entry["preview_url"] == ""
    assert use_case._test_scanner.persist_calls == 1


@pytest.mark.asyncio
async def test_migrate_reconcile_survives_per_model_errors(
    library_root: Path, sidecar_root: Path, monkeypatch: pytest.MonkeyPatch
):
    _set_mode("centralized")
    model_ok = _write_model(library_root, "ok")
    _write_sidecar(library_root, "ok", model_ok)
    (library_root / "ok.preview.webp").write_bytes(b"preview")
    model_bad = _write_model(library_root, "bad")
    _write_sidecar(library_root, "bad", model_bad, preview_ext=None)

    use_case = _make_use_case([str(model_ok), str(model_bad)])
    original = use_case._migrate_model

    async def failing_migrate(model_path: str, **kwargs):
        if os.path.basename(model_path) == "bad.safetensors":
            raise RuntimeError("boom")
        return await original(model_path, **kwargs)

    monkeypatch.setattr(use_case, "_migrate_model", failing_migrate)
    summary = await use_case.migrate_to_centralized(force=True)

    assert summary["success"] is False
    assert summary["error_count"] == 1
    # The healthy model's cache entry is still reconciled and persisted.
    ok_entry = use_case._test_scanner._cache.raw_data[0]
    assert ok_entry["preview_url"] == _normalize(
        _mirror_dir(library_root, sidecar_root) / "ok.preview.webp"
    )
    assert use_case._test_scanner.persist_calls == 1


@pytest.mark.asyncio
async def test_migrate_covers_mixed_case_and_example_previews(
    library_root: Path, sidecar_root: Path
):
    """Previews like model.WEBP / model.example.0.jpeg migrate too (#225 compat)."""

    _set_mode("centralized")
    model = _write_model(library_root, "model")
    _write_sidecar(library_root, "model", model, preview_ext=".preview.WEBP")
    (library_root / "model.preview.WEBP").write_bytes(b"preview")
    (library_root / "model.example.0.jpeg").write_bytes(b"example")

    use_case = _make_use_case([str(model)])
    summary = await use_case.migrate_to_centralized(force=True)

    assert summary["success"] is True
    assert summary["moved"] == 3  # sidecar + 2 previews

    mirror = _mirror_dir(library_root, sidecar_root)
    assert (mirror / "model.preview.WEBP").exists()
    assert (mirror / "model.example.0.jpeg").exists()
    assert not (library_root / "model.preview.WEBP").exists()
    assert not (library_root / "model.example.0.jpeg").exists()

    metadata = json.loads((mirror / "model.metadata.json").read_text(encoding="utf-8"))
    assert metadata["preview_url"] == _normalize(mirror / "model.preview.WEBP")


@pytest.mark.asyncio
async def test_migrate_root_relocates_tree_and_reconciles(
    library_root: Path, sidecar_root: Path, tmp_path: Path
):
    _set_mode("centralized")
    library = get_settings_manager().get_active_library_name()
    component = root_mirror_component(str(library_root))

    # Assets under the OLD root, mirroring the layout.
    old_root = tmp_path / "old_sidecars"
    old_mirror = old_root / library / component / "sub"
    old_mirror.mkdir(parents=True)
    model = _write_model(library_root / "sub", "model")
    payload = {
        "file_name": "model",
        "file_path": _normalize(model),
        "preview_url": _normalize(old_mirror / "model.preview.png"),
    }
    (old_mirror / "model.metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    (old_mirror / "model.preview.png").write_bytes(b"preview")

    entries = [
        {
            "file_path": str(model),
            "preview_url": _normalize(old_mirror / "model.preview.png"),
            "preview_nsfw_level": 2,
        }
    ]
    use_case = _make_use_case_with_entries(entries)
    summary = await use_case.migrate_root(str(old_root), force=True)

    assert summary["success"] is True
    assert summary["moved"] == 2

    new_mirror = sidecar_root / library / component / "sub"
    assert (new_mirror / "model.metadata.json").exists()
    assert (new_mirror / "model.preview.png").exists()

    # Sidecar preview_url rewritten onto the new root.
    migrated = json.loads((new_mirror / "model.metadata.json").read_text(encoding="utf-8"))
    assert migrated["preview_url"] == _normalize(new_mirror / "model.preview.png")
    # Model path fields untouched — model files never move.
    assert migrated["file_path"] == _normalize(model)

    # Scanner cache preview URLs repointed and persisted.
    entry = use_case._test_scanner._cache.raw_data[0]
    assert entry["preview_url"] == _normalize(new_mirror / "model.preview.png")
    assert use_case._test_scanner.persist_calls == 1

    # Emptied old tree pruned.
    assert not old_root.exists()


@pytest.mark.asyncio
async def test_migrate_root_guards(
    library_root: Path, sidecar_root: Path, tmp_path: Path
):
    _set_mode("centralized")
    use_case = _make_use_case([])

    summary = await use_case.migrate_root("")
    assert summary["success"] is False
    assert "old_root is required" in summary["error"]

    summary = await use_case.migrate_root(str(sidecar_root))
    assert summary["success"] is False
    assert "matches the configured" in summary["error"]

    _set_mode("alongside")
    summary = await use_case.migrate_root(str(tmp_path / "old_sidecars"))
    assert summary["success"] is False
    assert "not centralized" in summary["error"]


@pytest.mark.asyncio
async def test_migrate_root_missing_old_tree_is_noop(
    library_root: Path, sidecar_root: Path, tmp_path: Path
):
    _set_mode("centralized")
    use_case = _make_use_case([])

    summary = await use_case.migrate_root(str(tmp_path / "nonexistent"), force=True)

    assert summary["success"] is True
    assert summary["moved"] == 0
