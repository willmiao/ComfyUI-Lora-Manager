"""Service for updating tag collections on metadata records."""

from __future__ import annotations

import os

from typing import Awaitable, Callable, Dict, List, Sequence


class TagUpdateService:
    """Encapsulate tag manipulation for models."""

    def __init__(self, *, metadata_manager) -> None:
        self._metadata_manager = metadata_manager

    async def add_tags(
        self,
        *,
        file_path: str,
        new_tags: Sequence[str],
        metadata_loader: Callable[[str], Awaitable[Dict[str, object]]],
        update_cache: Callable[[str, str, Dict[str, object]], Awaitable[bool]],
    ) -> List[str]:
        """Add tags to a metadata entry while keeping case-insensitive uniqueness."""

        base, _ = os.path.splitext(file_path)
        metadata_path = f"{base}.metadata.json"
        metadata = await metadata_loader(metadata_path)

        existing_tags = list(metadata.get("tags", []))
        existing_lower = [tag.lower() for tag in existing_tags]

        tags_added: List[str] = []
        for tag in new_tags:
            if isinstance(tag, str) and tag.strip():
                normalized = tag.strip()
                if normalized.lower() not in existing_lower:
                    existing_tags.append(normalized)
                    existing_lower.append(normalized.lower())
                    tags_added.append(normalized)

        metadata["tags"] = existing_tags
        await self._metadata_manager.save_metadata(file_path, metadata)
        await update_cache(file_path, file_path, metadata)

        return existing_tags

