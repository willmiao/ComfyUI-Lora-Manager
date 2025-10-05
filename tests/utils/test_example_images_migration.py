import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from py.utils import example_images_migration as migration_module


class FakeScanner:
    def __init__(self, data_map, init_cycles=0):
        self._data_map = data_map
        self._init_cycles = init_cycles
        self.update_calls = []

    def is_initializing(self):
        if self._init_cycles > 0:
            self._init_cycles -= 1
            return True
        return False

    def has_hash(self, hash_value):
        return hash_value in self._data_map

    async def get_cached_data(self):
        payload = [copy.deepcopy(item) for item in self._data_map.values()]
        return SimpleNamespace(raw_data=payload)

    async def update_single_model_cache(self, *args):
        self.update_calls.append(args)


@pytest.mark.asyncio
async def test_migrations_run_and_update_progress(tmp_path, monkeypatch):
    example_root = tmp_path / "example_images"
    library_root = example_root / "main"
    missing_library = tmp_path / "missing"
    library_root.mkdir(parents=True)

    progress_path = library_root / ".download_progress.json"
    progress_path.write_text(json.dumps({"naming_version": 0, "keep": "value"}))

    migrating_hash = "a" * 64
    migrating_folder = library_root / migrating_hash
    migrating_folder.mkdir()
    (migrating_folder / "image_1.png").write_bytes(b"one")
    (migrating_folder / "image_2.png").write_bytes(b"two")

    zero_based_hash = "b" * 64
    zero_based_folder = library_root / zero_based_hash
    zero_based_folder.mkdir()
    (zero_based_folder / "image_0.png").write_bytes(b"zero")
    (zero_based_folder / "image_1.png").write_bytes(b"one")

    rename_only_hash = "c" * 64
    rename_only_folder = library_root / rename_only_hash
    rename_only_folder.mkdir()
    (rename_only_folder / "image_1.png").write_bytes(b"needs rename")

    metadata_path = tmp_path / "models" / "model.safetensors"
    metadata_path.parent.mkdir()

    metadata_entry = {
        "sha256": migrating_hash,
        "file_path": str(metadata_path),
        "civitai": {
            "images": [
                {"url": "", "type": "image", "prompt": "custom"},
                {"url": "https://example.com/remote.png", "type": "image"},
            ],
            "customImages": [],
        },
    }

    lora_scanner = FakeScanner({migrating_hash: metadata_entry}, init_cycles=1)
    checkpoint_scanner = FakeScanner({}, init_cycles=0)

    async def fake_get_lora_scanner(cls):
        return lora_scanner

    async def fake_get_checkpoint_scanner(cls):
        return checkpoint_scanner

    monkeypatch.setattr(
        migration_module.ServiceRegistry,
        "get_lora_scanner",
        classmethod(fake_get_lora_scanner),
    )
    monkeypatch.setattr(
        migration_module.ServiceRegistry,
        "get_checkpoint_scanner",
        classmethod(fake_get_checkpoint_scanner),
    )

    monkeypatch.setattr(
        migration_module.settings,
        "get",
        lambda key, default=None: str(example_root) if key == "example_images_path" else default,
    )

    monkeypatch.setattr(
        migration_module,
        "iter_library_roots",
        lambda: [("main", str(library_root)), ("missing", str(missing_library))],
    )

    saved_metadata = []

    async def fake_save_metadata(path, metadata):
        saved_metadata.append((path, metadata))
        return True

    monkeypatch.setattr(
        migration_module.MetadataManager,
        "save_metadata",
        staticmethod(fake_save_metadata),
    )

    short_ids = iter(["short1234"])
    monkeypatch.setattr(
        migration_module.ExampleImagesProcessor,
        "generate_short_id",
        staticmethod(lambda: next(short_ids)),
    )

    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)
        return None

    monkeypatch.setattr(migration_module.asyncio, "sleep", fake_sleep)

    scheduled_tasks = []
    original_create_task = asyncio.create_task

    def capture_create_task(coro, *args, **kwargs):
        task = original_create_task(coro, *args, **kwargs)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(migration_module.asyncio, "create_task", capture_create_task)

    await migration_module.ExampleImagesMigration.check_and_run_migrations()

    assert len(scheduled_tasks) == 1
    await asyncio.gather(*scheduled_tasks)

    progress_data = json.loads(progress_path.read_text())
    assert progress_data["naming_version"] == migration_module.CURRENT_NAMING_VERSION
    assert progress_data["keep"] == "value"

    assert not (migrating_folder / "image_0.png").exists()
    assert (migrating_folder / "custom_short1234.png").exists()
    assert (migrating_folder / "image_1.png").exists()

    assert (zero_based_folder / "image_0.png").exists()
    assert (zero_based_folder / "image_1.png").exists()

    assert (rename_only_folder / "image_0.png").exists()
    assert not (rename_only_folder / "image_1.png").exists()

    assert not missing_library.exists()

    assert any(delay == 1 for delay in sleep_calls)

    assert len(saved_metadata) == 1
    saved_path, saved_payload = saved_metadata[0]
    assert saved_path == str(metadata_path)
    assert saved_payload["civitai"]["customImages"][0]["id"] == "short1234"
    assert saved_payload["civitai"]["images"] == [
        {"url": "https://example.com/remote.png", "type": "image"}
    ]

    assert len(lora_scanner.update_calls) == 1
    update_args = lora_scanner.update_calls[0]
    assert update_args[0] == str(metadata_path)
    assert update_args[2]["civitai"]["customImages"][0]["id"] == "short1234"
