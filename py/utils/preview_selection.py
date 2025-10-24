"""Utilities for selecting preview media from Civitai image metadata."""

from __future__ import annotations

from typing import Mapping, Optional, Sequence, Tuple

from .constants import NSFW_LEVELS

PreviewMedia = Mapping[str, object]


def _extract_nsfw_level(entry: Mapping[str, object]) -> int:
    """Return a normalized NSFW level value for the supplied media entry."""

    value = entry.get("nsfwLevel", 0)
    try:
        return int(value)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return 0


def select_preview_media(
    images: Sequence[Mapping[str, object]] | None,
    *,
    blur_mature_content: bool,
) -> Tuple[Optional[PreviewMedia], int]:
    """Select the most appropriate preview media entry.

    When ``blur_mature_content`` is enabled we first try to return the first media
    item with an ``nsfwLevel`` lower than :pydata:`NSFW_LEVELS["R"]`. If none are
    available we return the media entry with the lowest NSFW level. When the
    setting is disabled we simply return the first entry.
    """

    if not images:
        return None, 0

    candidates = [item for item in images if isinstance(item, Mapping)]
    if not candidates:
        return None, 0

    selected = candidates[0]
    selected_level = _extract_nsfw_level(selected)

    if not blur_mature_content:
        return selected, selected_level

    safe_threshold = NSFW_LEVELS.get("R", 4)
    for candidate in candidates:
        level = _extract_nsfw_level(candidate)
        if level < safe_threshold:
            return candidate, level

    for candidate in candidates[1:]:
        level = _extract_nsfw_level(candidate)
        if level < selected_level:
            selected = candidate
            selected_level = level

    return selected, selected_level


__all__ = ["select_preview_media"]
