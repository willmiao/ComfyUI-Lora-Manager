"""Utilities for working with Civitai assets."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def rewrite_preview_url(source_url: str | None, media_type: str | None = None) -> tuple[str | None, bool]:
    """Rewrite Civitai preview URLs to use optimized renditions.

    Args:
        source_url: Original preview URL from the Civitai API.
        media_type: Optional media type hint (e.g. ``"image"`` or ``"video"``).

    Returns:
        A tuple of the potentially rewritten URL and a flag indicating whether the
        replacement occurred. When the URL is not rewritten, the original value is
        returned with ``False``.
    """
    if not source_url:
        return source_url, False

    try:
        parsed = urlparse(source_url)
    except ValueError:
        return source_url, False

    if parsed.netloc.lower() != "image.civitai.com":
        return source_url, False

    replacement = "/width=450,optimized=true"
    if (media_type or "").lower() == "video":
        replacement = "/transcode=true,width=450,optimized=true"

    if "/original=true" not in parsed.path:
        return source_url, False

    updated_path = parsed.path.replace("/original=true", replacement, 1)
    if updated_path == parsed.path:
        return source_url, False

    rewritten = urlunparse(parsed._replace(path=updated_path))
    return rewritten, True


__all__ = ["rewrite_preview_url"]

