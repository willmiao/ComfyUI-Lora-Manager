import asyncio
import base64
import logging
import os
import posixpath
import re
import random
import string
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from aiohttp import web
from ..utils.constants import SUPPORTED_MEDIA_EXTENSIONS
from ..services.connectivity_guard import (
    OFFLINE_COOLDOWN_ERROR,
    OFFLINE_FRIENDLY_MESSAGE,
)
from ..services.service_registry import ServiceRegistry
from ..services.settings_manager import get_settings_manager
from ..utils.civitai_utils import build_civitai_media_url
from ..utils.example_images_paths import get_model_folder, get_model_relative_path
from .example_images_metadata import MetadataUpdater, update_cache_from_metadata
from .file_utils import detect_media_extension
from ..utils.metadata_manager import MetadataManager

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_ATTEMPTS = 3
# The shared aiohttp session allows a 300s socket read for large model files.
# Gallery images are small; a CDN that accepts the connection and then stalls
# must not park one model (and the serial run behind it) for five minutes.
# Videos are larger and keep a longer bound.
MEDIA_IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 25.0
MEDIA_VIDEO_DOWNLOAD_TIMEOUT_SECONDS = 180.0

_GENUR_HOSTS = frozenset({"img.genur.art", "c.genur.art"})
_TRANSIENT_ERROR_MARKERS = (
    "network offline",
    "offline_cooldown",
    "cannot connect to host",
    "server disconnected",
    "connection reset",
    "connection refused",
    "temporary failure",
    "name or service not known",
    "timed out",
    "timeout",
)


