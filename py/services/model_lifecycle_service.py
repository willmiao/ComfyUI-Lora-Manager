"""Service routines for model lifecycle mutations."""

from __future__ import annotations

import logging
import os
from typing import Awaitable, Callable, Dict, Iterable, List, Optional

from ..services.service_registry import ServiceRegistry
from ..utils.constants import PREVIEW_EXTENSIONS

logger = logging.getLogger(__name__)


async def delete_model_artifacts(target_dir: str, file_name: str) -> List[str]:
    """Delete the primary model artefacts within ``target_dir``."""

    patterns = [
        f"{file_name}.safetensors",
        f"{file_name}.metadata.json",
    ]
    for ext in PREVIEW_EXTENSIONS:
        patterns.append(f"{file_name}{ext}")

    deleted: List[str] = []
    main_file = patterns[0]
    main_path = os.path.join(target_dir, main_file).replace(os.sep, "/")

    if os.path.exists(main_path):
        os.remove(main_path)
        deleted.append(main_path)
    else:
        logger.warning("Model file not found: %s", main_file)

    for pattern in patterns[1:]:
        path = os.path.join(target_dir, pattern)
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted.append(pattern)
            except Exception as exc:  # pragma: no cover - defensive path
                logger.warning("Failed to delete %s: %s", pattern, exc)

    return deleted


