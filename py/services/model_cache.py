import asyncio
from typing import List, Dict
from dataclasses import dataclass
from operator import itemgetter
from natsort import natsorted

@dataclass
class ModelCache:
    """Cache structure for model data"""
    raw_data: List[Dict]
    sorted_by_name: List[Dict]
    sorted_by_date: List[Dict]
    folders: List[str]
    
    def __post_init__(self):
        self._lock = asyncio.Lock()

    async def resort(self, name_only: bool = False):
        """Resort all cached data views"""
        async with self._lock:
            self.sorted_by_name = natsorted(
                self.raw_data, 
                key=lambda x: x['model_name'].lower()  # Case-insensitive sort
            )
            if not name_only:
                self.sorted_by_date = sorted(
                    self.raw_data, 
                    key=itemgetter('modified'), 
                    reverse=True
                )
            # Update folder list
            all_folders = set(l['folder'] for l in self.raw_data)
            self.folders = sorted(list(all_folders), key=lambda x: x.lower())

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