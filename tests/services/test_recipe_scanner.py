import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from py.config import config
from py.services.recipe_scanner import RecipeScanner
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
        self._models_by_name: dict[str, dict] = {}
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

    def register_model(self, name: str, info: dict) -> None:
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
        self._cache.raw_data.append({
            "sha256": info.get("sha256", ""),
            "path": info.get("file_path", ""),
            "civitai": info.get("civitai", {}),
        })


@pytest.fixture
def recipe_scanner(tmp_path: Path, monkeypatch):
    RecipeScanner._instance = None
    monkeypatch.setattr(config, "loras_roots", [str(tmp_path)])
    stub = StubLoraScanner()
    scanner = RecipeScanner(lora_scanner=stub)
    asyncio.run(scanner.refresh_cache(force=True))
    yield scanner, stub
    RecipeScanner._instance = None


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
    await asyncio.sleep(0)
    cache = await scanner.get_cached_data()

    assert {item["id"] for item in cache.raw_data} == {"one", "two"}
    assert len(cache.sorted_by_name) == len(cache.raw_data)


async def test_remove_recipe_during_reads(recipe_scanner):
    scanner, _ = recipe_scanner

    recipe_ids = ["alpha", "beta", "gamma"]
    for index, recipe_id in enumerate(recipe_ids):
        await scanner.add_recipe({
            "id": recipe_id,
            "file_path": f"path/{recipe_id}.png",
            "title": recipe_id,
            "modified": float(index),
            "created_date": float(index),
            "loras": [],
        })

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
            {"file_name": "old", "strength": 1.0, "hash": "", "isDeleted": True, "exclude": True},
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
    scanner = RecipeScanner(lora_scanner=lora_scanner)

    await scanner.initialize_in_background()

    assert ready_flag.is_set()
    assert call_count == 1
    assert scanner._cache is not None


@pytest.mark.asyncio
async def test_invalid_model_version_marked_deleted_and_not_retried(monkeypatch, recipe_scanner):
    scanner, _ = recipe_scanner
    recipes_dir = Path(config.loras_roots[0]) / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    recipe = {
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
async def test_load_recipe_persists_deleted_flag_on_invalid_version(monkeypatch, recipe_scanner, tmp_path):
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
async def test_update_lora_filename_by_hash_updates_affected_recipes(tmp_path: Path, recipe_scanner):
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
            {"file_name": "other_lora", "hash": "hash2"}
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
        "loras": [
            {"file_name": "other_lora", "hash": "hash2"}
        ],
    }
    recipe2_path.write_text(json.dumps(recipe2_data))
    await scanner.add_recipe(dict(recipe2_data))

    # Update LoRA name for "hash1" (using different case to test normalization)
    new_name = "new_name"
    file_count, cache_count = await scanner.update_lora_filename_by_hash("HASH1", new_name)

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
    await scanner.add_recipe({
        "id": "regular",
        "file_path": "path/regular.png",
        "title": "Regular Recipe",
        "modified": 1.0,
        "created_date": 1.0,
        "loras": [],
    })
    
    # Add a favorite recipe
    await scanner.add_recipe({
        "id": "favorite",
        "file_path": "path/favorite.png",
        "title": "Favorite Recipe",
        "modified": 2.0,
        "created_date": 2.0,
        "loras": [],
        "favorite": True
    })
    
    # Wait for cache update (it's async in some places, add_recipe is usually enough but let's be safe)
    await asyncio.sleep(0)
    
    # Test without filter (should return both)
    result_all = await scanner.get_paginated_data(page=1, page_size=10)
    assert len(result_all["items"]) == 2
    
    # Test with favorite filter
    result_fav = await scanner.get_paginated_data(page=1, page_size=10, filters={"favorite": True})
    assert len(result_fav["items"]) == 1
    assert result_fav["items"][0]["id"] == "favorite"
    
    # Test with favorite filter set to False (should return both or at least not filter if it's the default)
    # Actually our implementation checks if 'favorite' in filters and filters['favorite']
    result_fav_false = await scanner.get_paginated_data(page=1, page_size=10, filters={"favorite": False})
    assert len(result_fav_false["items"]) == 2


@pytest.mark.asyncio
async def test_get_paginated_data_filters_by_prompt(recipe_scanner):
    scanner, _ = recipe_scanner
    
    # Add a recipe with a specific prompt
    await scanner.add_recipe({
        "id": "prompt-recipe",
        "file_path": "path/prompt.png",
        "title": "Prompt Recipe",
        "modified": 1.0,
        "created_date": 1.0,
        "loras": [],
        "gen_params": {
            "prompt": "a beautiful forest landscape"
        }
    })
    
    # Add a recipe with a specific negative prompt
    await scanner.add_recipe({
        "id": "neg-prompt-recipe",
        "file_path": "path/neg.png",
        "title": "Negative Prompt Recipe",
        "modified": 2.0,
        "created_date": 2.0,
        "loras": [],
        "gen_params": {
            "negative_prompt": "ugly, blurry mountains"
        }
    })
    
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
    await scanner.add_recipe({
        "id": "A", "title": "Alpha", "created_date": 10.0,
        "loras": [{}, {}], "file_path": "a.png"
    })
    # Recipe B: Name "Beta", Date 20, LoRAs 1
    await scanner.add_recipe({
        "id": "B", "title": "Beta", "created_date": 20.0,
        "loras": [{}], "file_path": "b.png"
    })
    # Recipe C: Name "Gamma", Date 5, LoRAs 3
    await scanner.add_recipe({
        "id": "C", "title": "Gamma", "created_date": 5.0,
        "loras": [{}, {}, {}], "file_path": "c.png"
    })
    
    await asyncio.sleep(0)
    
    # Test Name DESC: Gamma, Beta, Alpha
    res = await scanner.get_paginated_data(page=1, page_size=10, sort_by="name:desc")
    assert [i["id"] for i in res["items"]] == ["C", "B", "A"]
    
    # Test LoRA Count DESC: Gamma (3), Alpha (2), Beta (1)
    res = await scanner.get_paginated_data(page=1, page_size=10, sort_by="loras_count:desc")
    assert [i["id"] for i in res["items"]] == ["C", "A", "B"]
    
    # Test LoRA Count ASC: Beta (1), Alpha (2), Gamma (3)
    res = await scanner.get_paginated_data(page=1, page_size=10, sort_by="loras_count:asc")
    assert [i["id"] for i in res["items"]] == ["B", "A", "C"]
    
    # Test Date ASC: Gamma (5), Alpha (10), Beta (20)
    res = await scanner.get_paginated_data(page=1, page_size=10, sort_by="date:asc")
    assert [i["id"] for i in res["items"]] == ["C", "A", "B"]
