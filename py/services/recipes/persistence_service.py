"""Services encapsulating recipe persistence workflows."""
from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from ...config import config
from ...utils.utils import calculate_recipe_fingerprint
from .errors import RecipeNotFoundError, RecipeValidationError


@dataclass(frozen=True)
class PersistenceResult:
    """Return payload from persistence operations."""

    payload: dict[str, Any]
    status: int = 200


class RecipePersistenceService:
    """Coordinate recipe persistence tasks across storage and caches."""

    def __init__(
        self,
        *,
        exif_utils,
        card_preview_width: int,
        logger,
    ) -> None:
        self._exif_utils = exif_utils
        self._card_preview_width = card_preview_width
        self._logger = logger

    async def save_recipe(
        self,
        *,
        recipe_scanner,
        image_bytes: bytes | None,
        image_base64: str | None,
        name: str | None,
        tags: Iterable[str],
        metadata: Optional[dict[str, Any]],
    ) -> PersistenceResult:
        """Persist a user uploaded recipe."""

        missing_fields = []
        if not name:
            missing_fields.append("name")
        if metadata is None:
            missing_fields.append("metadata")
        if missing_fields:
            raise RecipeValidationError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )

        resolved_image_bytes = self._resolve_image_bytes(image_bytes, image_base64)
        recipes_dir = recipe_scanner.recipes_dir
        os.makedirs(recipes_dir, exist_ok=True)

        recipe_id = str(uuid.uuid4())
        optimized_image, extension = self._exif_utils.optimize_image(
            image_data=resolved_image_bytes,
            target_width=self._card_preview_width,
            format="webp",
            quality=85,
            preserve_metadata=True,
        )
        image_filename = f"{recipe_id}{extension}"
        image_path = os.path.join(recipes_dir, image_filename)
        normalized_image_path = os.path.normpath(image_path)
        with open(normalized_image_path, "wb") as file_obj:
            file_obj.write(optimized_image)

        current_time = time.time()
        loras_data = [self._normalise_lora_entry(lora) for lora in metadata.get("loras", [])]

        gen_params = metadata.get("gen_params", {})
        if not gen_params and "raw_metadata" in metadata:
            raw_metadata = metadata.get("raw_metadata", {})
            gen_params = {
                "prompt": raw_metadata.get("prompt", ""),
                "negative_prompt": raw_metadata.get("negative_prompt", ""),
                "checkpoint": raw_metadata.get("checkpoint", {}),
                "steps": raw_metadata.get("steps", ""),
                "sampler": raw_metadata.get("sampler", ""),
                "cfg_scale": raw_metadata.get("cfg_scale", ""),
                "seed": raw_metadata.get("seed", ""),
                "size": raw_metadata.get("size", ""),
                "clip_skip": raw_metadata.get("clip_skip", ""),
            }

        fingerprint = calculate_recipe_fingerprint(loras_data)
        recipe_data: Dict[str, Any] = {
            "id": recipe_id,
            "file_path": normalized_image_path,
            "title": name,
            "modified": current_time,
            "created_date": current_time,
            "base_model": metadata.get("base_model", ""),
            "loras": loras_data,
            "gen_params": gen_params,
            "fingerprint": fingerprint,
        }

        tags_list = list(tags)
        if tags_list:
            recipe_data["tags"] = tags_list

        if metadata.get("source_path"):
            recipe_data["source_path"] = metadata.get("source_path")

        json_filename = f"{recipe_id}.recipe.json"
        json_path = os.path.join(recipes_dir, json_filename)
        json_path = os.path.normpath(json_path)
        with open(json_path, "w", encoding="utf-8") as file_obj:
            json.dump(recipe_data, file_obj, indent=4, ensure_ascii=False)

        self._exif_utils.append_recipe_metadata(normalized_image_path, recipe_data)

        matching_recipes = await self._find_matching_recipes(recipe_scanner, fingerprint, exclude_id=recipe_id)
        await recipe_scanner.add_recipe(recipe_data)

        return PersistenceResult(
            {
                "success": True,
                "recipe_id": recipe_id,
                "image_path": normalized_image_path,
                "json_path": json_path,
                "matching_recipes": matching_recipes,
            }
        )

    async def delete_recipe(self, *, recipe_scanner, recipe_id: str) -> PersistenceResult:
        """Delete an existing recipe."""

        recipes_dir = recipe_scanner.recipes_dir
        if not recipes_dir or not os.path.exists(recipes_dir):
            raise RecipeNotFoundError("Recipes directory not found")

        recipe_json_path = os.path.join(recipes_dir, f"{recipe_id}.recipe.json")
        if not os.path.exists(recipe_json_path):
            raise RecipeNotFoundError("Recipe not found")

        with open(recipe_json_path, "r", encoding="utf-8") as file_obj:
            recipe_data = json.load(file_obj)

        image_path = recipe_data.get("file_path")
        os.remove(recipe_json_path)
        if image_path and os.path.exists(image_path):
            os.remove(image_path)

        await recipe_scanner.remove_recipe(recipe_id)
        return PersistenceResult({"success": True, "message": "Recipe deleted successfully"})

    async def update_recipe(self, *, recipe_scanner, recipe_id: str, updates: dict[str, Any]) -> PersistenceResult:
        """Update persisted metadata for a recipe."""

        if not any(key in updates for key in ("title", "tags", "source_path", "preview_nsfw_level")):
            raise RecipeValidationError(
                "At least one field to update must be provided (title or tags or source_path or preview_nsfw_level)"
            )

        success = await recipe_scanner.update_recipe_metadata(recipe_id, updates)
        if not success:
            raise RecipeNotFoundError("Recipe not found or update failed")

        return PersistenceResult({"success": True, "recipe_id": recipe_id, "updates": updates})

    async def reconnect_lora(
        self,
        *,
        recipe_scanner,
        recipe_id: str,
        lora_index: int,
        target_name: str,
    ) -> PersistenceResult:
        """Reconnect a LoRA entry within an existing recipe."""

        recipe_path = os.path.join(recipe_scanner.recipes_dir, f"{recipe_id}.recipe.json")
        if not os.path.exists(recipe_path):
            raise RecipeNotFoundError("Recipe not found")

        target_lora = await recipe_scanner.get_local_lora(target_name)
        if not target_lora:
            raise RecipeNotFoundError(f"Local LoRA not found with name: {target_name}")

        recipe_data, updated_lora = await recipe_scanner.update_lora_entry(
            recipe_id,
            lora_index,
            target_name=target_name,
            target_lora=target_lora,
        )

        image_path = recipe_data.get("file_path")
        if image_path and os.path.exists(image_path):
            self._exif_utils.append_recipe_metadata(image_path, recipe_data)

        matching_recipes = []
        if "fingerprint" in recipe_data:
            matching_recipes = await recipe_scanner.find_recipes_by_fingerprint(recipe_data["fingerprint"])
            if recipe_id in matching_recipes:
                matching_recipes.remove(recipe_id)

        return PersistenceResult(
            {
                "success": True,
                "recipe_id": recipe_id,
                "updated_lora": updated_lora,
                "matching_recipes": matching_recipes,
            }
        )

    async def bulk_delete(
        self,
        *,
        recipe_scanner,
        recipe_ids: Iterable[str],
    ) -> PersistenceResult:
        """Delete multiple recipes in a single request."""

        recipe_ids = list(recipe_ids)
        if not recipe_ids:
            raise RecipeValidationError("No recipe IDs provided")

        recipes_dir = recipe_scanner.recipes_dir
        if not recipes_dir or not os.path.exists(recipes_dir):
            raise RecipeNotFoundError("Recipes directory not found")

        deleted_recipes: list[str] = []
        failed_recipes: list[dict[str, Any]] = []

        for recipe_id in recipe_ids:
            recipe_json_path = os.path.join(recipes_dir, f"{recipe_id}.recipe.json")
            if not os.path.exists(recipe_json_path):
                failed_recipes.append({"id": recipe_id, "reason": "Recipe not found"})
                continue

            try:
                with open(recipe_json_path, "r", encoding="utf-8") as file_obj:
                    recipe_data = json.load(file_obj)
                image_path = recipe_data.get("file_path")
                os.remove(recipe_json_path)
                if image_path and os.path.exists(image_path):
                    os.remove(image_path)
                deleted_recipes.append(recipe_id)
            except Exception as exc:
                failed_recipes.append({"id": recipe_id, "reason": str(exc)})

        if deleted_recipes:
            await recipe_scanner.bulk_remove(deleted_recipes)

        return PersistenceResult(
            {
                "success": True,
                "deleted": deleted_recipes,
                "failed": failed_recipes,
                "total_deleted": len(deleted_recipes),
                "total_failed": len(failed_recipes),
            }
        )

    async def save_recipe_from_widget(
        self,
        *,
        recipe_scanner,
        metadata: dict[str, Any],
        image_bytes: bytes,
    ) -> PersistenceResult:
        """Save a recipe constructed from widget metadata."""

        if not metadata:
            raise RecipeValidationError("No generation metadata found")

        recipes_dir = recipe_scanner.recipes_dir
        os.makedirs(recipes_dir, exist_ok=True)

        recipe_id = str(uuid.uuid4())
        optimized_image, extension = self._exif_utils.optimize_image(
            image_data=image_bytes,
            target_width=self._card_preview_width,
            format="webp",
            quality=85,
            preserve_metadata=True,
        )
        image_filename = f"{recipe_id}{extension}"
        image_path = os.path.join(recipes_dir, image_filename)
        with open(image_path, "wb") as file_obj:
            file_obj.write(optimized_image)

        lora_stack = metadata.get("loras", "")
        lora_matches = re.findall(r"<lora:([^:]+):([^>]+)>", lora_stack)
        if not lora_matches:
            raise RecipeValidationError("No LoRAs found in the generation metadata")

        loras_data = []
        base_model_counts: Dict[str, int] = {}

        for name, strength in lora_matches:
            lora_info = await recipe_scanner.get_local_lora(name)
            lora_data = {
                "file_name": name,
                "strength": float(strength),
                "hash": (lora_info.get("sha256") or "").lower() if lora_info else "",
                "modelVersionId": (lora_info.get("civitai") or {}).get("id", 0) if lora_info else 0,
                "modelName": ((lora_info.get("civitai") or {}).get("model") or {}).get("name", name) if lora_info else "",
                "modelVersionName": (lora_info.get("civitai") or {}).get("name", "") if lora_info else "",
                "isDeleted": False,
                "exclude": False,
            }
            loras_data.append(lora_data)

            if lora_info and "base_model" in lora_info:
                base_model = lora_info["base_model"]
                base_model_counts[base_model] = base_model_counts.get(base_model, 0) + 1

        recipe_name = self._derive_recipe_name(lora_matches)
        most_common_base_model = (
            max(base_model_counts.items(), key=lambda item: item[1])[0] if base_model_counts else ""
        )

        recipe_data = {
            "id": recipe_id,
            "file_path": image_path,
            "title": recipe_name,
            "modified": time.time(),
            "created_date": time.time(),
            "base_model": most_common_base_model,
            "loras": loras_data,
            "checkpoint": metadata.get("checkpoint", ""),
            "gen_params": {
                key: value
                for key, value in metadata.items()
                if key not in ["checkpoint", "loras"]
            },
            "loras_stack": lora_stack,
        }

        json_filename = f"{recipe_id}.recipe.json"
        json_path = os.path.join(recipes_dir, json_filename)
        with open(json_path, "w", encoding="utf-8") as file_obj:
            json.dump(recipe_data, file_obj, indent=4, ensure_ascii=False)

        self._exif_utils.append_recipe_metadata(image_path, recipe_data)
        await recipe_scanner.add_recipe(recipe_data)

        return PersistenceResult(
            {
                "success": True,
                "recipe_id": recipe_id,
                "image_path": image_path,
                "json_path": json_path,
                "recipe_name": recipe_name,
            }
        )

    # Helper methods ---------------------------------------------------

    def _resolve_image_bytes(self, image_bytes: bytes | None, image_base64: str | None) -> bytes:
        if image_bytes is not None:
            return image_bytes
        if image_base64:
            try:
                payload = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
                return base64.b64decode(payload)
            except Exception as exc:  # pragma: no cover - validation guard
                raise RecipeValidationError(f"Invalid base64 image data: {exc}") from exc
        raise RecipeValidationError("No image data provided")

    def _normalise_lora_entry(self, lora: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_name": lora.get("file_name", "")
            or (
                os.path.splitext(os.path.basename(lora.get("localPath", "")))[0]
                if lora.get("localPath")
                else ""
            ),
            "hash": (lora.get("hash") or "").lower(),
            "strength": float(lora.get("weight", 1.0)),
            "modelVersionId": lora.get("id", 0),
            "modelName": lora.get("name", ""),
            "modelVersionName": lora.get("version", ""),
            "isDeleted": lora.get("isDeleted", False),
            "exclude": lora.get("exclude", False),
        }

    async def _find_matching_recipes(
        self,
        recipe_scanner,
        fingerprint: str | None,
        *,
        exclude_id: Optional[str] = None,
    ) -> list[str]:
        if not fingerprint:
            return []
        matches = await recipe_scanner.find_recipes_by_fingerprint(fingerprint)
        if exclude_id and exclude_id in matches:
            matches.remove(exclude_id)
        return matches

    def _derive_recipe_name(self, lora_matches: list[tuple[str, str]]) -> str:
        recipe_name_parts = [f"{name.strip()}-{float(strength):.2f}" for name, strength in lora_matches[:3]]
        recipe_name = "_".join(recipe_name_parts)
        return recipe_name or "recipe"
