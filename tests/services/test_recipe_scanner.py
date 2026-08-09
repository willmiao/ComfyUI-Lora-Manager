import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from py.config import config
from py.services import model_scanner as model_scanner_module
from py.services.model_cache import ModelCache
from py.services.model_hash_index import ModelHashIndex
from py.services.model_scanner import CacheBuildResult, ModelScanner
from py.services.recipe_scanner import RecipeScanner
from py.services import settings_manager as settings_manager_module
from py.utils.models import BaseModelMetadata
from py.utils.utils import calculate_recipe_fingerprint


class StubHashIndex:
    def __init__(self) -> None:
        self._hash_to_path: dict[str, str] = {}

    def get_path(self, hash_value: str) -> str | None:
        return self._hash_to_path.get(hash_value)


class StubLoraScanner:
    def __init__(self) -> None:
        self._hash_index = StubHashIndex()
        self._hash_meta: dict[str, dict[str, str]] = {}
        self._models_by_name: dict[str, Dict[str, Any]] = {}
        self._cache = SimpleNamespace(raw_data=[], version_index={})

    async def get_cached_data(self):
        return self._cache

    def has_hash(self, hash_value: str) -> bool:
        return hash_value.lower() in self._hash_meta

    def get_preview_url_by_hash(self, hash_value: str) -> str:
        meta = self._hash_meta.get(hash_value.lower())
        return meta.get("preview_url", "") if meta else ""

    def get_path_by_hash(self, hash_value: str) -> str | None:
        meta = self._hash_meta.get(hash_value.lower())
        return meta.get("path") if meta else None

    async def get_model_info_by_name(self, name: str):
        return self._models_by_name.get(name)

    def register_model(self, name: str, info: Dict[str, Any]) -> None:
        self._models_by_name[name] = info
        hash_value = (info.get("sha256") or "").lower()
        version_id = info.get("civitai", {}).get("id")
        if hash_value:
            self._hash_meta[hash_value] = {
                "path": info.get("file_path", ""),
                "preview_url": info.get("preview_url", ""),
            }
            self._hash_index._hash_to_path[hash_value] = info.get("file_path", "")
        if version_id is not None:
            self._cache.version_index[int(version_id)] = {
                "file_path": info.get("file_path", ""),
                "sha256": hash_value,
                "preview_url": info.get("preview_url", ""),
                "civitai": info.get("civitai", {}),
            }
        self._cache.raw_data.append(
            {
                "sha256": info.get("sha256", ""),
                "path": info.get("file_path", ""),
                "civitai": info.get("civitai", {}),
            }
        )


@pytest.fixture
def recipe_scanner(tmp_path: Path, monkeypatch):
    RecipeScanner._instance = None
    settings_manager_module.reset_settings_manager()
    monkeypatch.setattr(config, "loras_roots", [str(tmp_path)])
    stub = StubLoraScanner()
    scanner = RecipeScanner(lora_scanner=stub)  # pyright: ignore[reportArgumentType]

    async def _init():
        await scanner.refresh_cache(force=True)
        # Wait for FTS index build to finish — asyncio.run()
        # cancels background tasks on return, so we must await it here.
        if scanner._fts_index_task:
            await scanner._fts_index_task

    asyncio.run(_init())
    yield scanner, stub
    RecipeScanner._instance = None
    settings_manager_module.reset_settings_manager()


def test_recipes_dir_uses_custom_settings_path(tmp_path: Path, monkeypatch):
    RecipeScanner._instance = None
    settings_manager_module.reset_settings_manager()

    settings_path = tmp_path / "settings.json"
    custom_recipes = tmp_path / "custom" / ".." / "custom_recipes"

    monkeypatch.setattr(
        "py.services.settings_manager.ensure_settings_file",
        lambda logger=None: str(settings_path),
    )
    monkeypatch.setattr(config, "loras_roots", [str(tmp_path / "loras-root")])

    manager = settings_manager_module.get_settings_manager()
    manager.set("recipes_path", str(custom_recipes))

    scanner = RecipeScanner(lora_scanner=StubLoraScanner())  # pyright: ignore[reportArgumentType]
    resolved = scanner.recipes_dir

    assert resolved == str((tmp_path / "custom_recipes").resolve())
    assert Path(resolved).is_dir()

    RecipeScanner._instance = None
    settings_manager_module.reset_settings_manager()


def test_recipes_dir_falls_back_to_first_lora_root(tmp_path: Path, monkeypatch):
    RecipeScanner._instance = None
    settings_manager_module.reset_settings_manager()

    monkeypatch.setattr(config, "loras_roots", [str(tmp_path / "alpha")])

    scanner = RecipeScanner(lora_scanner=StubLoraScanner())  # pyright: ignore[reportArgumentType]
    resolved = scanner.recipes_dir

    assert resolved == str(tmp_path / "alpha" / "recipes")
    assert Path(resolved).is_dir()

    RecipeScanner._instance = None
    settings_manager_module.reset_settings_manager()


async def test_add_recipe_during_concurrent_reads(recipe_scanner):
    scanner, _ = recipe_scanner

    initial_recipe = {
        "id": "one",
        "file_path": "path/a.png",
        "title": "First",
        "modified": 1.0,
        "created_date": 1.0,
        "loras": [],
    }
    await scanner.add_recipe(initial_recipe)

    new_recipe = {
        "id": "two",
        "file_path": "path/b.png",
        "title": "Second",
        "modified": 2.0,
        "created_date": 2.0,
        "loras": [],
    }

    async def reader_task():
        for _ in range(5):
            cache = await scanner.get_cached_data()
            _ = [item["id"] for item in cache.raw_data]
            await asyncio.sleep(0)

    await asyncio.gather(reader_task(), reader_task(), scanner.add_recipe(new_recipe))
    # Wait a bit longer for the thread-pool resort to complete
    await asyncio.sleep(0.1)
    cache = await scanner.get_cached_data()

    assert {item["id"] for item in cache.raw_data} == {"one", "two"}
    assert len(cache.sorted_by_name) == len(cache.raw_data)


async def test_remove_recipe_during_reads(recipe_scanner):
    scanner, _ = recipe_scanner

    recipe_ids = ["alpha", "beta", "gamma"]
    for index, recipe_id in enumerate(recipe_ids):
        await scanner.add_recipe(
            {
                "id": recipe_id,
                "file_path": f"path/{recipe_id}.png",
                "title": recipe_id,
                "modified": float(index),
                "created_date": float(index),
                "loras": [],
            }
        )

    async def reader_task():
        for _ in range(5):
            cache = await scanner.get_cached_data()
            _ = list(cache.sorted_by_date)
            await asyncio.sleep(0)

    await asyncio.gather(reader_task(), scanner.remove_recipe("beta"))
    await asyncio.sleep(0)
    cache = await scanner.get_cached_data()

    assert {item["id"] for item in cache.raw_data} == {"alpha", "gamma"}


async def test_update_lora_entry_updates_cache_and_file(tmp_path: Path, recipe_scanner):
    scanner, stub = recipe_scanner
    recipes_dir = Path(config.loras_roots[0]) / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    recipe_id = "recipe-1"
    recipe_path = recipes_dir / f"{recipe_id}.recipe.json"
    recipe_data = {
        "id": recipe_id,
        "file_path": str(tmp_path / "image.png"),
        "title": "Original",
        "modified": 0.0,
        "created_date": 0.0,
        "loras": [
            {
                "file_name": "old",
                "strength": 1.0,
                "hash": "",
                "isDeleted": True,
                "exclude": True,
            },
        ],
    }
    recipe_path.write_text(json.dumps(recipe_data))

    await scanner.add_recipe(dict(recipe_data))

    target_hash = "abc123"
    target_info = {
        "sha256": target_hash,
        "file_path": str(tmp_path / "loras" / "target.safetensors"),
        "preview_url": "preview.png",
        "civitai": {"id": 42, "name": "v1", "model": {"name": "Target"}},
    }
    stub.register_model("target", target_info)

    updated_recipe, updated_lora = await scanner.update_lora_entry(
        recipe_id,
        0,
        target_name="target",
        target_lora=target_info,
    )

    assert updated_lora["inLibrary"] is True
    assert updated_lora["localPath"] == target_info["file_path"]
    assert updated_lora["hash"] == target_hash

    with recipe_path.open("r", encoding="utf-8") as file_obj:
        persisted = json.load(file_obj)

    expected_fingerprint = calculate_recipe_fingerprint(persisted["loras"])
    assert persisted["fingerprint"] == expected_fingerprint

    cache = await scanner.get_cached_data()
    cached_recipe = next(item for item in cache.raw_data if item["id"] == recipe_id)
    assert cached_recipe["loras"][0]["hash"] == target_hash
    assert cached_recipe["fingerprint"] == expected_fingerprint


@pytest.mark.asyncio
async def test_load_recipe_rewrites_missing_image_path(tmp_path: Path, recipe_scanner):
    scanner, _ = recipe_scanner
    recipes_dir = Path(config.loras_roots[0]) / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    recipe_id = "moved"
    old_root = tmp_path / "old_root"
    old_path = old_root / "recipes" / f"{recipe_id}.webp"
    recipe_path = recipes_dir / f"{recipe_id}.recipe.json"
    current_image = recipes_dir / f"{recipe_id}.webp"
    current_image.write_bytes(b"image-bytes")

    recipe_data = {
        "id": recipe_id,
        "file_path": str(old_path),
        "title": "Relocated",
        "modified": 0.0,
        "created_date": 0.0,
        "loras": [],
    }
    recipe_path.write_text(json.dumps(recipe_data))

    loaded = await scanner._load_recipe_file(str(recipe_path))

    expected_path = os.path.normpath(str(current_image))
    assert loaded["file_path"] == expected_path

    persisted = json.loads(recipe_path.read_text())
    assert persisted["file_path"] == expected_path


@pytest.mark.asyncio
async def test_load_recipe_upgrades_string_checkpoint(tmp_path: Path, recipe_scanner):
    scanner, _ = recipe_scanner
    recipes_dir = Path(config.loras_roots[0]) / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    recipe_id = "legacy-checkpoint"
    image_path = recipes_dir / f"{recipe_id}.webp"
    recipe_path = recipes_dir / f"{recipe_id}.recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": str(image_path),
                "title": "Legacy",
                "modified": 0.0,
                "created_date": 0.0,
                "loras": [],
                "checkpoint": "sd15.safetensors",
            }
        )
    )

    loaded = await scanner._load_recipe_file(str(recipe_path))

    assert isinstance(loaded["checkpoint"], dict)
    assert loaded["checkpoint"]["name"] == "sd15.safetensors"
    assert loaded["checkpoint"]["file_name"] == "sd15"


@pytest.mark.asyncio
async def test_get_paginated_data_normalizes_legacy_checkpoint(recipe_scanner):
    scanner, _ = recipe_scanner
    image_path = Path(config.loras_roots[0]) / "legacy.webp"
    await scanner.add_recipe(
        {
            "id": "legacy-checkpoint",
            "file_path": str(image_path),
            "title": "Legacy",
            "modified": 0.0,
            "created_date": 0.0,
            "loras": [],
            "checkpoint": ["legacy.safetensors"],
        }
    )
    await asyncio.sleep(0)

    result = await scanner.get_paginated_data(page=1, page_size=5)

    checkpoint = result["items"][0]["checkpoint"]
    assert checkpoint["name"] == "legacy.safetensors"
    assert checkpoint["file_name"] == "legacy"


@pytest.mark.asyncio
async def test_get_recipe_by_id_handles_non_dict_checkpoint(recipe_scanner):
    scanner, _ = recipe_scanner
    image_path = Path(config.loras_roots[0]) / "by-id.webp"
    await scanner.add_recipe(
        {
            "id": "by-id-checkpoint",
            "file_path": str(image_path),
            "title": "ById",
            "modified": 0.0,
            "created_date": 0.0,
            "loras": [],
            "checkpoint": ("by-id.safetensors",),
        }
    )

    recipe = await scanner.get_recipe_by_id("by-id-checkpoint")

    assert recipe["checkpoint"]["name"] == "by-id.safetensors"
    assert recipe["checkpoint"]["file_name"] == "by-id"


