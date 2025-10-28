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

DISPLAY_NAME_MODES = {"model_name", "file_name"}


@dataclass
class ModelCache:
    """Cache structure for model data with extensible sorting."""

    raw_data: List[Dict]
    folders: List[str]
    version_index: Dict[int, Dict] = field(default_factory=dict)
    model_id_index: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict)
    name_display_mode: str = "model_name"

    def __post_init__(self):
        self._lock = asyncio.Lock()
        # Cache for last sort: (sort_key, order) -> sorted list
        self._last_sort: Tuple[str, str] = (None, None)
        self._last_sorted_data: List[Dict] = []
        self._normalize_raw_data()
        self.name_display_mode = self._normalize_display_mode(self.name_display_mode)
        # Default sort on init
        asyncio.create_task(self.resort())
        self.rebuild_version_index()

    @staticmethod
    def _normalize_display_mode(value: Optional[str]) -> str:
        if isinstance(value, str) and value in DISPLAY_NAME_MODES:
            return value
        return "model_name"

    @staticmethod
    def _ensure_string(value: Any) -> str:
        """Return a safe string representation for metadata fields."""

        if isinstance(value, str):
            return value
        if value is None:
            return ""
        return str(value)

    def _normalize_item(self, item: Dict) -> None:
        """Ensure core metadata fields are present and string typed."""

        if not isinstance(item, dict):
            return

        for field in ("model_name", "file_name", "folder"):
            if field in item:
                item[field] = self._ensure_string(item.get(field))

    def _normalize_raw_data(self) -> None:
        """Normalize every cached entry before it is consumed."""

        for item in self.raw_data:
            self._normalize_item(item)

    def _get_display_name(self, item: Dict) -> str:
        """Return the value used for name-based sorting based on display settings."""

        if self.name_display_mode == "file_name":
            primary = self._ensure_string(item.get("file_name"))
            fallback = self._ensure_string(item.get("model_name"))
        else:
            primary = self._ensure_string(item.get("model_name"))
            fallback = self._ensure_string(item.get("file_name"))

        candidate = primary or fallback
        return candidate or ""

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
        """Rebuild the version and model indexes from the current raw data."""

        self.version_index = {}
        self.model_id_index = {}
        for item in self.raw_data:
            self.add_to_version_index(item)

    def add_to_version_index(self, item: Dict) -> None:
        """Register a cache item in the version/model indexes if possible."""

        civitai_data = item.get('civitai') if isinstance(item, dict) else None
        if not isinstance(civitai_data, dict):
            return

        version_id = self._normalize_version_id(civitai_data.get('id'))
        if version_id is None:
            return

        self.version_index[version_id] = item

        model_id = self._normalize_version_id(civitai_data.get('modelId'))
        if model_id is None:
            return

        descriptor = self._build_version_descriptor(item, civitai_data, version_id)
        if descriptor is None:
            return

        versions = self.model_id_index.setdefault(model_id, [])
        for index, existing in enumerate(versions):
            if existing.get('versionId') == descriptor['versionId']:
                versions[index] = descriptor
                break
        else:
            versions.append(descriptor)

    def remove_from_version_index(self, item: Dict) -> None:
        """Remove a cache item from the version/model indexes if present."""

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

        model_id = self._normalize_version_id(civitai_data.get('modelId'))
        if model_id is None:
            return

        versions = self.model_id_index.get(model_id)
        if not versions:
            return

        filtered = [v for v in versions if v.get('versionId') != version_id]
        if filtered:
            self.model_id_index[model_id] = filtered
        else:
            self.model_id_index.pop(model_id, None)

    def _build_version_descriptor(
        self,
        item: Dict,
        civitai_data: Dict[str, Any],
        version_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Create a lightweight descriptor for a version entry."""

        model_name = self._ensure_string(civitai_data.get('name'))
        file_name = self._ensure_string(item.get('file_name'))
        return {
            'versionId': version_id,
            'name': model_name,
            'fileName': file_name,
        }

    def get_versions_by_model_id(self, model_id: Any) -> List[Dict[str, Any]]:
        """Return cached version descriptors for a given model ID."""

        normalized_id = self._normalize_version_id(model_id)
        if normalized_id is None:
            return []

        versions = self.model_id_index.get(normalized_id, [])
        return [dict(version) for version in versions]

    async def resort(self):
        """Resort cached data according to last sort mode if set"""
        async with self._lock:
            if self._last_sort != (None, None):
                sort_key, order = self._last_sort
                sorted_data = self._sort_data(self.raw_data, sort_key, order)
                self._last_sorted_data = sorted_data
                # Update folder list
            # else: do nothing

            all_folders = {
                self._ensure_string(item.get('folder'))
                for item in self.raw_data
                if isinstance(item, dict)
            }
            self.folders = sorted(list(all_folders), key=lambda x: x.lower())
            self.rebuild_version_index()

    def _sort_data(self, data: List[Dict], sort_key: str, order: str) -> List[Dict]:
        """Sort data by sort_key and order"""
        reverse = (order == 'desc')
        if sort_key == 'name':
            # Natural sort by configured display name, case-insensitive
            return natsorted(
                data,
                key=lambda x: self._get_display_name(x).lower(),
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

    async def update_name_display_mode(self, display_mode: str) -> None:
        """Update the display mode used for name sorting and refresh cached results."""

        normalized = self._normalize_display_mode(display_mode)
        async with self._lock:
            if self.name_display_mode == normalized:
                return

            self.name_display_mode = normalized

            if self._last_sort[0] == 'name':
                sort_key, order = self._last_sort
                self._last_sorted_data = self._sort_data(self.raw_data, sort_key, order)

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