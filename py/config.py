import os
import platform
from pathlib import Path
import folder_paths # type: ignore
from typing import Dict, Iterable, List, Mapping, Set
import logging
import json
import urllib.parse

from .utils.settings_paths import ensure_settings_file

# Use an environment variable to control standalone mode
standalone_mode = os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1" or os.environ.get("HF_HUB_DISABLE_TELEMETRY", "0") == "0"

logger = logging.getLogger(__name__)


def _normalize_folder_paths_for_comparison(
    folder_paths: Mapping[str, Iterable[str]]
) -> Dict[str, Set[str]]:
    """Normalize folder paths for comparison across libraries."""

    normalized: Dict[str, Set[str]] = {}
    for key, values in folder_paths.items():
        if isinstance(values, str):
            candidate_values: Iterable[str] = [values]
        else:
            try:
                candidate_values = iter(values)
            except TypeError:
                continue

        normalized_values: Set[str] = set()
        for value in candidate_values:
            if not isinstance(value, str):
                continue
            stripped = value.strip()
            if not stripped:
                continue
            normalized_values.add(os.path.normcase(os.path.normpath(stripped)))

        if normalized_values:
            normalized[key] = normalized_values

    return normalized


class Config:
    """Global configuration for LoRA Manager"""
    
    def __init__(self):
        self.templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
        self.static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
        self.i18n_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'locales')
        # Path mapping dictionary, target to link mapping
        self._path_mappings: Dict[str, str] = {}
        # Normalized preview root directories used to validate preview access
        self._preview_root_paths: Set[Path] = set()
        self.loras_roots = self._init_lora_paths()
        self.checkpoints_roots = None
        self.unet_roots = None
        self.embeddings_roots = None
        self.base_models_roots = self._init_checkpoint_paths()
        self.embeddings_roots = self._init_embedding_paths()
        # Scan symbolic links during initialization
        self._scan_symbolic_links()
        self._rebuild_preview_roots()
        
        if not standalone_mode:
            # Save the paths to settings.json when running in ComfyUI mode
            self.save_folder_paths_to_settings()

    def save_folder_paths_to_settings(self):
        """Persist ComfyUI-derived folder paths to the multi-library settings."""
        try:
            ensure_settings_file(logger)
            from .services.settings_manager import get_settings_manager

            settings_service = get_settings_manager()
            libraries = settings_service.get_libraries()
            comfy_library = libraries.get("comfyui", {})
            default_library = libraries.get("default", {})

            target_folder_paths = {
                'loras': list(self.loras_roots),
                'checkpoints': list(self.checkpoints_roots or []),
                'unet': list(self.unet_roots or []),
                'embeddings': list(self.embeddings_roots or []),
            }

            normalized_target_paths = _normalize_folder_paths_for_comparison(target_folder_paths)

            if (not comfy_library and default_library and normalized_target_paths and
                    _normalize_folder_paths_for_comparison(default_library.get("folder_paths", {})) ==
                    normalized_target_paths):
                try:
                    settings_service.rename_library("default", "comfyui")
                    logger.info("Renamed legacy 'default' library to 'comfyui'")
                    libraries = settings_service.get_libraries()
                    comfy_library = libraries.get("comfyui", {})
                except Exception as rename_error:
                    logger.debug(
                        "Failed to rename legacy 'default' library: %s", rename_error
                    )

            default_lora_root = comfy_library.get("default_lora_root", "")
            if not default_lora_root and len(self.loras_roots) == 1:
                default_lora_root = self.loras_roots[0]

            default_checkpoint_root = comfy_library.get("default_checkpoint_root", "")
            if (not default_checkpoint_root and self.checkpoints_roots and
                    len(self.checkpoints_roots) == 1):
                default_checkpoint_root = self.checkpoints_roots[0]

            default_embedding_root = comfy_library.get("default_embedding_root", "")
            if (not default_embedding_root and self.embeddings_roots and
                    len(self.embeddings_roots) == 1):
                default_embedding_root = self.embeddings_roots[0]

            metadata = dict(comfy_library.get("metadata", {}))
            metadata.setdefault("display_name", "ComfyUI")
            metadata["source"] = "comfyui"

            settings_service.upsert_library(
                "comfyui",
                folder_paths=target_folder_paths,
                default_lora_root=default_lora_root,
                default_checkpoint_root=default_checkpoint_root,
                default_embedding_root=default_embedding_root,
                metadata=metadata,
                activate=True,
            )

            logger.info("Updated 'comfyui' library with current folder paths")
        except Exception as e:
            logger.warning(f"Failed to save folder paths: {e}")

    def _is_link(self, path: str) -> bool:
        try:
            if os.path.islink(path):
                return True
            if platform.system() == 'Windows':
                try:
                    import ctypes
                    FILE_ATTRIBUTE_REPARSE_POINT = 0x400
                    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
                    return attrs != -1 and (attrs & FILE_ATTRIBUTE_REPARSE_POINT)
                except Exception as e:
                    logger.error(f"Error checking Windows reparse point: {e}")
            return False
        except Exception as e:
            logger.error(f"Error checking link status for {path}: {e}")
            return False

    def _scan_symbolic_links(self):
        """Scan all symbolic links in LoRA, Checkpoint, and Embedding root directories"""
        for root in self.loras_roots:
            self._scan_directory_links(root)
        
        for root in self.base_models_roots:
            self._scan_directory_links(root)
            
        for root in self.embeddings_roots:
            self._scan_directory_links(root)

    def _scan_directory_links(self, root: str):
        """Recursively scan symbolic links in a directory"""
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if self._is_link(entry.path):
                        target_path = os.path.realpath(entry.path)
                        if os.path.isdir(target_path):
                            self.add_path_mapping(entry.path, target_path)
                            self._scan_directory_links(target_path)
                    elif entry.is_dir(follow_symlinks=False):
                        self._scan_directory_links(entry.path)
        except Exception as e:
            logger.error(f"Error scanning links in {root}: {e}")

    def add_path_mapping(self, link_path: str, target_path: str):
        """Add a symbolic link path mapping
        target_path: actual target path
        link_path: symbolic link path
        """
        normalized_link = os.path.normpath(link_path).replace(os.sep, '/')
        normalized_target = os.path.normpath(target_path).replace(os.sep, '/')
        # Keep the original mapping: target path -> link path
        self._path_mappings[normalized_target] = normalized_link
        logger.info(f"Added path mapping: {normalized_target} -> {normalized_link}")
        self._preview_root_paths.update(self._expand_preview_root(normalized_target))
        self._preview_root_paths.update(self._expand_preview_root(normalized_link))

    def _expand_preview_root(self, path: str) -> Set[Path]:
        """Return normalized ``Path`` objects representing a preview root."""

        roots: Set[Path] = set()
        if not path:
            return roots

        try:
            raw_path = Path(path).expanduser()
        except Exception:
            return roots

        if raw_path.is_absolute():
            roots.add(raw_path)

        try:
            resolved = raw_path.resolve(strict=False)
        except RuntimeError:
            resolved = raw_path.absolute()
        roots.add(resolved)

        try:
            real_path = raw_path.resolve()
        except (FileNotFoundError, RuntimeError):
            real_path = resolved
        roots.add(real_path)

        normalized: Set[Path] = set()
        for candidate in roots:
            if candidate.is_absolute():
                normalized.add(candidate)
            else:
                try:
                    normalized.add(candidate.resolve(strict=False))
                except RuntimeError:
                    normalized.add(candidate.absolute())

        return normalized

    def _rebuild_preview_roots(self) -> None:
        """Recompute the cache of directories permitted for previews."""

        preview_roots: Set[Path] = set()

        for root in self.loras_roots or []:
            preview_roots.update(self._expand_preview_root(root))
        for root in self.base_models_roots or []:
            preview_roots.update(self._expand_preview_root(root))
        for root in self.embeddings_roots or []:
            preview_roots.update(self._expand_preview_root(root))

        for target, link in self._path_mappings.items():
            preview_roots.update(self._expand_preview_root(target))
            preview_roots.update(self._expand_preview_root(link))

        self._preview_root_paths = {path for path in preview_roots if path.is_absolute()}

    def map_path_to_link(self, path: str) -> str:
        """Map a target path back to its symbolic link path"""
        normalized_path = os.path.normpath(path).replace(os.sep, '/')
        # Check if the path is contained in any mapped target path
        for target_path, link_path in self._path_mappings.items():
            if normalized_path.startswith(target_path):
                # If the path starts with the target path, replace with link path
                mapped_path = normalized_path.replace(target_path, link_path, 1)
                return mapped_path
        return path
    
    def map_link_to_path(self, link_path: str) -> str:
        """Map a symbolic link path back to the actual path"""
        normalized_link = os.path.normpath(link_path).replace(os.sep, '/')
        # Check if the path is contained in any mapped target path
        for target_path, link_path in self._path_mappings.items():
            if normalized_link.startswith(target_path):
                # If the path starts with the target path, replace with actual path
                mapped_path = normalized_link.replace(target_path, link_path, 1)
                return mapped_path
        return link_path

    def _dedupe_existing_paths(self, raw_paths: Iterable[str]) -> Dict[str, str]:
        dedup: Dict[str, str] = {}
        for path in raw_paths:
            if not isinstance(path, str):
                continue
            if not os.path.exists(path):
                continue
            real_path = os.path.normpath(os.path.realpath(path)).replace(os.sep, '/')
            normalized = os.path.normpath(path).replace(os.sep, '/')
            if real_path not in dedup:
                dedup[real_path] = normalized
        return dedup

    def _prepare_lora_paths(self, raw_paths: Iterable[str]) -> List[str]:
        path_map = self._dedupe_existing_paths(raw_paths)
        unique_paths = sorted(path_map.values(), key=lambda p: p.lower())

        for original_path in unique_paths:
            real_path = os.path.normpath(os.path.realpath(original_path)).replace(os.sep, '/')
            if real_path != original_path:
                self.add_path_mapping(original_path, real_path)

        return unique_paths

    def _prepare_checkpoint_paths(
        self, checkpoint_paths: Iterable[str], unet_paths: Iterable[str]
    ) -> List[str]:
        checkpoint_map = self._dedupe_existing_paths(checkpoint_paths)
        unet_map = self._dedupe_existing_paths(unet_paths)

        merged_map: Dict[str, str] = {}
        for real_path, original in {**checkpoint_map, **unet_map}.items():
            if real_path not in merged_map:
                merged_map[real_path] = original

        unique_paths = sorted(merged_map.values(), key=lambda p: p.lower())

        checkpoint_values = set(checkpoint_map.values())
        unet_values = set(unet_map.values())
        self.checkpoints_roots = [p for p in unique_paths if p in checkpoint_values]
        self.unet_roots = [p for p in unique_paths if p in unet_values]

        for original_path in unique_paths:
            real_path = os.path.normpath(os.path.realpath(original_path)).replace(os.sep, '/')
            if real_path != original_path:
                self.add_path_mapping(original_path, real_path)

        return unique_paths

    def _prepare_embedding_paths(self, raw_paths: Iterable[str]) -> List[str]:
        path_map = self._dedupe_existing_paths(raw_paths)
        unique_paths = sorted(path_map.values(), key=lambda p: p.lower())

        for original_path in unique_paths:
            real_path = os.path.normpath(os.path.realpath(original_path)).replace(os.sep, '/')
            if real_path != original_path:
                self.add_path_mapping(original_path, real_path)

        return unique_paths

    def _apply_library_paths(self, folder_paths: Mapping[str, Iterable[str]]) -> None:
        self._path_mappings.clear()
        self._preview_root_paths = set()

        lora_paths = folder_paths.get('loras', []) or []
        checkpoint_paths = folder_paths.get('checkpoints', []) or []
        unet_paths = folder_paths.get('unet', []) or []
        embedding_paths = folder_paths.get('embeddings', []) or []

        self.loras_roots = self._prepare_lora_paths(lora_paths)
        self.base_models_roots = self._prepare_checkpoint_paths(checkpoint_paths, unet_paths)
        self.embeddings_roots = self._prepare_embedding_paths(embedding_paths)

        self._scan_symbolic_links()
        self._rebuild_preview_roots()

    def _init_lora_paths(self) -> List[str]:
        """Initialize and validate LoRA paths from ComfyUI settings"""
        try:
            raw_paths = folder_paths.get_folder_paths("loras")
            unique_paths = self._prepare_lora_paths(raw_paths)
            logger.info("Found LoRA roots:" + ("\n - " + "\n - ".join(unique_paths) if unique_paths else "[]"))

            if not unique_paths:
                logger.warning("No valid loras folders found in ComfyUI configuration")
                return []

            return unique_paths
        except Exception as e:
            logger.warning(f"Error initializing LoRA paths: {e}")
            return []

    def _init_checkpoint_paths(self) -> List[str]:
        """Initialize and validate checkpoint paths from ComfyUI settings"""
        try:
            raw_checkpoint_paths = folder_paths.get_folder_paths("checkpoints")
            raw_unet_paths = folder_paths.get_folder_paths("unet")
            unique_paths = self._prepare_checkpoint_paths(raw_checkpoint_paths, raw_unet_paths)

            logger.info("Found checkpoint roots:" + ("\n - " + "\n - ".join(unique_paths) if unique_paths else "[]"))

            if not unique_paths:
                logger.warning("No valid checkpoint folders found in ComfyUI configuration")
                return []

            return unique_paths
        except Exception as e:
            logger.warning(f"Error initializing checkpoint paths: {e}")
            return []

    def _init_embedding_paths(self) -> List[str]:
        """Initialize and validate embedding paths from ComfyUI settings"""
        try:
            raw_paths = folder_paths.get_folder_paths("embeddings")
            unique_paths = self._prepare_embedding_paths(raw_paths)
            logger.info("Found embedding roots:" + ("\n - " + "\n - ".join(unique_paths) if unique_paths else "[]"))

            if not unique_paths:
                logger.warning("No valid embeddings folders found in ComfyUI configuration")
                return []

            return unique_paths
        except Exception as e:
            logger.warning(f"Error initializing embedding paths: {e}")
            return []

    def get_preview_static_url(self, preview_path: str) -> str:
        if not preview_path:
            return ""

        normalized = os.path.normpath(preview_path).replace(os.sep, '/')
        encoded_path = urllib.parse.quote(normalized, safe='')
        return f'/api/lm/previews?path={encoded_path}'

    def is_preview_path_allowed(self, preview_path: str) -> bool:
        """Return ``True`` if ``preview_path`` is within an allowed directory."""

        if not preview_path:
            return False

        try:
            candidate = Path(preview_path).expanduser().resolve(strict=False)
        except Exception:
            return False

        for root in self._preview_root_paths:
            try:
                candidate.relative_to(root)
                return True
            except ValueError:
                continue

        return False

    def apply_library_settings(self, library_config: Mapping[str, object]) -> None:
        """Update runtime paths to match the provided library configuration."""
        folder_paths = library_config.get('folder_paths') if isinstance(library_config, Mapping) else {}
        if not isinstance(folder_paths, Mapping):
            folder_paths = {}

        self._apply_library_paths(folder_paths)

        logger.info(
            "Applied library settings with %d lora roots, %d checkpoint roots, and %d embedding roots",
            len(self.loras_roots or []),
            len(self.base_models_roots or []),
            len(self.embeddings_roots or []),
        )

    def get_library_registry_snapshot(self) -> Dict[str, object]:
        """Return the current library registry and active library name."""

        try:
            from .services.settings_manager import get_settings_manager

            settings_service = get_settings_manager()
            libraries = settings_service.get_libraries()
            active_library = settings_service.get_active_library_name()
            return {
                "active_library": active_library,
                "libraries": libraries,
            }
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to collect library registry snapshot: %s", exc)
            return {"active_library": "", "libraries": {}}

# Global config instance
config = Config()