@pytest.mark.asyncio
async def test_get_recipe_by_id_merges_recipe_json_details(recipe_scanner):
    scanner, _ = recipe_scanner
    recipes_dir = Path(scanner.recipes_dir)
    recipe_id = "hydrate-me"
    recipe_json_path = recipes_dir / f"{recipe_id}.recipe.json"
    recipe_json_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": "/tmp/hydrate-me.png",
                "title": "Hydrated Recipe",
                "source_path": "https://example.com/source",
                "gen_params": {
                    "prompt": "prompt from json",
                    "negative_prompt": "negative from json",
                },
                "loras": [],
            }
        ),
        encoding="utf-8",
    )

    scanner._cache.raw_data = [
        {
            "id": recipe_id,
            "file_path": "/tmp/hydrate-me.png",
            "title": "Cached Recipe",
            "folder": "",
            "modified": 0.0,
            "created_date": 0.0,
            "loras": [],
            "gen_params": {},
        }
    ]

    recipe = await scanner.get_recipe_by_id(recipe_id)

    assert recipe is not None
    assert recipe["title"] == "Hydrated Recipe"
    assert recipe["source_path"] == "https://example.com/source"
    assert recipe["gen_params"]["prompt"] == "prompt from json"


@pytest.mark.asyncio
async def test_get_recipe_by_id_normalizes_gen_params_aliases_without_dropping_metadata(
    recipe_scanner,
):
    scanner, _ = recipe_scanner
    recipes_dir = Path(scanner.recipes_dir)
    recipe_id = "dirty-json-gen-params"
    recipe_json_path = recipes_dir / f"{recipe_id}.recipe.json"
    recipe_json_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": "/tmp/dirty-json-gen-params.png",
                "title": "Dirty Recipe",
                "gen_params": {
                    "Prompt": "prompt from json",
                    "negativePrompt": "negative from json",
                    "cfgScale": 7,
                    "raw_metadata": {"prompt": "nested"},
                    "Version": "ComfyUI",
                    "RNG": "cpu",
                },
                "loras": [],
            }
        ),
        encoding="utf-8",
    )

    scanner._cache.raw_data = [
        {
            "id": recipe_id,
            "file_path": "/tmp/dirty-json-gen-params.png",
            "title": "Cached Recipe",
            "folder": "",
            "modified": 0.0,
            "created_date": 0.0,
            "loras": [],
            "gen_params": {"prompt": "cached prompt", "raw_metadata": {"bad": True}},
        }
    ]

    recipe = await scanner.get_recipe_by_id(recipe_id)

    assert recipe is not None
    assert recipe["gen_params"]["Prompt"] == "prompt from json"
    assert recipe["gen_params"]["negativePrompt"] == "negative from json"
    assert recipe["gen_params"]["cfgScale"] == 7
    assert recipe["gen_params"]["raw_metadata"] == {"prompt": "nested"}
    assert recipe["gen_params"]["Version"] == "ComfyUI"
    assert recipe["gen_params"]["RNG"] == "cpu"
    assert recipe["gen_params"]["prompt"] == "prompt from json"
    assert recipe["gen_params"]["negative_prompt"] == "negative from json"
    assert recipe["gen_params"]["cfg_scale"] == 7


@pytest.mark.asyncio
async def test_get_recipe_by_id_prefers_json_file_path(recipe_scanner):
    scanner, _ = recipe_scanner
    recipes_dir = Path(scanner.recipes_dir)
    recipe_id = "move-me"
    recipe_json_path = recipes_dir / f"{recipe_id}.recipe.json"
    recipe_json_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": "/tmp/new-location.png",
                "title": "Moved Recipe",
                "source_path": "https://example.com/moved",
                "gen_params": {},
                "loras": [],
            }
        ),
        encoding="utf-8",
    )

    scanner._cache.raw_data = [
        {
            "id": recipe_id,
            "file_path": "/tmp/old-location.png",
            "title": "Cached Title",
            "folder": "",
            "modified": 0.0,
            "created_date": 0.0,
            "loras": [],
            "gen_params": {},
        }
    ]

    recipe = await scanner.get_recipe_by_id(recipe_id)

    assert recipe is not None
    assert recipe["file_path"] == "/tmp/new-location.png"
    assert recipe["title"] == "Moved Recipe"
    assert recipe["source_path"] == "https://example.com/moved"


@pytest.mark.asyncio
async def test_get_recipe_by_id_drops_deleted_optional_json_fields(recipe_scanner):
    scanner, _ = recipe_scanner
    recipes_dir = Path(scanner.recipes_dir)
    recipe_id = "drop-optional-fields"
    recipe_json_path = recipes_dir / f"{recipe_id}.recipe.json"
    recipe_json_path.write_text(
        json.dumps(
            {
                "id": recipe_id,
                "file_path": "/tmp/drop-optional-fields.png",
                "title": "Trimmed Recipe",
            }
        ),
        encoding="utf-8",
    )

    scanner._cache.raw_data = [
        {
            "id": recipe_id,
            "file_path": "/tmp/drop-optional-fields.png",
            "title": "Cached Recipe",
            "folder": "",
            "modified": 0.0,
            "created_date": 0.0,
            "source_path": "https://example.com/stale-source",
            "checkpoint": {"name": "stale-checkpoint.safetensors"},
            "loras": [{"modelName": "stale-lora"}],
            "gen_params": {"prompt": "stale prompt"},
        }
    ]

    recipe = await scanner.get_recipe_by_id(recipe_id)

    assert recipe is not None
    assert recipe["title"] == "Trimmed Recipe"
    assert "source_path" not in recipe
    assert "checkpoint" not in recipe
    assert "gen_params" not in recipe
    assert "loras" not in recipe


@pytest.mark.asyncio
async def test_get_paginated_data_filters_by_checkpoint_hash(recipe_scanner):
    scanner, _ = recipe_scanner
    image_path = Path(config.loras_roots[0]) / "checkpoint-filter.webp"
    await scanner.add_recipe(
        {
            "id": "checkpoint-match",
            "file_path": str(image_path),
            "title": "Checkpoint Match",
            "modified": 0.0,
            "created_date": 0.0,
            "loras": [],
            "checkpoint": {
                "name": "flux-base.safetensors",
                "hash": "ABC123",
            },
        }
    )
    await scanner.add_recipe(
        {
            "id": "checkpoint-miss",
            "file_path": str(Path(config.loras_roots[0]) / "checkpoint-miss.webp"),
            "title": "Checkpoint Miss",
            "modified": 1.0,
            "created_date": 1.0,
            "loras": [],
            "checkpoint": {
                "name": "other.safetensors",
                "hash": "zzz999",
            },
        }
    )
    await asyncio.sleep(0)

    result = await scanner.get_paginated_data(
        page=1,
        page_size=10,
        checkpoint_hash="abc123",
    )

    assert [item["id"] for item in result["items"]] == ["checkpoint-match"]


@pytest.mark.asyncio
async def test_get_paginated_data_normalizes_gen_params_aliases_without_dropping_metadata(
    recipe_scanner,
):
    scanner, _ = recipe_scanner
    await scanner.add_recipe(
        {
            "id": "dirty-listing",
            "file_path": str(Path(config.loras_roots[0]) / "dirty-listing.webp"),
            "title": "Dirty Listing",
            "modified": 0.0,
            "created_date": 0.0,
            "loras": [],
            "gen_params": {
                "Prompt": "a beautiful forest landscape",
                "cfgScale": 7,
                "Version": "ComfyUI",
                "raw_metadata": {"bad": True},
            },
        }
    )
    await asyncio.sleep(0)

    result = await scanner.get_paginated_data(page=1, page_size=10)
    item = next(entry for entry in result["items"] if entry["id"] == "dirty-listing")

    assert item["gen_params"]["Prompt"] == "a beautiful forest landscape"
    assert item["gen_params"]["cfgScale"] == 7
    assert item["gen_params"]["Version"] == "ComfyUI"
    assert item["gen_params"]["raw_metadata"] == {"bad": True}
    assert item["gen_params"]["prompt"] == "a beautiful forest landscape"
    assert item["gen_params"]["cfg_scale"] == 7


@pytest.mark.asyncio
async def test_get_recipes_for_checkpoint_matches_hash_case_insensitively(recipe_scanner):
    scanner, _ = recipe_scanner
    image_path = Path(config.loras_roots[0]) / "checkpoint-linked.webp"
    await scanner.add_recipe(
        {
            "id": "checkpoint-linked",
            "file_path": str(image_path),
            "title": "Checkpoint Linked",
            "modified": 0.0,
            "created_date": 0.0,
            "loras": [],
            "checkpoint": {
                "name": "flux-base.safetensors",
                "hash": "ABC123",
            },
        }
    )

    recipes = await scanner.get_recipes_for_checkpoint("abc123")

    assert len(recipes) == 1
    assert recipes[0]["id"] == "checkpoint-linked"
    assert recipes[0]["checkpoint"]["hash"] == "ABC123"


def test_enrich_uses_version_index_when_hash_missing(recipe_scanner):
    scanner, stub = recipe_scanner
    version_id = 77
    file_path = str(Path(config.loras_roots[0]) / "loras" / "version-entry.safetensors")
    registered = {
        "sha256": "deadbeef",
        "file_path": file_path,
        "preview_url": "preview-from-cache.png",
        "civitai": {"id": version_id},
    }
    stub.register_model("version-entry", registered)

    lora = {"hash": "", "file_name": "", "modelVersionId": version_id, "strength": 0.5}

    enriched = scanner._enrich_lora_entry(dict(lora))

    assert enriched["inLibrary"] is True
    assert enriched["hash"] == registered["sha256"]
    assert enriched["localPath"] == file_path
    assert enriched["file_name"] == Path(file_path).stem
    assert enriched["preview_url"] == registered["preview_url"]


def test_enrich_formats_absolute_preview_paths(recipe_scanner, tmp_path):
    scanner, stub = recipe_scanner
    version_id = 88
    preview_path = tmp_path / "loras" / "version-entry.preview.jpeg"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text("preview")
    model_path = tmp_path / "loras" / "version-entry.safetensors"
    model_path.write_text("weights")

    stub.register_model(
        "absolute-preview",
        {
            "sha256": "feedface",
            "file_path": str(model_path),
            "preview_url": str(preview_path),
            "civitai": {"id": version_id},
        },
    )

    lora = {"hash": "", "file_name": "", "modelVersionId": version_id, "strength": 0.5}

    enriched = scanner._enrich_lora_entry(dict(lora))

    assert enriched["preview_url"] == config.get_preview_static_url(str(preview_path))


@pytest.mark.asyncio
async def test_initialize_waits_for_lora_scanner(monkeypatch):
    ready_flag = asyncio.Event()
    call_count = 0

    class StubLoraScanner:
        def __init__(self):
            self._cache = None
            self._is_initializing = True

        async def initialize_in_background(self):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0)
            self._cache = SimpleNamespace(raw_data=[])
            self._is_initializing = False
            ready_flag.set()

    lora_scanner = StubLoraScanner()
    scanner = RecipeScanner(lora_scanner=lora_scanner)  # pyright: ignore[reportArgumentType]

    await scanner.initialize_in_background()

    assert ready_flag.is_set()
    assert call_count == 1
    assert scanner._cache is not None


@pytest.mark.asyncio
async def test_invalid_model_version_marked_deleted_and_not_retried(
    monkeypatch, recipe_scanner
):
    scanner, _ = recipe_scanner
    recipes_dir = Path(config.loras_roots[0]) / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    recipe: Dict[str, Any] = {
        "id": "invalid-version",
        "file_path": str(recipes_dir / "invalid-version.webp"),
        "title": "Invalid",
        "modified": 0.0,
        "created_date": 0.0,
        "loras": [{"modelVersionId": 999, "file_name": "", "hash": ""}],
    }
    await scanner.add_recipe(dict(recipe))

    call_count = 0

    async def fake_get_hash(model_version_id):
        nonlocal call_count
        call_count += 1
        return None

    monkeypatch.setattr(scanner, "_get_hash_from_civitai", fake_get_hash)

    metadata_updated = await scanner._update_lora_information(recipe)

    assert metadata_updated is True
    assert recipe["loras"][0]["isDeleted"] is True
    assert call_count == 1

    # Subsequent calls should skip remote lookup once marked deleted
    metadata_updated_again = await scanner._update_lora_information(recipe)
    assert metadata_updated_again is False
    assert call_count == 1


