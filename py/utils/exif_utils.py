import json
import logging
import os
from io import BytesIO
from typing import Any, Optional

import piexif
from PIL import Image, PngImagePlugin

logger = logging.getLogger(__name__)

class ExifUtils:
    """Utility functions for working with EXIF data in images"""

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
        metadata = {
            "parameters": None,
            "prompt": None,
            "workflow": None,
            "comment": None,
        }

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

            if piexif.ExifIFD.UserComment in exif_dict.get("Exif", {}):
                metadata["comment"] = ExifUtils._decode_user_comment(
                    exif_dict["Exif"][piexif.ExifIFD.UserComment]
                )

            image_description = ExifUtils._decode_exif_text(
                exif_dict.get("0th", {}).get(piexif.ImageIFD.ImageDescription)
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

        if parameters:
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = (
                b"UNICODE\0" + parameters.encode("utf-16be")
            )
        else:
            exif_dict["Exif"].pop(piexif.ExifIFD.UserComment, None)

        if workflow:
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = f"Workflow:{workflow}"
        elif prompt:
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = prompt
        else:
            exif_dict["0th"].pop(piexif.ImageIFD.ImageDescription, None)

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
            # Skip for video files
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
            # Skip for video files
            if image_path:
                ext = os.path.splitext(image_path)[1].lower()
                if ext in ['.mp4', '.webm']:
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
                save_kwargs = {"exif": exif_bytes}
                if img_format == "WEBP":
                    save_kwargs["quality"] = 85

                img.save(image_path, format=img_format, **save_kwargs)

            return image_path
        except Exception as e:
            logger.error(f"Error updating metadata in {image_path}: {e}")
            return image_path
            
    @staticmethod
    def append_recipe_metadata(image_path, recipe_data) -> str:
        """Append recipe metadata to an image's EXIF data"""
        try:
            # Skip for video files
            if image_path:
                ext = os.path.splitext(image_path)[1].lower()
                if ext in ['.mp4', '.webm']:
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
            
            # Write back to the image
            return ExifUtils.update_image_metadata(image_path, new_metadata)
        except Exception as e:
            logger.error(f"Error appending recipe metadata: {e}", exc_info=True)
            return image_path

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
            # Skip for video files early if it's a file path
            if isinstance(image_data, str) and os.path.exists(image_data):
                ext = os.path.splitext(image_data)[1].lower()
                if ext in ['.mp4', '.webm']:
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
                    with BytesIO(image_data) as temp_buf:
                        test_img = Image.open(temp_buf)
                        # Verify the image can be fully loaded
                        width, height = test_img.size
                    # If successful, reopen for processing
                    img = Image.open(BytesIO(image_data))
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
                            temp_file.write(image_data)
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
                resized_img = img.resize((target_width, new_height), Image.LANCZOS)
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
