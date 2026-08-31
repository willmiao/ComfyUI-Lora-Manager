import functools
import json
import logging
import os
import struct
from io import BytesIO
from typing import Any, Optional, Tuple, cast

import piexif  # pyright: ignore[reportMissingTypeStubs]
from PIL import Image, PngImagePlugin

try:
    import brotli  # pyright: ignore[reportMissingTypeStubs]
    _BROTLI_AVAILABLE = True
except ImportError:
    brotli = None
    _BROTLI_AVAILABLE = False

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=2048)
def _get_image_dimensions_cached(path: str, _mtime_ns: int, _size: int) -> Optional[Tuple[int, int]]:
    """Return ``(width, height)`` for ``path``, or ``None`` on any failure.

    The ``_mtime_ns`` and ``_size`` arguments are part of the cache key only;
    they invalidate the entry when the file is replaced with a new image, so a
    stale preview never serves outdated dimensions.
    """
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


class ExifUtils:
    """Utility functions for working with EXIF data in images"""

    @staticmethod
    def _parse_isobmff_boxes(data: bytes, offset: int = 0) -> list[dict[str, Any]]:
        boxes = []
        while offset + 8 <= len(data):
            size = struct.unpack('>I', data[offset:offset + 4])[0]
            box_type = data[offset + 4:offset + 8]
            if size == 0:
                break
            if size < 8 or offset + size > len(data):
                break
            box_data = data[offset + 8:offset + size]
            boxes.append({'type': box_type, 'data': box_data, 'size': size})
            offset += size
        return boxes

    @staticmethod
    def _is_jxl_container(data: bytes) -> bool:
        if len(data) < 32:
            return False
        return (
            struct.unpack('>I', data[:4])[0] == 12
            and data[4:8] == b'JXL '
            and data[8:12] == bytes([0x0d, 0x0a, 0x87, 0x0a])
            and struct.unpack('>I', data[12:16])[0] >= 16
            and data[16:20] == b'ftyp'
            and data[20:24] == b'jxl '
        )

    @staticmethod
    def _is_avif_container(data: bytes) -> bool:
        if len(data) < 16:
            return False
        for box in ExifUtils._parse_isobmff_boxes(data):
            if box['type'] == b'ftyp' and b'avif' in box['data']:
                return True
        return False

    # Max decompressed size for brotli metadata (2 MB)
    _BROTLI_MAX_DECOMPRESSED = 2 * 1024 * 1024

    @staticmethod
    def _extract_isobmff_brotli(image_path: str) -> Optional[dict[str, Any]]:
        try:
            with open(image_path, 'rb') as f:
                data = f.read()
        except Exception:
            return None

        if ExifUtils._is_jxl_container(data):
            boxes = ExifUtils._parse_isobmff_boxes(data, offset=12)
        elif ExifUtils._is_avif_container(data):
            boxes = ExifUtils._parse_isobmff_boxes(data)
        else:
            return None

        brob = None
        for box in boxes:
            if box['type'] == b'brob':
                brob = box
                break
        if brob is None:
            return None

        payload = brob['data']
        if payload[:4] != b'comf':
            return None
        compressed = payload[4:]

        if _BROTLI_AVAILABLE:
            try:
                decompressed = brotli.decompress(compressed)  # pyright: ignore[reportOptionalMemberAccess]
                if len(decompressed) > ExifUtils._BROTLI_MAX_DECOMPRESSED:
                    logger.warning(
                        "Brotli metadata too large (%d bytes, max %d), ignoring",
                        len(decompressed),
                        ExifUtils._BROTLI_MAX_DECOMPRESSED,
                    )
                    decompressed = None
            except Exception:
                decompressed = None
        else:
            decompressed = None

        raw = decompressed if decompressed is not None else compressed
        try:
            meta = json.loads(raw.decode('utf-8'))
        except Exception:
            return None

        result: dict[str, Optional[str]] = {
            "parameters": None, "prompt": None, "workflow": None, "comment": None
        }
        if isinstance(meta.get("prompt"), (dict, list)):
            result["prompt"] = json.dumps(meta["prompt"])
        elif isinstance(meta.get("prompt"), str):
            result["prompt"] = meta["prompt"]
        if isinstance(meta.get("workflow"), (dict, list)):
            result["workflow"] = json.dumps(meta["workflow"])
        elif isinstance(meta.get("workflow"), str):
            result["workflow"] = meta["workflow"]
        return result

    @staticmethod
    def _decode_user_comment(user_comment: Any) -> Optional[str]:
        if user_comment is None:
            return None
        if isinstance(user_comment, bytes):
            if user_comment.startswith(b"UNICODE\0"):
                return user_comment[8:].decode("utf-16be", errors="ignore")
            return user_comment.decode("utf-8", errors="ignore")
        if isinstance(user_comment, str):
            return user_comment
        return str(user_comment)

    @staticmethod
    def _decode_exif_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _load_structured_metadata(image_path: str) -> dict[str, Optional[str]]:
        metadata: dict[str, Optional[str]] = {
            "parameters": None,
            "prompt": None,
            "workflow": None,
            "comment": None,
        }

        ext = os.path.splitext(image_path)[1].lower()
        if ext in ('.avif', '.jxl'):
            brotli_meta = ExifUtils._extract_isobmff_brotli(image_path)
            if brotli_meta:
                return brotli_meta

        with Image.open(image_path) as img:
            info = getattr(img, "info", {}) or {}

            if "parameters" in info:
                metadata["parameters"] = info["parameters"]
            if "prompt" in info:
                metadata["prompt"] = info["prompt"]
            if "workflow" in info:
                metadata["workflow"] = info["workflow"]

            if img.format not in ["JPEG", "TIFF", "WEBP"]:
                exif = img.getexif()
                if exif and piexif.ExifIFD.UserComment in exif:
                    metadata["comment"] = ExifUtils._decode_user_comment(
                        exif[piexif.ExifIFD.UserComment]
                    )

            try:
                exif_dict = piexif.load(image_path)
            except Exception as e:
                logger.debug(f"Error loading EXIF data: {e}")
                exif_dict = {}

            exif_ifd = exif_dict.get("Exif")
            if exif_ifd and piexif.ExifIFD.UserComment in exif_ifd:
                metadata["comment"] = ExifUtils._decode_user_comment(
                    exif_ifd[piexif.ExifIFD.UserComment]
                )

            image_description = ExifUtils._decode_exif_text(
                (exif_dict.get("0th") or {}).get(piexif.ImageIFD.ImageDescription)
            )
            if image_description:
                if image_description.startswith("Workflow:"):
                    metadata["workflow"] = image_description[len("Workflow:") :]
                elif not metadata["prompt"]:
                    metadata["prompt"] = image_description

        if not metadata["parameters"] and metadata["comment"]:
            metadata["parameters"] = metadata["comment"]

        return metadata

    @staticmethod
    def _build_pnginfo(img: Image.Image, metadata_fields: dict[str, Optional[str]]) -> PngImagePlugin.PngInfo:
        png_info = PngImagePlugin.PngInfo()
        existing_info = getattr(img, "info", {}) or {}
        managed_keys = {"parameters", "prompt", "workflow"}

        for key, value in existing_info.items():
            if key in {"exif", "dpi", "transparency", "gamma", "aspect"}:
                continue
            if key in managed_keys:
                continue
            if isinstance(value, str):
                png_info.add_text(key, value)

        for key in managed_keys:
            value = metadata_fields.get(key)
            if value:
                png_info.add_text(key, value)

        return png_info

    @staticmethod
    def _build_exif_bytes(
        metadata_fields: dict[str, Optional[str]], existing_exif: bytes | None = None
    ) -> bytes:
        try:
            exif_dict = piexif.load(existing_exif or b"")
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}}

        exif_dict.setdefault("0th", {})
        exif_dict.setdefault("Exif", {})

        parameters = metadata_fields.get("parameters")
        workflow = metadata_fields.get("workflow")
        prompt = metadata_fields.get("prompt")

        # Work on local references, then write the (possibly new) IFD dicts back.
        exif_ifd = exif_dict.get("Exif") or {}
        exif_0th = exif_dict.get("0th") or {}

        if parameters:
            exif_ifd[piexif.ExifIFD.UserComment] = (
                b"UNICODE\0" + parameters.encode("utf-16be")
            )
        else:
            exif_ifd.pop(piexif.ExifIFD.UserComment, None)

        if workflow:
            exif_0th[piexif.ImageIFD.ImageDescription] = f"Workflow:{workflow}"
        elif prompt:
            exif_0th[piexif.ImageIFD.ImageDescription] = prompt
        else:
            exif_0th.pop(piexif.ImageIFD.ImageDescription, None)

        exif_dict["Exif"] = exif_ifd
        exif_dict["0th"] = exif_0th

        return piexif.dump(exif_dict)
    
    @staticmethod
    def extract_image_metadata(image_path: str) -> Optional[str]:
        """Extract metadata from image including UserComment or parameters field
        
        Args:
            image_path (str): Path to the image file
            
        Returns:
            Optional[str]: Extracted metadata or None if not found
        """
        try:
            if image_path:
                ext = os.path.splitext(image_path)[1].lower()
                if ext in ['.mp4', '.webm']:
                    return None

            metadata = ExifUtils._load_structured_metadata(image_path)
            return (
                metadata.get("parameters")
                or metadata.get("prompt")
                or metadata.get("workflow")
            )
        except Exception as e:
            logger.error(f"Error extracting image metadata: {e}", exc_info=True)
            return None
    
    @staticmethod
    def update_image_metadata(image_path: str, metadata: str) -> str:
        """Update metadata in image's EXIF data or parameters fields
        
        Args:
            image_path (str): Path to the image file
            metadata (str): Metadata string to save
            
        Returns:
            str: Path to the updated image
        """
        try:
            if image_path:
                ext = os.path.splitext(image_path)[1].lower()
                if ext in ['.mp4', '.webm', '.avif', '.jxl']:
                    return image_path

            metadata_fields = ExifUtils._load_structured_metadata(image_path)
            metadata_fields["parameters"] = metadata

            with Image.open(image_path) as img:
                img_format = img.format

                if img_format == "PNG":
                    png_info = ExifUtils._build_pnginfo(img, metadata_fields)
                    img.save(image_path, format="PNG", pnginfo=png_info)
                    return image_path

                exif_bytes = ExifUtils._build_exif_bytes(
                    metadata_fields, img.info.get("exif")
                )
                save_kwargs: dict[str, Any] = {"exif": exif_bytes}
                if img_format == "WEBP":
                    save_kwargs["quality"] = 85

                img.save(image_path, format=img_format, **save_kwargs)

            return image_path
        except Exception as e:
            logger.error(f"Error updating metadata in {image_path}: {e}")
            return image_path
            
    @staticmethod
    def append_recipe_metadata(image_path, recipe_data, pixel_preserving=False) -> str:
        """Append recipe metadata to an image's EXIF data

        When ``pixel_preserving`` is True (and the image is a WebP) only the
        EXIF container is rewritten at the byte level, so the preview pixels
        are never re-encoded. Local re-import uses this because its source is
        the recipe's own already-optimized preview image.
        """
        try:
            if image_path:
                ext = os.path.splitext(image_path)[1].lower()
                if ext in ['.mp4', '.webm', '.avif', '.jxl']:
                    return image_path

            # First, extract existing metadata
            metadata = ExifUtils.extract_image_metadata(image_path)
            
            # Check if there's already recipe metadata
            if metadata:
                # Remove any existing recipe metadata
                metadata = ExifUtils.remove_recipe_metadata(metadata)

            # Prepare checkpoint data
            checkpoint_data = recipe_data.get("checkpoint") or {}
            simplified_checkpoint = None
            if isinstance(checkpoint_data, dict) and checkpoint_data:
                simplified_checkpoint = {
                    "type": checkpoint_data.get("type", "checkpoint"),
                    "modelId": checkpoint_data.get("modelId", 0),
                    "modelVersionId": checkpoint_data.get("modelVersionId")
                    or checkpoint_data.get("id", 0),
                    "modelName": checkpoint_data.get(
                        "modelName", checkpoint_data.get("name", "")
                    ),
                    "modelVersionName": checkpoint_data.get(
                        "modelVersionName", checkpoint_data.get("version", "")
                    ),
                    "hash": checkpoint_data.get("hash", "").lower()
                    if checkpoint_data.get("hash")
                    else "",
                    "file_name": checkpoint_data.get("file_name", ""),
                    "baseModel": checkpoint_data.get("baseModel", ""),
                }
            
            # Prepare simplified loras data
            simplified_loras = []
            for lora in recipe_data.get("loras", []):
                simplified_lora = {
                    "file_name": lora.get("file_name", ""),
                    "hash": lora.get("hash", "").lower() if lora.get("hash") else "",
                    "strength": float(lora.get("strength", 1.0)),
                    "modelVersionId": lora.get("modelVersionId", 0),
                    "modelName": lora.get("modelName", ""),
                    "modelVersionName": lora.get("modelVersionName", ""),
                }
                simplified_loras.append(simplified_lora)            
            
            # Create recipe metadata JSON
            recipe_metadata = {
                'title': recipe_data.get('title', ''),
                'base_model': recipe_data.get('base_model', ''),
                'loras': simplified_loras,
                'gen_params': recipe_data.get('gen_params', {}),
                'tags': recipe_data.get('tags', []),
                **({'checkpoint': simplified_checkpoint} if simplified_checkpoint else {})
            }
            
            # Convert to JSON string
            recipe_metadata_json = json.dumps(recipe_metadata)
            
            # Create the recipe metadata marker
            recipe_metadata_marker = f"Recipe metadata: {recipe_metadata_json}"
            
            # Append to existing metadata or create new one
            new_metadata = f"{metadata} \n {recipe_metadata_marker}" if metadata else recipe_metadata_marker

            # Write back to the image. Re-import keeps the already-optimized
            # preview pixels untouched and updates only the WebP EXIF chunk
            # instead of re-encoding the whole image.
            if pixel_preserving and image_path.lower().endswith(".webp"):
                metadata_fields = ExifUtils._load_structured_metadata(image_path)
                metadata_fields["parameters"] = new_metadata
                exif_bytes = ExifUtils._build_exif_bytes(metadata_fields)
                with open(image_path, "rb") as file_obj:
                    image_bytes = file_obj.read()
                try:
                    updated = ExifUtils._replace_webp_exif(image_bytes, exif_bytes)
                except ValueError:
                    # Container without an EXIF chunk; fall back to re-encoding.
                    return ExifUtils.update_image_metadata(image_path, new_metadata)
                with open(image_path, "wb") as file_obj:
                    file_obj.write(updated)
                return image_path

            # Write back to the image
            return ExifUtils.update_image_metadata(image_path, new_metadata)
        except Exception as e:
            logger.error(f"Error appending recipe metadata: {e}", exc_info=True)
            return image_path

    @staticmethod
    def _replace_webp_exif(image_bytes: bytes, exif_bytes: bytes) -> bytes:
        """Replace the EXIF chunk of a WebP file without re-encoding pixels."""
        if image_bytes[:4] != b"RIFF" or image_bytes[8:12] != b"WEBP":
            raise ValueError("Not a WebP file")
        # The WebP EXIF chunk stores raw TIFF data; strip the JPEG-style
        # "Exif\\0\\0" prefix that piexif.dump may prepend.
        tiff = exif_bytes[6:] if exif_bytes[:6] == b"Exif\x00\x00" else exif_bytes

        out = bytearray(image_bytes[:12])
        pos = 12
        exif_payload = None
        while pos + 8 <= len(image_bytes):
            fourcc = image_bytes[pos : pos + 4]
            size = struct.unpack("<I", image_bytes[pos + 4 : pos + 8])[0]
            chunk_data = image_bytes[pos + 8 : pos + 8 + size]
            pad = size % 2
            if fourcc == b"EXIF":
                exif_payload = tiff
            else:
                out += (
                    fourcc
                    + struct.pack("<I", size)
                    + chunk_data
                    + (b"\x00" * pad)
                )
            pos += 8 + size + pad

        if exif_payload is None:
            raise ValueError("WebP has no EXIF chunk")

        out += (
            b"EXIF"
            + struct.pack("<I", len(exif_payload))
            + exif_payload
            + (b"\x00" * (len(exif_payload) % 2))
        )
        out[4:8] = struct.pack("<I", len(out) - 8)
        return bytes(out)

    @staticmethod
    def remove_recipe_metadata(user_comment):
        """Remove recipe metadata from user comment"""
        if not user_comment:
            return ""
        
        # Find the recipe metadata marker
        recipe_marker_index = user_comment.find("Recipe metadata: ")
        if recipe_marker_index == -1:
            return user_comment
        
        # If recipe metadata is not at the start, remove the preceding ", "
        if recipe_marker_index >= 2 and user_comment[recipe_marker_index-2:recipe_marker_index] == ", ":
            recipe_marker_index -= 2
        
        # Remove the recipe metadata part
        # First, find where the metadata ends (next line or end of string)
        next_line_index = user_comment.find("\n", recipe_marker_index)
        if next_line_index == -1:
            # Metadata is at the end of the string
            return user_comment[:recipe_marker_index].rstrip()
        else:
            # Metadata is in the middle of the string
            return user_comment[:recipe_marker_index] + user_comment[next_line_index:]
            
    @staticmethod
    def get_image_dimensions(image_path: str) -> Optional[Tuple[int, int]]:
        """Return ``(width, height)`` for an image, or ``None`` if unavailable.

        Video containers (``.mp4``/``.webm``/``.avi``) and formats PIL cannot
        read (``.avif``/``.jxl``) return ``None`` before PIL is invoked.
        Missing or corrupt files return ``None``. Never raises.
        """
        try:
            ext = os.path.splitext(image_path)[1].lower()
            if ext in ('.mp4', '.webm', '.avi', '.avif', '.jxl'):
                return None
            stat = os.stat(image_path)
            return _get_image_dimensions_cached(
                image_path, stat.st_mtime_ns, stat.st_size
            )
        except Exception:
            return None

    @staticmethod
    def optimize_image(image_data, target_width=250, format='webp', quality=85, preserve_metadata=False):
        """
        Optimize an image by resizing and converting to WebP format
        
        Args:
            image_data: Binary image data or path to image file
            target_width: Width to resize the image to (preserves aspect ratio)
            format: Output format (default: webp)
            quality: Output quality (0-100)
            preserve_metadata: Whether to preserve EXIF metadata
            
        Returns:
            Tuple of (optimized_image_data, extension)
        """
        try:
            if isinstance(image_data, str) and os.path.exists(image_data):
                ext = os.path.splitext(image_data)[1].lower()
                if ext in ['.mp4', '.webm', '.avif', '.jxl']:
                    try:
                        with open(image_data, 'rb') as f:
                            return f.read(), ext
                    except Exception:
                        return image_data, ext

            # First validate the image data is usable
            img = None
            if isinstance(image_data, str) and os.path.exists(image_data):
                # It's a file path - validate file
                try:
                    with Image.open(image_data) as test_img:
                        # Verify the image can be fully loaded by accessing its size
                        width, height = test_img.size
                    # If we got here, the image is valid
                    img = Image.open(image_data)
                except (IOError, OSError) as e:
                    logger.error(f"Invalid or corrupt image file: {image_data}: {e}")
                    raise ValueError(f"Cannot process corrupt image: {e}")
            else:
                # It's binary data - validate data
                try:
                    with BytesIO(cast(bytes, image_data)) as temp_buf:
                        test_img = Image.open(temp_buf)
                        # Verify the image can be fully loaded
                        width, height = test_img.size
                    # If successful, reopen for processing
                    img = Image.open(BytesIO(cast(bytes, image_data)))
                except Exception as e:
                    logger.error(f"Invalid binary image data: {e}")
                    raise ValueError(f"Cannot process corrupt image data: {e}")

            # Extract metadata if needed and valid
            metadata_fields = None
            if preserve_metadata:
                try:
                    if isinstance(image_data, str) and os.path.exists(image_data):
                        # For file path, extract directly
                        metadata_fields = ExifUtils._load_structured_metadata(image_data)
                    else:
                        # For binary data, save to temp file first
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                            temp_path = temp_file.name
                            temp_file.write(cast(bytes, image_data))
                        try:
                            metadata_fields = ExifUtils._load_structured_metadata(temp_path)
                        except Exception as e:
                            logger.warning(f"Failed to extract metadata from temp file: {e}")
                        finally:
                            # Clean up temp file
                            try:
                                os.unlink(temp_path)
                            except Exception:
                                pass
                except Exception as e:
                    logger.warning(f"Failed to extract metadata, continuing without it: {e}")
                    # Continue without metadata

            # Calculate new height to maintain aspect ratio
            width, height = img.size
            new_height = int(height * (target_width / width))
            
            # Resize the image with error handling
            try:
                resized_img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
            except Exception as e:
                logger.error(f"Failed to resize image: {e}")
                # Return original image if resize fails
                return image_data, '.jpg' if not isinstance(image_data, str) else os.path.splitext(image_data)[1]
            
            # Save to BytesIO in the specified format
            output = BytesIO()
            
            # Set format and extension
            if format.lower() == 'webp':
                save_format, extension = 'WEBP', '.webp'
            elif format.lower() in ('jpg', 'jpeg'):
                save_format, extension = 'JPEG', '.jpg'
            elif format.lower() == 'png':
                save_format, extension = 'PNG', '.png'
            else:
                save_format, extension = 'WEBP', '.webp'
            
            # Save with error handling
            try:
                if save_format == 'PNG':
                    resized_img.save(output, format=save_format, optimize=True)
                else:
                    resized_img.save(output, format=save_format, quality=quality)
            except Exception as e:
                logger.error(f"Failed to save optimized image: {e}")
                # Return original image if save fails
                return image_data, '.jpg' if not isinstance(image_data, str) else os.path.splitext(image_data)[1]
            
            # Get the optimized image data
            optimized_data = output.getvalue()
            
            # Handle metadata preservation if requested and available
            if preserve_metadata and metadata_fields:
                try:
                    if save_format == 'WEBP':
                        # For WebP format, directly save with metadata
                        try:
                            output_with_metadata = BytesIO()
                            exif_bytes = ExifUtils._build_exif_bytes(metadata_fields)
                            resized_img.save(output_with_metadata, format='WEBP', exif=exif_bytes, quality=quality)
                            optimized_data = output_with_metadata.getvalue()
                        except Exception as e:
                            logger.warning(f"Failed to add metadata to WebP, continuing without it: {e}")
                    else:
                        # For other formats, use temporary file
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp_file:
                            temp_path = temp_file.name
                            temp_file.write(optimized_data)
                        
                        try:
                            ExifUtils.update_image_metadata(
                                temp_path, metadata_fields.get("parameters") or ""
                            )
                            # Read back the file
                            with open(temp_path, 'rb') as f:
                                optimized_data = f.read()
                        except Exception as e:
                            logger.warning(f"Failed to add metadata to image, continuing without it: {e}")
                        finally:
                            # Clean up temp file
                            try:
                                os.unlink(temp_path)
                            except Exception:
                                pass
                except Exception as e:
                    logger.warning(f"Failed to preserve metadata: {e}, continuing with unmodified output")
            
            return optimized_data, extension
            
        except Exception as e:
            logger.error(f"Error optimizing image: {e}", exc_info=True)
            # Return original data if optimization completely fails
            if isinstance(image_data, str) and os.path.exists(image_data):
                try:
                    with open(image_data, 'rb') as f:
                        return f.read(), os.path.splitext(image_data)[1]
                except Exception:
                    return image_data, '.jpg'  # Last resort fallback
            return image_data, '.jpg'