@pytest.mark.asyncio
async def test_load_recipe_persists_deleted_flag_on_invalid_version(
    monkeypatch, recipe_scanner, tmp_path
):
    scanner, _ = recipe_scanner
    recipes_dir = Path(config.loras_roots[0]) / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    recipe_id = "persist-invalid"
    recipe_path = recipes_dir / f"{recipe_id}.recipe.json"
    recipe_data = {
        "id": recipe_id,
        "file_path": str(recipes_dir / f"{recipe_id}.webp"),
        "title": "Invalid",
        "modified": 0.0,
        "created_date": 0.0,
        "loras": [{"modelVersionId": 1234, "file_name": "", "hash": ""}],
    }
    recipe_path.write_text(json.dumps(recipe_data))

    async def fake_get_hash(model_version_id):
        return None

    monkeypatch.setattr(scanner, "_get_hash_from_civitai", fake_get_hash)

    loaded = await scanner._load_recipe_file(str(recipe_path))

    assert loaded["loras"][0]["isDeleted"] is True

    persisted = json.loads(recipe_path.read_text())
    assert persisted["loras"][0]["isDeleted"] is True


@pytest.mark.asyncio
async def test_update_lora_filename_by_hash_updates_affected_recipes(
    tmp_path: Path, recipe_scanner
):
    scanner, _ = recipe_scanner
    recipes_dir = Path(config.loras_roots[0]) / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    # Recipe 1: Contains the LoRA with hash "hash1"
    recipe1_id = "recipe1"
    recipe1_path = recipes_dir / f"{recipe1_id}.recipe.json"
    recipe1_data = {
        "id": recipe1_id,
        "file_path": str(tmp_path / "img1.png"),
        "title": "Recipe 1",
        "modified": 0.0,
        "created_date": 0.0,
        "loras": [
            {"file_name": "old_name", "hash": "hash1"},
            {"file_name": "other_lora", "hash": "hash2"},
        ],
    }
    recipe1_path.write_text(json.dumps(recipe1_data))
    await scanner.add_recipe(dict(recipe1_data))

    # Recipe 2: Does NOT contain the LoRA
    recipe2_id = "recipe2"
    recipe2_path = recipes_dir / f"{recipe2_id}.recipe.json"
    recipe2_data = {
        "id": recipe2_id,
        "file_path": str(tmp_path / "img2.png"),
        "title": "Recipe 2",
        "modified": 0.0,
        "created_date": 0.0,
        "loras": [{"file_name": "other_lora", "hash": "hash2"}],
    }
    recipe2_path.write_text(json.dumps(recipe2_data))
    await scanner.add_recipe(dict(recipe2_data))

    # Update LoRA name for "hash1" (using different case to test normalization)
    new_name = "new_name"
    file_count, cache_count = await scanner.update_lora_filename_by_hash(
        "HASH1", new_name
    )

    assert file_count == 1
    assert cache_count == 1

    # Check file on disk
    persisted1 = json.loads(recipe1_path.read_text())
    assert persisted1["loras"][0]["file_name"] == new_name
    assert persisted1["loras"][1]["file_name"] == "other_lora"

    # Verify Recipe 2 unchanged
    persisted2 = json.loads(recipe2_path.read_text())
    assert persisted2["loras"][0]["file_name"] == "other_lora"

    cache = await scanner.get_cached_data()
    cached1 = next(r for r in cache.raw_data if r["id"] == recipe1_id)
    assert cached1["loras"][0]["file_name"] == new_name


@pytest.mark.asyncio
async def test_get_paginated_data_filters_by_favorite(recipe_scanner):
    scanner, _ = recipe_scanner

    # Add a normal recipe
    await scanner.add_recipe(
        {
            "id": "regular",
            "file_path": "path/regular.png",
            "title": "Regular Recipe",
            "modified": 1.0,
            "created_date": 1.0,
            "loras": [],
        }
    )

    # Add a favorite recipe
    await scanner.add_recipe(
        {
            "id": "favorite",
            "file_path": "path/favorite.png",
            "title": "Favorite Recipe",
            "modified": 2.0,
            "created_date": 2.0,
            "loras": [],
            "favorite": True,
        }
    )

    # Wait for cache update (it's async in some places, add_recipe is usually enough but let's be safe)
    await asyncio.sleep(0)

    # Test without filter (should return both)
    result_all = await scanner.get_paginated_data(page=1, page_size=10)
    assert len(result_all["items"]) == 2

    # Test with favorite filter
    result_fav = await scanner.get_paginated_data(
        page=1, page_size=10, filters={"favorite": True}
    )
    assert len(result_fav["items"]) == 1
    assert result_fav["items"][0]["id"] == "favorite"

    # Test with favorite filter set to False (should return both or at least not filter if it's the default)
    # Actually our implementation checks if 'favorite' in filters and filters['favorite']
    result_fav_false = await scanner.get_paginated_data(
        page=1, page_size=10, filters={"favorite": False}
    )
    assert len(result_fav_false["items"]) == 2


@pytest.mark.asyncio
async def test_get_paginated_data_filters_by_prompt(recipe_scanner):
    scanner, _ = recipe_scanner

    # Add a recipe with a specific prompt
    await scanner.add_recipe(
        {
            "id": "prompt-recipe",
            "file_path": "path/prompt.png",
            "title": "Prompt Recipe",
            "modified": 1.0,
            "created_date": 1.0,
            "loras": [],
            "gen_params": {"prompt": "a beautiful forest landscape"},
        }
    )

    # Add a recipe with a specific negative prompt
    await scanner.add_recipe(
        {
            "id": "neg-prompt-recipe",
            "file_path": "path/neg.png",
            "title": "Negative Prompt Recipe",
            "modified": 2.0,
            "created_date": 2.0,
            "loras": [],
            "gen_params": {"negative_prompt": "ugly, blurry mountains"},
        }
    )

    await asyncio.sleep(0)

    # Test search in prompt
    result_prompt = await scanner.get_paginated_data(
        page=1, page_size=10, search="forest", search_options={"prompt": True}
    )
    assert len(result_prompt["items"]) == 1
    assert result_prompt["items"][0]["id"] == "prompt-recipe"

    # Test search in negative prompt
    result_neg = await scanner.get_paginated_data(
        page=1, page_size=10, search="mountains", search_options={"prompt": True}
    )
    assert len(result_neg["items"]) == 1
    assert result_neg["items"][0]["id"] == "neg-prompt-recipe"

    # Test search disabled (should not find by prompt)
    result_disabled = await scanner.get_paginated_data(
        page=1, page_size=10, search="forest", search_options={"prompt": False}
    )
    assert len(result_disabled["items"]) == 0


@pytest.mark.asyncio
async def test_get_paginated_data_sorting(recipe_scanner):
    scanner, _ = recipe_scanner

    # Add test recipes
    # Recipe A: Name "Alpha", Date 10, LoRAs 2
    await scanner.add_recipe(
        {
            "id": "A",
            "title": "Alpha",
            "created_date": 10.0,
            "loras": [{}, {}],
            "file_path": "a.png",
        }
    )
    # Recipe B: Name "Beta", Date 20, LoRAs 1
    await scanner.add_recipe(
        {
            "id": "B",
            "title": "Beta",
            "created_date": 20.0,
            "loras": [{}],
            "file_path": "b.png",
        }
    )
    # Recipe C: Name "Gamma", Date 5, LoRAs 3
    await scanner.add_recipe(
        {
            "id": "C",
            "title": "Gamma",
            "created_date": 5.0,
            "loras": [{}, {}, {}],
            "file_path": "c.png",
        }
    )

    await asyncio.sleep(0)

    # Test Name DESC: Gamma, Beta, Alpha
    res = await scanner.get_paginated_data(page=1, page_size=10, sort_by="name:desc")
    assert [i["id"] for i in res["items"]] == ["C", "B", "A"]

    # Test LoRA Count DESC: Gamma (3), Alpha (2), Beta (1)
    res = await scanner.get_paginated_data(
        page=1, page_size=10, sort_by="loras_count:desc"
    )
    assert [i["id"] for i in res["items"]] == ["C", "A", "B"]

    # Test LoRA Count ASC: Beta (1), Alpha (2), Gamma (3)
    res = await scanner.get_paginated_data(
        page=1, page_size=10, sort_by="loras_count:asc"
    )
    assert [i["id"] for i in res["items"]] == ["B", "A", "C"]

    # Test Date ASC: Gamma (5), Alpha (10), Beta (20)
    res = await scanner.get_paginated_data(page=1, page_size=10, sort_by="date:asc")
    assert [i["id"] for i in res["items"]] == ["C", "A", "B"]


async def test_build_image_id_map_filters_correctly(recipe_scanner):
    """Only recipes with valid CivitAI source_path appear in image_id_map.

    Recipes imported from local files or with empty/missing source_path
    must be naturally excluded.
    """
    scanner, _ = recipe_scanner
    from py.services.recipe_cache import RecipeCache

    scanner._cache = RecipeCache(
        raw_data=[
            {"id": "r1", "source_path": "https://civitai.com/images/12345"},
            {"id": "r2", "source_path": "https://civitai.com/images/67890"},
            {"id": "r3", "source_path": "/home/user/local_image.png"},
            {"id": "r4", "source_path": ""},
            {"id": "r5"},
        ],
        sorted_by_name=[],
        sorted_by_date=[],
    )

    result = scanner._build_image_id_map()

    assert result == {
        "12345": "r1",
        "67890": "r2",
    }
    # r3 = local file path, r4 = empty string, r5 = no key → all excluded
    for rid in ("r3", "r4", "r5"):
        assert rid not in result.values()


async def test_add_recipe_updates_image_id_map(recipe_scanner):
    """Adding a recipe with a CivitAI URL must update image_id_map.

    A recipe with a local file path must NOT produce an entry.
    """
    scanner, _ = recipe_scanner

    await scanner.add_recipe({
        "id": "civitai-recipe",
        "title": "CivitAI",
        "source_path": "https://civitai.com/images/55555",
    })

    cache = await scanner.get_cached_data()
    assert cache.image_id_map.get("55555") == "civitai-recipe"

    await scanner.add_recipe({
        "id": "local-recipe",
        "title": "Local",
        "source_path": "/path/to/local.png",
    })

    assert "local-recipe" not in cache.image_id_map.values()


async def test_remove_recipe_clears_image_id_map(recipe_scanner):
    """Removing a recipe that has a CivitAI image_id must clean up the map."""
    scanner, _ = recipe_scanner

    await scanner.add_recipe({
        "id": "recipe-a",
        "title": "A",
        "source_path": "https://civitai.com/images/111",
    })
    await scanner.add_recipe({
        "id": "recipe-b",
        "title": "B",
        "source_path": "https://civitai.com/images/222",
    })

    cache = await scanner.get_cached_data()
    assert "111" in cache.image_id_map
    assert cache.image_id_map["222"] == "recipe-b"

    await scanner.remove_recipe("recipe-a")

    assert "111" not in cache.image_id_map
    assert cache.image_id_map["222"] == "recipe-b"


# ---------------------------------------------------------------------------
# cache_version — ModelScanner write-path bump coverage (plan todo 1)
# ---------------------------------------------------------------------------


class DummyScanner(ModelScanner):
    """Minimal ModelScanner subclass exercising the base-class write paths."""

    def __init__(self, root: str):
        self._root = root
        super().__init__(
            model_type="dummy",
            model_class=BaseModelMetadata,
            file_extensions={".txt"},
            hash_index=ModelHashIndex(),
        )

    def get_model_roots(self) -> list[str]:
        return [self._root]

    async def _process_model_file(
        self,
        file_path: str,
        root_path: str,
        *,
        hash_index: ModelHashIndex | None = None,
        excluded_models: list[str] | None = None,
    ) -> Dict[str, Any] | None:
        hash_index = hash_index or self._hash_index
        excluded_models = excluded_models if excluded_models is not None else self._excluded_models
        name = os.path.splitext(os.path.basename(file_path))[0]
        if name.startswith("skip"):
            excluded_models.append(file_path.replace(os.sep, "/"))
            return None
        return {
            "file_path": file_path.replace(os.sep, "/"),
            "folder": os.path.dirname(os.path.relpath(file_path, root_path)).replace(os.path.sep, "/"),
            "sha256": f"hash-{name}",
            "tags": [],
            "model_name": name,
            "file_name": name,
            "size": 1,
            "modified": 1.0,
        }


