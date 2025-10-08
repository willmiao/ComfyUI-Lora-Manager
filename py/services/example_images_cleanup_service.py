"""Service for cleaning up example image folders."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from .service_registry import ServiceRegistry
from .settings_manager import get_settings_manager
from ..utils.example_images_paths import iter_library_roots


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CleanupResult:
    """Structured result returned from cleanup operations."""

    success: bool
    checked_folders: int
    moved_empty_folders: int
    moved_orphaned_folders: int
    skipped_non_hash: int
    move_failures: int
    errors: List[str]
    deleted_root: str | None
    partial_success: bool

    def to_dict(self) -> Dict[str, object]:
        """Convert the dataclass to a serialisable dictionary."""

        data = {
            "success": self.success,
            "checked_folders": self.checked_folders,
            "moved_empty_folders": self.moved_empty_folders,
            "moved_orphaned_folders": self.moved_orphaned_folders,
            "moved_total": self.moved_empty_folders + self.moved_orphaned_folders,
            "skipped_non_hash": self.skipped_non_hash,
            "move_failures": self.move_failures,
            "errors": self.errors,
            "deleted_root": self.deleted_root,
            "partial_success": self.partial_success,
        }

        return data


class ExampleImagesCleanupService:
    """Encapsulates logic for cleaning example image folders."""

    DELETED_FOLDER_NAME = "_deleted"

    def __init__(self, deleted_folder_name: str | None = None) -> None:
        self._deleted_folder_name = deleted_folder_name or self.DELETED_FOLDER_NAME

    async def cleanup_example_image_folders(self) -> Dict[str, object]:
        """Clean empty or orphaned example image folders by moving them under a deleted bucket."""

        settings_manager = get_settings_manager()
        example_images_path = settings_manager.get("example_images_path")
        if not example_images_path:
            logger.debug("Cleanup skipped: example images path not configured")
            return {
                "success": False,
                "error": "Example images path is not configured.",
                "error_code": "path_not_configured",
            }

        base_root = Path(example_images_path)
        if not base_root.exists():
            logger.debug("Cleanup skipped: example images path missing -> %s", base_root)
            return {
                "success": False,
                "error": "Example images path does not exist.",
                "error_code": "path_not_found",
            }

        try:
            lora_scanner = await ServiceRegistry.get_lora_scanner()
            checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
            embedding_scanner = await ServiceRegistry.get_embedding_scanner()
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.error("Failed to acquire scanners for cleanup: %s", exc, exc_info=True)
            return {
                "success": False,
                "error": f"Failed to load model scanners: {exc}",
                "error_code": "scanner_initialization_failed",
            }

        checked_folders = 0
        moved_empty = 0
        moved_orphaned = 0
        skipped_non_hash = 0
        move_failures = 0
        errors: List[str] = []

        resolved_base = base_root.resolve()
        library_paths: List[Tuple[str, Path]] = []
        processed_paths = {resolved_base}

        for library_name, library_path in iter_library_roots():
            if not library_path:
                continue
            library_root = Path(library_path)
            try:
                resolved = library_root.resolve()
            except FileNotFoundError:
                continue
            if resolved in processed_paths:
                continue
            if not library_root.exists():
                logger.debug(
                    "Skipping cleanup for library '%s': folder missing (%s)",
                    library_name,
                    library_root,
                )
                continue
            processed_paths.add(resolved)
            library_paths.append((library_name, library_root))

        deleted_roots: List[Path] = []

        # Build list of (label, root) pairs including the base root for legacy layouts
        cleanup_targets: List[Tuple[str, Path]] = [("__base__", base_root)] + library_paths

        library_root_set = {root.resolve() for _, root in library_paths}

        for label, root_path in cleanup_targets:
            deleted_bucket = root_path / self._deleted_folder_name
            deleted_bucket.mkdir(exist_ok=True)
            deleted_roots.append(deleted_bucket)

            for entry in os.scandir(root_path):
                if not entry.is_dir(follow_symlinks=False):
                    continue

                if entry.name == self._deleted_folder_name:
                    continue

                entry_path = Path(entry.path)

                if label == "__base__":
                    try:
                        resolved_entry = entry_path.resolve()
                    except FileNotFoundError:
                        continue
                    if resolved_entry in library_root_set:
                        # Skip library-specific folders tracked separately
                        continue

                checked_folders += 1

                try:
                    if self._is_folder_empty(entry_path):
                        if await self._remove_empty_folder(entry_path):
                            moved_empty += 1
                        else:
                            move_failures += 1
                        continue

                    if not self._is_hash_folder(entry.name):
                        skipped_non_hash += 1
                        continue

                    hash_exists = (
                        lora_scanner.has_hash(entry.name)
                        or checkpoint_scanner.has_hash(entry.name)
                        or embedding_scanner.has_hash(entry.name)
                    )

                    if not hash_exists:
                        if await self._move_folder(entry_path, deleted_bucket):
                            moved_orphaned += 1
                        else:
                            move_failures += 1

                except Exception as exc:  # pragma: no cover - filesystem guard
                    move_failures += 1
                    error_message = f"{entry.name}: {exc}"
                    errors.append(error_message)
                    logger.error(
                        "Error processing example images folder %s: %s",
                        entry_path,
                        exc,
                        exc_info=True,
                    )

        partial_success = move_failures > 0 and (moved_empty > 0 or moved_orphaned > 0)
        success = move_failures == 0 and not errors

        result = CleanupResult(
            success=success,
            checked_folders=checked_folders,
            moved_empty_folders=moved_empty,
            moved_orphaned_folders=moved_orphaned,
            skipped_non_hash=skipped_non_hash,
            move_failures=move_failures,
            errors=errors,
            deleted_root=str(deleted_roots[0]) if deleted_roots else None,
            partial_success=partial_success,
        )

        summary = result.to_dict()
        summary["deleted_roots"] = [str(path) for path in deleted_roots]
        if success:
            logger.info(
                "Example images cleanup complete: checked=%s, moved_empty=%s, moved_orphaned=%s",
                checked_folders,
                moved_empty,
                moved_orphaned,
            )
        elif partial_success:
            logger.warning(
                "Example images cleanup partially complete: moved=%s, failures=%s",
                summary["moved_total"],
                move_failures,
            )
        else:
            logger.error(
                "Example images cleanup failed: move_failures=%s, errors=%s",
                move_failures,
                errors,
            )

        return summary

    @staticmethod
    def _is_folder_empty(folder_path: Path) -> bool:
        try:
            with os.scandir(folder_path) as iterator:
                return not any(iterator)
        except FileNotFoundError:
            return True
        except OSError as exc:  # pragma: no cover - defensive guard
            logger.debug("Failed to inspect folder %s: %s", folder_path, exc)
            return False

    @staticmethod
    def _is_hash_folder(name: str) -> bool:
        if len(name) != 64:
            return False
        hex_chars = set("0123456789abcdefABCDEF")
        return all(char in hex_chars for char in name)

    async def _remove_empty_folder(self, folder_path: Path) -> bool:
        loop = asyncio.get_running_loop()

        try:
            await loop.run_in_executor(
                None,
                shutil.rmtree,
                str(folder_path),
            )
            logger.debug("Removed empty example images folder %s", folder_path)
            return True
        except Exception as exc:  # pragma: no cover - filesystem guard
            logger.error("Failed to remove empty example images folder %s: %s", folder_path, exc, exc_info=True)
            return False

    async def _move_folder(self, folder_path: Path, deleted_bucket: Path) -> bool:
        destination = self._build_destination(folder_path.name, deleted_bucket)
        loop = asyncio.get_running_loop()

        try:
            await loop.run_in_executor(
                None,
                shutil.move,
                str(folder_path),
                str(destination),
            )
            logger.debug("Moved example images folder %s -> %s", folder_path, destination)
            return True
        except Exception as exc:  # pragma: no cover - filesystem guard
            logger.error(
                "Failed to move example images folder %s to %s: %s",
                folder_path,
                destination,
                exc,
                exc_info=True,
            )
            return False

    def _build_destination(self, folder_name: str, deleted_bucket: Path) -> Path:
        destination = deleted_bucket / folder_name
        suffix = 1

        while destination.exists():
            destination = deleted_bucket / f"{folder_name}_{suffix}"
            suffix += 1

        return destination
