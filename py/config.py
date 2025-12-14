import os
import platform
from pathlib import Path
import folder_paths # type: ignore
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set
import logging
import json
import urllib.parse
import time

from .utils.settings_paths import ensure_settings_file, get_settings_dir, load_settings_template

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


def _normalize_library_folder_paths(
    library_payload: Mapping[str, Any]
) -> Dict[str, Set[str]]:
    """Return normalized folder paths extracted from a library payload."""

    folder_paths = library_payload.get("folder_paths")
    if isinstance(folder_paths, Mapping):
        return _normalize_folder_paths_for_comparison(folder_paths)
    return {}


def _get_template_folder_paths() -> Dict[str, Set[str]]:
    """Return normalized folder paths defined in the bundled template."""

    template_payload = load_settings_template()
    if not template_payload:
        return {}

    folder_paths = template_payload.get("folder_paths")
    if isinstance(folder_paths, Mapping):
        return _normalize_folder_paths_for_comparison(folder_paths)
    return {}


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
        self._initialize_symlink_mappings()
        
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

            template_folder_paths = _get_template_folder_paths()
            default_library_paths: Dict[str, Set[str]] = {}
            if isinstance(default_library, Mapping):
                default_library_paths = _normalize_library_folder_paths(default_library)

            libraries_changed = False
            if (
                isinstance(default_library, Mapping)
                and template_folder_paths
                and default_library_paths == template_folder_paths
            ):
                if "comfyui" in libraries:
                    try:
                        settings_service.delete_library("default")
                        libraries_changed = True
                        logger.info("Removed template 'default' library entry")
                    except Exception as delete_error:
                        logger.debug(
                            "Failed to delete template 'default' library: %s",
                            delete_error,
                        )
                else:
                    try:
                        settings_service.rename_library("default", "comfyui")
                        libraries_changed = True
                        logger.info("Renamed template 'default' library to 'comfyui'")
                    except Exception as rename_error:
                        logger.debug(
                            "Failed to rename template 'default' library: %s",
                            rename_error,
                        )

            if libraries_changed:
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

            normalized_default_paths: Optional[Dict[str, Set[str]]] = None
            if isinstance(default_library, Mapping):
                normalized_default_paths = _normalize_library_folder_paths(default_library)

            if (
                not comfy_library
                and default_library
                and normalized_target_paths
                and normalized_default_paths == normalized_target_paths
            ):
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

    def _normalize_path(self, path: str) -> str:
        return os.path.normpath(path).replace(os.sep, '/')

    def _get_symlink_cache_path(self) -> Path:
        cache_dir = Path(get_settings_dir(create=True)) / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "symlink_map.json"

    def _compute_noise_mtime(self, root: str) -> Optional[int]:
        """Return the latest mtime of known noisy paths inside ``root``."""

        normalized_root = self._normalize_path(root)
        noise_paths: List[str] = []

        # The first LoRA root hosts recipes and stats files which routinely
        # update without changing symlink layout.
        first_lora_root = self._normalize_path(self.loras_roots[0]) if self.loras_roots else None
        if first_lora_root and normalized_root == first_lora_root:
            recipes_dir = os.path.join(root, "recipes")
            stats_file = os.path.join(root, "lora_manager_stats.json")
            noise_paths.extend([recipes_dir, stats_file])

        mtimes: List[int] = []
        for path in noise_paths:
            try:
                stat_result = os.stat(path)
                mtimes.append(getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1e9)))
            except OSError:
                continue

        if not mtimes:
            return None
        return max(mtimes)

    def _symlink_roots(self) -> List[str]:
        roots: List[str] = []
        roots.extend(self.loras_roots or [])
        roots.extend(self.base_models_roots or [])
        roots.extend(self.embeddings_roots or [])
        return roots

    def _build_symlink_fingerprint(self) -> Dict[str, object]:
        roots = [self._normalize_path(path) for path in self._symlink_roots() if path]
        unique_roots = sorted(set(roots))

        stats: Dict[str, Dict[str, int]] = {}
        for root in unique_roots:
            try:
                root_stat = os.stat(root)
                noise_mtime = self._compute_noise_mtime(root)
                stats[root] = {
                    "mtime_ns": getattr(root_stat, "st_mtime_ns", int(root_stat.st_mtime * 1e9)),
                    "inode": getattr(root_stat, "st_ino", 0),
                    "noise_mtime_ns": noise_mtime,
                }
            except OSError:
                continue

        return {"roots": unique_roots, "stats": stats}

    def _load_symlink_cache(self) -> bool:
        cache_path = self._get_symlink_cache_path()
        if not cache_path.exists():
            logger.info("Symlink cache not found at %s", cache_path)
            return False

        try:
            with cache_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            logger.info("Failed to load symlink cache %s: %s", cache_path, exc)
            return False

        if not isinstance(payload, dict):
            logger.info("Symlink cache payload is not a dict: %s", type(payload))
            return False

        cached_fingerprint = payload.get("fingerprint")
        cached_mappings = payload.get("path_mappings")
        if not isinstance(cached_fingerprint, dict) or not isinstance(cached_mappings, Mapping):
            logger.info("Symlink cache missing fingerprint or path mappings")
            return False

        current_fingerprint = self._build_symlink_fingerprint()
        cached_roots = cached_fingerprint.get("roots")
        cached_stats = cached_fingerprint.get("stats")
        if (
            not isinstance(cached_roots, list)
            or not isinstance(cached_stats, Mapping)
            or sorted(cached_roots) != sorted(current_fingerprint["roots"])  # type: ignore[index]
        ):
            logger.info("Symlink cache invalidated: roots changed")
            return False

        for root in current_fingerprint["roots"]:  # type: ignore[assignment]
            cached_stat = cached_stats.get(root) if isinstance(cached_stats, Mapping) else None
            current_stat = current_fingerprint["stats"].get(root)  # type: ignore[index]
            if not isinstance(cached_stat, Mapping) or not current_stat:
                logger.info("Symlink cache invalidated: missing stats for %s", root)
                return False

            cached_mtime = cached_stat.get("mtime_ns")
            cached_inode = cached_stat.get("inode")
            current_mtime = current_stat.get("mtime_ns")
            current_inode = current_stat.get("inode")

            if cached_inode != current_inode:
                logger.info("Symlink cache invalidated: inode changed for %s", root)
                return False

            if cached_mtime != current_mtime:
                cached_noise = cached_stat.get("noise_mtime_ns")
                current_noise = current_stat.get("noise_mtime_ns")
                if not (
                    cached_noise
                    and current_noise
                    and cached_mtime == cached_noise
                    and current_mtime == current_noise
                ):
                    logger.info("Symlink cache invalidated: mtime changed for %s", root)
                    return False

        normalized_mappings: Dict[str, str] = {}
        for target, link in cached_mappings.items():
            if not isinstance(target, str) or not isinstance(link, str):
                continue
            normalized_mappings[self._normalize_path(target)] = self._normalize_path(link)

        self._path_mappings = normalized_mappings
        logger.info("Symlink cache loaded with %d mappings", len(self._path_mappings))
        return True

    def _save_symlink_cache(self) -> None:
        cache_path = self._get_symlink_cache_path()
        payload = {
            "fingerprint": self._build_symlink_fingerprint(),
            "path_mappings": self._path_mappings,
        }

        try:
            with cache_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            logger.info("Symlink cache saved to %s with %d mappings", cache_path, len(self._path_mappings))
        except Exception as exc:
            logger.info("Failed to write symlink cache %s: %s", cache_path, exc)

    def _initialize_symlink_mappings(self) -> None:
        start = time.perf_counter()
        if not self._load_symlink_cache():
            self._scan_symbolic_links()
            self._save_symlink_cache()
            logger.info(
                "Symlink mappings rebuilt and cached in %.2f ms",
                (time.perf_counter() - start) * 1000,
            )
        else:
            logger.info(
                "Symlink mappings restored from cache in %.2f ms",
                (time.perf_counter() - start) * 1000,
            )
        self._rebuild_preview_roots()

    def _scan_symbolic_links(self):
        """Scan all symbolic links in LoRA, Checkpoint, and Embedding root directories"""
        start = time.perf_counter()
        visited_dirs: Set[str] = set()
        for root in self._symlink_roots():
            self._scan_directory_links(root, visited_dirs)
        logger.info(
            "Symlink scan finished in %.2f ms with %d mappings",
            (time.perf_counter() - start) * 1000,
            len(self._path_mappings),
        )

    def _scan_directory_links(self, root: str, visited_dirs: Set[str]):
        """Iteratively scan directory symlinks to avoid deep recursion."""
        try:
            root_real = self._normalize_path(os.path.realpath(root))
        except OSError:
            root_real = self._normalize_path(root)

        if root_real in visited_dirs:
            return

        visited_dirs.add(root_real)
        stack: List[str] = [root]

        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        try:
                            entry_path = entry.path
                            if self._is_link(entry_path):
                                target_path = os.path.realpath(entry_path)
                                if not os.path.isdir(target_path):
                                    continue

                                normalized_target = self._normalize_path(target_path)
                                # Always record the mapping even if we already visited
                                # the real directory via another path. This prevents the
                                # traversal order from dropping valid link->target pairs.
                                self.add_path_mapping(entry_path, target_path)
                                if normalized_target in visited_dirs:
                                    continue
                                visited_dirs.add(normalized_target)
                                stack.append(target_path)
                                continue

                            if not entry.is_dir(follow_symlinks=False):
                                continue

                            normalized_real = self._normalize_path(os.path.realpath(entry_path))
                            if normalized_real in visited_dirs:
                                continue
                            visited_dirs.add(normalized_real)
                            stack.append(entry_path)
                        except Exception as inner_exc:
                            logger.debug(
                                "Error processing directory entry %s: %s", entry.path, inner_exc
                            )
            except Exception as e:
                logger.error(f"Error scanning links in {current}: {e}")

    def add_path_mapping(self, link_path: str, target_path: str):
        """Add a symbolic link path mapping
        target_path: actual target path
        link_path: symbolic link path
        """
        normalized_link = self._normalize_path(link_path)
        normalized_target = self._normalize_path(target_path)
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
            if normalized_link.startswith(link_path):
                # If the path starts with the link path, replace with actual path
                mapped_path = normalized_link.replace(link_path, target_path, 1)
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

        self._initialize_symlink_mappings()

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