class DummyScannerB(DummyScanner):
    """A second ModelScanner subclass so per-class versions are independent."""


class DummyScannerC(DummyScanner):
    """A third ModelScanner subclass (embedding stand-in for the misc route test)."""


async def _empty_metadata_loader(path: str) -> Dict[str, Any]:
    return {}


class DummyMetadataManagerForLifecycle:
    async def load_metadata_payload(self, file_path: str) -> Dict[str, Any]:
        return {}

    async def save_metadata(self, file_path: str, metadata: Dict[str, Any]) -> None:
        return None


def _make_scanner(raw_data: list[Dict[str, Any]], root: str) -> DummyScanner:
    scanner = DummyScanner(root)
    scanner._cache = ModelCache(raw_data=[dict(item) for item in raw_data], folders=[])
    return scanner


def _normalize(root_path: str) -> str:
    return root_path.replace(os.sep, "/")


async def test_cache_version_starts_at_zero(tmp_path: Path):
    scanner = DummyScanner(str(tmp_path))
    assert scanner.cache_version == 0


async def test_scan_apply_bumps_cache_version(tmp_path: Path):
    scanner = _make_scanner([], str(tmp_path))
    result = CacheBuildResult(
        raw_data=[{"file_path": "a.txt", "folder": "", "sha256": "abc", "tags": []}],
        hash_index=ModelHashIndex(),
        tags_count={},
        excluded_models=[],
    )
    assert scanner.cache_version == 0
    await scanner._apply_scan_result(result)
    assert scanner.cache_version == 1
    assert scanner._cache.raw_data == result.raw_data


async def test_add_model_to_cache_bumps_cache_version(tmp_path: Path):
    scanner = _make_scanner([], str(tmp_path))
    assert scanner.cache_version == 0
    ok = await scanner.add_model_to_cache(
        {"file_path": "x.txt", "folder": "", "sha256": "abc", "tags": []}
    )
    assert ok is True
    assert scanner.cache_version == 1
    assert len(scanner._cache.raw_data) == 1


async def test_update_single_model_cache_bumps_cache_version(tmp_path: Path):
    scanner = _make_scanner(
        [{"file_path": "old.txt", "folder": "", "sha256": "abc", "tags": [], "model_name": "m", "file_name": "old"}],
        str(tmp_path),
    )
    await scanner._cache.resort()
    assert scanner.cache_version == 0
    result = await scanner.update_single_model_cache(
        "old.txt",
        "new.txt",
        {"sha256": "def", "tags": [], "model_name": "new", "file_name": "new"},
    )
    assert result is not None
    assert scanner.cache_version == 1
    assert [item["file_path"] for item in scanner._cache.raw_data] == ["new.txt"]


async def test_sync_cache_from_metadata_sha256_change_bumps_cache_version(tmp_path: Path):
    scanner = _make_scanner(
        [{"file_path": "m.txt", "folder": "", "sha256": "oldsha", "tags": [], "model_name": "m", "file_name": "m"}],
        str(tmp_path),
    )
    await scanner._cache.resort()
    assert scanner.cache_version == 0
    changed = await scanner._sync_cache_from_metadata_impl(
        "m.txt",
        {"sha256": "newsha", "tags": [], "model_name": "m", "file_name": "m", "size": 1, "modified": 1.0},
    )
    assert changed is True
    assert scanner.cache_version == 1
    assert scanner._cache.raw_data[0]["sha256"] == "newsha"


async def test_update_autov3_for_model_bumps_cache_version(tmp_path: Path):
    scanner = _make_scanner(
        [{"file_path": "m.txt", "folder": "", "sha256": "abc", "tags": [], "model_name": "m", "file_name": "m", "autov3": ""}],
        str(tmp_path),
    )
    assert scanner.cache_version == 0
    ok = await scanner.update_autov3_for_model("dummy", "m.txt", "AAA12BBB34CD")
    assert ok is True
    assert scanner.cache_version == 1
    assert scanner._cache.raw_data[0]["autov3"] == "aaa12bbb34cd"


async def test_batch_remove_bumps_cache_version(tmp_path: Path):
    scanner = _make_scanner(
        [{"file_path": "gone.txt", "folder": "", "sha256": "abc", "tags": [], "model_name": "gone", "file_name": "gone"}],
        str(tmp_path),
    )
    assert scanner.cache_version == 0
    updated = await scanner._batch_update_cache_for_deleted_models(["gone.txt"])
    assert updated is True
    assert scanner.cache_version == 1
    assert scanner._cache.raw_data == []


async def test_reconcile_cache_append_only_bumps_cache_version(tmp_path: Path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "new.txt").write_text("data", encoding="utf-8")
    scanner = _make_scanner([], str(root))
    assert scanner.cache_version == 0
    await scanner._reconcile_cache()
    assert scanner.cache_version == 1
    assert len(scanner._cache.raw_data) == 1


async def test_reconcile_cache_bumps_unconditionally(tmp_path: Path):
    root = tmp_path / "models"
    root.mkdir()
    scanner = _make_scanner([], str(root))
    assert scanner.cache_version == 0
    await scanner._reconcile_cache()
    assert scanner.cache_version == 1


async def test_get_cached_data_read_does_not_bump_cache_version(tmp_path: Path):
    scanner = _make_scanner([], str(tmp_path))
    assert scanner.cache_version == 0
    cache = await scanner.get_cached_data()
    assert cache is scanner._cache
    assert scanner.cache_version == 0
    _ = scanner.cache_version
    assert scanner.cache_version == 0


async def test_scanner_versions_are_independent(tmp_path: Path):
    root = tmp_path / "models"
    root.mkdir()
    lora = DummyScanner(str(root))
    checkpoint = DummyScannerB(str(root))
    assert lora.cache_version == 0
    assert checkpoint.cache_version == 0
    lora.bump_cache_version()
    assert lora.cache_version == 1
    assert checkpoint.cache_version == 0


async def test_on_library_changed_bumps_cache_version(tmp_path: Path, monkeypatch):
    scanner = DummyScanner(str(tmp_path))
    assert scanner.cache_version == 0

    async def _noop_initialize() -> None:
        pass

    monkeypatch.setattr(scanner, "initialize_in_background", _noop_initialize)
    scanner.on_library_changed()
    assert scanner.cache_version == 1


async def test_checkpoint_lazy_hash_bumps_cache_version(tmp_path: Path, monkeypatch):
    from py.services.checkpoint_scanner import CheckpointScanner

    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()
    checkpoint_file = checkpoints_root / "test_model.safetensors"
    checkpoint_file.write_text("fake content", encoding="utf-8")

    normalized_root = _normalize(str(checkpoints_root))
    normalized_file = _normalize(str(checkpoint_file))

    monkeypatch.setattr(
        model_scanner_module.config, "base_models_roots", [normalized_root], raising=False
    )
    monkeypatch.setattr(
        model_scanner_module.config, "checkpoints_roots", [normalized_root], raising=False
    )

    scanner = CheckpointScanner()
    scanner._cache = ModelCache(
        raw_data=[
            {
                "file_path": normalized_file,
                "folder": "",
                "sha256": "",
                "hash_status": "pending",
                "tags": [],
                "model_name": "test_model",
                "file_name": "test_model",
            }
        ],
        folders=[],
    )
    assert scanner.cache_version == 0
    hash_result = await scanner.calculate_hash_for_model(normalized_file)
    assert hash_result is not None
    assert scanner.cache_version == 1
    assert scanner._cache.raw_data[0]["sha256"] == hash_result.lower()


async def test_lifecycle_delete_model_bumps_cache_version(tmp_path: Path):
    from py.services.model_lifecycle_service import ModelLifecycleService

    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")

    scanner = _make_scanner(
        [{"file_path": str(model), "folder": "", "sha256": "abc", "tags": [], "model_name": "m", "file_name": "m"}],
        str(root),
    )
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=DummyMetadataManagerForLifecycle(),
        metadata_loader=_empty_metadata_loader,
    )
    assert scanner.cache_version == 0
    result = await service.delete_model(str(model))
    assert result["success"] is True
    assert scanner.cache_version == 1
    assert scanner._cache.raw_data == []


async def test_lifecycle_exclude_model_bumps_cache_version(tmp_path: Path):
    from py.services.model_lifecycle_service import ModelLifecycleService

    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")

    scanner = _make_scanner(
        [{"file_path": str(model), "folder": "", "sha256": "abc", "tags": [], "model_name": "m", "file_name": "m"}],
        str(root),
    )
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=DummyMetadataManagerForLifecycle(),
        metadata_loader=_empty_metadata_loader,
    )
    assert scanner.cache_version == 0
    result = await service.exclude_model(str(model))
    assert result["success"] is True
    assert scanner.cache_version == 1
    assert scanner._cache.raw_data == []


async def test_misc_delete_model_version_bumps_cache_version(tmp_path: Path):
    from aiohttp.test_utils import make_mocked_request

    from py.routes.handlers.misc_handlers import ModelLibraryHandler, ServiceRegistryAdapter

    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")

    lora_scanner = _make_scanner(
        [
            {
                "file_path": str(model),
                "folder": "",
                "sha256": "abc",
                "tags": [],
                "model_name": "m",
                "file_name": "m",
                "civitai": {"id": 42, "modelId": 7, "name": "m"},
            }
        ],
        str(root),
    )
    lora_scanner._cache.rebuild_version_index()
    # Use distinct scanner classes: ModelScanner is a per-class singleton, so
    # re-instantiating DummyScanner would return the same instance and clobber
    # the lora cache set above.
    checkpoint_scanner = DummyScannerB(str(root))
    checkpoint_scanner._cache = ModelCache(raw_data=[], folders=[])
    embedding_scanner = DummyScannerC(str(root))
    embedding_scanner._cache = ModelCache(raw_data=[], folders=[])

    deleted: list[tuple[str, int]] = []

    async def history_factory():
        class FakeHistory:
            async def mark_as_deleted(self, model_type: str, model_version_id: int) -> None:
                deleted.append((model_type, model_version_id))

        return FakeHistory()

    async def lora_factory():
        return lora_scanner

    async def checkpoint_factory():
        return checkpoint_scanner

    async def embedding_factory():
        return embedding_scanner

    async def _noop_metadata_provider() -> Any:
        return None

    handler = ModelLibraryHandler(
        ServiceRegistryAdapter(
            get_lora_scanner=lora_factory,
            get_checkpoint_scanner=checkpoint_factory,
            get_embedding_scanner=embedding_factory,
            get_downloaded_version_history_service=history_factory,
        ),
        metadata_provider_factory=_noop_metadata_provider,
    )

    request = make_mocked_request("GET", "/api/models/versions/delete?modelVersionId=42")
    assert lora_scanner.cache_version == 0
    response = await handler.delete_model_version(request)
    assert response.status == 200
    assert lora_scanner.cache_version == 1
    assert checkpoint_scanner.cache_version == 0
    assert embedding_scanner.cache_version == 0
    assert deleted == [("lora", 42)]


# ---------------------------------------------------------------------------
# build_local_hash_cache — version-cached local hash map (plan todo 2)
# ---------------------------------------------------------------------------


def _lora_item(sha256: str = "", autov3: str = "", **extra: Any) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "sha256": sha256,
        "autov3": autov3,
        "file_path": f"/models/{sha256 or 'x'}.safetensors",
        "file_name": "m",
        "model_name": "m",
    }
    item.update(extra)
    return item


def _make_recipe_scanner(
    lora: DummyScanner, checkpoint: DummyScannerB
) -> RecipeScanner:
    RecipeScanner._instance = None
    return RecipeScanner(
        lora_scanner=lora, checkpoint_scanner=checkpoint  # pyright: ignore[reportArgumentType]
    )


