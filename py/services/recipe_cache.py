import asyncio
from typing import Iterable, List, Dict, Optional
from dataclasses import dataclass
from operator import itemgetter
from natsort import natsorted

@dataclass
class RecipeCache:
    """Cache structure for Recipe data"""
    raw_data: List[Dict]
    sorted_by_name: List[Dict]
    sorted_by_date: List[Dict]

    def __post_init__(self):
        self._lock = asyncio.Lock()

    async def resort(self, name_only: bool = False):
        """Resort all cached data views"""
        async with self._lock:
            self._resort_locked(name_only=name_only)

    async def update_recipe_metadata(self, recipe_id: str, metadata: Dict, *, resort: bool = True) -> bool:
        """Update metadata for a specific recipe in all cached data

        Args:
            recipe_id: The ID of the recipe to update
            metadata: The new metadata

        Returns:
            bool: True if the update was successful, False if the recipe wasn't found
        """
        async with self._lock:
            for item in self.raw_data:
                if str(item.get('id')) == str(recipe_id):
                    item.update(metadata)
                    if resort:
                        self._resort_locked()
                    return True
        return False  # Recipe not found

    async def add_recipe(self, recipe_data: Dict, *, resort: bool = False) -> None:
        """Add a new recipe to the cache."""

        async with self._lock:
            self.raw_data.append(recipe_data)
            if resort:
                self._resort_locked()

    async def remove_recipe(self, recipe_id: str, *, resort: bool = False) -> Optional[Dict]:
        """Remove a recipe from the cache by ID.

        Args:
            recipe_id: The ID of the recipe to remove

        Returns:
            The removed recipe data if found, otherwise ``None``.
        """

        async with self._lock:
            for index, recipe in enumerate(self.raw_data):
                if str(recipe.get('id')) == str(recipe_id):
                    removed = self.raw_data.pop(index)
                    if resort:
                        self._resort_locked()
                    return removed
        return None

    async def bulk_remove(self, recipe_ids: Iterable[str], *, resort: bool = False) -> List[Dict]:
        """Remove multiple recipes from the cache."""

        id_set = {str(recipe_id) for recipe_id in recipe_ids}
        if not id_set:
            return []

        async with self._lock:
            removed = [item for item in self.raw_data if str(item.get('id')) in id_set]
            if not removed:
                return []

            self.raw_data = [item for item in self.raw_data if str(item.get('id')) not in id_set]
            if resort:
                self._resort_locked()
            return removed

    async def replace_recipe(self, recipe_id: str, new_data: Dict, *, resort: bool = False) -> bool:
        """Replace cached data for a recipe."""

        async with self._lock:
            for index, recipe in enumerate(self.raw_data):
                if str(recipe.get('id')) == str(recipe_id):
                    self.raw_data[index] = new_data
                    if resort:
                        self._resort_locked()
                    return True
        return False

    async def get_recipe(self, recipe_id: str) -> Optional[Dict]:
        """Return a shallow copy of a cached recipe."""

        async with self._lock:
            for recipe in self.raw_data:
                if str(recipe.get('id')) == str(recipe_id):
                    return dict(recipe)
        return None

    async def snapshot(self) -> List[Dict]:
        """Return a copy of all cached recipes."""

        async with self._lock:
            return [dict(item) for item in self.raw_data]

    def _resort_locked(self, *, name_only: bool = False) -> None:
        """Sort cached views. Caller must hold ``_lock``."""

        self.sorted_by_name = natsorted(
            self.raw_data,
            key=lambda x: x.get('title', '').lower()
        )
        if not name_only:
            self.sorted_by_date = sorted(
                self.raw_data,
                key=itemgetter('created_date', 'file_path'),
                reverse=True
            )