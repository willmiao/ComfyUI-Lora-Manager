import json
import os
import logging
import asyncio
import time
import shutil
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Set, Type, Union

from ..utils.models import BaseModelMetadata
from ..config import config
from ..utils.file_utils import find_preview_file, get_preview_extension
from ..utils.metadata_manager import MetadataManager
from .model_cache import ModelCache
from .model_hash_index import ModelHashIndex
from ..utils.constants import PREVIEW_EXTENSIONS
from .model_lifecycle_service import delete_model_artifacts
from .service_registry import ServiceRegistry
from .websocket_manager import ws_manager
from .persistent_model_cache import get_persistent_cache
from .settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


@dataclass
class CacheBuildResult:
    """Represents the outcome of scanning model files for cache building."""

    raw_data: List[Dict]
    hash_index: ModelHashIndex
    tags_count: Dict[str, int]
    excluded_models: List[str]

class ModelScanner:
    """Base service for scanning and managing model files"""
    
    _instances = {}  # Dictionary to store instances by class
    _locks = {}  # Dictionary to store locks by class
    
    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern for each subclass"""
        if cls not in cls._instances:
            cls._instances[cls] = super().__new__(cls)
        return cls._instances[cls]
    
    @classmethod
    def _get_lock(cls):
        """Get or create a lock for this class"""
        if cls not in cls._locks:
            cls._locks[cls] = asyncio.Lock()
        return cls._locks[cls]
    
    @classmethod
    async def get_instance(cls):
        """Get singleton instance with async support"""
        lock = cls._get_lock()
        async with lock:
            if cls not in cls._instances:
                cls._instances[cls] = cls()
            return cls._instances[cls]
    
    def __init__(self, model_type: str, model_class: Type[BaseModelMetadata], file_extensions: Set[str], hash_index: Optional[ModelHashIndex] = None):
        """Initialize the scanner
        
        Args:
            model_type: Type of model (lora, checkpoint, etc.)
            model_class: Class used to create metadata instances
            file_extensions: Set of supported file extensions including the dot (e.g. {'.safetensors'})
            hash_index: Hash index instance (optional)
        """
        # Ensure initialization happens only once per instance
        if hasattr(self, '_initialized'):
            return
            
        self.model_type = model_type
        self.model_class = model_class
        self.file_extensions = file_extensions
        self._cache = None
        self._hash_index = hash_index or ModelHashIndex()
        self._tags_count = {}  # Dictionary to store tag counts
        self._is_initializing = False  # Flag to track initialization state
        self._excluded_models = []  # List to track excluded models
        self._persistent_cache = get_persistent_cache()
        self._name_display_mode = self._resolve_name_display_mode()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        self._loop = loop
        self.loop = loop
        self._initialized = True

        # Register this service
        asyncio.create_task(self._register_service())

    def on_library_changed(self) -> None:
        """Reset caches when the active library changes."""
        self._persistent_cache = get_persistent_cache()
        self._cache = None
        self._hash_index = ModelHashIndex()
        self._tags_count = {}
        self._excluded_models = []
        self._is_initializing = False
        self._name_display_mode = self._resolve_name_display_mode()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and not loop.is_closed():
            self._loop = loop
            self.loop = loop
            loop.create_task(self.initialize_in_background())

    def _resolve_name_display_mode(self) -> str:
        """Return the configured display mode for name sorting."""

        try:
            manager = get_settings_manager()
        except Exception:  # pragma: no cover - fallback to defaults
            return "model_name"

        value = manager.get("model_name_display", "model_name")
        return ModelCache._normalize_display_mode(value)

    async def on_model_name_display_changed(self, display_mode: str) -> None:
        """Handle updates to the model name display preference."""

        normalized = ModelCache._normalize_display_mode(display_mode)
        self._name_display_mode = normalized

        if self._cache is not None:
            await self._cache.update_name_display_mode(normalized)

    async def _register_service(self):
        """Register this instance with the ServiceRegistry"""
        service_name = f"{self.model_type}_scanner"
        await ServiceRegistry.register_service(service_name, self)

    def _slim_civitai_payload(self, civitai: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
        """Return a lightweight civitai payload containing only frequently used keys."""
        if not isinstance(civitai, Mapping) or not civitai:
            return None

        slim: Dict[str, Any] = {}
        for key in ('id', 'modelId', 'name'):
            value = civitai.get(key)
            if value not in (None, '', []):
                slim[key] = value

        creator = civitai.get('creator')
        if isinstance(creator, Mapping):
            username = creator.get('username')
            if username:
                slim['creator'] = {'username': username}

        trained_words = civitai.get('trainedWords')
        if trained_words:
            slim['trainedWords'] = list(trained_words) if isinstance(trained_words, list) else trained_words

        return slim or None

    def _build_cache_entry(
        self,
        source: Union[BaseModelMetadata, Mapping[str, Any]],
        *,
        folder: Optional[str] = None,
        file_path_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Project metadata into the lightweight cache representation."""
        is_mapping = isinstance(source, Mapping)

        def get_value(key: str, default: Any = None) -> Any:
            if is_mapping:
                return source.get(key, default)
            return getattr(source, key, default)

        file_path = file_path_override or get_value('file_path', '') or ''
        normalized_path = file_path.replace('\\', '/')

        folder_value = folder if folder is not None else get_value('folder', '') or ''
        normalized_folder = folder_value.replace('\\', '/')

        tags_value = get_value('tags') or []
        if isinstance(tags_value, list):
            tags_list = list(tags_value)
        elif isinstance(tags_value, (set, tuple)):
            tags_list = list(tags_value)
        else:
            tags_list = []

        preview_url = get_value('preview_url', '') or ''
        if isinstance(preview_url, str):
            preview_url = preview_url.replace('\\', '/')
        else:
            preview_url = ''

        civitai_slim = self._slim_civitai_payload(get_value('civitai'))
        usage_tips = get_value('usage_tips', '') or ''
        if not isinstance(usage_tips, str):
            usage_tips = str(usage_tips)
        notes = get_value('notes', '') or ''
        if not isinstance(notes, str):
            notes = str(notes)

        entry: Dict[str, Any] = {
            'file_path': normalized_path,
            'file_name': get_value('file_name', '') or '',
            'model_name': get_value('model_name', '') or '',
            'folder': normalized_folder,
            'size': int(get_value('size', 0) or 0),
            'modified': float(get_value('modified', 0.0) or 0.0),
            'sha256': (get_value('sha256', '') or '').lower(),
            'base_model': get_value('base_model', '') or '',
            'preview_url': preview_url,
            'preview_nsfw_level': int(get_value('preview_nsfw_level', 0) or 0),
            'from_civitai': bool(get_value('from_civitai', True)),
            'favorite': bool(get_value('favorite', False)),
            'notes': notes,
            'usage_tips': usage_tips,
            'metadata_source': get_value('metadata_source', None),
            'exclude': bool(get_value('exclude', False)),
            'db_checked': bool(get_value('db_checked', False)),
            'last_checked_at': float(get_value('last_checked_at', 0.0) or 0.0),
            'tags': tags_list,
            'civitai': civitai_slim,
            'civitai_deleted': bool(get_value('civitai_deleted', False)),
        }

        model_type = get_value('model_type', None)
        if model_type:
            entry['model_type'] = model_type

        return entry

    async def initialize_in_background(self) -> None:
        """Initialize cache in background using thread pool"""
        try:
            # Set initial empty cache to avoid None reference errors
            if self._cache is None:
                self._cache = ModelCache(
                    raw_data=[],
                    folders=[],
                    name_display_mode=self._name_display_mode,
                )
            
            # Set initializing flag to true
            self._is_initializing = True
            
            # Determine the page type based on model type
            page_type_map = {
                'lora': 'loras',
                'checkpoint': 'checkpoints',
                'embedding': 'embeddings'
            }
            page_type = page_type_map.get(self.model_type, self.model_type)
            
            # First, try to load from cache
            await ws_manager.broadcast_init_progress({
                'stage': 'loading_cache',
                'progress': 0,
                'details': f"Loading {self.model_type} cache...",
                'scanner_type': self.model_type,
                'pageType': page_type
            })

            cache_loaded = await self._load_persisted_cache(page_type)

            if cache_loaded:
                await asyncio.sleep(0)  # Yield control so the UI can process the cache hydration update
                await ws_manager.broadcast_init_progress({
                    'stage': 'finalizing',
                    'progress': 100,
                    'status': 'complete',
                    'details': f"Loaded {len(self._cache.raw_data)} cached {self.model_type} files from disk.",
                    'scanner_type': self.model_type,
                    'pageType': page_type
                })
                logger.info(
                    f"{self.model_type.capitalize()} cache hydrated from persisted snapshot with {len(self._cache.raw_data)} models"
                )
                return

            # Persistent load failed; fall back to a full scan
            await ws_manager.broadcast_init_progress({
                'stage': 'scan_folders',
                'progress': 0,
                'details': f"Scanning {self.model_type} folders...",
                'scanner_type': self.model_type,
                'pageType': page_type
            })
            
            # Count files in a separate thread to avoid blocking
            loop = asyncio.get_event_loop()
            total_files = await loop.run_in_executor(
                None,  # Use default thread pool
                self._count_model_files  # Run file counting in thread
            )
            
            await ws_manager.broadcast_init_progress({
                'stage': 'count_models',
                'progress': 1, # Changed from 10 to 1
                'details': f"Found {total_files} {self.model_type} files",
                'scanner_type': self.model_type,
                'pageType': page_type
            })
            
            start_time = time.time()
            
            # Use thread pool to execute CPU-intensive operations with progress reporting
            scan_result: Optional[CacheBuildResult] = await loop.run_in_executor(
                None,  # Use default thread pool
                self._initialize_cache_sync,  # Run synchronous version in thread
                total_files,  # Pass the total file count for progress reporting
                page_type  # Pass the page type for progress reporting
            )

            if scan_result:
                await self._apply_scan_result(scan_result)
                await self._save_persistent_cache(scan_result)

            # Send final progress update
            await ws_manager.broadcast_init_progress({
                'stage': 'finalizing',
                'progress': 99, # Changed from 95 to 99
                'details': f"Finalizing {self.model_type} cache...",
                'scanner_type': self.model_type,
                'pageType': page_type
            })
            
            logger.info(f"{self.model_type.capitalize()} cache initialized in {time.time() - start_time:.2f} seconds. Found {len(self._cache.raw_data)} models")
            
            # Send completion message
            await asyncio.sleep(0.5)  # Small delay to ensure final progress message is sent
            await ws_manager.broadcast_init_progress({
                'stage': 'finalizing',
                'progress': 100,
                'status': 'complete',
                'details': f"Completed! Found {len(self._cache.raw_data)} {self.model_type} files.",
                'scanner_type': self.model_type,
                'pageType': page_type
            })
            
        except Exception as e:
            logger.error(f"{self.model_type.capitalize()} Scanner: Error initializing cache in background: {e}")
        finally:
            # Always clear the initializing flag when done
            self._is_initializing = False
    
    async def _load_persisted_cache(self, page_type: str) -> bool:
        """Attempt to hydrate the in-memory cache from the SQLite snapshot."""
        if not getattr(self, '_persistent_cache', None):
            return False

        loop = asyncio.get_event_loop()
        try:
            persisted = await loop.run_in_executor(
                None,
                self._persistent_cache.load_cache,
                self.model_type
            )
        except FileNotFoundError:
            return False
        except Exception as exc:
            logger.debug("%s Scanner: Could not load persisted cache: %s", self.model_type.capitalize(), exc)
            return False

        if not persisted or not persisted.raw_data:
            return False

        hash_index = ModelHashIndex()
        for sha_value, path in persisted.hash_rows:
            if sha_value and path:
                hash_index.add_entry(sha_value.lower(), path)

        tags_count: Dict[str, int] = {}
        adjusted_raw_data: List[Dict[str, Any]] = []
        for item in persisted.raw_data:
            adjusted_item = self.adjust_cached_entry(dict(item))
            adjusted_raw_data.append(adjusted_item)

            for tag in adjusted_item.get('tags') or []:
                tags_count[tag] = tags_count.get(tag, 0) + 1

        scan_result = CacheBuildResult(
            raw_data=adjusted_raw_data,
            hash_index=hash_index,
            tags_count=tags_count,
            excluded_models=list(persisted.excluded_models)
        )

        await self._apply_scan_result(scan_result)

        await ws_manager.broadcast_init_progress({
            'stage': 'loading_cache',
            'progress': 1,
            'details': f"Loaded cached {self.model_type} data from disk",
            'scanner_type': self.model_type,
            'pageType': page_type
        })
        return True

    async def _save_persistent_cache(self, scan_result: CacheBuildResult) -> None:
        if not scan_result or not getattr(self, '_persistent_cache', None):
            return

        hash_snapshot = self._build_hash_index_snapshot(scan_result.hash_index)
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                self._persistent_cache.save_cache,
                self.model_type,
                list(scan_result.raw_data),
                hash_snapshot,
                list(scan_result.excluded_models)
            )
        except Exception as exc:
            logger.warning("%s Scanner: Failed to persist cache: %s", self.model_type.capitalize(), exc)

    def _build_hash_index_snapshot(self, hash_index: Optional[ModelHashIndex]) -> Dict[str, List[str]]:
        snapshot: Dict[str, List[str]] = {}
        if not hash_index:
            return snapshot

        for sha_value, path in getattr(hash_index, '_hash_to_path', {}).items():
            if not sha_value or not path:
                continue
            bucket = snapshot.setdefault(sha_value.lower(), [])
            if path not in bucket:
                bucket.append(path)

        for sha_value, paths in getattr(hash_index, '_duplicate_hashes', {}).items():
            if not sha_value:
                continue
            bucket = snapshot.setdefault(sha_value.lower(), [])
            for path in paths:
                if path and path not in bucket:
                    bucket.append(path)
        return snapshot

    async def _persist_current_cache(self) -> None:
        if self._cache is None or not getattr(self, '_persistent_cache', None):
            return

        snapshot = CacheBuildResult(
            raw_data=list(self._cache.raw_data),
            hash_index=self._hash_index,
            tags_count=dict(self._tags_count),
            excluded_models=list(self._excluded_models)
        )
        await self._save_persistent_cache(snapshot)
    def _count_model_files(self) -> int:
        """Count all model files with supported extensions in all roots
        
        Returns:
            int: Total number of model files found
        """
        total_files = 0
        visited_real_paths = set()
        
        for root_path in self.get_model_roots():
            if not os.path.exists(root_path):
                continue
                
            def count_recursive(path):
                nonlocal total_files
                try:
                    real_path = os.path.realpath(path)
                    if real_path in visited_real_paths:
                        return
                    visited_real_paths.add(real_path)
                    
                    with os.scandir(path) as it:
                        for entry in it:
                            try:
                                if entry.is_file(follow_symlinks=True):
                                    ext = os.path.splitext(entry.name)[1].lower()
                                    if ext in self.file_extensions:
                                        total_files += 1
                                elif entry.is_dir(follow_symlinks=True):
                                    count_recursive(entry.path)
                            except Exception as e:
                                logger.error(f"Error counting files in entry {entry.path}: {e}")
                except Exception as e:
                    logger.error(f"Error counting files in {path}: {e}")
            
            count_recursive(root_path)
        
        return total_files
    
    def _initialize_cache_sync(self, total_files: int = 0, page_type: str = 'loras') -> Optional[CacheBuildResult]:
        """Synchronous version of cache initialization for thread pool execution"""

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)

            last_progress_time = time.time()
            last_progress_percent = 0

            async def progress_callback(processed_files: int, expected_total: int) -> None:
                nonlocal last_progress_time, last_progress_percent

                if expected_total <= 0:
                    return

                current_time = time.time()
                progress_percent = min(99, int(1 + (processed_files / expected_total) * 98))

                if progress_percent <= last_progress_percent:
                    return

                if current_time - last_progress_time <= 0.5 and processed_files != expected_total:
                    return

                last_progress_percent = progress_percent
                last_progress_time = current_time

                await ws_manager.broadcast_init_progress({
                    'stage': 'process_models',
                    'progress': progress_percent,
                    'details': f"Processing {self.model_type} files: {processed_files}/{expected_total}",
                    'scanner_type': self.model_type,
                    'pageType': page_type
                })

            return loop.run_until_complete(
                self._gather_model_data(
                    total_files=total_files,
                    progress_callback=progress_callback
                )
            )
        except Exception as e:
            logger.error(f"Error in thread-based {self.model_type} cache initialization: {e}")
            return None
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    async def get_cached_data(self, force_refresh: bool = False, rebuild_cache: bool = False) -> ModelCache:
        """Get cached model data, refresh if needed
        
        Args:
            force_refresh: Whether to refresh the cache
            rebuild_cache: Whether to completely rebuild the cache
        """
        # If cache is not initialized, return an empty cache
        # Actual initialization should be done via initialize_in_background
        if self._cache is None and not force_refresh:
            return ModelCache(
                raw_data=[],
                folders=[],
                name_display_mode=self._name_display_mode,
            )

        # If force refresh is requested, initialize the cache directly
        if force_refresh:
            if rebuild_cache:
                await self._initialize_cache()
            else:
                await self._reconcile_cache()
        
        return self._cache

    async def _initialize_cache(self) -> None:
        """Initialize or refresh the cache"""
        self._is_initializing = True  # Set flag
        try:
            start_time = time.time()
            # Determine the page type based on model type
            # Scan for new data
            scan_result = await self._gather_model_data()
            await self._apply_scan_result(scan_result)
            await self._save_persistent_cache(scan_result)

            logger.info(
                f"{self.model_type.capitalize()} Scanner: Cache initialization completed in {time.time() - start_time:.2f} seconds, "
                f"found {len(scan_result.raw_data)} models"
            )
        except Exception as e:
            logger.error(f"{self.model_type.capitalize()} Scanner: Error initializing cache: {e}")
            # Ensure cache is at least an empty structure on error
            if self._cache is None:
                self._cache = ModelCache(
                    raw_data=[],
                    folders=[],
                    name_display_mode=self._name_display_mode,
                )
        finally:
            self._is_initializing = False # Unset flag

    async def _reconcile_cache(self) -> None:
        """Fast cache reconciliation - only process differences between cache and filesystem"""
        self._is_initializing = True # Set flag for reconciliation duration
        try:
            start_time = time.time()
            logger.info(f"{self.model_type.capitalize()} Scanner: Starting fast cache reconciliation...")
            
            # Get current cached file paths
            cached_paths = {item['file_path'] for item in self._cache.raw_data}
            path_to_item = {item['file_path']: item for item in self._cache.raw_data}
            
            # Track found files and new files
            found_paths = set()
            new_files = []
            
            # Scan all model roots
            for root_path in self.get_model_roots():
                if not os.path.exists(root_path):
                    continue
                    
                # Track visited real paths to avoid symlink loops
                visited_real_paths = set()
                
                # Recursively scan directory
                for root, _, files in os.walk(root_path, followlinks=True):
                    real_root = os.path.realpath(root)
                    if real_root in visited_real_paths:
                        continue
                    visited_real_paths.add(real_root)
                    
                    for file in files:
                        ext = os.path.splitext(file)[1].lower()
                        if ext in self.file_extensions:
                            # Construct paths exactly as they would be in cache
                            file_path = os.path.join(root, file).replace(os.sep, '/')
                            
                            # Check if this file is already in cache
                            if file_path in cached_paths:
                                found_paths.add(file_path)
                                continue

                            if file_path in self._excluded_models:
                                continue
                                
                            # Try case-insensitive match on Windows
                            if os.name == 'nt':
                                lower_path = file_path.lower()
                                matched = False
                                for cached_path in cached_paths:
                                    if cached_path.lower() == lower_path:
                                        found_paths.add(cached_path)
                                        matched = True
                                        break
                                if matched:
                                    continue
                                
                            # This is a new file to process
                            new_files.append(file_path)
                    
                    # Yield control periodically
                    await asyncio.sleep(0)
            
            # Process new files in batches
            total_added = 0
            if new_files:
                logger.info(f"{self.model_type.capitalize()} Scanner: Found {len(new_files)} new files to process")
                batch_size = 50
                for i in range(0, len(new_files), batch_size):
                    batch = new_files[i:i+batch_size]
                    for path in batch:
                        logger.info(f"{self.model_type.capitalize()} Scanner: Processing {path}")
                        try:
                            # Find the appropriate root path for this file
                            root_path = None
                            model_roots = self.get_model_roots()
                            for potential_root in model_roots:
                                # Normalize both paths for comparison
                                normalized_path = os.path.normpath(path)
                                normalized_root = os.path.normpath(potential_root)
                                if normalized_path.startswith(normalized_root):
                                    root_path = potential_root
                                    break
                            
                            if root_path:
                                model_data = await self._process_model_file(path, root_path)
                                if model_data:
                                    model_data = self.adjust_cached_entry(dict(model_data))
                                    if not model_data:
                                        continue
                                    # Add to cache
                                    self._cache.raw_data.append(model_data)
                                    self._cache.add_to_version_index(model_data)

                                    # Update hash index if available
                                    if 'sha256' in model_data and 'file_path' in model_data:
                                        self._hash_index.add_entry(model_data['sha256'].lower(), model_data['file_path'])
                                    
                                    # Update tags count
                                    if 'tags' in model_data and model_data['tags']:
                                        for tag in model_data['tags']:
                                            self._tags_count[tag] = self._tags_count.get(tag, 0) + 1
                                            
                                    total_added += 1
                            else:
                                logger.error(f"Could not determine root path for {path}")
                        except Exception as e:
                            logger.error(f"Error adding {path} to cache: {e}")
            
            # Find missing files (in cache but not in filesystem)
            missing_files = cached_paths - found_paths
            total_removed = 0
            
            if missing_files:
                logger.info(f"{self.model_type.capitalize()} Scanner: Found {len(missing_files)} files to remove from cache")
                
                # Process files to remove
                for path in missing_files:
                    try:
                        model_to_remove = path_to_item[path]

                        self._cache.remove_from_version_index(model_to_remove)

                        # Update tags count
                        for tag in model_to_remove.get('tags', []):
                            if tag in self._tags_count:
                                self._tags_count[tag] = max(0, self._tags_count[tag] - 1)
                                if self._tags_count[tag] == 0:
                                    del self._tags_count[tag]
                        
                        # Remove from hash index
                        self._hash_index.remove_by_path(path)
                        total_removed += 1
                    except Exception as e:
                        logger.error(f"Error removing {path} from cache: {e}")
                
                # Update cache data
                self._cache.raw_data = [item for item in self._cache.raw_data if item['file_path'] not in missing_files]
            
            # Resort cache if changes were made
            if total_added > 0 or total_removed > 0:
                # Update folders list
                all_folders = set(item.get('folder', '') for item in self._cache.raw_data)
                self._cache.folders = sorted(list(all_folders), key=lambda x: x.lower())

                self._cache.rebuild_version_index()

                # Resort cache
                await self._cache.resort()

                await self._persist_current_cache()
                
            logger.info(f"{self.model_type.capitalize()} Scanner: Cache reconciliation completed in {time.time() - start_time:.2f} seconds. Added {total_added}, removed {total_removed} models.")
        except Exception as e:
            logger.error(f"{self.model_type.capitalize()} Scanner: Error reconciling cache: {e}", exc_info=True)
        finally:
            self._is_initializing = False # Unset flag
    
    def is_initializing(self) -> bool:
        """Check if the scanner is currently initializing"""
        return self._is_initializing
    
    def get_model_roots(self) -> List[str]:
        """Get model root directories"""
        raise NotImplementedError("Subclasses must implement get_model_roots")
    
    async def _create_default_metadata(self, file_path: str) -> Optional[BaseModelMetadata]:
        """Get model file info and metadata (extensible for different model types)"""
        return await MetadataManager.create_default_metadata(file_path, self.model_class)
    
    def _calculate_folder(self, file_path: str) -> str:
        """Calculate the folder path for a model file"""
        for root in self.get_model_roots():
            if file_path.startswith(root):
                rel_path = os.path.relpath(file_path, root)
                return os.path.dirname(rel_path).replace(os.path.sep, '/')
        return ''

    def adjust_metadata(self, metadata, file_path, root_path):
        """Hook for subclasses: adjust metadata during scanning"""
        return metadata

    def adjust_cached_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Hook for subclasses: adjust entries loaded from the persisted cache."""
        return entry

    @staticmethod
    def _normalize_path_value(path: Optional[str]) -> str:
        if not path:
            return ''

        normalized = os.path.normpath(path)
        if normalized == '.':
            return ''

        return normalized.replace('\\', '/')

    def _find_root_for_file(self, file_path: Optional[str]) -> Optional[str]:
        """Return the configured root directory that contains ``file_path``."""

        normalized_path = self._normalize_path_value(file_path)
        if not normalized_path:
            return None

        for root in self.get_model_roots() or []:
            normalized_root = self._normalize_path_value(root)
            if not normalized_root:
                continue

            if (
                normalized_path == normalized_root
                or normalized_path.startswith(f"{normalized_root}/")
            ):
                return root

        return None

    async def _process_model_file(
        self,
        file_path: str,
        root_path: str,
        *,
        hash_index: Optional[ModelHashIndex] = None,
        excluded_models: Optional[List[str]] = None
    ) -> Dict:
        """Process a single model file and return its metadata"""
        hash_index = hash_index or self._hash_index
        excluded_models = excluded_models if excluded_models is not None else self._excluded_models

        metadata, should_skip = await MetadataManager.load_metadata(file_path, self.model_class)
    
        if should_skip:
            # Metadata file exists but cannot be parsed - skip this model
            logger.warning(f"Skipping model {file_path} due to corrupted metadata file")
            return None
        
        if metadata is None:
            civitai_info_path = f"{os.path.splitext(file_path)[0]}.civitai.info"
            if os.path.exists(civitai_info_path):
                try:
                    with open(civitai_info_path, 'r', encoding='utf-8') as f:
                        version_info = json.load(f)
                    
                    file_info = next((f for f in version_info.get('files', []) if f.get('primary')), None)
                    if file_info:
                        file_name = os.path.splitext(os.path.basename(file_path))[0]
                        file_info['name'] = file_name
                    
                        metadata = self.model_class.from_civitai_info(version_info, file_info, file_path)
                        metadata.preview_url = find_preview_file(file_name, os.path.dirname(file_path))
                        await MetadataManager.save_metadata(file_path, metadata)
                        logger.debug(f"Created metadata from .civitai.info for {file_path}")
                except Exception as e:
                    logger.error(f"Error creating metadata from .civitai.info for {file_path}: {e}")
        else:
            # Check if metadata exists but civitai field is empty - try to restore from civitai.info
            if metadata.civitai is None or metadata.civitai == {}:
                civitai_info_path = f"{os.path.splitext(file_path)[0]}.civitai.info"
                if os.path.exists(civitai_info_path):
                    try:
                        with open(civitai_info_path, 'r', encoding='utf-8') as f:
                            version_info = json.load(f)
                        
                        logger.debug(f"Restoring missing civitai data from .civitai.info for {file_path}")
                        metadata.civitai = version_info
                        
                        # Ensure tags are also updated if they're missing
                        if (not metadata.tags or len(metadata.tags) == 0) and 'model' in version_info:
                            if 'tags' in version_info['model']:
                                metadata.tags = version_info['model']['tags']
                        
                        # Also restore description if missing
                        if (not metadata.modelDescription or metadata.modelDescription == "") and 'model' in version_info:
                            if 'description' in version_info['model']:
                                metadata.modelDescription = version_info['model']['description']
                        
                        # Save the updated metadata
                        await MetadataManager.save_metadata(file_path, metadata)
                        logger.debug(f"Updated metadata with civitai info for {file_path}")
                    except Exception as e:
                        logger.error(f"Error restoring civitai data from .civitai.info for {file_path}: {e}")
            
        if metadata is None:
            metadata = await self._create_default_metadata(file_path)
        
        # Hook: allow subclasses to adjust metadata
        metadata = self.adjust_metadata(metadata, file_path, root_path)
        
        rel_path = os.path.relpath(file_path, root_path)
        folder = os.path.dirname(rel_path)
        normalized_folder = folder.replace(os.path.sep, '/')

        model_data = self._build_cache_entry(metadata, folder=normalized_folder)

        # Skip excluded models
        if model_data.get('exclude', False):
            excluded_models.append(model_data['file_path'])
            return None

        # Check for duplicate filename before adding to hash index
        # filename = os.path.splitext(os.path.basename(file_path))[0]
        # existing_hash = hash_index.get_hash_by_filename(filename)
        # if existing_hash and existing_hash != model_data.get('sha256', '').lower():
        #     existing_path = hash_index.get_path(existing_hash)
        #     if existing_path and existing_path != file_path:
        #         logger.warning(f"Duplicate filename detected: '{filename}' - files: '{existing_path}' and '{file_path}'")

        return model_data

    async def _apply_scan_result(self, scan_result: CacheBuildResult) -> None:
        """Apply scan results to the cache and associated indexes."""

        if scan_result is None:
            return

        self._hash_index = scan_result.hash_index
        self._tags_count = dict(scan_result.tags_count)
        self._excluded_models = list(scan_result.excluded_models)

        if self._cache is None:
            self._cache = ModelCache(
                raw_data=list(scan_result.raw_data),
                folders=[],
                name_display_mode=self._name_display_mode,
            )
        else:
            self._cache.raw_data = list(scan_result.raw_data)

        self._cache.rebuild_version_index()

        await self._cache.resort()

    async def _gather_model_data(
        self,
        *,
        total_files: int = 0,
        progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None
    ) -> CacheBuildResult:
        """Collect metadata for all model files."""

        raw_data: List[Dict] = []
        hash_index = ModelHashIndex()
        tags_count: Dict[str, int] = {}
        excluded_models: List[str] = []
        processed_files = 0

        async def handle_progress() -> None:
            if progress_callback is None:
                return
            try:
                await progress_callback(processed_files, total_files)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"Error reporting progress for {self.model_type}: {exc}")

        async def scan_recursive(current_path: str, root_path: str, visited_paths: Set[str]) -> None:
            nonlocal processed_files

            try:
                real_path = os.path.realpath(current_path)
                if real_path in visited_paths:
                    return
                visited_paths.add(real_path)

                with os.scandir(current_path) as iterator:
                    entries = list(iterator)

                for entry in entries:
                    try:
                        if entry.is_file(follow_symlinks=True):
                            ext = os.path.splitext(entry.name)[1].lower()
                            if ext not in self.file_extensions:
                                continue

                            file_path = entry.path.replace(os.sep, "/")
                            result = await self._process_model_file(
                                file_path,
                                root_path,
                                hash_index=hash_index,
                                excluded_models=excluded_models
                            )

                            processed_files += 1

                            if result:
                                raw_data.append(result)

                                sha_value = result.get('sha256')
                                model_path = result.get('file_path')
                                if sha_value and model_path:
                                    hash_index.add_entry(sha_value.lower(), model_path)

                                for tag in result.get('tags') or []:
                                    tags_count[tag] = tags_count.get(tag, 0) + 1

                            await handle_progress()
                            await asyncio.sleep(0)
                        elif entry.is_dir(follow_symlinks=True):
                            await scan_recursive(entry.path, root_path, visited_paths)
                    except Exception as entry_error:
                        logger.error(f"Error processing entry {entry.path}: {entry_error}")
            except Exception as scan_error:
                logger.error(f"Error scanning {current_path}: {scan_error}")

        for model_root in self.get_model_roots():
            if not os.path.exists(model_root):
                continue

            await scan_recursive(model_root, model_root, set())

        return CacheBuildResult(
            raw_data=raw_data,
            hash_index=hash_index,
            tags_count=tags_count,
            excluded_models=excluded_models
        )

    async def add_model_to_cache(self, metadata_dict: Dict, folder: str = '') -> bool:
        """Add a model to the cache

        Args:
            metadata_dict: The model metadata dictionary
            folder: The relative folder path for the model
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self._cache is None:
                await self.get_cached_data()
                
            # Update folder in metadata
            metadata_dict['folder'] = folder
            
            # Add to cache
            self._cache.raw_data.append(metadata_dict)
            self._cache.add_to_version_index(metadata_dict)

            # Resort cache data
            await self._cache.resort()
            
            # Update folders list
            all_folders = set(self._cache.folders)
            all_folders.add(folder)
            self._cache.folders = sorted(list(all_folders), key=lambda x: x.lower())
            
            # Update the hash index
            self._hash_index.add_entry(metadata_dict['sha256'], metadata_dict['file_path'])
            await self._persist_current_cache()
            return True
        except Exception as e:
            logger.error(f"Error adding model to cache: {e}")
            return False
    
    async def move_model(self, source_path: str, target_path: str) -> Optional[str]:
        """Move a model and its associated files to a new location
        
        Args:
            source_path: Original file path
            target_path: Target directory path
            
        Returns:
            Optional[str]: New file path if successful, None if failed
        """
        try:
            source_path = source_path.replace(os.sep, '/')
            target_path = target_path.replace(os.sep, '/')
            
            file_ext = os.path.splitext(source_path)[1]
            
            if not file_ext or file_ext.lower() not in self.file_extensions:
                logger.error(f"Invalid file extension for model: {file_ext}")
                return None
                
            base_name = os.path.splitext(os.path.basename(source_path))[0]
            source_dir = os.path.dirname(source_path)
            
            os.makedirs(target_path, exist_ok=True)
            
            def get_source_hash():
                return self.get_hash_by_path(source_path)
            
            # Check for filename conflicts and auto-rename if necessary
            from ..utils.models import BaseModelMetadata
            final_filename = BaseModelMetadata.generate_unique_filename(
                target_path, base_name, file_ext, get_source_hash
            )
            
            target_file = os.path.join(target_path, final_filename).replace(os.sep, '/')
            final_base_name = os.path.splitext(final_filename)[0]
            
            # Log if filename was changed due to conflict
            if final_filename != f"{base_name}{file_ext}":
                logger.info(f"Renamed {base_name}{file_ext} to {final_filename} to avoid filename conflict")

            real_source = os.path.realpath(source_path)
            real_target = os.path.realpath(target_file)
            
            shutil.move(real_source, real_target)
            
            # Move all associated files with the same base name
            source_metadata = None
            moved_metadata_path = None
            
            # Find all files with the same base name in the source directory
            files_to_move = []
            try:
                for file in os.listdir(source_dir):
                    if file.startswith(base_name + ".") and file != os.path.basename(source_path):
                        source_file_path = os.path.join(source_dir, file)
                        # Generate new filename with the same base name as the model file
                        file_suffix = file[len(base_name):]  # Get the part after base_name (e.g., ".metadata.json", ".preview.png")
                        new_associated_filename = f"{final_base_name}{file_suffix}"
                        target_associated_path = os.path.join(target_path, new_associated_filename)
                        
                        # Store metadata file path for special handling
                        if file == f"{base_name}.metadata.json":
                            source_metadata = source_file_path
                            moved_metadata_path = target_associated_path
                        else:
                            files_to_move.append((source_file_path, target_associated_path))
            except Exception as e:
                logger.error(f"Error listing files in {source_dir}: {e}")
            
            # Move all associated files
            metadata = None
            for source_file, target_file_path in files_to_move:
                try:
                    shutil.move(source_file, target_file_path)
                except Exception as e:
                    logger.error(f"Error moving associated file {source_file}: {e}")
            
            # Handle metadata file specially to update paths
            if source_metadata and os.path.exists(source_metadata):
                try:
                    shutil.move(source_metadata, moved_metadata_path)
                    metadata = await self._update_metadata_paths(moved_metadata_path, target_file)
                except Exception as e:
                    logger.error(f"Error moving metadata file: {e}")
            
            await self.update_single_model_cache(source_path, target_file, metadata)
            
            return target_file
            
        except Exception as e:
            logger.error(f"Error moving model: {e}", exc_info=True)
            return None
    
    async def _update_metadata_paths(self, metadata_path: str, model_path: str) -> Dict:
        """Update file paths in metadata file"""
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            metadata['file_path'] = model_path.replace(os.sep, '/')
            # Update file_name to match the new filename
            metadata['file_name'] = os.path.splitext(os.path.basename(model_path))[0]
            
            if 'preview_url' in metadata and metadata['preview_url']:
                preview_dir = os.path.dirname(model_path)
                # Update preview filename to match the new base name
                new_base_name = os.path.splitext(os.path.basename(model_path))[0]
                preview_ext = get_preview_extension(metadata['preview_url'])
                new_preview_path = os.path.join(preview_dir, f"{new_base_name}{preview_ext}")
                metadata['preview_url'] = new_preview_path.replace(os.sep, '/')
            
            await MetadataManager.save_metadata(metadata_path, metadata)

            return metadata
                
        except Exception as e:
            logger.error(f"Error updating metadata paths: {e}", exc_info=True)
            return None

    async def update_single_model_cache(self, original_path: str, new_path: str, metadata: Dict) -> bool:
        """Update cache after a model has been moved or modified"""
        cache = await self.get_cached_data()

        existing_item = next((item for item in cache.raw_data if item['file_path'] == original_path), None)
        if existing_item:
            cache.remove_from_version_index(existing_item)

        if existing_item and 'tags' in existing_item:
            for tag in existing_item.get('tags', []):
                if tag in self._tags_count:
                    self._tags_count[tag] = max(0, self._tags_count[tag] - 1)
                    if self._tags_count[tag] == 0:
                        del self._tags_count[tag]
        
        self._hash_index.remove_by_path(original_path)
        
        cache.raw_data = [
            item for item in cache.raw_data
            if item['file_path'] != original_path
        ]

        cache_modified = bool(existing_item) or bool(metadata)

        if metadata:
            normalized_new_path = new_path.replace(os.sep, '/')
            if original_path == new_path and existing_item:
                folder_value = existing_item.get('folder', self._calculate_folder(new_path))
            else:
                folder_value = self._calculate_folder(new_path)

            cache_entry = self._build_cache_entry(
                metadata,
                folder=folder_value,
                file_path_override=normalized_new_path,
            )

            cache.raw_data.append(cache_entry)
            cache.add_to_version_index(cache_entry)

            sha_value = cache_entry.get('sha256')
            if sha_value:
                self._hash_index.add_entry(sha_value.lower(), normalized_new_path)

            all_folders = set(item['folder'] for item in cache.raw_data)
            cache.folders = sorted(list(all_folders), key=lambda x: x.lower())

            for tag in cache_entry.get('tags', []):
                self._tags_count[tag] = self._tags_count.get(tag, 0) + 1

        cache.rebuild_version_index()

        await cache.resort()

        if cache_modified:
            await self._persist_current_cache()

        return True
        
    def has_hash(self, sha256: str) -> bool:
        """Check if a model with given hash exists"""
        return self._hash_index.has_hash(sha256.lower())
        
    def get_path_by_hash(self, sha256: str) -> Optional[str]:
        """Get file path for a model by its hash"""
        return self._hash_index.get_path(sha256.lower())
        
    def get_hash_by_path(self, file_path: str) -> Optional[str]:
        """Get hash for a model by its file path"""
        if self._cache is None or not self._cache.raw_data:
            return None
            
        # Iterate through cache data to find matching file path
        for model_data in self._cache.raw_data:
            if model_data.get('file_path') == file_path:
                return model_data.get('sha256')
        
        return None
    
    def get_hash_by_filename(self, filename: str) -> Optional[str]:
        """Get hash for a model by its filename without path"""
        return self._hash_index.get_hash_by_filename(filename)

    # TODO: Adjust this method to use metadata instead of finding the file    
    def get_preview_url_by_hash(self, sha256: str) -> Optional[str]:
        """Get preview static URL for a model by its hash"""
        file_path = self._hash_index.get_path(sha256.lower())
        if not file_path:
            return None
            
        base_name = os.path.splitext(file_path)[0]
        
        for ext in PREVIEW_EXTENSIONS:
            preview_path = f"{base_name}{ext}"
            if os.path.exists(preview_path):
                return config.get_preview_static_url(preview_path)
        
        return None
        
    async def get_top_tags(self, limit: int = 20) -> List[Dict[str, any]]:
        """Get top tags sorted by count"""
        await self.get_cached_data()
        
        sorted_tags = sorted(
            [{"tag": tag, "count": count} for tag, count in self._tags_count.items()],
            key=lambda x: x['count'],
            reverse=True
        )
        
        return sorted_tags[:limit]
        
    async def get_base_models(self, limit: int = 20) -> List[Dict[str, any]]:
        """Get base models sorted by frequency"""
        cache = await self.get_cached_data()
        
        base_model_counts = {}
        for model in cache.raw_data:
            if 'base_model' in model and model['base_model']:
                base_model = model['base_model']
                base_model_counts[base_model] = base_model_counts.get(base_model, 0) + 1
        
        sorted_models = [{'name': model, 'count': count} for model, count in base_model_counts.items()]
        sorted_models.sort(key=lambda x: x['count'], reverse=True)
        
        return sorted_models[:limit]
        
    async def get_model_info_by_name(self, name):
        """Get model information by name"""
        try:
            cache = await self.get_cached_data()
            
            for model in cache.raw_data:
                if model.get("file_name") == name:
                    return model
                    
            return None
        except Exception as e:
            logger.error(f"Error getting model info by name: {e}", exc_info=True)
            return None
        
    def get_excluded_models(self) -> List[str]:
        """Get list of excluded model file paths"""
        return self._excluded_models.copy()

    async def update_preview_in_cache(self, file_path: str, preview_url: str, preview_nsfw_level: int) -> bool:
        """Update preview URL in cache for a specific lora
        
        Args:
            file_path: The file path of the lora to update
            preview_url: The new preview URL
            preview_nsfw_level: The NSFW level of the preview
            
        Returns:
            bool: True if the update was successful, False if cache doesn't exist or lora wasn't found
        """
        if self._cache is None:
            return False

        updated = await self._cache.update_preview_url(file_path, preview_url, preview_nsfw_level)
        if updated:
            await self._persist_current_cache()
        return updated

    async def bulk_delete_models(self, file_paths: List[str]) -> Dict:
        """Delete multiple models and update cache in a batch operation
        
        Args:
            file_paths: List of file paths to delete
            
        Returns:
            Dict containing results of the operation
        """
        try:
            if not file_paths:
                return {
                    'success': False,
                    'error': 'No file paths provided for deletion',
                    'results': []
                }
            
            # Keep track of success and failures
            results = []
            total_deleted = 0
            cache_updated = False
            
            # Get cache data
            cache = await self.get_cached_data()
            
            # Track deleted models to update cache once
            deleted_models = []
            
            for file_path in file_paths:
                try:
                    target_dir = os.path.dirname(file_path)
                    file_name = os.path.splitext(os.path.basename(file_path))[0]
                    
                    deleted_files = await delete_model_artifacts(
                        target_dir,
                        file_name
                    )
                    
                    if deleted_files:
                        deleted_models.append(file_path)
                        results.append({
                            'file_path': file_path,
                            'success': True,
                            'deleted_files': deleted_files
                        })
                        total_deleted += 1
                    else:
                        results.append({
                            'file_path': file_path,
                            'success': False,
                            'error': 'No files deleted'
                        })
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {e}")
                    results.append({
                        'file_path': file_path,
                        'success': False,
                        'error': str(e)
                    })
            
            # Batch update cache if any models were deleted
            if deleted_models:
                # Update the cache in a batch operation
                cache_updated = await self._batch_update_cache_for_deleted_models(deleted_models)
                
            return {
                'success': True,
                'total_deleted': total_deleted,
                'total_attempted': len(file_paths),
                'cache_updated': cache_updated,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Error in bulk delete: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'results': []
            }
    
    async def _batch_update_cache_for_deleted_models(self, file_paths: List[str]) -> bool:
        """Update cache after multiple models have been deleted
        
        Args:
            file_paths: List of file paths that were deleted
            
        Returns:
            bool: True if cache was updated and saved successfully
        """
        if not file_paths or self._cache is None:
            return False
            
        try:
            # Get all models that need to be removed from cache
            models_to_remove = [item for item in self._cache.raw_data if item['file_path'] in file_paths]
            
            if not models_to_remove:
                return False
                
            # Update tag counts
            for model in models_to_remove:
                for tag in model.get('tags', []):
                    if tag in self._tags_count:
                        self._tags_count[tag] = max(0, self._tags_count[tag] - 1)
                        if self._tags_count[tag] == 0:
                            del self._tags_count[tag]
            
            # Update hash index
            for model in models_to_remove:
                file_path = model['file_path']
                self._cache.remove_from_version_index(model)
                if hasattr(self, '_hash_index') and self._hash_index:
                    # Get the hash and filename before removal for duplicate checking
                    file_name = os.path.splitext(os.path.basename(file_path))[0]
                    hash_val = model.get('sha256', '').lower()

                    # Remove from hash index
                    self._hash_index.remove_by_path(file_path, hash_val)
                    
                    # Check and clean up duplicates
                    self._cleanup_duplicates_after_removal(hash_val, file_name)
            
            # Update cache data
            self._cache.raw_data = [item for item in self._cache.raw_data if item['file_path'] not in file_paths]

            # Resort cache
            self._cache.rebuild_version_index()
            await self._cache.resort()

            await self._persist_current_cache()

            return True
            
        except Exception as e:
            logger.error(f"Error updating cache after bulk delete: {e}", exc_info=True)
            return False
    
    def _cleanup_duplicates_after_removal(self, hash_val: str, file_name: str) -> None:
        """Clean up duplicate entries in hash index after removing a model
        
        Args:
            hash_val: SHA256 hash of the removed model
            file_name: File name of the removed model without extension
        """
        if not hash_val or not file_name or not hasattr(self, '_hash_index'):
            return
            
        # Clean up hash duplicates if only 0 or 1 entries remain
        if hash_val in self._hash_index._duplicate_hashes:
            if len(self._hash_index._duplicate_hashes[hash_val]) <= 1:
                del self._hash_index._duplicate_hashes[hash_val]
        
        # Clean up filename duplicates if only 0 or 1 entries remain
        if file_name in self._hash_index._duplicate_filenames:
            if len(self._hash_index._duplicate_filenames[file_name]) <= 1:
                del self._hash_index._duplicate_filenames[file_name]

    async def check_model_version_exists(self, model_version_id: int) -> bool:
        """Check if a specific model version exists in the cache

        Args:
            model_version_id: Civitai model version ID

        Returns:
            bool: True if the model version exists, False otherwise
        """
        try:
            normalized_id = int(model_version_id)
        except (TypeError, ValueError):
            return False

        try:
            cache = await self.get_cached_data()
            if not cache:
                return False

            return normalized_id in cache.version_index
        except Exception as e:
            logger.error(f"Error checking model version existence: {e}")
            return False

    async def get_model_versions_by_id(self, model_id: int) -> List[Dict]:
        """Get all versions of a model by its ID
        
        Args:
            model_id: Civitai model ID
            
        Returns:
            List[Dict]: List of version information dictionaries
        """
        try:
            cache = await self.get_cached_data()
            if not cache:
                return []

            return cache.get_versions_by_model_id(model_id)
        except Exception as e:
            logger.error(f"Error getting model versions: {e}")
            return []