async def test_build_local_hash_cache_has_sha256_autov2_autov3_keys(tmp_path: Path):
    sha256 = "A" * 64
    autov3 = "AAA12BBB34CD"
    lora = _make_scanner([_lora_item(sha256=sha256, autov3=autov3)], str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(raw_data=[], folders=[])
    scanner = _make_recipe_scanner(lora, checkpoint)

    result = await scanner.build_local_hash_cache()

    assert set(result) == {sha256.lower(), sha256.lower()[:10], autov3.lower()}
    assert result[sha256.lower()] is lora._cache.raw_data[0]


async def test_build_local_hash_cache_skips_items_without_sha256(tmp_path: Path):
    lora = _make_scanner(
        [
            _lora_item(sha256=""),
            {"file_path": "/models/none.safetensors", "file_name": "n", "model_name": "n"},
            _lora_item(sha256="B" * 64),
        ],
        str(tmp_path),
    )
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(raw_data=[], folders=[])
    scanner = _make_recipe_scanner(lora, checkpoint)

    result = await scanner.build_local_hash_cache()

    assert set(result) == {("B" * 64).lower(), ("B" * 64).lower()[:10]}


async def test_build_local_hash_cache_skips_empty_autov3_keys(tmp_path: Path):
    sha256 = "C" * 64
    lora = _make_scanner([_lora_item(sha256=sha256, autov3="")], str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(raw_data=[], folders=[])
    scanner = _make_recipe_scanner(lora, checkpoint)

    result = await scanner.build_local_hash_cache()

    assert "" not in result
    assert set(result) == {sha256.lower(), sha256.lower()[:10]}


async def test_build_local_hash_cache_never_calls_calculate_autov3(
    tmp_path: Path, monkeypatch
):
    from py.utils import file_utils

    called: list[str] = []

    def fake_calculate_autov3(file_path: str) -> str:
        called.append(file_path)
        return "AAABBBCCCDDD"

    monkeypatch.setattr(file_utils, "calculate_autov3", fake_calculate_autov3)

    autov3 = "E" * 12
    lora = _make_scanner([_lora_item(sha256="D" * 64, autov3=autov3)], str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(raw_data=[], folders=[])
    scanner = _make_recipe_scanner(lora, checkpoint)

    result = await scanner.build_local_hash_cache()

    assert called == []
    assert autov3.lower() in result


async def test_build_local_hash_cache_reuses_same_object_while_versions_unchanged(
    tmp_path: Path,
):
    lora = _make_scanner([_lora_item(sha256="F" * 64)], str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(raw_data=[], folders=[])
    scanner = _make_recipe_scanner(lora, checkpoint)

    first = await scanner.build_local_hash_cache()
    second = await scanner.build_local_hash_cache()

    assert first is second
    assert scanner._local_hash_cache_versions == (
        lora.cache_version,
        checkpoint.cache_version,
    )


async def test_build_local_hash_cache_rebuilds_after_lora_version_change(
    tmp_path: Path,
):
    lora = _make_scanner([_lora_item(sha256="G" * 64)], str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(raw_data=[], folders=[])
    scanner = _make_recipe_scanner(lora, checkpoint)

    first = await scanner.build_local_hash_cache()
    lora.bump_cache_version()
    second = await scanner.build_local_hash_cache()

    assert first is not second
    assert first["g" * 64] is second["g" * 64]


async def test_build_local_hash_cache_rebuilds_after_checkpoint_version_change(
    tmp_path: Path,
):
    lora = _make_scanner([], str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(
        raw_data=[_lora_item(sha256="H" * 64)], folders=[]
    )
    scanner = _make_recipe_scanner(lora, checkpoint)

    first = await scanner.build_local_hash_cache()
    checkpoint.bump_cache_version()
    second = await scanner.build_local_hash_cache()

    assert first is not second


async def test_build_local_hash_cache_includes_lora_and_checkpoint_items(
    tmp_path: Path,
):
    lora = _make_scanner([_lora_item(sha256="I" * 64, autov3="I1" * 6)], str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(
        raw_data=[_lora_item(sha256="J" * 64, autov3="J1" * 6)], folders=[]
    )
    scanner = _make_recipe_scanner(lora, checkpoint)

    result = await scanner.build_local_hash_cache()

    assert ("I" * 64).lower() in result
    assert ("J" * 64).lower() in result
    assert result[("J" * 64).lower()] is checkpoint._cache.raw_data[0]


async def test_build_local_hash_cache_returns_empty_dict_when_no_data(tmp_path: Path):
    lora = _make_scanner([], str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(raw_data=[], folders=[])
    scanner = _make_recipe_scanner(lora, checkpoint)

    result = await scanner.build_local_hash_cache()

    assert result == {}


async def test_build_local_hash_cache_single_flight_concurrent_calls(tmp_path: Path):
    lora = _make_scanner([_lora_item(sha256="K" * 64, autov3="K1" * 6)], str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(
        raw_data=[_lora_item(sha256="L" * 64)], folders=[]
    )
    scanner = _make_recipe_scanner(lora, checkpoint)

    first, second = await asyncio.gather(
        scanner.build_local_hash_cache(),
        scanner.build_local_hash_cache(),
    )

    assert first is second
    assert ("K" * 64).lower() in first
    assert ("L" * 64).lower() in first


async def test_build_local_hash_cache_handles_missing_scanner(tmp_path: Path):
    lora = _make_scanner([_lora_item(sha256="M" * 64)], str(tmp_path))
    RecipeScanner._instance = None
    scanner = RecipeScanner(lora_scanner=lora)  # pyright: ignore[reportArgumentType]

    result = await scanner.build_local_hash_cache()

    assert ("M" * 64).lower() in result
    assert len(result) == 2


# ---------------------------------------------------------------------------
# rematch matching helpers (plan todo 1)
# ---------------------------------------------------------------------------


def _rematch_item(
    sha256: str = "",
    autov3: str | None = "",
    *,
    sub_type: Any = None,
    civitai_type: Any = None,
    civitai_version_id: Any = None,
    file_name: str = "model.safetensors",
    **extra: Any,
) -> Dict[str, Any]:
    item = _lora_item(sha256=sha256, file_name=file_name, **extra)
    item["autov3"] = autov3
    if sub_type is not None:
        item["sub_type"] = sub_type
    civitai: Dict[str, Any] = {}
    if civitai_version_id is not None:
        civitai["id"] = civitai_version_id
    if civitai_type is not None:
        civitai.setdefault("model", {})["type"] = civitai_type
    if civitai:
        item["civitai"] = civitai
    return item


def _make_rematch_scanner(
    lora_items: list[Dict[str, Any]],
    checkpoint_items: list[Dict[str, Any]],
    tmp_path: Path,
) -> tuple[RecipeScanner, DummyScanner, DummyScannerB]:
    lora = _make_scanner(lora_items, str(tmp_path))
    checkpoint = DummyScannerB(str(tmp_path))
    checkpoint._cache = ModelCache(
        raw_data=[dict(item) for item in checkpoint_items], folders=[]
    )
    return _make_recipe_scanner(lora, checkpoint), lora, checkpoint


# _is_rematch_candidate — candidate filter


async def test_is_rematch_candidate_is_deleted_only_passes(tmp_path: Path):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    assert scanner._is_rematch_candidate(
        {"isDeleted": True, "hash": "abc", "file_name": "m.safetensors"}
    )


async def test_is_rematch_candidate_hash_empty_passes(tmp_path: Path):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    assert scanner._is_rematch_candidate(
        {"hash": "", "modelVersionId": 1, "file_name": "m.safetensors"}
    )


async def test_is_rematch_candidate_file_name_empty_passes(tmp_path: Path):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    assert scanner._is_rematch_candidate(
        {"hash": "abc", "modelVersionId": 1, "file_name": ""}
    )


async def test_is_rematch_candidate_rejects_healthy_entry(tmp_path: Path):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    assert not scanner._is_rematch_candidate({"hash": "abc", "file_name": "m.safetensors"})


async def test_is_rematch_candidate_rejects_no_identifier(tmp_path: Path):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    assert not scanner._is_rematch_candidate({"isDeleted": True, "file_name": "m.safetensors"})
    assert not scanner._is_rematch_candidate({"isDeleted": True})


async def test_is_rematch_candidate_parser_convention_id_only_passes(tmp_path: Path):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    assert scanner._is_rematch_candidate({"isDeleted": True, "id": 42})


async def test_is_rematch_candidate_rejects_non_dict(tmp_path: Path):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    malformed: Any = "garbage"
    assert not scanner._is_rematch_candidate(malformed)


# _match_rematch_entry — L1 hash-cache lookup


async def test_match_rematch_entry_l1_sha256_key(tmp_path: Path):
    sha256 = ("A" * 64).lower()
    scanner, lora, _ = _make_rematch_scanner(
        [_rematch_item(sha256=sha256, sub_type="lora")], [], tmp_path
    )
    local_cache = await scanner.build_local_hash_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": sha256.upper(), "modelVersionId": 999},
        local_cache,
        {},
        is_checkpoint=False,
    )

    assert matched is lora._cache.raw_data[0]


async def test_match_rematch_entry_l1_sha256_autov2_prefix_key(tmp_path: Path):
    sha256 = ("B" * 64).lower()
    scanner, lora, _ = _make_rematch_scanner(
        [_rematch_item(sha256=sha256, sub_type="lora")], [], tmp_path
    )
    local_cache = await scanner.build_local_hash_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": sha256[:10]}, local_cache, {}, is_checkpoint=False
    )

    assert matched is lora._cache.raw_data[0]


async def test_match_rematch_entry_l1_stored_autov3_key(tmp_path: Path):
    sha256 = ("C" * 64).lower()
    autov3 = "CCCDDDEEEFFF"
    scanner, lora, _ = _make_rematch_scanner(
        [_rematch_item(sha256=sha256, autov3=autov3, sub_type="lora")], [], tmp_path
    )
    local_cache = await scanner.build_local_hash_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": autov3}, local_cache, {}, is_checkpoint=False
    )

    assert matched is lora._cache.raw_data[0]


# _match_rematch_entry — L2 version_index lookup


async def test_match_rematch_entry_l2_lora_via_model_version_id(tmp_path: Path):
    sha256 = ("D" * 64).lower()
    scanner, lora, _ = _make_rematch_scanner(
        [_rematch_item(sha256=sha256, sub_type="lora", civitai_version_id=123)],
        [],
        tmp_path,
    )

    matched = await scanner._match_rematch_entry(
        {"modelVersionId": 123, "file_name": "m.safetensors", "isDeleted": True},
        {},
        {},
        is_checkpoint=False,
    )

    assert matched is lora._cache.raw_data[0]


async def test_match_rematch_entry_l2_lora_via_id_key(tmp_path: Path):
    sha256 = ("E" * 64).lower()
    scanner, lora, _ = _make_rematch_scanner(
        [_rematch_item(sha256=sha256, sub_type="lora", civitai_version_id=456)],
        [],
        tmp_path,
    )

    matched = await scanner._match_rematch_entry(
        {"id": 456, "file_name": "m.safetensors", "isDeleted": True},
        {},
        {},
        is_checkpoint=False,
    )

    assert matched is lora._cache.raw_data[0]


async def test_match_rematch_entry_l2_checkpoint_via_version_index(tmp_path: Path):
    sha256 = ("F" * 64).lower()
    scanner, _, checkpoint = _make_rematch_scanner(
        [],
        [_rematch_item(sha256=sha256, sub_type="checkpoint", civitai_version_id=789)],
        tmp_path,
    )

    matched = await scanner._match_rematch_entry(
        {"modelVersionId": 789, "file_name": "m.safetensors", "isDeleted": True},
        {},
        {},
        is_checkpoint=True,
    )

    assert matched is checkpoint._cache.raw_data[0]


# _match_rematch_entry — L3 computed autov3 lookup


async def test_match_rematch_entry_l3_computed_autov3_renamed_file(
    tmp_path: Path, monkeypatch
):
    from py.services import recipe_scanner as recipe_scanner_module

    entry_hash = "AABBCCDDEEFF"
    monkeypatch.setattr(
        recipe_scanner_module, "calculate_autov3", lambda path: entry_hash.lower()
    )

    item = _rematch_item(
        sha256=("G" * 64).lower(), file_name="renamed.safetensors", sub_type="lora"
    )
    del item["autov3"]  # unchecked state
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    autov3_cache = await scanner._build_rematch_autov3_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": entry_hash, "file_name": "original-name.safetensors", "isDeleted": True},
        {},
        autov3_cache,
        is_checkpoint=False,
    )

    assert matched is not None
    assert matched["file_name"] == "renamed.safetensors"


async def test_match_rematch_entry_l3_skips_empty_autov3_terminal(
    tmp_path: Path, monkeypatch
):
    from py.services import recipe_scanner as recipe_scanner_module

    entry_hash = "H1H2H3H4H5H6"
    called: list[str] = []
    monkeypatch.setattr(
        recipe_scanner_module,
        "calculate_autov3",
        lambda path: (called.append(path), entry_hash.lower())[1],
    )

    item = _rematch_item(
        sha256=("H" * 64).lower(), autov3="", file_name="m.safetensors", sub_type="lora"
    )
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    autov3_cache = await scanner._build_rematch_autov3_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": entry_hash}, {}, autov3_cache, is_checkpoint=False
    )

    assert matched is None
    assert called == []  # '' is terminal — must never be recomputed


async def test_match_rematch_entry_l3_skipped_for_non_12_char_hash(
    tmp_path: Path, monkeypatch
):
    from py.services import recipe_scanner as recipe_scanner_module

    entry_hash = "AA"
    monkeypatch.setattr(
        recipe_scanner_module, "calculate_autov3", lambda path: entry_hash.lower()
    )

    item = _rematch_item(sha256=("I" * 64).lower(), file_name="m.safetensors", sub_type="lora")
    del item["autov3"]
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    autov3_cache = await scanner._build_rematch_autov3_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": entry_hash}, {}, autov3_cache, is_checkpoint=False
    )

    assert matched is None


# _match_rematch_entry — precedence


async def test_match_rematch_entry_precedence_l1_wins_over_l2(tmp_path: Path):
    sha256 = ("J" * 64).lower()
    scanner, lora, _ = _make_rematch_scanner(
        [
            _rematch_item(
                sha256=sha256, sub_type="lora", civitai_version_id=500, file_name="l1-item.safetensors"
            ),
            _rematch_item(
                sha256=("K" * 64).lower(),
                sub_type="lora",
                civitai_version_id=999,
                file_name="l2-item.safetensors",
            ),
        ],
        [],
        tmp_path,
    )
    local_cache = await scanner.build_local_hash_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": sha256, "modelVersionId": 999, "file_name": "m.safetensors", "isDeleted": True},
        local_cache,
        {},
        is_checkpoint=False,
    )

    assert matched is lora._cache.raw_data[0]
    assert lora._cache.raw_data[0]["file_name"] == "l1-item.safetensors"


# _match_rematch_entry — type gate


async def test_match_rematch_type_gate_checkpoint_accepts_sub_type(tmp_path: Path):
    for sub_type in ("checkpoint", "diffusion_model"):
        item = _rematch_item(sha256=("M" * 64).lower(), sub_type=sub_type)
        scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
        local_cache = await scanner.build_local_hash_cache()

        matched = await scanner._match_rematch_entry(
            {"hash": ("M" * 64).lower()}, local_cache, {}, is_checkpoint=True
        )

        assert matched is not None


async def test_match_rematch_type_gate_checkpoint_accepts_diffusion_model_civitai_alias(
    tmp_path: Path,
):
    item = _rematch_item(sha256=("N" * 64).lower(), civitai_type="DiffusionModel")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    local_cache = await scanner.build_local_hash_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": ("N" * 64).lower()}, local_cache, {}, is_checkpoint=True
    )

    assert matched is not None


async def test_match_rematch_type_gate_checkpoint_rejects_lora_typed_item(tmp_path: Path):
    cases = [("LORA", None), ("lora", None), (None, "LORA"), (None, "lora")]
    for sub_type, civitai_type in cases:
        item = _rematch_item(
            sha256=("O" * 64).lower(), sub_type=sub_type, civitai_type=civitai_type
        )
        scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
        local_cache = await scanner.build_local_hash_cache()

        matched = await scanner._match_rematch_entry(
            {"hash": ("O" * 64).lower()}, local_cache, {}, is_checkpoint=True
        )

        assert matched is None


async def test_match_rematch_type_gate_lora_rejects_checkpoint_sub_type_no_civitai(
    tmp_path: Path,
):
    item = _rematch_item(sha256=("P" * 64).lower(), sub_type="checkpoint")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    local_cache = await scanner.build_local_hash_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": ("P" * 64).lower()}, local_cache, {}, is_checkpoint=False
    )

    assert matched is None


