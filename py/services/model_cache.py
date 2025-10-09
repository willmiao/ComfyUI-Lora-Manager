import asyncio
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from operator import itemgetter
from natsort import natsorted

# Supported sort modes: (sort_key, order)
# order: 'asc' for ascending, 'desc' for descending
SUPPORTED_SORT_MODES = [
    ('name', 'asc'),
    ('name', 'desc'),
    ('date', 'asc'),
    ('date', 'desc'),
    ('size', 'asc'),
    ('size', 'desc'),
]

@dataclass
class ModelCache:
    """Cache structure for model data with extensible sorting."""

    raw_data: List[Dict]
    folders: List[str]
    version_index: Dict[int, Dict] = field(default_factory=dict)

    def __post_init__(self):
        self._lock = asyncio.Lock()
        # Cache for last sort: (sort_key, order) -> sorted list
        self._last_sort: Tuple[str, str] = (None, None)
        self._last_sorted_data: List[Dict] = []
        # Default sort on init
        asyncio.create_task(self.resort())
        self.rebuild_version_index()

    @staticmethod
    def _normalize_version_id(value: Any) -> Optional[int]:
        """Normalize a potential version identifier into an integer."""

        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    def rebuild_version_index(self) -> None:
        """Rebuild the version index from the current raw data."""

        self.version_index = {}
        for item in self.raw_data:
            self.add_to_version_index(item)

    def add_to_version_index(self, item: Dict) -> None:
        """Register a cache item in the version index if possible."""

        civitai_data = item.get('civitai') if isinstance(item, dict) else None
        if not isinstance(civitai_data, dict):
            return

        version_id = self._normalize_version_id(civitai_data.get('id'))
        if version_id is None:
            return

        self.version_index[version_id] = item

    def remove_from_version_index(self, item: Dict) -> None:
        """Remove a cache item from the version index if present."""

        civitai_data = item.get('civitai') if isinstance(item, dict) else None
        if not isinstance(civitai_data, dict):
            return

        version_id = self._normalize_version_id(civitai_data.get('id'))
        if version_id is None:
            return

        existing = self.version_index.get(version_id)
        if existing is item or (
            isinstance(existing, dict)
            and existing.get('file_path') == item.get('file_path')
        ):
            self.version_index.pop(version_id, None)

    async def resort(self):
        """Resort cached data according to last sort mode if set"""
        async with self._lock:
            if self._last_sort != (None, None):
                sort_key, order = self._last_sort
                sorted_data = self._sort_data(self.raw_data, sort_key, order)
                self._last_sorted_data = sorted_data
                # Update folder list
            # else: do nothing

            all_folders = set(l['folder'] for l in self.raw_data)
            self.folders = sorted(list(all_folders), key=lambda x: x.lower())
            self.rebuild_version_index()

    def _sort_data(self, data: List[Dict], sort_key: str, order: str) -> List[Dict]:
        """Sort data by sort_key and order"""
        reverse = (order == 'desc')
        if sort_key == 'name':
            # Natural sort by model_name, case-insensitive
            return natsorted(
                data,
                key=lambda x: x['model_name'].lower(),
                reverse=reverse
            )
        elif sort_key == 'date':
            # Sort by modified timestamp
            return sorted(
                data,
                key=itemgetter('modified'),
                reverse=reverse
            )
        elif sort_key == 'size':
            # Sort by file size
            return sorted(
                data,
                key=itemgetter('size'),
                reverse=reverse
            )
        else:
            # Fallback: no sort
            return list(data)

    async def get_sorted_data(self, sort_key: str = 'name', order: str = 'asc') -> List[Dict]:
        """Get sorted data by sort_key and order, using cache if possible"""
        async with self._lock:
            if (sort_key, order) == self._last_sort:
                return self._last_sorted_data
            sorted_data = self._sort_data(self.raw_data, sort_key, order)
            self._last_sort = (sort_key, order)
            self._last_sorted_data = sorted_data
            return sorted_data

    async def update_preview_url(self, file_path: str, preview_url: str, preview_nsfw_level: int) -> bool:
        """Update preview_url for a specific model in all cached data
        
        Args:
            file_path: The file path of the model to update
            preview_url: The new preview URL
            preview_nsfw_level: The NSFW level of the preview
            
        Returns:
            bool: True if the update was successful, False if the model wasn't found
        """
        async with self._lock:
            # Update in raw_data
            for item in self.raw_data:
                if item['file_path'] == file_path:
                    item['preview_url'] = preview_url
                    item['preview_nsfw_level'] = preview_nsfw_level
                    break
            else:
                return False  # Model not found
                    
            return True