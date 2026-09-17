import inspect
import logging
import os
import re
from typing import TYPE_CHECKING, Any, Dict, Mapping, MutableMapping, Optional

from ..recipes.constants import GEN_PARAM_KEYS
from ..services.metadata_service import get_default_metadata_provider, get_metadata_provider
from ..services.metadata_sync_service import MetadataSyncService
from ..services.preview_asset_service import PreviewAssetService
from ..services.settings_manager import get_settings_manager
from ..services.downloader import get_downloader
from ..utils.constants import SUPPORTED_MEDIA_EXTENSIONS
from ..utils.exif_utils import ExifUtils
from ..utils.metadata_manager import MetadataManager
from ..utils.video_metadata import get_video_dimensions

logger = logging.getLogger(__name__)

# Placeholder dimensions written when the real ones cannot be determined.
# Kept for backwards compatibility with pre-existing metadata entries.
_DEFAULT_MEDIA_WIDTH = 720
_DEFAULT_MEDIA_HEIGHT = 1280

# Example metadata entries carry a marker: ``customImages`` use their ``id``
# while ``images`` use the positional index. Either way the marker must be a
# plain filename-safe token, never a path fragment.
_ENTRY_MARKER_PATTERN = re.compile(r"^(?:custom_|image_)?([^./\\]+)$")

_preview_service = PreviewAssetService(
    metadata_manager=MetadataManager,
    downloader_factory=get_downloader,
    exif_utils=ExifUtils,
)

_metadata_sync_service: MetadataSyncService | None = None
_metadata_sync_service_settings: Optional["SettingsManager"] = None

if TYPE_CHECKING:  # pragma: no cover - import for type checkers only
    from ..services.settings_manager import SettingsManager


async def update_cache_from_metadata(
    scanner: Any, file_path: str, metadata: Dict[str, Any]
) -> bool:
    """Update the scanner cache from a metadata dict using the in-place sync path.

    ``sync_cache_from_metadata`` patches the existing cache entry incrementally
    (tag/hash/version indexes, targeted single-row SQL update) and only resorts
    when a sort-key field changed. This avoids the ``O(n)`` full-list resort and
    full cache rewrite that ``update_single_model_cache`` performs on every call,
    which is critical for libraries with 100k+ models.

    Falls back to the legacy full update when the scanner does not expose an
    async ``sync_cache_from_metadata`` method.

    Returns:
        ``True`` if the cache entry was updated, ``False`` otherwise.
    """

    sync_method = getattr(scanner, "sync_cache_from_metadata", None)
    if inspect.iscoroutinefunction(sync_method):
        return await sync_method(file_path, metadata)

    return await scanner.update_single_model_cache(file_path, file_path, metadata)


def _build_metadata_sync_service(settings_manager: "SettingsManager") -> MetadataSyncService:
    """Construct a metadata sync service bound to the provided settings."""

    return MetadataSyncService(
        metadata_manager=MetadataManager,
        preview_service=_preview_service,
        settings=settings_manager,
        default_metadata_provider_factory=get_default_metadata_provider,
        metadata_provider_selector=get_metadata_provider,
    )


def _read_media_dimensions(path: str, is_video: bool) -> tuple[int, int]:
    """Return ``(width, height)`` for an example image or video file.

    Videos are read from their container headers (PIL cannot open them) so the
    showcase viewer sizes the gallery to the real aspect ratio. Falls back to
    the legacy ``720x1280`` placeholder when the dimensions cannot be
    determined — e.g. an unreadable file or an exotic codec — which only
    affects the displayed aspect ratio, never the file itself.
    """

    dimensions = None

    if is_video:
        dimensions = get_video_dimensions(path)
    else:
        try:
            from PIL import Image

            if os.path.exists(path):
                with Image.open(path) as img:
                    dimensions = img.size
        except Exception:
            dimensions = None

    if dimensions:
        width, height = dimensions
        if width > 0 and height > 0:
            return int(width), int(height)

    return _DEFAULT_MEDIA_WIDTH, _DEFAULT_MEDIA_HEIGHT


def _is_video_entry(file_path: Optional[str], entry: Mapping[str, Any]) -> bool:
    """Return True when an example entry points at a video file.

    The local file extension wins over the recorded ``type`` because files in
    the wild are frequently mislabelled (animated WebP saved as ``.mp4``);
    ``_read_media_dimensions`` handles that correctly either way.
    """

    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in SUPPORTED_MEDIA_EXTENSIONS["videos"]:
            return True
        if ext in SUPPORTED_MEDIA_EXTENSIONS["images"]:
            return False
    return str(entry.get("type", "")).lower() == "video"