async def test_match_rematch_type_gate_lora_rejects_checkpoint_civitai_type(tmp_path: Path):
    item = _rematch_item(sha256=("Q" * 64).lower(), civitai_type="checkpoint")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    local_cache = await scanner.build_local_hash_cache()

    matched = await scanner._match_rematch_entry(
        {"hash": ("Q" * 64).lower()}, local_cache, {}, is_checkpoint=False
    )

    assert matched is None


async def test_match_rematch_type_gate_type_less_item_accepted_for_both(tmp_path: Path):
    for is_checkpoint in (False, True):
        item = _rematch_item(sha256=("R" * 64).lower())
        scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
        local_cache = await scanner.build_local_hash_cache()

        matched = await scanner._match_rematch_entry(
            {"hash": ("R" * 64).lower()}, local_cache, {}, is_checkpoint=is_checkpoint
        )

        assert matched is not None


async def test_match_rematch_type_gate_lora_accepts_lora_typed_item(tmp_path: Path):
    cases = [("lora", None), ("locon", None), ("dora", None), (None, "LORA"), (None, "lora")]
    for sub_type, civitai_type in cases:
        item = _rematch_item(
            sha256=("S" * 64).lower(), sub_type=sub_type, civitai_type=civitai_type
        )
        scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
        local_cache = await scanner.build_local_hash_cache()

        matched = await scanner._match_rematch_entry(
            {"hash": ("S" * 64).lower()}, local_cache, {}, is_checkpoint=False
        )

        assert matched is not None


# _build_rematch_autov3_cache


async def test_build_rematch_autov3_cache_computes_only_absent_none_items(
    tmp_path: Path, monkeypatch
):
    from py.services import recipe_scanner as recipe_scanner_module

    called: list[str] = []

    def fake_calculate_autov3(file_path: str) -> str:
        called.append(file_path)
        return ("AAA" + str(len(called)).zfill(9))[:12]

    monkeypatch.setattr(recipe_scanner_module, "calculate_autov3", fake_calculate_autov3)

    lora_items = [
        _rematch_item(sha256=("T" * 64).lower(), autov3=""),  # terminal '' — skip
        _rematch_item(sha256=("U" * 64).lower(), autov3=None),  # None — compute
        _rematch_item(sha256=("V" * 64).lower(), autov3="V1V2V3V4V5V6"),  # stored — skip
        _rematch_item(sha256=("W" * 64).lower()),  # absent key — compute
    ]
    del lora_items[3]["autov3"]
    checkpoint_items = [
        _rematch_item(sha256=("X" * 64).lower(), autov3=None),  # checkpoint too — compute
    ]
    scanner, _, _ = _make_rematch_scanner(lora_items, checkpoint_items, tmp_path)

    result = await scanner._build_rematch_autov3_cache()

    assert set(called) == {
        lora_items[1]["file_path"],
        lora_items[3]["file_path"],
        checkpoint_items[0]["file_path"],
    }
    assert set(result) == {"aaa000000001", "aaa000000002", "aaa000000003"}
    assert result["aaa000000001"] is scanner._lora_scanner._cache.raw_data[1]
    # Items must not be mutated while building the cache
    assert "autov3" not in scanner._lora_scanner._cache.raw_data[3]


async def test_build_rematch_autov3_cache_does_not_persist(tmp_path: Path, monkeypatch):
    from py.services import recipe_scanner as recipe_scanner_module

    monkeypatch.setattr(
        recipe_scanner_module, "calculate_autov3", lambda path: "AAABBBCCCDDD"
    )
    item = _rematch_item(sha256=("Z" * 64).lower())
    del item["autov3"]
    scanner, lora, checkpoint = _make_rematch_scanner([item], [], tmp_path)
    persist_calls: list[Any] = []
    monkeypatch.setattr(
        lora,
        "update_autov3_for_model",
        lambda *args, **kwargs: persist_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        checkpoint,
        "update_autov3_for_model",
        lambda *args, **kwargs: persist_calls.append((args, kwargs)),
    )

    result = await scanner._build_rematch_autov3_cache()

    assert persist_calls == []
    assert result == {"aaabbbcccddd": scanner._lora_scanner._cache.raw_data[0]}


# ---------------------------------------------------------------------------
# rematch_recipe_by_id — single-recipe rematch core (plan todo 2)
# ---------------------------------------------------------------------------


def _set_recipe_cache(scanner: RecipeScanner, recipes: list[Dict[str, Any]]) -> None:
    """Place recipes directly into the scanner's recipe cache (no copy)."""
    from py.services.recipe_cache import RecipeCache

    scanner._cache = RecipeCache(
        raw_data=recipes, sorted_by_name=[], sorted_by_date=[]
    )


