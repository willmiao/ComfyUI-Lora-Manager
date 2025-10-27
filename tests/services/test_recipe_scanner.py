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
        self._cache = SimpleNamespace(raw_data=[])

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
        if hash_value:
            self._hash_meta[hash_value] = {
                "path": info.get("file_path", ""),
                "preview_url": info.get("preview_url", ""),
            }
            self._hash_index._hash_to_path[hash_value] = info.get("file_path", "")
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