def _resolve_local_file(
    entry: Mapping[str, Any],
    index: int,
    local_files: Mapping[str, str],
) -> Optional[str]:
    """Map a metadata entry onto its example file inside the model folder.

    Reads the entry's own marker (``id`` for ``customImages``, positional
    ``index`` for ``images``) with an anchored regex, so the identifier can
    never bleed into a neighbouring filename the way a prefix comparison can.
    """

    marker = entry.get("id")
    if not isinstance(marker, str) or not marker:
        marker = str(index)

    match = _ENTRY_MARKER_PATTERN.fullmatch(marker)
    if not match:
        return None

    return local_files.get(match.group(1))


def repair_local_video_dimensions(
    metadata: MutableMapping[str, Any],
    local_files: Mapping[str, str],
    *,
    dry_run: bool = False,
) -> int:
    """Backfill real video dimensions for an entry that has local files.

    Only entries with an empty ``url`` are considered: those have no remote
    source, so the local file is the single source of truth for their size and
    rewriting them cannot discard API-supplied data. Entries whose dimensions
    already match the file are left byte-identical.

    Args:
        metadata: Raw metadata payload (mutated in place unless ``dry_run``).
        local_files: ``{identifier: path}`` for files present in the model's
            example folder, where the identifier is the entry's ``id`` (for
            ``customImages``) or its positional index (for ``images``).
        dry_run: Count the fixes without mutating ``metadata``.

    Returns:
        The number of entries that were (or would be) repaired.
    """

    civitai = metadata.get("civitai")
    if not isinstance(civitai, dict):
        return 0

    repaired = 0

    for key in ("customImages", "images"):
        entries = civitai.get(key)
        if not isinstance(entries, list) or not entries:
            continue

        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            if entry.get("url", "") != "":
                # Remote-backed entry: never rebuilt from local state.
                continue

            file_path = _resolve_local_file(entry, index, local_files)
            if not file_path or not os.path.isfile(file_path):
                continue

            dimensions = _read_media_dimensions(
                file_path, _is_video_entry(file_path, entry)
            )
            width, height = dimensions
            if width <= 0 or height <= 0:
                continue
            if entry.get("width") == width and entry.get("height") == height:
                continue

            if not dry_run:
                entry["width"] = width
                entry["height"] = height
            repaired += 1

    return repaired


def _get_metadata_sync_service() -> MetadataSyncService:
    """Return the shared metadata sync service, initialising it lazily."""

    global _metadata_sync_service, _metadata_sync_service_settings

    settings_manager = get_settings_manager()

    if isinstance(_metadata_sync_service, MetadataSyncService):
        if _metadata_sync_service_settings is not settings_manager:
            _metadata_sync_service = _build_metadata_sync_service(settings_manager)
            _metadata_sync_service_settings = settings_manager
    elif _metadata_sync_service is None:
        _metadata_sync_service = _build_metadata_sync_service(settings_manager)
        _metadata_sync_service_settings = settings_manager
    else:
        # Tests may inject stand-ins that do not match the sync service type. Preserve
        # those injections while still updating our cached settings reference so the
        # next real service instantiation uses the current configuration.
        _metadata_sync_service_settings = settings_manager

    return _metadata_sync_service


