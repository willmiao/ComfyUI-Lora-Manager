"""Service for managing autocomplete via TagFTSIndex.

This service provides full-text search capabilities for Danbooru/e621 tags
with category filtering and enriched results including post counts.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class CustomWordsService:
    """Service for autocomplete via TagFTSIndex.

    This service:
    - Uses TagFTSIndex for fast full-text search of Danbooru/e621 tags
    - Supports category-based filtering
    - Returns enriched results with category and post_count
    - Provides sub-100ms search times for 221k+ tags
    """

    _instance: Optional[CustomWordsService] = None
    _initialized: bool = False

    def __new__(cls) -> CustomWordsService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._tag_index: Optional[Any] = None
        self._initialized = True

    @classmethod
    def get_instance(cls) -> CustomWordsService:
        """Get the singleton instance of CustomWordsService."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_tag_index(self):
        """Get or create the TagFTSIndex instance (lazy initialization)."""
        if self._tag_index is None:
            try:
                from .tag_fts_index import get_tag_fts_index
                self._tag_index = get_tag_fts_index()
            except Exception as e:
                logger.warning(f"Failed to initialize TagFTSIndex: {e}")
                self._tag_index = None
        return self._tag_index

    def search_words(
        self,
        search_term: str,
        limit: int = 20,
        categories: Optional[List[int]] = None,
        enriched: bool = False
    ) -> List[Dict[str, Any]]:
        """Search tags using TagFTSIndex with category filtering.

        Args:
            search_term: The search term to match against.
            limit: Maximum number of results to return.
            categories: Optional list of category IDs to filter by.
            enriched: If True, always return enriched results with category
                       and post_count (default behavior now).

        Returns:
            List of dicts with tag_name, category, and post_count.
        """
        tag_index = self._get_tag_index()
        if tag_index is not None:
            results = tag_index.search(search_term, categories=categories, limit=limit)
            return results

        logger.debug("TagFTSIndex not available, returning empty results")
        return []


def get_custom_words_service() -> CustomWordsService:
    """Factory function to get the CustomWordsService singleton."""
    return CustomWordsService.get_instance()


__all__ = ["CustomWordsService", "get_custom_words_service"]
