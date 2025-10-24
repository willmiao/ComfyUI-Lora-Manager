"""Service for processing preview assets for models."""

from __future__ import annotations

import logging
import os
from typing import Awaitable, Callable, Dict, Optional, Sequence
from urllib.parse import urlparse

from ..utils.constants import CARD_PREVIEW_WIDTH, PREVIEW_EXTENSIONS
from ..utils.civitai_utils import rewrite_preview_url
from ..utils.preview_selection import select_preview_media
from .settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


class PreviewAssetService:
    """Manage fetching and persisting preview assets."""

    def __init__(
        self,
        *,
        metadata_manager,
        downloader_factory: Callable[[], Awaitable],
        exif_utils,
    ) -> None:
        self._metadata_manager = metadata_manager
        self._downloader_factory = downloader_factory
        self._exif_utils = exif_utils

    async def ensure_preview_for_metadata(
        self,
        metadata_path: str,
        local_metadata: Dict[str, object],
        images: Sequence[Dict[str, object]] | None,
    ) -> None:
        """Ensure preview assets exist for the supplied metadata entry."""

        if local_metadata.get("preview_url") and os.path.exists(
            str(local_metadata["preview_url"])
        ):
            return

        if not images:
            return

        settings_manager = get_settings_manager()
        blur_mature_content = bool(
            settings_manager.get("blur_mature_content", True)
        )
        first_preview, nsfw_level = select_preview_media(
            images,
            blur_mature_content=blur_mature_content,
        )

        if not first_preview:
            return

        base_name = os.path.splitext(os.path.splitext(os.path.basename(metadata_path))[0])[0]
        preview_dir = os.path.dirname(metadata_path)
        is_video = first_preview.get("type") == "video"
        preview_url = first_preview.get("url")

        if not preview_url:
            return

        def extension_from_url(url: str, fallback: str) -> str:
            try:
                parsed = urlparse(url)
            except ValueError:
                return fallback
            ext = os.path.splitext(parsed.path)[1]
            return ext or fallback

        downloader = await self._downloader_factory()

        if is_video:
            extension = extension_from_url(preview_url, ".mp4")
            preview_path = os.path.join(preview_dir, base_name + extension)
            rewritten_url, rewritten = rewrite_preview_url(preview_url, media_type="video")

            attempt_urls = []
            if rewritten:
                attempt_urls.append(rewritten_url)
            attempt_urls.append(preview_url)

            seen: set[str] = set()
            for candidate in attempt_urls:
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)

                success, _ = await downloader.download_file(candidate, preview_path, use_auth=False)
                if success:
                    local_metadata["preview_url"] = preview_path.replace(os.sep, "/")
                    local_metadata["preview_nsfw_level"] = nsfw_level
                    return
        else:
            rewritten_url, rewritten = rewrite_preview_url(preview_url, media_type="image")
            if rewritten:
                extension = extension_from_url(preview_url, ".png")
                preview_path = os.path.join(preview_dir, base_name + extension)
                success, _ = await downloader.download_file(
                    rewritten_url, preview_path, use_auth=False
                )
                if success:
                    local_metadata["preview_url"] = preview_path.replace(os.sep, "/")
                    local_metadata["preview_nsfw_level"] = nsfw_level
                    return

            extension = ".webp"
            preview_path = os.path.join(preview_dir, base_name + extension)
            success, content, _headers = await downloader.download_to_memory(
                preview_url, use_auth=False
            )
            if not success:
                return

            try:
                optimized_data, _ = self._exif_utils.optimize_image(
                    image_data=content,
                    target_width=CARD_PREVIEW_WIDTH,
                    format="webp",
                    quality=85,
                    preserve_metadata=False,
                )
                with open(preview_path, "wb") as handle:
                    handle.write(optimized_data)
            except Exception as exc:  # pragma: no cover - defensive path
                logger.error("Error optimizing preview image: %s", exc)
                try:
                    with open(preview_path, "wb") as handle:
                        handle.write(content)
                except Exception as save_exc:
                    logger.error("Error saving preview image: %s", save_exc)
                    return

            local_metadata["preview_url"] = preview_path.replace(os.sep, "/")
            local_metadata["preview_nsfw_level"] = nsfw_level

    async def replace_preview(
        self,
        *,
        model_path: str,
        preview_data: bytes,
        content_type: str,
        original_filename: Optional[str],
        nsfw_level: int,
        update_preview_in_cache: Callable[[str, str, int], Awaitable[bool]],
        metadata_loader: Callable[[str], Awaitable[Dict[str, object]]],
    ) -> Dict[str, object]:
        """Replace an existing preview asset for a model."""

        base_name = os.path.splitext(os.path.basename(model_path))[0]
        folder = os.path.dirname(model_path)

        extension, optimized_data = await self._convert_preview(
            preview_data, content_type, original_filename
        )

        for ext in PREVIEW_EXTENSIONS:
            existing_preview = os.path.join(folder, base_name + ext)
            if os.path.exists(existing_preview):
                try:
                    os.remove(existing_preview)
                except Exception as exc:  # pragma: no cover - defensive path
                    logger.warning(
                        "Failed to delete existing preview %s: %s", existing_preview, exc
                    )

        preview_path = os.path.join(folder, base_name + extension).replace(os.sep, "/")
        with open(preview_path, "wb") as handle:
            handle.write(optimized_data)

        metadata_path = os.path.splitext(model_path)[0] + ".metadata.json"
        metadata = await metadata_loader(metadata_path)
        metadata["preview_url"] = preview_path
        metadata["preview_nsfw_level"] = nsfw_level
        await self._metadata_manager.save_metadata(model_path, metadata)

        await update_preview_in_cache(model_path, preview_path, nsfw_level)

        return {"preview_path": preview_path, "preview_nsfw_level": nsfw_level}

    async def _convert_preview(
        self, data: bytes, content_type: str, original_filename: Optional[str]
    ) -> tuple[str, bytes]:
        """Convert preview bytes to the persisted representation."""

        if content_type.startswith("video/"):
            extension = self._resolve_video_extension(content_type, original_filename)
            return extension, data

        original_ext = (original_filename or "").lower()
        if original_ext.endswith(".gif") or content_type.lower() == "image/gif":
            return ".gif", data

        optimized_data, _ = self._exif_utils.optimize_image(
            image_data=data,
            target_width=CARD_PREVIEW_WIDTH,
            format="webp",
            quality=85,
            preserve_metadata=False,
        )
        return ".webp", optimized_data

    def _resolve_video_extension(self, content_type: str, original_filename: Optional[str]) -> str:
        """Infer the best extension for a video preview."""

        if original_filename:
            extension = os.path.splitext(original_filename)[1].lower()
            if extension in {".mp4", ".webm", ".mov", ".avi"}:
                return extension

        if "webm" in content_type:
            return ".webm"
        return ".mp4"

