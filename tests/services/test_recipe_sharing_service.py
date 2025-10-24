import logging

import pytest

from py.services.recipes.errors import RecipeNotFoundError
from py.services.recipes.sharing_service import RecipeSharingService


class DummyScanner:
    def __init__(self, recipe_by_id):
        self._recipes = recipe_by_id

    async def get_recipe_by_id(self, recipe_id):
        return self._recipes.get(recipe_id)


@pytest.mark.asyncio
async def test_share_recipe_sanitizes_filename(tmp_path):
    image_path = tmp_path / "original.png"
    image_path.write_bytes(b"data")

    recipe_id = "unsafe:id"
    recipe = {
        "file_path": str(image_path),
        "title": "Bad\rTitle\n../",
    }
    scanner = DummyScanner({recipe_id: recipe})

    service = RecipeSharingService(ttl_seconds=30, logger=logging.getLogger("test"))

    result = await service.share_recipe(recipe_scanner=scanner, recipe_id=recipe_id)
    assert result.payload["filename"] == "recipe_bad_title.png"

    download_info = await service.prepare_download(recipe_scanner=scanner, recipe_id=recipe_id)
    assert download_info.download_filename == "recipe_bad_title.png"

    service._cleanup_entry(recipe_id)


@pytest.mark.asyncio
async def test_share_recipe_falls_back_to_recipe_id(tmp_path):
    image_path = tmp_path / "original.png"
    image_path.write_bytes(b"data")

    recipe_id = "ID 123"
    recipe = {
        "file_path": str(image_path),
        "title": "\n\t",
    }
    scanner = DummyScanner({recipe_id: recipe})

    service = RecipeSharingService(ttl_seconds=30, logger=logging.getLogger("test"))

    result = await service.share_recipe(recipe_scanner=scanner, recipe_id=recipe_id)
    assert result.payload["filename"] == "recipe_id_123.png"

    service._cleanup_entry(recipe_id)


@pytest.mark.asyncio
async def test_prepare_download_rejects_expired(tmp_path):
    service = RecipeSharingService(ttl_seconds=30, logger=logging.getLogger("test"))

    image_path = tmp_path / "original.png"
    image_path.write_bytes(b"data")
    recipe_id = "recipe"

    recipe = {"file_path": str(image_path), "title": "sample"}
    scanner = DummyScanner({recipe_id: recipe})

    await service.share_recipe(recipe_scanner=scanner, recipe_id=recipe_id)

    # Force the entry to expire
    service._shared_recipes[recipe_id]["expires"] = 0

    with pytest.raises(RecipeNotFoundError):
        await service.prepare_download(recipe_scanner=scanner, recipe_id=recipe_id)

    service._cleanup_entry(recipe_id)