async def _spy_rematch_persistence(
    scanner: RecipeScanner, monkeypatch, *, save_result: bool = True
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    """Stub the persist path so rematch tests avoid the filesystem.

    Returns (saved_calls, enriched_dict) — the enriched dict is what the
    mocked get_recipe_by_id returns for the changed+success path.
    """
    saved: list[Dict[str, Any]] = []

    async def fake_save(rcp: Dict[str, Any]) -> bool:
        saved.append(rcp)
        return save_result

    monkeypatch.setattr(scanner, "_save_recipe_persistently", fake_save)

    enriched: Dict[str, Any] = {
        "id": "enriched",
        "file_url": "/loras_static/preview/enriched.png",
    }

    async def fake_get(rid: str) -> Dict[str, Any]:
        return enriched

    monkeypatch.setattr(scanner, "get_recipe_by_id", fake_get)
    return saved, enriched


async def _spy_fts(scanner: RecipeScanner, monkeypatch) -> list[tuple[Any, str]]:
    calls: list[tuple[Any, str]] = []

    def fake_fts(recipe: Any, operation: str) -> None:
        calls.append((recipe, operation))

    monkeypatch.setattr(scanner, "_update_fts_index_for_recipe", fake_fts)
    return calls


async def _spy_resort(scanner: RecipeScanner, monkeypatch) -> list[bool]:
    calls: list[bool] = []

    def fake_resort() -> None:
        calls.append(True)

    monkeypatch.setattr(scanner, "_schedule_resort", fake_resort)
    return calls


def _civitai_lora_item(
    *,
    sha256: str = "",
    version_id: Any = None,
    name: str = "",
    model_name: str = "m",
    file_name: str = "m.safetensors",
    **extra: Any,
) -> Dict[str, Any]:
    item = _rematch_item(
        sha256=sha256,
        sub_type="lora",
        civitai_version_id=version_id,
        file_name=file_name,
        model_name=model_name,
        **extra,
    )
    if name:
        item["civitai"].setdefault("name", name)
    return item


def _civitai_checkpoint_item(
    *,
    sha256: str = "",
    version_id: Any = None,
    name: str = "",
    model_name: str = "m",
    file_name: str = "cp.safetensors",
    base_model: str = "",
) -> Dict[str, Any]:
    item = _rematch_item(
        sha256=sha256,
        sub_type="checkpoint",
        civitai_version_id=version_id,
        file_name=file_name,
        model_name=model_name,
    )
    if base_model:
        item["base_model"] = base_model
    if name:
        item["civitai"].setdefault("name", name)
    return item


# Acceptance criterion (1): lora entry rematched via L1


async def test_rematch_recipe_by_id_lora_l1_write_back(tmp_path: Path, monkeypatch):
    sha256 = ("A" * 64).lower()
    item = _civitai_lora_item(
        sha256=sha256,
        version_id=111,
        name="v1.0",
        model_name="Lora Model",
        file_name="m.safetensors",
    )
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "modified": 123.0,
        "fingerprint": "stale",
        "loras": [
            {
                "isDeleted": True,
                "hash": sha256.upper(),
                "file_name": "old.safetensors",
                "modelVersionId": 0,
            }
        ],
    }
    _set_recipe_cache(scanner, [recipe])

    saved, enriched = await _spy_rematch_persistence(scanner, monkeypatch)
    fts_calls = await _spy_fts(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    assert result["rematched"] == 1
    assert result["skipped"] == 0
    assert result["matched_recipes"] == 1
    assert result["matched_entries"] == 1
    assert result["unresolved_recipes"] == 0
    assert result["unresolved_entries"] == 0
    assert result["details"]["matched"] == [
        {
            "type": "lora",
            "entry": "old.safetensors",
            "file_name": "m.safetensors",
            "match_level": "L1",
        }
    ]
    assert result["recipe"] is enriched
    assert result["recipe"]["file_url"] == "/loras_static/preview/enriched.png"

    entry = recipe["loras"][0]
    assert entry["isDeleted"] is False
    assert entry["hash"] == sha256
    assert entry["file_name"] == "m.safetensors"
    assert entry["modelName"] == "Lora Model"
    assert entry["modelVersionName"] == "v1.0"
    assert entry["modelVersionId"] == 111

    assert saved == [recipe]
    assert recipe["modified"] == 123.0  # Metis F8 — never bumped
    assert recipe["fingerprint"] == calculate_recipe_fingerprint([entry])
    assert fts_calls == [(recipe, "update")]
    assert resort_calls == []  # Metis F1 — hoisted to public entry points


# Acceptance criterion (2): checkpoint entry rematched via L2 — parser style


async def test_rematch_recipe_by_id_checkpoint_l2_parser_style_backfill(
    tmp_path: Path, monkeypatch
):
    sha256 = ("C" * 64).lower()
    cp_item = _civitai_checkpoint_item(
        sha256=sha256,
        version_id=222,
        name="v2.0",
        model_name="Checkpoint Model",
        file_name="cp.safetensors",
        base_model="SD 1.5",
    )
    scanner, _, _ = _make_rematch_scanner([], [cp_item], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "checkpoint": {
            "isDeleted": True,
            "modelVersionId": 222,
            "type": "checkpoint",
            "name": "old-name",
            "version": "old-v",
            "baseModel": "SD 1.5",
            "file_name": "old.safetensors",
            "hash": "",
        },
        "loras": [],
    }
    _set_recipe_cache(scanner, [recipe])
    saved, _ = await _spy_rematch_persistence(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    assert result["rematched"] == 1

    cp = recipe["checkpoint"]
    assert cp["isDeleted"] is False
    assert cp["hash"] == sha256
    assert cp["file_name"] == "cp.safetensors"
    assert cp["name"] == "Checkpoint Model"
    assert cp["version"] == "v2.0"
    assert cp["baseModel"] == "SD 1.5"
    assert cp["modelVersionId"] == 222  # identifier key convention preserved
    assert "modelName" not in cp  # Oracle R2-F5 — never added to parser-style
    assert "modelVersionName" not in cp
    assert saved == [recipe]


# Acceptance criterion (2): checkpoint widget-style names updated (Oracle R3-F2)


async def test_rematch_recipe_by_id_checkpoint_widget_style_names_updated(
    tmp_path: Path, monkeypatch
):
    cp_item = _civitai_checkpoint_item(
        sha256=("D" * 64).lower(),
        version_id=333,
        name="v3.0",
        model_name="Widget Model",
    )
    scanner, _, _ = _make_rematch_scanner([], [cp_item], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "checkpoint": {
            "isDeleted": True,
            "modelVersionId": 333,
            "modelName": "stale-name",
            "modelVersionName": "stale-v",
            "file_name": "old.safetensors",
            "hash": "",
        },
        "loras": [],
    }
    _set_recipe_cache(scanner, [recipe])
    await _spy_rematch_persistence(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    cp = recipe["checkpoint"]
    assert cp["modelName"] == "Widget Model"
    assert cp["modelVersionName"] == "v3.0"


# Acceptance criterion (3): PENDING-HASH GUARD (Oracle R2-F3)


async def test_rematch_recipe_by_id_pending_hash_guard_preserves_existing_hash(
    tmp_path: Path, monkeypatch
):
    # Item matched via L2 carries sha256 == "" (hash_status pending).
    item = _civitai_lora_item(
        sha256="", version_id=444, name="v4", model_name="Pending", file_name="p.safetensors"
    )
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    stored_hash = "aabbccddeeff"
    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {
                "isDeleted": True,
                "hash": stored_hash,
                "modelVersionId": 444,
                "file_name": "old.safetensors",
            }
        ],
    }
    _set_recipe_cache(scanner, [recipe])
    await _spy_rematch_persistence(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    assert result["rematched"] == 1
    entry = recipe["loras"][0]
    assert entry["hash"] == stored_hash  # preserved, NOT wiped to ""
    assert entry["isDeleted"] is False
    assert entry["file_name"] == "p.safetensors"


# Acceptance criterion (4)+(5): exclude preserved (Metis F4), modified untouched (Metis F8)


async def test_rematch_recipe_by_id_preserves_exclude_and_modified(
    tmp_path: Path, monkeypatch
):
    sha256 = ("E" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=555, name="v5")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "modified": 999.0,
        "loras": [
            {
                "isDeleted": True,
                "hash": sha256,
                "file_name": "old.safetensors",
                "exclude": True,
            }
        ],
    }
    _set_recipe_cache(scanner, [recipe])
    await _spy_rematch_persistence(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    entry = recipe["loras"][0]
    assert entry["exclude"] is True
    assert recipe["modified"] == 999.0


# Acceptance criterion (6): no-change recipe → no persistence, rematched=0


async def test_rematch_recipe_by_id_no_change_skips_persistence(
    tmp_path: Path, monkeypatch
):
    sha256 = ("F" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=666, name="v6")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "fingerprint": "original",
        "loras": [
            # Healthy entry — not a rematch candidate, nothing to change.
            {"isDeleted": False, "hash": sha256, "file_name": "m.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])

    saved, enriched = await _spy_rematch_persistence(scanner, monkeypatch)
    fts_calls = await _spy_fts(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    assert result["rematched"] == 0
    assert result["skipped"] == 1
    assert result["recipe"] is recipe  # raw cache dict, not enriched
    assert saved == []
    assert fts_calls == []
    assert resort_calls == []
    assert recipe["fingerprint"] == "original"  # no fingerprint churn


# Acceptance criterion (7): fingerprint recomputed on hash change


async def test_rematch_recipe_by_id_fingerprint_recomputed_on_hash_change(
    tmp_path: Path, monkeypatch
):
    sha256 = ("G" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=777, name="v7")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {
                "isDeleted": True,
                "hash": "oldhash123",
                "modelVersionId": 777,
                "file_name": "old.safetensors",
            }
        ],
    }
    _set_recipe_cache(scanner, [recipe])
    original_fingerprint = calculate_recipe_fingerprint([dict(recipe["loras"][0])])
    await _spy_rematch_persistence(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    entry = recipe["loras"][0]
    assert entry["hash"] == sha256
    assert recipe["fingerprint"] == calculate_recipe_fingerprint([entry])
    assert recipe["fingerprint"] != original_fingerprint


# Acceptance criterion (7): fingerprint UNCHANGED when only isDeleted flips (Metis F16a)


async def test_rematch_recipe_by_id_fingerprint_unchanged_when_only_deleted_flips(
    tmp_path: Path, monkeypatch
):
    sha256 = ("H" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=888, name="v8")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {"isDeleted": True, "hash": sha256, "file_name": "old.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])
    original_fingerprint = calculate_recipe_fingerprint([dict(recipe["loras"][0])])
    await _spy_rematch_persistence(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    assert result["rematched"] == 1
    assert recipe["loras"][0]["isDeleted"] is False
    assert recipe["fingerprint"] == original_fingerprint  # hash-only fingerprint


# Acceptance criterion (8): hash-empty entry via L2 → fingerprint form changes (Metis F16b)


async def test_rematch_recipe_by_id_fingerprint_changes_from_version_fallback_to_hash(
    tmp_path: Path, monkeypatch
):
    sha256 = ("I" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=999, name="v9")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {"isDeleted": True, "hash": "", "modelVersionId": 999, "file_name": "old.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])
    original_fingerprint = calculate_recipe_fingerprint([dict(recipe["loras"][0])])
    assert original_fingerprint == "999:1.0"  # modelVersionId fallback form

    await _spy_rematch_persistence(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    entry = recipe["loras"][0]
    assert entry["hash"] == sha256
    assert recipe["fingerprint"] == calculate_recipe_fingerprint([entry])
    assert recipe["fingerprint"] != original_fingerprint


# Acceptance criterion (9): FTS called only when persistence returned True
# (False branch covered by the persist-failure test below)


async def test_rematch_recipe_by_id_fts_skipped_when_persistence_false_stub(
    tmp_path: Path, monkeypatch
):
    sha256 = ("J" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=1000, name="v10")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {"isDeleted": True, "hash": sha256, "file_name": "old.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])

    saved, _ = await _spy_rematch_persistence(scanner, monkeypatch, save_result=False)
    fts_calls = await _spy_fts(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is False
    assert result["errors"] == 1
    assert result["rematched"] == 0
    assert result["skipped"] == 0
    assert result["recipe"] is recipe
    assert "error" in result
    assert saved == [recipe]
    assert fts_calls == []
    assert resort_calls == []


# Acceptance criterion (10): PERSIST-FAILURE via EXIF raise (Oracle R1-F2/R2-F2/R4-F2)


async def test_rematch_recipe_by_id_exif_raise_counts_error_and_skips_fts(
    tmp_path: Path, monkeypatch
):
    sha256 = ("K" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=1001, name="v11")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {"isDeleted": True, "hash": sha256, "file_name": "old.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])

    # Real persist path: JSON file + existing image so EXIF is reached.
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir(exist_ok=True)
    json_path = recipes_dir / "r1.recipe.json"
    json_path.write_text(json.dumps(recipe))
    image = tmp_path / "r1.png"
    image.write_bytes(b"fake-png")
    recipe["file_path"] = str(image)

    async def fake_get_json_path(rid: str) -> str:
        return str(json_path)

    monkeypatch.setattr(scanner, "get_recipe_json_path", fake_get_json_path)

    def _boom_exif(image_path, recipe_data):
        raise RuntimeError("exif boom")

    monkeypatch.setattr(
        "py.utils.exif_utils.ExifUtils.append_recipe_metadata", _boom_exif
    )
    fts_calls = await _spy_fts(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is False
    assert result["errors"] == 1
    assert result["rematched"] == 0
    assert result["skipped"] == 0
    assert result["recipe"] is recipe
    assert "error" in result
    assert fts_calls == []
    assert resort_calls == []


# Acceptance criterion (11): LEGACY STRING CHECKPOINT (Oracle R1-F3)


async def test_rematch_recipe_by_id_legacy_string_checkpoint_skipped(
    tmp_path: Path, monkeypatch
):
    sha256 = ("L" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=1002, name="v12")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "checkpoint": "name.safetensors",  # bare string — must not crash
        "loras": [
            {"isDeleted": True, "hash": sha256, "file_name": "old.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])
    saved, _ = await _spy_rematch_persistence(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    assert result["rematched"] == 1  # loras still processed
    assert recipe["checkpoint"] == "name.safetensors"  # skipped silently
    assert recipe["loras"][0]["isDeleted"] is False
    assert saved == [recipe]


# Acceptance criterion (12): recipe not found → RecipeNotFoundError (handler → 404)


async def test_rematch_recipe_by_id_not_found_raises(tmp_path: Path):
    from py.services.recipes.errors import RecipeNotFoundError

    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    _set_recipe_cache(scanner, [])

    with pytest.raises(RecipeNotFoundError):
        await scanner.rematch_recipe_by_id("missing")


# Acceptance criterion (13): EXIF written once per changed recipe


async def test_rematch_recipe_by_id_exif_written_once(tmp_path: Path, monkeypatch):
    sha256 = ("M" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=1003, name="v13")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {"isDeleted": True, "hash": sha256, "file_name": "old.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])

    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir(exist_ok=True)
    json_path = recipes_dir / "r1.recipe.json"
    json_path.write_text(json.dumps(recipe))
    image = tmp_path / "r1.png"
    image.write_bytes(b"fake-png")
    recipe["file_path"] = str(image)

    async def fake_get_json_path(rid: str) -> str:
        return str(json_path)

    monkeypatch.setattr(scanner, "get_recipe_json_path", fake_get_json_path)

    exif_calls: list[tuple[Any, Any]] = []

    def _spy_exif(image_path, recipe_data):
        exif_calls.append((image_path, recipe_data))

    monkeypatch.setattr(
        "py.utils.exif_utils.ExifUtils.append_recipe_metadata", _spy_exif
    )

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    assert len(exif_calls) == 1
    assert exif_calls[0][0] == str(image)
    assert exif_calls[0][1] is recipe


# Acceptance criterion (14): response recipe is the enriched dict (Metis F14)


async def test_rematch_recipe_by_id_response_recipe_enriched(tmp_path: Path, monkeypatch):
    sha256 = ("N" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=1004, name="v14")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {"isDeleted": True, "hash": sha256, "file_name": "old.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])

    saved, enriched = await _spy_rematch_persistence(scanner, monkeypatch)

    result = await scanner.rematch_recipe_by_id("r1")

    assert result["success"] is True
    assert result["recipe"] is enriched
    assert result["recipe"]["file_url"]
    assert saved == [recipe]


# ---------------------------------------------------------------------------
# rematch_all_recipes / rematch_recipes_bulk — bulk + progress (plan todo 3)
# ---------------------------------------------------------------------------


async def test_rematch_all_recipes_progress_sequence(tmp_path: Path, monkeypatch):
    sha256 = ("A" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=111, name="v1")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipes: list[Dict[str, Any]] = [
        {
            "id": "r1",
            "loras": [
                {"isDeleted": True, "hash": sha256, "file_name": "old.safetensors"}
            ],
        },
        {
            "id": "r2",
            "loras": [
                {"isDeleted": True, "hash": "zzz", "file_name": "gone.safetensors"}
            ],
        },
    ]
    _set_recipe_cache(scanner, recipes)
    await _spy_rematch_persistence(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    events: list[Dict[str, Any]] = []

    async def cb(ev: Dict[str, Any]) -> None:
        events.append(ev)

    result = await scanner.rematch_all_recipes(progress_callback=cb)

    assert [e["status"] for e in events] == [
        "started",
        "processing",
        "processing",
        "completed",
    ]
    assert events[1]["current"] == 1 and events[1]["total"] == 2
    assert events[2]["current"] == 2 and events[2]["total"] == 2
    assert events[3]["status"] == "completed"
    assert events[3]["rematched"] == 1
    assert events[3]["skipped"] == 1
    assert events[3]["errors"] == 0
    assert events[3]["total"] == 2
    assert events[3]["matched_recipes"] == 1
    assert events[3]["matched_entries"] == 1
    assert events[3]["unresolved_recipes"] == 1
    assert events[3]["unresolved_entries"] == 1

    assert result["success"] is True
    assert result["rematched"] == 1
    assert result["skipped"] == 1
    assert result["errors"] == 0
    assert result["total"] == 2
    assert result["matched_recipes"] == 1
    assert result["matched_entries"] == 1
    assert result["unresolved_recipes"] == 1
    assert result["unresolved_entries"] == 1
    assert "status" not in result
    assert resort_calls == [True]  # Metis F1 — exactly once per run


async def test_rematch_all_recipes_cancellation_stops_mid_loop(
    tmp_path: Path, monkeypatch
):
    sha256 = ("B" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=222, name="v2")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)

    recipes: list[Dict[str, Any]] = [
        {
            "id": f"r{i}",
            "loras": [
                {
                    "isDeleted": True,
                    "hash": sha256,
                    "file_name": f"old{i}.safetensors",
                }
            ],
        }
        for i in range(3)
    ]
    _set_recipe_cache(scanner, recipes)
    saved, _ = await _spy_rematch_persistence(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    events: list[Dict[str, Any]] = []
    cancelled = False

    async def cb(ev: Dict[str, Any]) -> None:
        nonlocal cancelled
        events.append(ev)
        if ev.get("status") == "processing" and ev.get("current") == 1:
            if not cancelled:
                cancelled = True
                scanner.cancel_task()

    result = await scanner.rematch_all_recipes(progress_callback=cb)

    assert result["status"] == "cancelled"
    assert result["success"] is False
    assert result["rematched"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == 0
    assert result["total"] == 3

    # Only the first recipe was processed — the later ones are untouched.
    assert recipes[0]["loras"][0]["isDeleted"] is False
    assert recipes[1]["loras"][0]["isDeleted"] is True
    assert recipes[2]["loras"][0]["isDeleted"] is True
    assert len(saved) == 1
    assert [e["status"] for e in events][-1] == "cancelled"
    assert events[-1]["current"] == 1
    assert resort_calls == []  # cancelled run — no resort scheduled


async def test_rematch_all_recipes_per_recipe_error_continues_loop(
    tmp_path: Path, monkeypatch
):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    _set_recipe_cache(
        scanner,
        [{"id": "boom", "name": "Broken"}, {"id": "fine", "loras": []}],
    )
    await _spy_rematch_persistence(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    async def fake_single(
        recipe: Dict[str, Any],
        local_cache: dict[str, Any],
        autov3_cache: dict[str, Any],
    ) -> tuple[int, int, dict[str, Any]]:
        if recipe.get("id") == "boom":
            raise RuntimeError("kaboom")
        return (0, 0, {"matched": [], "unresolved": []})

    monkeypatch.setattr(scanner, "_rematch_single_recipe", fake_single)

    events: list[Dict[str, Any]] = []

    async def cb(ev: Dict[str, Any]) -> None:
        events.append(ev)

    result = await scanner.rematch_all_recipes(progress_callback=cb)

    assert result["success"] is True
    assert result["errors"] == 1
    assert result["rematched"] == 0
    assert result["skipped"] == 1
    assert result["total"] == 2
    # The loop continued past the failing recipe.
    assert [e["status"] for e in events] == [
        "started",
        "processing",
        "processing",
        "completed",
    ]
    assert resort_calls == [True]


async def test_rematch_all_recipes_schedule_resort_exactly_once(
    tmp_path: Path, monkeypatch
):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    _set_recipe_cache(scanner, [{"id": "a", "loras": []}, {"id": "b", "loras": []}])
    await _spy_rematch_persistence(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    await scanner.rematch_all_recipes()

    assert resort_calls == [True]


async def test_rematch_all_recipes_holds_mutation_lock(tmp_path: Path, monkeypatch):
    scanner, _, _ = _make_rematch_scanner([], [], tmp_path)
    recipes = [{"id": f"r{i}", "loras": []} for i in range(5)]
    _set_recipe_cache(scanner, recipes)
    await _spy_rematch_persistence(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    entered = False
    release = asyncio.Event()
    original = scanner._rematch_single_recipe

    async def blocking_single(
        recipe: Dict[str, Any],
        local_cache: dict[str, Any],
        autov3_cache: dict[str, Any],
    ) -> tuple[int, int]:
        nonlocal entered
        if recipe.get("id") == "r0":
            entered = True
            await release.wait()
        return await original(recipe, local_cache, autov3_cache)

    monkeypatch.setattr(scanner, "_rematch_single_recipe", blocking_single)

    run_task = asyncio.create_task(scanner.rematch_all_recipes())
    for _ in range(100):
        if entered:
            break
        await asyncio.sleep(0.01)
    assert entered  # the run is now inside the lock

    acquired = asyncio.Event()

    async def probe() -> None:
        async with scanner._mutation_lock:
            acquired.set()

    probe_task = asyncio.create_task(probe())
    done, _ = await asyncio.wait([probe_task], timeout=0.1)
    assert not done  # mutation_lock is held by the run
    assert not acquired.is_set()

    release.set()
    await run_task
    await probe_task

    assert resort_calls == [True]


async def test_rematch_bulk_not_found_ids_skipped(tmp_path: Path, monkeypatch):
    sha256 = ("C" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=333, name="v3")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    recipes: list[Dict[str, Any]] = [
        {
            "id": f"r{i}",
            "loras": [
                {
                    "isDeleted": True,
                    "hash": sha256,
                    "file_name": f"old{i}.safetensors",
                }
            ],
        }
        for i in range(2)
    ]
    _set_recipe_cache(scanner, recipes)
    saved, enriched = await _spy_rematch_persistence(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    result = await scanner.rematch_recipes_bulk(["r0", "missing", "r1"])

    assert result["success"] is True
    assert result["total"] == 3
    assert result["rematched"] == 2  # r0 and r1 both matched
    assert result["skipped"] == 1  # missing id → RecipeNotFoundError → skipped
    assert result["errors"] == 0
    assert result["recipes"] == [enriched, enriched]
    assert saved == [recipes[0], recipes[1]]
    assert resort_calls == [True]


async def test_rematch_bulk_persist_failure_counted_once(tmp_path: Path, monkeypatch):
    sha256 = ("D" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=444, name="v4")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {"isDeleted": True, "hash": sha256, "file_name": "old.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])
    saved, _ = await _spy_rematch_persistence(scanner, monkeypatch, save_result=False)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    result = await scanner.rematch_recipes_bulk(["r1"])

    # Persist failure surfaces via the by_id summary's errors field and is NOT
    # additionally counted by the bulk loop (Oracle R2-F2 — no double count).
    assert result["errors"] == 1
    assert result["rematched"] == 0
    assert result["skipped"] == 0
    assert result["total"] == 1
    assert saved == [recipe]
    assert resort_calls == [True]


async def test_rematch_bulk_generic_exception_continues(tmp_path: Path, monkeypatch):
    sha256 = ("E" * 64).lower()
    item = _civitai_lora_item(sha256=sha256, version_id=555, name="v5")
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    recipes: list[Dict[str, Any]] = [
        {
            "id": f"r{i}",
            "loras": [
                {
                    "isDeleted": True,
                    "hash": sha256,
                    "file_name": f"old{i}.safetensors",
                }
            ],
        }
        for i in range(2)
    ]
    _set_recipe_cache(scanner, recipes)
    await _spy_rematch_persistence(scanner, monkeypatch)
    resort_calls = await _spy_resort(scanner, monkeypatch)

    # A generic exception inside matching escapes by_id (only
    # RecipePersistenceError is converted there) and is caught by the bulk
    # loop, which continues with the remaining ids (Oracle R4-F3).
    calls = 0

    async def fake_match(
        entry: Dict[str, Any],
        local_cache: dict[str, Any],
        autov3_cache: dict[str, Any],
        *,
        is_checkpoint: bool,
    ) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("match boom")
        return (None, None)

    monkeypatch.setattr(scanner, "_match_rematch_entry_with_level", fake_match)

    result = await scanner.rematch_recipes_bulk(["r0", "r1"])

    assert result["success"] is True
    assert result["errors"] == 1
    assert result["rematched"] == 0
    assert result["skipped"] == 1  # r1 still processed after r0 blew up
    assert result["total"] == 2
    assert resort_calls == [True]


async def test_rematch_all_autov3_cache_reuse_across_calls(
    tmp_path: Path, monkeypatch
):
    from py.services import recipe_scanner as recipe_scanner_module

    called: list[str] = []

    def fake_calculate_autov3(file_path: str) -> str:
        called.append(file_path)
        return "AAAABBBBCCCD"

    monkeypatch.setattr(recipe_scanner_module, "calculate_autov3", fake_calculate_autov3)

    item = _rematch_item(
        sha256=("F" * 64).lower(), autov3=None, sub_type="lora"
    )
    scanner, _, _ = _make_rematch_scanner([item], [], tmp_path)
    recipe: Dict[str, Any] = {
        "id": "r1",
        "loras": [
            {"isDeleted": True, "hash": "AAAABBBBCCCD", "file_name": "old.safetensors"}
        ],
    }
    _set_recipe_cache(scanner, [recipe])
    await _spy_rematch_persistence(scanner, monkeypatch)

    first = await scanner.rematch_recipe_by_id("r1")
    second = await scanner.rematch_recipe_by_id("r1")

    assert first["success"] is True
    assert second["success"] is True
    # The version-cached autov3 snapshot is reused — the safetensors headers
    # are read once across both calls (Oracle R2-F4).
    assert len(called) == 1