class MetadataUpdater:
    """Handles updating model metadata related to example images"""
    
    @staticmethod
    async def refresh_model_metadata(model_hash, model_name, scanner_type, scanner, progress: dict[str, Any] | None = None):
        """Refresh model metadata from CivitAI
        
        Args:
            model_hash: SHA256 hash of the model
            model_name: Model name (for logging)
            scanner_type: Scanner type ('lora' or 'checkpoint')
            scanner: Scanner instance for this model type
            
        Returns:
            bool: True if metadata was successfully refreshed, False otherwise
        """
        try:
            # Find the model in the scanner cache
            cache = await scanner.get_cached_data()
            model_data = None
            
            for item in cache.raw_data:
                if item.get('sha256') == model_hash:
                    model_data = item
                    break
            
            if not model_data:
                logger.warning(f"Model {model_name} with hash {model_hash} not found in cache")
                return False
            
            file_path = model_data.get('file_path')
            if not file_path:
                logger.warning(f"Model {model_name} has no file path")
                return False
            
            # Track that we're refreshing this model
            if progress is not None:
                progress['refreshed_models'].add(model_hash)
            
            async def update_cache_func(old_path, new_path, metadata):
                return await update_cache_from_metadata(scanner, new_path, metadata)

            await MetadataManager.hydrate_model_data(model_data)
            success, error = await _get_metadata_sync_service().fetch_and_update_model(
                sha256=model_hash,
                file_path=file_path,
                model_data=model_data,
                update_cache_func=update_cache_func,
            )
            
            if success:
                logger.info(f"Successfully refreshed metadata for {model_name}")
                return True
            else:
                logger.warning(f"Failed to refresh metadata for {model_name}, {error}")
                return False

        except Exception as e:
            error_msg = f"Error refreshing metadata for {model_name}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if progress is not None:
                progress['errors'].append(error_msg)
                progress['last_error'] = error_msg
            return False
    
    @staticmethod
    async def get_updated_model(model_hash, scanner):
        """Load the most recent metadata for a model identified by hash."""
        cache = await scanner.get_cached_data()
        target = None
        for item in cache.raw_data:
            if item.get('sha256') == model_hash:
                target = item
                break

        if not target:
            return None

        file_path = target.get('file_path')
        if not file_path:
            return target

        model_cls = getattr(scanner, 'model_class', None)
        if model_cls is None:
            metadata, should_skip = await MetadataManager.load_metadata(file_path)
        else:
            metadata, should_skip = await MetadataManager.load_metadata(file_path, model_cls)

        if should_skip or metadata is None:
            return target

        rich_metadata = metadata.to_dict()
        rich_metadata.setdefault('folder', target.get('folder', ''))
        return rich_metadata


    @staticmethod
    async def update_metadata_from_local_examples(model_hash, model, scanner_type, scanner, model_dir):
        """Update model metadata with local example image information
        
        Args:
            model_hash: SHA256 hash of the model
            model: Model data dictionary
            scanner_type: Scanner type ('lora' or 'checkpoint')
            scanner: Scanner instance for this model type
            model_dir: Model images directory
            
        Returns:
            bool: True if metadata was successfully updated, False otherwise
        """
        try:
            # Collect local image paths
            local_images_paths = []
            if os.path.exists(model_dir):
                for file in os.listdir(model_dir):
                    file_path = os.path.join(model_dir, file)
                    if os.path.isfile(file_path):
                        file_ext = os.path.splitext(file)[1].lower()
                        is_supported = (file_ext in SUPPORTED_MEDIA_EXTENSIONS['images'] or
                                       file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos'])
                        if is_supported:
                            local_images_paths.append(file_path)
            
            await MetadataManager.hydrate_model_data(model)
            civitai_data = model.setdefault('civitai', {})

            # Check if metadata update is needed (no civitai field or empty images)
            needs_update = not civitai_data or not civitai_data.get('images')
            
            if needs_update and local_images_paths:
                logger.debug(f"Found {len(local_images_paths)} local example images for {model.get('model_name')}, updating metadata")
                
                # Create or get civitai field
                # Create images array
                images = []
                
                # Generate metadata for each local image/video
                for path in local_images_paths:
                    # Determine if video or image
                    file_ext = os.path.splitext(path)[1].lower()
                    is_video = file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos']

                    width, height = _read_media_dimensions(path, is_video)

                    # Create image metadata entry
                    image_entry = {
                        "url": "",  # Empty URL as required
                        "nsfwLevel": 0,
                        "width": width,
                        "height": height,
                        "type": "video" if is_video else "image",
                        "meta": None,
                        "hasMeta": False,
                        "hasPositivePrompt": False
                    }

                    images.append(image_entry)
                
                # Update the model's civitai.images field
                civitai_data['images'] = images
                
                # Save metadata to .metadata.json file
                file_path = model.get('file_path')
                model_copy: Optional[Dict[str, Any]] = None
                try:
                    model_copy = model.copy()
                    if model_copy is not None:
                        model_copy.pop('folder', None)
                        await MetadataManager.save_metadata(file_path, model_copy)
                    logger.info(f"Saved metadata for {model.get('model_name')}")
                except Exception as e:
                    logger.error(f"Failed to save metadata for {model.get('model_name')}: {str(e)}")

                # Save updated metadata to scanner cache. sync_cache_from_metadata
                # returns False both for "already in sync" and for actual failures,
                # so the cache sync result is deliberately not treated as an error;
                # the return value reflects whether the metadata was persisted.
                if file_path and model_copy is not None:
                    await update_cache_from_metadata(scanner, file_path, model_copy)
                    logger.info(f"Successfully updated metadata for {model.get('model_name')} with {len(images)} local examples")
                    return True

                logger.warning(f"Failed to update metadata for {model.get('model_name')}")
                return False
            
            return False
        except Exception as e:
            logger.error(f"Error updating metadata from local examples: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    async def update_metadata_after_import(model_hash, model_data, scanner, newly_imported_paths):
        """Update model metadata after importing example images
        
        Args:
            model_hash: SHA256 hash of the model
            model_data: Model data dictionary
            scanner: Scanner instance (lora or checkpoint)
            newly_imported_paths: List of paths to newly imported files
            
        Returns:
            tuple: (regular_images, custom_images) - Both image arrays
        """
        try:
            await MetadataManager.hydrate_model_data(model_data)
            civitai_data = model_data.get('civitai')

            if not isinstance(civitai_data, dict):
                civitai_data = {}
                model_data['civitai'] = civitai_data

            custom_images = civitai_data.get('customImages')

            if not isinstance(custom_images, list):
                custom_images = []
                civitai_data['customImages'] = custom_images
            
            # Add new image entry for each imported file
            for path_tuple in newly_imported_paths:
                path, short_id = path_tuple

                # Determine if video or image
                file_ext = os.path.splitext(path)[1].lower()
                is_video = file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos']

                width, height = _read_media_dimensions(path, is_video)

                # Create image metadata entry
                image_entry = {
                    "url": "",  # Empty URL as requested
                    "id": short_id,
                    "nsfwLevel": 0,
                    "width": width,
                    "height": height,
                    "type": "video" if is_video else "image",
                    "meta": None,
                    "hasMeta": False,
                    "hasPositivePrompt": False
                }
                
                # Extract and parse metadata if this is an image
                if not is_video:
                    try:
                        # Extract metadata from image
                        extracted_metadata = ExifUtils.extract_image_metadata(path)
                        
                        if extracted_metadata:
                            # Parse the extracted metadata to get generation parameters
                            parsed_meta = MetadataUpdater._parse_image_metadata(extracted_metadata)
                            
                            if parsed_meta:
                                image_entry["meta"] = parsed_meta
                                image_entry["hasMeta"] = True
                                image_entry["hasPositivePrompt"] = bool(parsed_meta.get("prompt", ""))
                                logger.debug(f"Extracted metadata from {os.path.basename(path)}")
                    except Exception as e:
                        logger.warning(f"Failed to extract metadata from {os.path.basename(path)}: {e}")
                
                # Append to existing customImages array
                custom_images.append(image_entry)
            
            # Save metadata to .metadata.json file
            file_path = model_data.get('file_path')
            model_copy: Optional[Dict[str, Any]] = None
            if file_path:
                try:
                    model_copy = model_data.copy()
                    if model_copy is not None:
                        model_copy.pop('folder', None)
                        await MetadataManager.save_metadata(file_path, model_copy)
                    logger.info(f"Saved metadata for {model_data.get('model_name')}")
                except Exception as e:
                    logger.error(f"Failed to save metadata: {str(e)}")

            # Save updated metadata to scanner cache
            if file_path and model_copy is not None:
                await update_cache_from_metadata(scanner, file_path, model_copy)

            # Get regular images array (might be None)
            regular_images = civitai_data.get('images', [])
            
            # Return both image arrays
            return regular_images, custom_images
                
        except Exception as e:
            logger.error(f"Failed to update metadata after import: {e}", exc_info=True)
            return [], []
    
    @staticmethod
    def _parse_image_metadata(user_comment):
        """Parse metadata from image to extract generation parameters
        
        Args:
            user_comment: Metadata string extracted from image
            
        Returns:
            dict: Parsed metadata with generation parameters
        """
        if not user_comment:
            return None
            
        try:
            # Initialize metadata dictionary
            metadata = {}
            
            # Split on Negative prompt if it exists
            if "Negative prompt:" in user_comment:
                parts = user_comment.split('Negative prompt:', 1)
                prompt = parts[0].strip()
                negative_and_params = parts[1] if len(parts) > 1 else ""
            else:
                # No negative prompt section
                param_start = re.search(r'Steps: \d+', user_comment)
                if param_start:
                    prompt = user_comment[:param_start.start()].strip()
                    negative_and_params = user_comment[param_start.start():]
                else:
                    prompt = user_comment.strip()
                    negative_and_params = ""
            
            # Add prompt if it's in GEN_PARAM_KEYS
            if 'prompt' in GEN_PARAM_KEYS:
                metadata['prompt'] = prompt
            
            # Extract negative prompt and parameters
            if negative_and_params:
                # If we split on "Negative prompt:", check for params section
                if "Negative prompt:" in user_comment:
                    param_start = re.search(r'Steps: ', negative_and_params)
                    if param_start:
                        neg_prompt = negative_and_params[:param_start.start()].strip()
                        if 'negative_prompt' in GEN_PARAM_KEYS:
                            metadata['negative_prompt'] = neg_prompt
                        params_section = negative_and_params[param_start.start():]
                    else:
                        if 'negative_prompt' in GEN_PARAM_KEYS:
                            metadata['negative_prompt'] = negative_and_params.strip()
                        params_section = ""
                else:
                    # No negative prompt, entire section is params
                    params_section = negative_and_params
                
                # Extract generation parameters
                if params_section:
                    # Extract basic parameters
                    param_pattern = r'([A-Za-z\s]+): ([^,]+)'
                    params = re.findall(param_pattern, params_section)
                    
                    for key, value in params:
                        clean_key = key.strip().lower().replace(' ', '_')
                        
                        # Skip if not in recognized gen param keys
                        if clean_key not in GEN_PARAM_KEYS:
                            continue
                            
                        # Convert numeric values
                        if clean_key in ['steps', 'seed']:
                            try:
                                metadata[clean_key] = int(value.strip())
                            except ValueError:
                                metadata[clean_key] = value.strip()
                        elif clean_key in ['cfg_scale']:
                            try:
                                metadata[clean_key] = float(value.strip())
                            except ValueError:
                                metadata[clean_key] = value.strip()
                        else:
                            metadata[clean_key] = value.strip()
                    
                    # Extract size if available and add if a recognized key
                    size_match = re.search(r'Size: (\d+)x(\d+)', params_section)
                    if size_match and 'size' in GEN_PARAM_KEYS:
                        width, height = size_match.groups()
                        metadata['size'] = f"{width}x{height}"
            
            # Return metadata if we have any entries
            return metadata if metadata else None
            
        except Exception as e:
            logger.error(f"Error parsing image metadata: {e}", exc_info=True)
            return None

    @staticmethod
    async def prune_stale_example_images(metadata) -> bool:
        """Remove example-image metadata entries whose files no longer exist on disk.

        Checks ``civitai.customImages`` (by ``id``) and ``civitai.images`` entries
        that have an empty ``url`` (no remote fallback) against actual files in
        the model's example-image folder.  Stale entries are removed in-place so
        the caller can persist the cleaned metadata afterwards.

        Args:
            metadata: A ``BaseModelMetadata`` instance (modified in place).

        Returns:
            True if at least one entry was removed.
        """
        from ..utils.example_images_paths import get_model_folder

        model_hash = getattr(metadata, "sha256", None)
        if not model_hash:
            return False

        model_folder = get_model_folder(model_hash)
        if not model_folder or not os.path.isdir(model_folder):
            return False

        civitai = getattr(metadata, "civitai", None)
        if not isinstance(civitai, dict):
            return False

        # Read the directory listing once so every image entry reuses it.
        try:
            dir_entries = os.listdir(model_folder)
        except OSError:
            dir_entries = []

        has_changes = False

        custom_images = civitai.get("customImages")
        if isinstance(custom_images, list) and custom_images:
            stale: list[int] = []

            for idx, img in enumerate(custom_images):
                img_id = img.get("id", "")
                if not img_id:
                    continue

                prefix = f"custom_{img_id}"
                found = any(
                    f.startswith(prefix) and os.path.isfile(
                        os.path.join(model_folder, f)
                    )
                    for f in dir_entries
                )
                if not found:
                    stale.append(idx)

            if stale:
                for idx in reversed(stale):
                    custom_images.pop(idx)
                has_changes = True
                logger.info(
                    "Pruned %d stale custom image(s) for %s",
                    len(stale),
                    getattr(metadata, "model_name", model_hash),
                )

        images = civitai.get("images")
        if isinstance(images, list) and images:
            stale_images: list[int] = []

            for idx, img in enumerate(images):
                if img.get("url", ""):
                    # Has a remote fallback – keep it even if the local copy
                    # is gone.
                    continue

                prefix = f"image_{idx}."
                if not any(f.startswith(prefix) for f in dir_entries):
                    stale_images.append(idx)

            if stale_images:
                for idx in reversed(stale_images):
                    images.pop(idx)
                has_changes = True
                logger.info(
                    "Pruned %d stale image entry(ies) for %s",
                    len(stale_images),
                    getattr(metadata, "model_name", model_hash),
                )

        return has_changes
