"""Service for managing custom autocomplete words.

This service provides functionality to parse CSV-formatted custom words,
search them with priority-based ranking, and manage storage.

It also integrates with TagFTSIndex to search the Danbooru/e621 tag database
for comprehensive autocomplete suggestions with category filtering.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WordEntry:
    """Represents a single custom word entry."""
    text: str
    priority: Optional[int] = None
    value: Optional[str] = None

    def get_insert_text(self) -> str:
        """Get the text to insert when this word is selected."""
        return self.value if self.value is not None else self.text


class CustomWordsService:
    """Service for managing custom autocomplete words.

    This service:
    - Loads custom words from CSV files (sharing with pysssss plugin)
    - Parses CSV format: word[,priority] or word[,alias][,priority]
    - Searches words with priority-based ranking
    - Caches parsed words for performance
    - Integrates with TagFTSIndex for Danbooru/e621 tag search
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

        self._words_cache: Dict[str, WordEntry] = {}
        self._file_path: Optional[Path] = None
        self._tag_index: Optional[Any] = None  # Lazy-loaded TagFTSIndex
        self._initialized = True

        self._determine_file_path()

    @classmethod
    def get_instance(cls) -> CustomWordsService:
        """Get the singleton instance of CustomWordsService."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _determine_file_path(self) -> None:
        """Determine file path for custom words.

        Priority order:
        1. pysssss plugin's user/autocomplete.txt (if exists)
        2. Lora Manager's user directory
        """
        try:
            import folder_paths  # type: ignore
            comfy_dir = Path(folder_paths.base_path)
        except (ImportError, AttributeError):
            # Fallback: compute from __file__
            comfy_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

        pysssss_user_dir = comfy_dir / "custom_nodes" / "comfyui-custom-scripts" / "user"

        if pysssss_user_dir.exists():
            pysssss_file = pysssss_user_dir / "autocomplete.txt"
            if pysssss_file.exists():
                self._file_path = pysssss_file
                logger.info(f"Using pysssss custom words file: {pysssss_file}")
                return

        # Fallback to Lora Manager's user directory
        from .settings_manager import get_settings_manager

        settings_manager = get_settings_manager()
        lm_user_dir = Path(settings_manager._get_user_config_directory())
        lm_user_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = lm_user_dir / "autocomplete.txt"
        logger.info(f"Using Lora Manager custom words file: {self._file_path}")

    def get_file_path(self) -> Optional[Path]:
        """Get the current file path for custom words."""
        return self._file_path

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

    def load_words(self) -> Dict[str, WordEntry]:
        """Load and parse words from the custom words file.

        Returns:
            Dictionary mapping text to WordEntry objects.
        """
        if self._file_path is None or not self._file_path.exists():
            self._words_cache = {}
            return self._words_cache

        try:
            content = self._file_path.read_text(encoding="utf-8")
            self._words_cache = self._parse_csv_content(content)
            logger.debug(f"Loaded {len(self._words_cache)} custom words")
        except Exception as e:
            logger.error(f"Error loading custom words: {e}", exc_info=True)
            self._words_cache = {}

        return self._words_cache

    def _parse_csv_content(self, content: str) -> Dict[str, WordEntry]:
        """Parse CSV content into word entries.

        Supported formats:
        - word
        - word,priority

        Args:
            content: CSV-formatted string with one word per line.

        Returns:
            Dictionary mapping text to WordEntry objects.
        """
        words: Dict[str, WordEntry] = {}

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(",")
            parts = [p.strip() for p in parts if p.strip()]

            if not parts:
                continue

            text = parts[0]
            priority = None
            value = None

            if len(parts) == 2:
                try:
                    priority = int(parts[1])
                except ValueError:
                    # Not a priority, could be alias or unknown format
                    pass

            if text:
                words[text] = WordEntry(text=text, priority=priority, value=value)

        return words

    def search_words(
        self,
        search_term: str,
        limit: int = 20,
        categories: Optional[List[int]] = None,
        enriched: bool = False
    ) -> Union[List[str], List[Dict[str, Any]]]:
        """Search custom words with priority-based ranking.

        When categories are provided or enriched is True, uses TagFTSIndex to search
        the Danbooru/e621 tag database and returns enriched results with category
        and post_count.

        Matching priority (for custom words):
        1. Words with priority (sorted by priority descending)
        2. Prefix matches (word starts with search term)
        3. Include matches (word contains search term)

        Args:
            search_term: The search term to match against.
            limit: Maximum number of results to return.
            categories: Optional list of category IDs to filter by.
                       When provided, searches TagFTSIndex instead of custom words.
            enriched: If True, return enriched results even without category filtering.

        Returns:
            List of matching word texts (when categories is None and enriched is False), or
            List of dicts with tag_name, category, post_count (when categories is provided
            or enriched is True).
        """
        # Use TagFTSIndex when categories are specified or when explicitly requested
        tag_index = self._get_tag_index()
        if tag_index is not None:
            # Search the tag database
            results = tag_index.search(search_term, categories=categories, limit=limit)
            if results:
                # If categories were specified or enriched requested, return enriched results
                if categories is not None or enriched:
                    return results
                # Otherwise, convert to simple string list for backward compatibility
                return [r["tag_name"] for r in results]
            # Fall through to custom words if no tag results

        # Fall back to custom words search
        words = self._words_cache if self._words_cache else self.load_words()

        if not search_term:
            term_lower = ""
        else:
            term_lower = search_term.lower()

        priority_matches = []
        prefix_matches = []
        include_matches = []

        for text, entry in words.items():
            text_lower = text.lower()
            pos = text_lower.find(term_lower)

            if pos == -1:
                continue

            if entry.priority is not None:
                priority_matches.append((entry, pos))
            elif pos == 0:
                prefix_matches.append((entry, pos))
            else:
                include_matches.append((entry, pos))

        # Sort priority matches: by priority desc, then by length asc, then alphabetically
        priority_matches.sort(
            key=lambda x: (-x[0].priority if x[0].priority else 0, len(x[0].text), x[0].text)
        )

        # Sort prefix and include matches by position, then length, then alphabetically
        prefix_matches.sort(key=lambda x: (x[1], len(x[0].text), x[0].text))
        include_matches.sort(key=lambda x: (x[1], len(x[0].text), x[0].text))

        # Combine results: 20% top priority + all prefix matches + rest of priority + all include
        top_priority_count = max(1, limit // 5)

        text_results = (
            [entry.text for entry, _ in priority_matches[:top_priority_count]]
            + [entry.text for entry, _ in prefix_matches]
            + [entry.text for entry, _ in priority_matches[top_priority_count:]]
            + [entry.text for entry, _ in include_matches]
        )

        # If categories were requested but tag index failed, return empty enriched format
        if categories is not None:
            return [{"tag_name": t, "category": 0, "post_count": 0} for t in text_results[:limit]]

        return text_results[:limit]

    def save_words(self, content: str) -> bool:
        """Save custom words content to file.

        Args:
            content: CSV-formatted content to save.

        Returns:
            True if save was successful, False otherwise.
        """
        if self._file_path is None:
            logger.error("No file path configured for custom words")
            return False

        try:
            self._file_path.write_text(content, encoding="utf-8")
            self._words_cache = self._parse_csv_content(content)
            logger.info(f"Saved {len(self._words_cache)} custom words")
            return True
        except Exception as e:
            logger.error(f"Error saving custom words: {e}", exc_info=True)
            return False

    def get_content(self) -> str:
        """Get the raw content of the custom words file.

        Returns:
            The file content as a string, or empty string if file doesn't exist.
        """
        if self._file_path is None or not self._file_path.exists():
            return ""

        try:
            return self._file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Error reading custom words file: {e}", exc_info=True)
            return ""


def get_custom_words_service() -> CustomWordsService:
    """Factory function to get the CustomWordsService singleton."""
    return CustomWordsService.get_instance()


__all__ = ["CustomWordsService", "WordEntry", "get_custom_words_service"]
