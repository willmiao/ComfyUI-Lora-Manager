"""Services handling recipe sharing and downloads."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict

from .errors import RecipeNotFoundError


@dataclass(frozen=True)
class SharingResult:
    """Return payload for share operations."""

    payload: dict[str, Any]
    status: int = 200


@dataclass(frozen=True)
class DownloadInfo:
    """Information required to stream a shared recipe file."""

    file_path: str
    download_filename: str


class RecipeSharingService:
    """Prepare temporary recipe downloads with TTL cleanup."""

    def __init__(self, *, ttl_seconds: int = 300, logger) -> None:
        self._ttl_seconds = ttl_seconds
        self._logger = logger
        self._shared_recipes: Dict[str, Dict[str, Any]] = {}

    async def share_recipe(self, *, recipe_scanner, recipe_id: str) -> SharingResult:
        """Prepare a temporary downloadable copy of a recipe image."""

        recipe = await recipe_scanner.get_recipe_by_id(recipe_id)
        if not recipe:
            raise RecipeNotFoundError("Recipe not found")

        image_path = recipe.get("file_path")
        if not image_path or not os.path.exists(image_path):
            raise RecipeNotFoundError("Recipe image not found")

        ext = os.path.splitext(image_path)[1]
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
            temp_path = temp_file.name

        shutil.copy2(image_path, temp_path)
        timestamp = int(time.time())
        self._shared_recipes[recipe_id] = {
            "path": temp_path,
            "timestamp": timestamp,
            "expires": time.time() + self._ttl_seconds,
        }
        self._cleanup_shared_recipes()

        filename = self._build_download_filename(
            title=recipe.get("title", ""), recipe_id=recipe_id, ext=ext
        )
        url_path = f"/api/lm/recipe/{recipe_id}/share/download?t={timestamp}"
        return SharingResult({"success": True, "download_url": url_path, "filename": filename})

    async def prepare_download(self, *, recipe_scanner, recipe_id: str) -> DownloadInfo:
        """Return file path and filename for a prepared shared recipe."""

        shared_info = self._shared_recipes.get(recipe_id)
        if not shared_info or time.time() > shared_info.get("expires", 0):
            self._cleanup_entry(recipe_id)
            raise RecipeNotFoundError("Shared recipe not found or expired")

        file_path = shared_info["path"]
        if not os.path.exists(file_path):
            self._cleanup_entry(recipe_id)
            raise RecipeNotFoundError("Shared recipe file not found")

        recipe = await recipe_scanner.get_recipe_by_id(recipe_id)
        ext = os.path.splitext(file_path)[1]
        download_filename = self._build_download_filename(
            title=recipe.get("title", "") if recipe else "",
            recipe_id=recipe_id,
            ext=ext,
        )
        return DownloadInfo(file_path=file_path, download_filename=download_filename)

    @staticmethod
    def _build_download_filename(*, title: str, recipe_id: str, ext: str) -> str:
        """Generate a sanitized filename safe for HTTP headers and filesystems."""

        ext = ext or ""
        safe_title = RecipeSharingService._slugify(title)
        fallback = RecipeSharingService._slugify(recipe_id)
        identifier = safe_title or fallback or "recipe"
        return f"recipe_{identifier}{ext}"

    @staticmethod
    def _slugify(value: str) -> str:
        """Convert arbitrary input into a lowercase, header-safe slug."""

        if not value:
            return ""

        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        ascii_value = ascii_value.replace("\n", " ").replace("\r", " ")
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_value)
        sanitized = re.sub(r"_+", "_", sanitized).strip("._-")
        return sanitized.lower()

    def _cleanup_shared_recipes(self) -> None:
        for recipe_id in list(self._shared_recipes.keys()):
            shared = self._shared_recipes.get(recipe_id)
            if not shared:
                continue
            if time.time() > shared.get("expires", 0):
                self._cleanup_entry(recipe_id)

    def _cleanup_entry(self, recipe_id: str) -> None:
        shared_info = self._shared_recipes.pop(recipe_id, None)
        if not shared_info:
            return
        file_path = shared_info.get("path")
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.error("Error cleaning up shared recipe %s: %s", recipe_id, exc)