def _write_media_file(path: str, content: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(content)


def is_genur_media_url(url: str) -> bool:
    """Return True for Genur image URLs handled by the fallback resolver."""

    try:
        hostname = urlparse(url or "").hostname
    except ValueError:
        return False
    return bool(hostname) and hostname.lower() in _GENUR_HOSTS


def resolve_genur_media_url(
    url: str,
    media_type: str | None = None,
    *,
    size: str = "small",
) -> str:
    """Map Genur image URLs to a direct rendition that is currently reachable.

    Genur's signed proxy (``img.genur.art/sig/.../<base64>``) embeds the direct
    asset URL in the last path segment.  The proxy host is not reachable from
    every network (fake-IP DNS / TLS resets), while the direct host serves the
    same image as ``<uuid>_small.webp`` and ``<uuid>_large.webp``.  Returning
    the direct rendition avoids a guaranteed failed request and the
    ConnectivityGuard cooldown that follows it.

    Non-Genur URLs, videos, and already-suffixed renditions are returned
    unchanged.
    """

    if not url or (media_type or "").lower() == "video":
        return url

    try:
        parsed = urlparse(url)
    except ValueError:
        return url

    hostname = (parsed.hostname or "").lower()
    if hostname == "img.genur.art":
        payload = parsed.path.rsplit("/", 1)[-1]
        try:
            padded = payload + "=" * (-len(payload) % 4)
            decoded = base64.b64decode(padded).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return url
        try:
            decoded_parsed = urlparse(decoded)
        except ValueError:
            return url
        if (decoded_parsed.hostname or "").lower() != "c.genur.art":
            return url
        base = f"https://c.genur.art{decoded_parsed.path}"
    elif hostname == "c.genur.art":
        base = f"https://c.genur.art{parsed.path}"
    else:
        return url

    base = base.rstrip("/")
    if base.endswith(("_small.webp", "_large.webp")):
        return base
    if posixpath.splitext(base)[1].lower() in SUPPORTED_MEDIA_EXTENSIONS["images"]:
        # Already a direct image path; do not invent a suffix.
        return base
    suffix = "_large.webp" if size == "large" else "_small.webp"
    return f"{base}{suffix}"


@dataclass
class ImageDownloadOutcome:
    """Result of one model's example-media download pass.

    ``downloaded`` and ``recovered`` contain the *original* metadata URLs so
    callers can match them against ``civitai.images``.  ``success`` is false
    when anything is still missing: a permanent failure, a rate-limit retry,
    a transient network failure, or a previously flagged image that this pass
    did not retry.
    """

    downloaded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    rate_limited: list[str] = field(default_factory=list)
    transient: list[str] = field(default_factory=list)
    recovered: list[str] = field(default_factory=list)
    skipped_failed: int = 0
    is_stale: bool = False

    @property
    def success(self) -> bool:
        return not (
            self.failed
            or self.rate_limited
            or self.transient
            or self.skipped_failed
        )


class MediaDownloadLimiter:
    """Bound concurrent media requests and share 429 cooldowns across workers.

    Civitai serves one binary per request and each request costs a CDN
    round-trip, so serial downloads spend most of their wall clock waiting.
    Concurrency is the useful lever, but it has to stay below the CDN's
    threshold: a 429 is a signal for the whole destination, not for the one
    task that happened to receive it.  A cooldown armed here therefore parks
    every worker, and the limit is halved on a 429 and grows back one slot at
    a time after a run of successes (AIMD) instead of oscillating around the
    limit.

    All waits are bounded by ``max_cooldown``.  The per-request retry budget
    lives in the caller; this class only decides when a request may start.
    """

    def __init__(
        self,
        max_concurrency: int = 6,
        *,
        min_cooldown: float = 1.0,
        default_cooldown: float = 30.0,
        max_cooldown: float = 300.0,
        recovery_successes: int | None = None,
    ) -> None:
        self.max_concurrency = max(1, int(max_concurrency))
        self._limit = self.max_concurrency
        self._in_flight = 0
        self._cooldown_until = 0.0
        self._min_cooldown = max(0.0, float(min_cooldown))
        self._default_cooldown = max(self._min_cooldown, float(default_cooldown))
        self._max_cooldown = max(self._default_cooldown, float(max_cooldown))
        self._recovery_successes = max(
            1, int(recovery_successes or max(8, self.max_concurrency * 2))
        )
        self._successes = 0
        self._condition = asyncio.Condition()

    @property
    def limit(self) -> int:
        """Current concurrency limit (may be below ``max_concurrency``)."""

        return self._limit

    async def acquire(self) -> None:
        """Wait for the shared cooldown and a concurrency slot."""

        async with self._condition:
            while True:
                remaining = self._cooldown_until - time.monotonic()
                if remaining > 0:
                    try:
                        await asyncio.wait_for(
                            self._condition.wait(), timeout=remaining
                        )
                    except asyncio.TimeoutError:
                        pass
                    continue
                if self._in_flight < self._limit:
                    self._in_flight += 1
                    return
                await self._condition.wait()

    async def release(self) -> None:
        async with self._condition:
            self._in_flight = max(0, self._in_flight - 1)
            self._condition.notify()

    async def report_rate_limit(self, retry_after: float | None = None) -> float:
        """Arm the shared cooldown and shrink the concurrency limit.

        Returns the cooldown actually applied, after clamping.
        """

        async with self._condition:
            requested = (
                retry_after
                if retry_after is not None and retry_after > 0
                else self._default_cooldown
            )
            cooldown = min(
                max(self._min_cooldown, float(requested)), self._max_cooldown
            )
            self._cooldown_until = max(
                self._cooldown_until, time.monotonic() + cooldown
            )
            self._limit = max(1, self._limit // 2)
            self._successes = 0
            self._condition.notify_all()
            return cooldown

    async def report_success(self) -> None:
        """Slowly restore concurrency after a run of successful requests."""

        async with self._condition:
            if self._limit >= self.max_concurrency:
                return
            self._successes += 1
            if self._successes >= self._recovery_successes:
                self._limit += 1
                self._successes = 0
                self._condition.notify()

    def reset(self) -> None:
        """Test seam: restore the initial state."""

        self._limit = self.max_concurrency
        self._in_flight = 0
        self._cooldown_until = 0.0
        self._successes = 0



class ExampleImagesImportError(RuntimeError):
    """Base error for example image import operations."""


class ExampleImagesValidationError(ExampleImagesImportError):
    """Raised when input validation fails."""

class ExampleImagesProcessor:
    """Processes and manipulates example images"""

    @staticmethod
    async def _model_scanners() -> list:
        """Return every scanner whose models can carry example images."""
        return [
            await ServiceRegistry.get_lora_scanner(),
            await ServiceRegistry.get_checkpoint_scanner(),
            await ServiceRegistry.get_embedding_scanner(),
            await ServiceRegistry.get_other_scanner(),
        ]

    @staticmethod
    async def resolve_hash_for_file_path(file_path: str) -> str:
        """Return the SHA256 for a cached model file, computing it on demand.

        Checkpoint and Other scanners record ``hash_status="pending"`` with an
        empty sha256 until something needs the hash; importing example images
        is such a moment because example folders are keyed by hash.  Returns
        ``''`` when the file is unknown to every scanner or hashing failed.
        """
        if not file_path:
            return ''
        normalized = file_path.replace(os.sep, '/')
        for scanner in await ExampleImagesProcessor._model_scanners():
            cache = await scanner.get_cached_data()
            for item in cache.raw_data:
                if item.get('file_path') != normalized:
                    continue
                sha256 = (item.get('sha256') or '').strip()
                if sha256 and item.get('hash_status', 'completed') == 'completed':
                    return sha256
                calculate = getattr(scanner, 'calculate_hash_for_model', None)
                if calculate is None:
                    return sha256
                return (await calculate(normalized)) or ''
        return ''

    @staticmethod
    def generate_short_id(length=8):
        """Generate a short random alphanumeric identifier"""
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(length))
    
    @staticmethod
    def _is_video_media(media_url: str, media_type_hint: str | None = None) -> bool:
        if (media_type_hint or "").lower() == "video":
            return True
        path = urlparse(media_url or "").path
        extension = posixpath.splitext(path)[1].lower()
        return extension in SUPPORTED_MEDIA_EXTENSIONS["videos"]

    @staticmethod
    def _media_width(media_type: str | None) -> int:
        """Return the configured rendition width for example media."""

        is_video = (media_type or "").lower() == "video"
        key = "example_images_video_max_width" if is_video else "example_images_max_width"
        default = 450 if is_video else 800
        try:
            width = int(get_settings_manager().get(key, default))
        except (TypeError, ValueError):
            return default
        # The image cacher's ladder starts at 96px; a smaller value is a
        # configuration mistake and would request an unusable thumbnail.
        return width if width >= 96 else default

    @staticmethod
    def build_example_media_url(
        media_url: str,
        media_type_hint: str | None,
        optimize: bool,
    ) -> str:
        """Return the URL to download for an example image or video.

        Civitai URLs are rewritten to a resized rendition (images default to
        800px, videos to 450px; both adjustable in settings).  Genur signed
        proxy URLs are mapped to the direct ``c.genur.art`` rendition, which
        the broken proxy host never reaches.  Other URLs are returned as-is.
        """

        media_url = (media_url or "").strip()
        if not media_url:
            return media_url

        media_type = (
            "video"
            if ExampleImagesProcessor._is_video_media(media_url, media_type_hint)
            else "image"
        )

        if is_genur_media_url(media_url):
            return resolve_genur_media_url(
                media_url, media_type, size="small" if optimize else "large"
            )

        if not optimize:
            return media_url

        width = ExampleImagesProcessor._media_width(media_type)
        return build_civitai_media_url(
            media_url, media_type, width=width, optimize=True
        ) or media_url
    
    @staticmethod
    def _get_file_extension_from_content_or_headers(content, headers, fallback_url=None, media_type_hint=None):
        """Determine file extension from content magic bytes or headers"""
        return detect_media_extension(
            content, headers, fallback_url=fallback_url, media_type_hint=media_type_hint
        )

    @staticmethod
    def _is_not_found_error(error) -> bool:
        """Return True when the downloader response represents a 404/Not Found."""

        if not error:
            return False

        message = str(error).lower()
        return '404' in message or 'file not found' in message

    @staticmethod
    def _example_image_file_exists(model_dir: str, index: int, media_type_hint: str | None = None) -> bool:
        """Return True when the file that would be written for a media index already exists.

        The final filename (``image_{index}{extension}``) depends on the downloaded
        content, so the extension cannot be known ahead of time. The post-download
        check skips the write when the exact target file exists; this pre-check
        approximates that with the candidate extensions for the media type (videos
        only when the metadata hints at a video) so the network request is avoided
        for files that already exist on disk.
        """
        if media_type_hint == "video":
            extensions = SUPPORTED_MEDIA_EXTENSIONS['videos']
        else:
            extensions = SUPPORTED_MEDIA_EXTENSIONS['images']
        return any(
            os.path.exists(os.path.join(model_dir, f"image_{index}{ext}"))
            for ext in extensions
        )

    @staticmethod
    async def download_model_images(model_hash, model_name, model_images, model_dir, optimize, downloader):
        """Download example media for a single model.

        Returns:
            tuple: (success, is_stale_metadata) - whether download was successful,
                whether metadata is stale.
        """

        outcome = await ExampleImagesProcessor.download_model_images_with_tracking(
            model_hash,
            model_name,
            model_images,
            model_dir,
            optimize,
            downloader,
        )
        return outcome.success, outcome.is_stale

    @staticmethod
    def _extract_retry_after(error_message: str) -> float:
        if not error_message:
            return 30.0
        match = re.search(r"retry after ([\d.]+)s", str(error_message))
        if match:
            return max(0.0, float(match.group(1)))
        return 30.0

    @staticmethod
    def _is_transient_failure(message: str) -> bool:
        """Return True for transport/offline/5xx errors that deserve a retry.

        A 404 is a statement about the asset and is handled separately; an
        offline/shared-cooldown message describes the network path, so
        blacklisting the image for it (the old behavior) is wrong.
        """

        if not message:
            return True
        text = str(message).strip()
        if not text:
            # aiohttp connection errors often stringify to an empty message;
            # an unexplained failure is not a statement that the asset is gone.
            return True
        if text in {OFFLINE_FRIENDLY_MESSAGE, OFFLINE_COOLDOWN_ERROR}:
            return True
        lower = text.lower()
        if any(marker in lower for marker in _TRANSIENT_ERROR_MARKERS):
            return True
        match = re.search(r"status (\d{3})", text, re.IGNORECASE)
        if match:
            status = int(match.group(1))
            return status in {408, 425, 429} or 500 <= status < 600
        return False

    @staticmethod
    async def download_model_images_with_tracking(
        model_hash,
        model_name,
        model_images,
        model_dir,
        optimize,
        downloader,
        limiter: MediaDownloadLimiter | None = None,
        retry_failed: bool = False,
    ) -> ImageDownloadOutcome:
        """Download all pending media for one model concurrently.

        Each image is still one CDN request (Civitai has no batch-binary
        endpoint), but the requests are pipelined through ``limiter`` instead
        of being serialized.  A 429 arms the limiter's shared cooldown, so one
        rate-limited response pauses every worker rather than letting each
        URL sleep and retry on its own.

        ``retry_failed`` re-attempts image-level ``downloadFailed`` entries
        for Genur URLs.  Genur images are the ones affected by the old
        network-error classification bug; retrying them lets the caller clear
        the flag only after a real download succeeds.

        Returns:
            ImageDownloadOutcome: per-URL lists and a ``success`` property.
                URL lists contain the *original* metadata URLs so callers can
                match them against the model's ``civitai.images`` entries.
        """

        limiter = limiter or MediaDownloadLimiter()
        outcome = ImageDownloadOutcome()
        candidates: list[tuple[int, dict[str, Any], str, bool]] = []

        for index, image in enumerate(model_images):
            original_url = image.get("url")
            if not original_url:
                continue

            # A file already on disk is authoritative; a stale failure flag
            # must not force a redundant request.
            if ExampleImagesProcessor._example_image_file_exists(
                model_dir, index, image.get("type")
            ):
                logger.debug("File already exists, skipping download for %s", original_url)
                if (
                    image.get("downloadFailed")
                    and retry_failed
                    and is_genur_media_url(original_url)
                ):
                    outcome.recovered.append(original_url)
                continue

            if image.get("downloadFailed"):
                if retry_failed and is_genur_media_url(original_url):
                    logger.debug(
                        "Retrying previously failed Genur image %s for %s",
                        original_url,
                        model_name,
                    )
                    candidates.append((index, image, original_url, True))
                    continue
                outcome.skipped_failed += 1
                logger.debug(
                    "Skipping example image %s for %s because it previously failed to download",
                    original_url,
                    model_name,
                )
                continue

            candidates.append((index, image, original_url, False))

        async def download_one(
            index: int,
            image: dict[str, Any],
            original_url: str,
            was_flagged: bool,
        ) -> None:
            target_url = ExampleImagesProcessor.build_example_media_url(
                original_url, image.get("type"), optimize
            )
            logger.debug(
                "Downloading media file %s for %s from %s",
                index,
                model_name,
                target_url,
            )

            for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
                timeout = (
                    MEDIA_VIDEO_DOWNLOAD_TIMEOUT_SECONDS
                    if ExampleImagesProcessor._is_video_media(
                        original_url, image.get("type")
                    )
                    else MEDIA_IMAGE_DOWNLOAD_TIMEOUT_SECONDS
                )
                await limiter.acquire()
                try:
                    success, content, headers = await asyncio.wait_for(
                        downloader.download_to_memory(
                            target_url,
                            use_auth=False,
                            return_headers=True,
                        ),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Timed out downloading %s after %.0fs; will retry next run",
                        target_url,
                        timeout,
                    )
                    outcome.transient.append(original_url)
                    return
                except Exception as e:
                    logger.error("Error downloading file %s: %s", target_url, e)
                    # An exception is a transport/runtime failure, not a 404:
                    # leave the image retryable instead of blacklisting it.
                    outcome.transient.append(original_url)
                    return
                finally:
                    await limiter.release()

                if success:
                    await limiter.report_success()

                    media_ext = ExampleImagesProcessor._get_file_extension_from_content_or_headers(
                        content, headers, original_url, image.get("type")
                    )
                    is_image = media_ext in SUPPORTED_MEDIA_EXTENSIONS["images"]
                    is_video = media_ext in SUPPORTED_MEDIA_EXTENSIONS["videos"]

                    if not (is_image or is_video):
                        logger.debug("Skipping unsupported file type: %s", media_ext)
                        return

                    save_path = os.path.join(model_dir, f"image_{index}{media_ext}")
                    if os.path.exists(save_path):
                        logger.debug("File already exists: %s", save_path)
                        return

                    try:
                        await asyncio.to_thread(_write_media_file, save_path, content)
                    except Exception as e:
                        logger.error("Failed to save example image %s: %s", save_path, e)
                        outcome.transient.append(original_url)
                        return

                    outcome.downloaded.append(original_url)
                    if was_flagged:
                        outcome.recovered.append(original_url)
                    return

                message = str(content)
                if ExampleImagesProcessor._is_not_found_error(message):
                    logger.warning(
                        "Failed to download file: %s, status code: 404 - Model metadata might be stale",
                        target_url,
                    )
                    outcome.failed.append(original_url)
                    outcome.is_stale = True
                    return

                if "Rate limited (429)" in message:
                    retry_after = ExampleImagesProcessor._extract_retry_after(message)
                    cooldown = await limiter.report_rate_limit(retry_after)
                    logger.warning(
                        "Rate limited (429) for %s, shared cooldown %.1fs (attempt %d/%d)",
                        target_url,
                        cooldown,
                        attempt,
                        MAX_DOWNLOAD_ATTEMPTS,
                    )
                    if attempt >= MAX_DOWNLOAD_ATTEMPTS:
                        outcome.rate_limited.append(original_url)
                        return
                    # Loop back into acquire(): it parks until the shared
                    # cooldown expires, so the retry is not a herd.
                    continue

                if ExampleImagesProcessor._is_transient_failure(message):
                    logger.warning(
                        "Transient failure for %s: %s (will retry next run)",
                        target_url,
                        content,
                    )
                    outcome.transient.append(original_url)
                    return

                logger.warning("Failed to download file: %s, error: %s", target_url, content)
                outcome.failed.append(original_url)
                return

        if candidates:
            await asyncio.gather(
                *(
                    download_one(index, image, url, was_flagged)
                    for index, image, url, was_flagged in candidates
                )
            )

        return outcome

    @staticmethod
    async def process_local_examples(model_file_path, model_file_name, model_name, model_dir, optimize):
        """Process local example images
        
        Returns:
            bool: True if local images were processed successfully, False otherwise
        """
        try:
            if not model_file_path or not os.path.exists(os.path.dirname(model_file_path)):
                return False
                
            model_dir_path = os.path.dirname(model_file_path)
            local_images = []
            
            # Look for files with pattern: filename.example.*.ext
            if model_file_name:
                example_prefix = f"{model_file_name}.example."
                
                if os.path.exists(model_dir_path):
                    for file in os.listdir(model_dir_path):
                        file_lower = file.lower()
                        if file_lower.startswith(example_prefix.lower()):
                            file_ext = os.path.splitext(file_lower)[1]
                            is_supported = (file_ext in SUPPORTED_MEDIA_EXTENSIONS['images'] or 
                                           file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos'])
                            
                            if is_supported:
                                local_images.append(os.path.join(model_dir_path, file))
            
            # Process local images if found
            if local_images:
                logger.info(f"Found {len(local_images)} local example images for {model_name}")
                
                for local_image_path in local_images:
                    # Extract index from filename
                    file_name = os.path.basename(local_image_path)
                    example_prefix = f"{model_file_name}.example."
                    
                    try:
                        # Extract the part between '.example.' and the file extension
                        index_part = file_name[len(example_prefix):].split('.')[0]
                        # Try to parse it as an integer
                        index = int(index_part)
                        local_ext = os.path.splitext(local_image_path)[1].lower()
                        save_filename = f"image_{index}{local_ext}"
                    except (ValueError, IndexError):
                        # If we can't parse the index, fall back to sequential numbering
                        logger.warning(f"Could not extract index from {file_name}, using sequential numbering")
                        local_ext = os.path.splitext(local_image_path)[1].lower()
                        save_filename = f"image_{len(local_images)}{local_ext}"
                    
                    save_path = os.path.join(model_dir, save_filename)
                    
                    # Skip if already exists in output directory
                    if os.path.exists(save_path):
                        logger.debug(f"File already exists in output: {save_path}")
                        continue
                    
                    # Copy the file
                    with open(local_image_path, 'rb') as src_file:
                        with open(save_path, 'wb') as dst_file:
                            dst_file.write(src_file.read())
                
                return True
            return False
        except Exception as e:
            logger.error(f"Error processing local examples for {model_name}: {str(e)}")
            return False
            
    @staticmethod
    async def import_images(model_hash: str, files_to_import: list[str]):
        """Import local example images for a model."""

        if not model_hash:
            raise ExampleImagesValidationError('Missing model_hash parameter')

        if not files_to_import:
            raise ExampleImagesValidationError('No files provided to import')

        try:
            # Get example images path
            example_images_path = get_settings_manager().get('example_images_path')
            if not example_images_path:
                raise ExampleImagesValidationError('No example images path configured')

            # Find the model and get current metadata
            model_data = None
            scanner = None

            # Check every scanner to find the model
            for scan_obj in await ExampleImagesProcessor._model_scanners():
                cache = await scan_obj.get_cached_data()
                for item in cache.raw_data:
                    if item.get('sha256') == model_hash:
                        model_data = item
                        scanner = scan_obj
                        break
                if model_data:
                    break

            if not model_data:
                raise ExampleImagesImportError(
                    f"Model with hash {model_hash} not found in cache"
                )

            # Create model folder
            model_folder = get_model_folder(model_hash)
            if not model_folder:
                raise ExampleImagesImportError('Failed to resolve model folder for example images')
            os.makedirs(model_folder, exist_ok=True)

            imported_files = []
            errors = []
            newly_imported_paths = []

            # Process each file path
            for file_path in files_to_import:
                try:
                    # Ensure the file exists
                    if not os.path.isfile(file_path):
                        errors.append(f"File not found: {file_path}")
                        continue

                    # Check if file type is supported
                    file_ext = os.path.splitext(file_path)[1].lower()
                    if not (file_ext in SUPPORTED_MEDIA_EXTENSIONS['images'] or
                            file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos']):
                        errors.append(f"Unsupported file type: {file_path}")
                        continue

                    # Generate new filename using short ID instead of UUID
                    short_id = ExampleImagesProcessor.generate_short_id()
                    new_filename = f"custom_{short_id}{file_ext}"

                    dest_path = os.path.join(model_folder, new_filename)

                    # Copy the file
                    import shutil
                    shutil.copy2(file_path, dest_path)
                    # Store both the dest_path and the short_id
                    newly_imported_paths.append((dest_path, short_id))

                    # Add to imported files list
                    imported_files.append({
                        'name': new_filename,
                        'path': f'/example_images_static/{get_model_relative_path(model_hash)}/{new_filename}',
                        'extension': file_ext,
                        'is_video': file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos']
                    })
                except Exception as e:
                    errors.append(f"Error importing {file_path}: {str(e)}")

            # Update metadata with new example images
            regular_images, custom_images = await MetadataUpdater.update_metadata_after_import(
                model_hash,
                model_data,
                scanner,
                newly_imported_paths
            )

            return {
                'success': len(imported_files) > 0,
                'message': f'Successfully imported {len(imported_files)} files' +
                        (f' with {len(errors)} errors' if errors else ''),
                'files': imported_files,
                'errors': errors,
                'regular_images': regular_images,
                'custom_images': custom_images,
                'model_hash': model_hash,
                "model_file_path": model_data.get('file_path', ''),
            }

        except ExampleImagesImportError:
            raise
        except Exception as e:
            logger.error(f"Failed to import example images: {e}", exc_info=True)
            raise ExampleImagesImportError(str(e)) from e

    @staticmethod
    async def delete_custom_image(request):
        """
        Delete a custom example image for a model
        
        Accepts:
        - JSON request with model_hash and short_id
        
        Returns:
        - Success status and updated image lists
        """
        try:
            # Parse request data
            data = await request.json()
            model_hash = data.get('model_hash')
            short_id = data.get('short_id')
            
            if not model_hash or not short_id:
                return web.json_response({
                    'success': False,
                    'error': 'Missing required parameters: model_hash and short_id'
                }, status=400)
            
            # Get example images path
            example_images_path = get_settings_manager().get('example_images_path')
            if not example_images_path:
                return web.json_response({
                    'success': False,
                    'error': 'No example images path configured'
                }, status=400)
            
            # Find the model and get current metadata
            model_data = None
            scanner = None

            # Check every scanner to find the model
            for scan_obj in await ExampleImagesProcessor._model_scanners():
                if scan_obj.has_hash(model_hash):
                    cache = await scan_obj.get_cached_data()
                    for item in cache.raw_data:
                        if item.get('sha256') == model_hash:
                            model_data = item
                            scanner = scan_obj
                            break
                if model_data:
                    break

            if not model_data:
                return web.json_response({
                    'success': False,
                    'error': f"Model with hash {model_hash} not found in cache"
                }, status=404)

            await MetadataManager.hydrate_model_data(model_data)
            civitai_data = model_data.setdefault('civitai', {})
            custom_images = civitai_data.get('customImages')

            if not isinstance(custom_images, list) or not custom_images:
                return web.json_response({
                    'success': False,
                    'error': f"Model has no custom images"
                }, status=404)
            
            # Find the custom image with matching short_id
            matching_image = None
            new_custom_images = []
            
            for image in custom_images:
                if image.get('id') == short_id:
                    matching_image = image
                else:
                    new_custom_images.append(image)
            
            if not matching_image:
                return web.json_response({
                    'success': False,
                    'error': f"Custom image with id {short_id} not found"
                }, status=404)
            
            # Find and delete the actual file
            model_folder = get_model_folder(model_hash)
            if not model_folder:
                return web.json_response({
                    'success': False,
                    'error': 'Failed to resolve model folder for example images'
                }, status=500)
            file_deleted = False
            
            if os.path.exists(model_folder):
                for filename in os.listdir(model_folder):
                    if f"custom_{short_id}" in filename:
                        file_path = os.path.join(model_folder, filename)
                        try:
                            os.remove(file_path)
                            file_deleted = True
                            logger.info(f"Deleted custom example file: {file_path}")
                            break
                        except Exception as e:
                            return web.json_response({
                                'success': False,
                                'error': f"Failed to delete file: {str(e)}"
                            }, status=500)
            
            if not file_deleted:
                logger.warning(f"File for custom example with id {short_id} not found, but metadata will still be updated")
            
            # Update metadata
            civitai_data['customImages'] = new_custom_images
            model_data.setdefault('civitai', {})['customImages'] = new_custom_images
            
            # Save updated metadata to file
            file_path = model_data.get('file_path')
            if file_path:
                try:
                    model_copy = model_data.copy()
                    model_copy.pop('folder', None)
                    await MetadataManager.save_metadata(file_path, model_copy)
                    logger.debug(f"Saved updated metadata for {model_data.get('model_name')}")
                except Exception as e:
                    logger.error(f"Failed to save metadata: {str(e)}")
                    return web.json_response({
                        'success': False,
                        'error': f"Failed to save metadata: {str(e)}"
                    }, status=500)
            
                # Update cache
                await update_cache_from_metadata(scanner, file_path, model_data)
            
            # Get regular images array (might be None)
            regular_images = civitai_data.get('images', [])
            
            return web.json_response({
                'success': True,
                'regular_images': regular_images,
                'custom_images': new_custom_images,
                'model_file_path': model_data.get('file_path', '')
            })
                
        except Exception as e:
            logger.error(f"Failed to delete custom example image: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    @staticmethod
    async def set_example_image_nsfw_level(request: web.Request) -> web.StreamResponse:
        """
        Update the NSFW level for a single example image (regular or custom).
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'success': False, 'error': 'Invalid JSON body'}, status=400)

        model_hash = data.get('model_hash')
        raw_level = data.get('nsfw_level')
        source = (data.get('source') or 'civitai').lower()
        index = data.get('index')
        image_id = data.get('id')

        if model_hash is None or raw_level is None:
            return web.json_response(
                {'success': False, 'error': 'Missing required parameters: model_hash and nsfw_level'},
                status=400,
            )

        try:
            nsfw_level = int(raw_level)
        except (TypeError, ValueError):
            return web.json_response(
                {'success': False, 'error': 'nsfw_level must be an integer'}, status=400
            )

        if source == 'custom':
            if not image_id:
                return web.json_response(
                    {'success': False, 'error': 'Custom images require an id field'}, status=400
                )
        else:
            try:
                index = int(index)
            except (TypeError, ValueError):
                return web.json_response(
                    {'success': False, 'error': 'Regular images require a numeric index'}, status=400
                )

        try:
            model_data = None
            scanner = None

            for scan_obj in await ExampleImagesProcessor._model_scanners():
                if scan_obj.has_hash(model_hash):
                    cache = await scan_obj.get_cached_data()
                    for item in cache.raw_data:
                        if item.get('sha256') == model_hash:
                            model_data = item
                            scanner = scan_obj
                            break
                if model_data:
                    break

            if not model_data:
                return web.json_response(
                    {'success': False, 'error': f"Model with hash {model_hash} not found in cache"},
                    status=404,
                )

            await MetadataManager.hydrate_model_data(model_data)
            civitai_data = model_data.setdefault('civitai', {})
            regular_images = civitai_data.get('images') or []
            custom_images = civitai_data.get('customImages') or []

            target_image = None
            if source == 'custom':
                for image in custom_images:
                    if image.get('id') == image_id:
                        target_image = image
                        break
            else:
                if 0 <= index < len(regular_images):
                    target_image = regular_images[index]

            if target_image is None:
                return web.json_response(
                    {'success': False, 'error': 'Target image not found'}, status=404
                )

            target_image['nsfwLevel'] = nsfw_level
            civitai_data['images'] = regular_images
            civitai_data['customImages'] = custom_images

            file_path = model_data.get('file_path')
            if file_path:
                model_copy = model_data.copy()
                model_copy.pop('folder', None)
                await MetadataManager.save_metadata(file_path, model_copy)
                await update_cache_from_metadata(scanner, file_path, model_copy)

            return web.json_response({
                'success': True,
                'regular_images': regular_images,
                'custom_images': custom_images,
                'model_file_path': model_data.get('file_path', ''),
                'nsfw_level': nsfw_level
            })
        except Exception as exc:
            logger.error("Failed to update example image NSFW level: %s", exc, exc_info=True)
            return web.json_response({'success': False, 'error': str(exc)}, status=500)


    
