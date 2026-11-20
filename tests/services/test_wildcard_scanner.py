from __future__ import annotations

import pytest

from py.services.model_cache import ModelCache
from py.services.model_scanner import ModelScanner
from py.services.wildcard_scanner import WildcardScanner
from py.utils.models import WildcardMetadata


@pytest.mark.asyncio
async def test_default_metadata_contains_parsed_index(tmp_path):
    artifact = tmp_path / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    scanner = WildcardScanner()

    metadata = await scanner._create_default_metadata(str(artifact))

    assert isinstance(metadata, WildcardMetadata)
    assert metadata.wildcard_format == "txt"
    assert metadata.entry_count == 1
    assert metadata.value_count == 2
    assert metadata.entries[0]["key"] == "colors"
    assert metadata.sha256


@pytest.mark.asyncio
async def test_cache_entry_keeps_parsed_index(tmp_path):
    artifact = tmp_path / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    scanner = WildcardScanner()

    metadata = await scanner._create_default_metadata(str(artifact))
    entry = scanner._build_cache_entry(metadata)

    assert entry["wildcard_format"] == "txt"
    assert entry["files"] == ["colors.txt"]
    assert entry["entries"][0]["key"] == "colors"
    assert entry["entry_count"] == 1
    assert entry["value_count"] == 2


@pytest.mark.asyncio
async def test_backfill_restores_index_for_hydrated_entries(tmp_path, monkeypatch):
    artifact = tmp_path / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    scanner = WildcardScanner()
    metadata = await scanner._create_default_metadata(str(artifact))

    hydrated = {
        "file_path": metadata.file_path,
        "file_name": metadata.file_name,
        "model_name": metadata.model_name,
        "sha256": metadata.sha256,
    }
    scanner._cache = ModelCache(raw_data=[hydrated], folders=[])

    persisted = []

    async def fake_persist():
        persisted.append(True)

    monkeypatch.setattr(scanner, "_persist_current_cache", fake_persist)

    await scanner._backfill_parsed_index()

    assert hydrated["wildcard_format"] == "txt"
    assert hydrated["files"] == ["colors.txt"]
    assert hydrated["entries"][0]["key"] == "colors"
    assert hydrated["entry_count"] == 1
    assert hydrated["value_count"] == 2
    assert persisted == [True]


def test_civitai_metadata_uses_model_and_version_identity():
    version = {
        "id": 20,
        "modelId": 10,
        "name": "v1",
        "baseModel": "Other",
        "model": {"name": "Pack", "type": "Wildcards", "tags": ["style"]},
    }
    file_info = {"name": "pack.zip", "sizeKB": 2, "hashes": {"SHA256": "abc"}}

    metadata = WildcardMetadata.from_civitai_info(version, file_info, "/library/pack.zip")

    assert metadata.model_name == "Pack"
    assert metadata.civitai["id"] == 20
    assert metadata.sub_type == "wildcard"
    assert metadata.wildcard_format == "zip"


class ActivationServiceStub:
    def __init__(self):
        self.moves = None
        self.resources = None
        self.reconcile_result = {}

    def rebind_paths(self, moves):
        self.moves = dict(moves)
        return {
            old: {"file_path": new, "active": True}
            for old, new in moves.items()
        }

    def reconcile_resources(self, resources):
        self.resources = resources
        return self.reconcile_result


@pytest.mark.asyncio
async def test_cache_path_update_rebinds_activation(tmp_path, monkeypatch):
    activation = ActivationServiceStub()
    scanner = WildcardScanner(activation_service=activation)
    old_path = str(tmp_path / "old" / "colors.txt")
    new_path = str(tmp_path / "new" / "colors.txt")

    async def fake_update(self, original_path, new_path, metadata):
        return True

    notifications = []

    async def fake_notify(rebound):
        notifications.append(rebound)

    monkeypatch.setattr(ModelScanner, "update_single_model_cache", fake_update)
    monkeypatch.setattr(scanner, "_notify_activation_rebindings", fake_notify)

    result = await scanner.update_single_model_cache(old_path, new_path, None)

    assert result is True
    assert activation.moves == {old_path: new_path}
    assert notifications == [{old_path: {"file_path": new_path, "active": True}}]


@pytest.mark.asyncio
async def test_folder_rename_rebinds_nested_activation_paths(tmp_path, monkeypatch):
    activation = ActivationServiceStub()
    scanner = WildcardScanner(activation_service=activation)
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_path = str(old_dir / "nested" / "colors.txt")
    unrelated_path = str(tmp_path / "other" / "colors.txt")
    scanner._cache = ModelCache(
        raw_data=[
            {"file_path": old_path},
            {"file_path": unrelated_path},
        ],
        folders=[],
    )

    async def fake_rename(self, previous_folder, new_folder, *, previous_path, new_path):
        return True

    async def fake_notify(rebound):
        return None

    monkeypatch.setattr(ModelScanner, "rename_known_folder", fake_rename)
    monkeypatch.setattr(scanner, "_notify_activation_rebindings", fake_notify)

    changed = await scanner.rename_known_folder(
        "old",
        "new",
        previous_path=str(old_dir),
        new_path=str(new_dir),
    )

    assert changed is True
    assert activation.moves == {old_path: str(new_dir / "nested" / "colors.txt")}


@pytest.mark.asyncio
async def test_initialize_reconciles_external_moves_before_backfill(tmp_path, monkeypatch):
    activation = ActivationServiceStub()
    old_path = str(tmp_path / "old.txt")
    new_path = str(tmp_path / "new.txt")
    activation.reconcile_result = {
        old_path: {"file_path": new_path, "active": True},
    }
    scanner = WildcardScanner(activation_service=activation)
    resources = [{"file_path": new_path, "sha256": "hash"}]
    calls = []

    async def fake_initialize(self, reconcile=False):
        scanner._cache = ModelCache(raw_data=resources, folders=[])
        calls.append("scan")

    async def fake_backfill():
        calls.append("backfill")

    notifications = []

    async def fake_notify(rebound):
        notifications.append(rebound)

    monkeypatch.setattr(ModelScanner, "initialize_in_background", fake_initialize)
    monkeypatch.setattr(scanner, "_backfill_parsed_index", fake_backfill)
    monkeypatch.setattr(scanner, "_notify_activation_rebindings", fake_notify)

    await scanner.initialize_in_background(reconcile=True)

    assert activation.resources is resources
    assert notifications == [activation.reconcile_result]
    assert calls == ["scan", "backfill"]


@pytest.mark.asyncio
async def test_rebind_notification_includes_old_and_new_paths(tmp_path, monkeypatch):
    scanner = WildcardScanner(activation_service=ActivationServiceStub())
    monkeypatch.setenv("LORA_MANAGER_STANDALONE", "1")
    events = []

    async def fake_broadcast(payload):
        events.append(payload)

    monkeypatch.setattr("py.services.wildcard_scanner.ws_manager.broadcast", fake_broadcast)
    old_path = str(tmp_path / "old.txt")
    new_path = str(tmp_path / "new.txt")

    await scanner._notify_activation_rebindings({
        old_path: {"file_path": new_path, "active": False},
    })

    assert events == [{
        "type": "wildcard_activation_changed",
        "file_path": new_path,
        "previous_file_path": old_path,
        "active": False,
    }]