class ModelLifecycleService:
    """Co-ordinate destructive and mutating model operations."""

    def __init__(
        self,
        *,
        scanner,
        metadata_manager,
        metadata_loader: Callable[[str], Awaitable[Dict[str, object]]],
        recipe_scanner_factory: Callable[[], Awaitable] | None = None,
    ) -> None:
        self._scanner = scanner
        self._metadata_manager = metadata_manager
        self._metadata_loader = metadata_loader
        self._recipe_scanner_factory = (
            recipe_scanner_factory or ServiceRegistry.get_recipe_scanner
        )

    async def delete_model(self, file_path: str) -> Dict[str, object]:
        """Delete a model file and associated artefacts."""

        if not file_path:
            raise ValueError("Model path is required")

        target_dir = os.path.dirname(file_path)
        file_name = os.path.splitext(os.path.basename(file_path))[0]

        deleted_files = await delete_model_artifacts(target_dir, file_name)

        cache = await self._scanner.get_cached_data()
        cache.raw_data = [item for item in cache.raw_data if item["file_path"] != file_path]
        await cache.resort()

        if hasattr(self._scanner, "_hash_index") and self._scanner._hash_index:
            self._scanner._hash_index.remove_by_path(file_path)

        return {"success": True, "deleted_files": deleted_files}

    async def exclude_model(self, file_path: str) -> Dict[str, object]:
        """Mark a model as excluded and prune cache references."""

        if not file_path:
            raise ValueError("Model path is required")

        metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
        metadata = await self._metadata_loader(metadata_path)
        metadata["exclude"] = True

        await self._metadata_manager.save_metadata(file_path, metadata)

        cache = await self._scanner.get_cached_data()
        model_to_remove = next(
            (item for item in cache.raw_data if item["file_path"] == file_path),
            None,
        )

        if model_to_remove:
            for tag in model_to_remove.get("tags", []):
                if tag in getattr(self._scanner, "_tags_count", {}):
                    self._scanner._tags_count[tag] = max(
                        0, self._scanner._tags_count[tag] - 1
                    )
                    if self._scanner._tags_count[tag] == 0:
                        del self._scanner._tags_count[tag]

            if hasattr(self._scanner, "_hash_index") and self._scanner._hash_index:
                self._scanner._hash_index.remove_by_path(file_path)

            cache.raw_data = [
                item for item in cache.raw_data if item["file_path"] != file_path
            ]
            await cache.resort()

        excluded = getattr(self._scanner, "_excluded_models", None)
        if isinstance(excluded, list):
            excluded.append(file_path)

        message = f"Model {os.path.basename(file_path)} excluded"
        return {"success": True, "message": message}

    async def bulk_delete_models(self, file_paths: Iterable[str]) -> Dict[str, object]:
        """Delete a collection of models via the scanner bulk operation."""

        file_paths = list(file_paths)
        if not file_paths:
            raise ValueError("No file paths provided for deletion")

        return await self._scanner.bulk_delete_models(file_paths)

    async def rename_model(
        self, *, file_path: str, new_file_name: str
    ) -> Dict[str, object]:
        """Rename a model and its companion artefacts."""

        if not file_path or not new_file_name:
            raise ValueError("File path and new file name are required")

        invalid_chars = {"/", "\\", ":", "*", "?", '"', "<", ">", "|"}
        if any(char in new_file_name for char in invalid_chars):
            raise ValueError("Invalid characters in file name")

        target_dir = os.path.dirname(file_path)
        old_file_name = os.path.splitext(os.path.basename(file_path))[0]
        new_file_path = os.path.join(target_dir, f"{new_file_name}.safetensors").replace(
            os.sep, "/"
        )

        if os.path.exists(new_file_path):
            raise ValueError("A file with this name already exists")

        patterns = [
            f"{old_file_name}.safetensors",
            f"{old_file_name}.metadata.json",
            f"{old_file_name}.metadata.json.bak",
        ]
        for ext in PREVIEW_EXTENSIONS:
            patterns.append(f"{old_file_name}{ext}")

        existing_files: List[tuple[str, str]] = []
        for pattern in patterns:
            path = os.path.join(target_dir, pattern)
            if os.path.exists(path):
                existing_files.append((path, pattern))

        metadata_path = os.path.join(target_dir, f"{old_file_name}.metadata.json")
        metadata: Optional[Dict[str, object]] = None
        hash_value: Optional[str] = None

        if os.path.exists(metadata_path):
            metadata = await self._metadata_loader(metadata_path)
            hash_value = metadata.get("sha256") if isinstance(metadata, dict) else None

        renamed_files: List[str] = []
        new_metadata_path: Optional[str] = None
        new_preview: Optional[str] = None

        for old_path, pattern in existing_files:
            ext = self._get_multipart_ext(pattern)
            new_path = os.path.join(target_dir, f"{new_file_name}{ext}").replace(
                os.sep, "/"
            )
            os.rename(old_path, new_path)
            renamed_files.append(new_path)

            if ext == ".metadata.json":
                new_metadata_path = new_path

        if metadata and new_metadata_path:
            metadata["file_name"] = new_file_name
            metadata["file_path"] = new_file_path

            if metadata.get("preview_url"):
                old_preview = str(metadata["preview_url"])
                ext = self._get_multipart_ext(old_preview)
                new_preview = os.path.join(target_dir, f"{new_file_name}{ext}").replace(
                    os.sep, "/"
                )
                metadata["preview_url"] = new_preview

            await self._metadata_manager.save_metadata(new_file_path, metadata)

        if metadata:
            await self._scanner.update_single_model_cache(
                file_path, new_file_path, metadata
            )

            if hash_value and getattr(self._scanner, "model_type", "") == "lora":
                recipe_scanner = await self._recipe_scanner_factory()
                if recipe_scanner:
                    try:
                        await recipe_scanner.update_lora_filename_by_hash(
                            hash_value, new_file_name
                        )
                    except Exception as exc:  # pragma: no cover - defensive logging
                        logger.error(
                            "Error updating recipe references for %s: %s",
                            file_path,
                            exc,
                        )

        return {
            "success": True,
            "new_file_path": new_file_path,
            "new_preview_path": new_preview,
            "renamed_files": renamed_files,
            "reload_required": False,
        }

    @staticmethod
    def _get_multipart_ext(filename: str) -> str:
        """Return the extension for files with compound suffixes."""

        known_suffixes = [
            ".metadata.json.bak",
            ".metadata.json",
            ".safetensors",
            *PREVIEW_EXTENSIONS,
        ]

        for suffix in sorted(known_suffixes, key=len, reverse=True):
            if filename.endswith(suffix):
                return suffix

        basename = os.path.basename(filename)
        dot_index = basename.find(".")
        if dot_index != -1:
            return basename[dot_index:]

        return os.path.splitext(basename)[1]
