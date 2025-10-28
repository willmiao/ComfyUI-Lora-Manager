from abc import ABC, abstractmethod
import asyncio
from typing import Dict, List, Optional, Type, TYPE_CHECKING
import logging
import os

from ..utils.models import BaseModelMetadata
from ..utils.metadata_manager import MetadataManager
from .model_query import FilterCriteria, ModelCacheRepository, ModelFilterSet, SearchStrategy, SettingsProvider
from .settings_manager import get_settings_manager

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .model_update_service import ModelUpdateService

class BaseModelService(ABC):
    """Base service class for all model types"""
    
    def __init__(
        self,
        model_type: str,
        scanner,
        metadata_class: Type[BaseModelMetadata],
        *,
        cache_repository: Optional[ModelCacheRepository] = None,
        filter_set: Optional[ModelFilterSet] = None,
        search_strategy: Optional[SearchStrategy] = None,
        settings_provider: Optional[SettingsProvider] = None,
        update_service: Optional["ModelUpdateService"] = None,
    ):
        """Initialize the service.

        Args:
            model_type: Type of model (lora, checkpoint, etc.).
            scanner: Model scanner instance.
            metadata_class: Metadata class for this model type.
            cache_repository: Custom repository for cache access (primarily for tests).
            filter_set: Filter component controlling folder/tag/favorites logic.
            search_strategy: Search component for fuzzy/text matching.
            settings_provider: Settings object; defaults to the global settings manager.
            update_service: Service used to determine whether models have remote updates available.
        """
        self.model_type = model_type
        self.scanner = scanner
        self.metadata_class = metadata_class
        self.settings = settings_provider or get_settings_manager()
        self.cache_repository = cache_repository or ModelCacheRepository(scanner)
        self.filter_set = filter_set or ModelFilterSet(self.settings)
        self.search_strategy = search_strategy or SearchStrategy()
        self.update_service = update_service
    
    async def get_paginated_data(
        self,
        page: int,
        page_size: int,
        sort_by: str = 'name',
        folder: str = None,
        search: str = None,
        fuzzy_search: bool = False,
        base_models: list = None,
        tags: list = None,
        search_options: dict = None,
        hash_filters: dict = None,
        favorites_only: bool = False,
        update_available_only: bool = False,
        **kwargs,
    ) -> Dict:
        """Get paginated and filtered model data"""

        sort_params = self.cache_repository.parse_sort(sort_by)
        sorted_data = await self.cache_repository.fetch_sorted(sort_params)

        if hash_filters:
            filtered_data = await self._apply_hash_filters(sorted_data, hash_filters)
        else:
            filtered_data = await self._apply_common_filters(
                sorted_data,
                folder=folder,
                base_models=base_models,
                tags=tags,
                favorites_only=favorites_only,
                search_options=search_options,
            )

            if search:
                filtered_data = await self._apply_search_filters(
                    filtered_data,
                    search,
                    fuzzy_search,
                    search_options,
                )

            filtered_data = await self._apply_specific_filters(filtered_data, **kwargs)

        annotated_for_filter: Optional[List[Dict]] = None
        if update_available_only:
            annotated_for_filter = await self._annotate_update_flags(filtered_data)
            filtered_data = [
                item for item in annotated_for_filter
                if item.get('update_available')
            ]

        paginated = self._paginate(filtered_data, page, page_size)

        if update_available_only:
            # Items already include update flags thanks to the pre-filter annotation.
            paginated['items'] = list(paginated['items'])
        else:
            paginated['items'] = await self._annotate_update_flags(
                paginated['items'],
            )
        return paginated

    
    async def _apply_hash_filters(self, data: List[Dict], hash_filters: Dict) -> List[Dict]:
        """Apply hash-based filtering"""
        single_hash = hash_filters.get('single_hash')
        multiple_hashes = hash_filters.get('multiple_hashes')
        
        if single_hash:
            # Filter by single hash
            single_hash = single_hash.lower()
            return [
                item for item in data
                if item.get('sha256', '').lower() == single_hash
            ]
        elif multiple_hashes:
            # Filter by multiple hashes
            hash_set = set(hash.lower() for hash in multiple_hashes)
            return [
                item for item in data
                if item.get('sha256', '').lower() in hash_set
            ]
        
        return data
    
    async def _apply_common_filters(
        self,
        data: List[Dict],
        folder: str = None,
        base_models: list = None,
        tags: list = None,
        favorites_only: bool = False,
        search_options: dict = None,
    ) -> List[Dict]:
        """Apply common filters that work across all model types"""
        normalized_options = self.search_strategy.normalize_options(search_options)
        criteria = FilterCriteria(
            folder=folder,
            base_models=base_models,
            tags=tags,
            favorites_only=favorites_only,
            search_options=normalized_options,
        )
        return self.filter_set.apply(data, criteria)
    
    async def _apply_search_filters(
        self,
        data: List[Dict],
        search: str,
        fuzzy_search: bool,
        search_options: dict,
    ) -> List[Dict]:
        """Apply search filtering"""
        normalized_options = self.search_strategy.normalize_options(search_options)
        return self.search_strategy.apply(data, search, normalized_options, fuzzy_search)
    
    async def _apply_specific_filters(self, data: List[Dict], **kwargs) -> List[Dict]:
        """Apply model-specific filters - to be overridden by subclasses if needed"""
        return data

    async def _annotate_update_flags(
        self,
        items: List[Dict],
    ) -> List[Dict]:
        """Attach an update_available flag to each response item.

        Items without a civitai model id default to False.
        """
        if not items:
            return []

        annotated = [dict(item) for item in items]

        if self.update_service is None:
            for item in annotated:
                item['update_available'] = False
            return annotated

        id_to_items: Dict[int, List[Dict]] = {}
        ordered_ids: List[int] = []
        for item in annotated:
            model_id = self._extract_model_id(item)
            if model_id is None:
                item['update_available'] = False
                continue
            if model_id not in id_to_items:
                id_to_items[model_id] = []
                ordered_ids.append(model_id)
            id_to_items[model_id].append(item)

        if not ordered_ids:
            return annotated

        resolved: Optional[Dict[int, bool]] = None
        bulk_method = getattr(self.update_service, "has_updates_bulk", None)
        if callable(bulk_method):
            try:
                resolved = await bulk_method(self.model_type, ordered_ids)
            except Exception as exc:
                logger.error(
                    "Failed to resolve update status in bulk for %s models (%s): %s",
                    self.model_type,
                    ordered_ids,
                    exc,
                    exc_info=True,
                )
                resolved = None

        if resolved is None:
            tasks = [
                self.update_service.has_update(self.model_type, model_id)
                for model_id in ordered_ids
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            resolved = {}
            for model_id, result in zip(ordered_ids, results):
                if isinstance(result, Exception):
                    logger.error(
                        "Failed to resolve update status for model %s (%s): %s",
                        model_id,
                        self.model_type,
                        result,
                    )
                    continue
                resolved[model_id] = bool(result)

        for model_id, items_for_id in id_to_items.items():
            flag = bool(resolved.get(model_id, False))
            for item in items_for_id:
                item['update_available'] = flag

        return annotated

    @staticmethod
    def _extract_model_id(item: Dict) -> Optional[int]:
        civitai = item.get('civitai') if isinstance(item, dict) else None
        if not isinstance(civitai, dict):
            return None
        try:
            value = civitai.get('modelId')
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
    
    def _paginate(self, data: List[Dict], page: int, page_size: int) -> Dict:
        """Apply pagination to filtered data"""
        total_items = len(data)
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)
        
        return {
            'items': data[start_idx:end_idx],
            'total': total_items,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_items + page_size - 1) // page_size
        }
    
    @abstractmethod
    async def format_response(self, model_data: Dict) -> Dict:
        """Format model data for API response - must be implemented by subclasses"""
        pass
    
    # Common service methods that delegate to scanner
    async def get_top_tags(self, limit: int = 20) -> List[Dict]:
        """Get top tags sorted by frequency"""
        return await self.scanner.get_top_tags(limit)
    
    async def get_base_models(self, limit: int = 20) -> List[Dict]:
        """Get base models sorted by frequency"""
        return await self.scanner.get_base_models(limit)
    
    def has_hash(self, sha256: str) -> bool:
        """Check if a model with given hash exists"""
        return self.scanner.has_hash(sha256)
    
    def get_path_by_hash(self, sha256: str) -> Optional[str]:
        """Get file path for a model by its hash"""
        return self.scanner.get_path_by_hash(sha256)
    
    def get_hash_by_path(self, file_path: str) -> Optional[str]:
        """Get hash for a model by its file path"""
        return self.scanner.get_hash_by_path(file_path)
    
    async def scan_models(self, force_refresh: bool = False, rebuild_cache: bool = False):
        """Trigger model scanning"""
        return await self.scanner.get_cached_data(force_refresh=force_refresh, rebuild_cache=rebuild_cache)
    
    async def get_model_info_by_name(self, name: str):
        """Get model information by name"""
        return await self.scanner.get_model_info_by_name(name)
    
    def get_model_roots(self) -> List[str]:
        """Get model root directories"""
        return self.scanner.get_model_roots()
    
    def filter_civitai_data(self, data: Dict, minimal: bool = False) -> Dict:
        """Filter relevant fields from CivitAI data"""
        if not data:
            return {}

        fields = ["id", "modelId", "name", "trainedWords"] if minimal else [
            "id", "modelId", "name", "createdAt", "updatedAt",
            "publishedAt", "trainedWords", "baseModel", "description",
            "model", "images", "customImages", "creator"
        ]
        return {k: data[k] for k in fields if k in data}
    
    async def get_folder_tree(self, model_root: str) -> Dict:
        """Get hierarchical folder tree for a specific model root"""
        cache = await self.scanner.get_cached_data()
        
        # Build tree structure from folders
        tree = {}
        
        for folder in cache.folders:
            # Check if this folder belongs to the specified model root
            folder_belongs_to_root = False
            for root in self.scanner.get_model_roots():
                if root == model_root:
                    folder_belongs_to_root = True
                    break
            
            if not folder_belongs_to_root:
                continue
            
            # Split folder path into components
            parts = folder.split('/') if folder else []
            current_level = tree
            
            for part in parts:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
        
        return tree
    
    async def get_unified_folder_tree(self) -> Dict:
        """Get unified folder tree across all model roots"""
        cache = await self.scanner.get_cached_data()
        
        # Build unified tree structure by analyzing all relative paths
        unified_tree = {}
        
        # Get all model roots for path normalization
        model_roots = self.scanner.get_model_roots()
        
        for folder in cache.folders:
            if not folder:  # Skip empty folders
                continue
            
            # Find which root this folder belongs to by checking the actual file paths
            # This is a simplified approach - we'll use the folder as-is since it should already be relative
            relative_path = folder
            
            # Split folder path into components
            parts = relative_path.split('/')
            current_level = unified_tree
            
            for part in parts:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
        
        return unified_tree

    async def get_model_notes(self, model_name: str) -> Optional[str]:
        """Get notes for a specific model file"""
        cache = await self.scanner.get_cached_data()
        
        for model in cache.raw_data:
            if model['file_name'] == model_name:
                return model.get('notes', '')
        
        return None
    
    async def get_model_preview_url(self, model_name: str) -> Optional[str]:
        """Get the static preview URL for a model file"""
        cache = await self.scanner.get_cached_data()
        
        for model in cache.raw_data:
            if model['file_name'] == model_name:
                preview_url = model.get('preview_url')
                if preview_url:
                    from ..config import config
                    return config.get_preview_static_url(preview_url)
        
        return '/loras_static/images/no-preview.png'
    
    async def get_model_civitai_url(self, model_name: str) -> Dict[str, Optional[str]]:
        """Get the Civitai URL for a model file"""
        cache = await self.scanner.get_cached_data()
        
        for model in cache.raw_data:
            if model['file_name'] == model_name:
                civitai_data = model.get('civitai', {})
                model_id = civitai_data.get('modelId')
                version_id = civitai_data.get('id')
                
                if model_id:
                    civitai_url = f"https://civitai.com/models/{model_id}"
                    if version_id:
                        civitai_url += f"?modelVersionId={version_id}"
                    
                    return {
                        'civitai_url': civitai_url,
                        'model_id': str(model_id),
                        'version_id': str(version_id) if version_id else None
                    }
        
        return {'civitai_url': None, 'model_id': None, 'version_id': None}

    async def get_model_metadata(self, file_path: str) -> Optional[Dict]:
        """Load full metadata for a single model.

        Listing/search endpoints return lightweight cache entries; this method performs
        a lazy read of the on-disk metadata snapshot when callers need full detail.
        """
        metadata, should_skip = await MetadataManager.load_metadata(file_path, self.metadata_class)
        if should_skip or metadata is None:
            return None
        return self.filter_civitai_data(metadata.to_dict().get("civitai", {}))


    async def get_model_description(self, file_path: str) -> Optional[str]:
        """Return the stored modelDescription field for a model."""
        metadata, should_skip = await MetadataManager.load_metadata(file_path, self.metadata_class)
        if should_skip or metadata is None:
            return None
        return metadata.modelDescription or ''


    async def search_relative_paths(self, search_term: str, limit: int = 15) -> List[str]:
        """Search model relative file paths for autocomplete functionality"""
        cache = await self.scanner.get_cached_data()
        
        matching_paths = []
        search_lower = search_term.lower()
        
        # Get model roots for path calculation
        model_roots = self.scanner.get_model_roots()
        
        for model in cache.raw_data:
            file_path = model.get('file_path', '')
            if not file_path:
                continue
                
            # Calculate relative path from model root
            relative_path = None
            for root in model_roots:
                # Normalize paths for comparison
                normalized_root = os.path.normpath(root)
                normalized_file = os.path.normpath(file_path)
                
                if normalized_file.startswith(normalized_root):
                    # Remove root and leading separator to get relative path
                    relative_path = normalized_file[len(normalized_root):].lstrip(os.sep)
                    break
            
            if relative_path and search_lower in relative_path.lower():
                matching_paths.append(relative_path)
                
                if len(matching_paths) >= limit * 2:  # Get more for better sorting
                    break
        
        # Sort by relevance (exact matches first, then by length)
        matching_paths.sort(key=lambda x: (
            not x.lower().startswith(search_lower),  # Exact prefix matches first
            len(x),  # Then by length (shorter first)
            x.lower()  # Then alphabetically
        ))
        
        return matching_paths[:limit]
