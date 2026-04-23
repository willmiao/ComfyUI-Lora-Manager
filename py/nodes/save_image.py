import json
import os
import re
import time
import uuid
from typing import Any, Dict, Optional
import numpy as np
import folder_paths  # type: ignore
from ..services.service_registry import ServiceRegistry
from ..metadata_collector.metadata_processor import MetadataProcessor
from ..metadata_collector import get_metadata
from ..utils.constants import CARD_PREVIEW_WIDTH
from ..utils.exif_utils import ExifUtils
from ..utils.utils import calculate_recipe_fingerprint
from PIL import Image, PngImagePlugin
import piexif
import logging

logger = logging.getLogger(__name__)


class SaveImageLM:
    NAME = "Save Image (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = "Save images with embedded generation metadata in compatible format"

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.prefix_append = ""
        self.compress_level = 4
        self.counter = 0

    # Add pattern format regex for filename substitution
    pattern_format = re.compile(r"(%[^%]+%)")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": (
                    "STRING",
                    {
                        "default": "ComfyUI",
                        "tooltip": "Base filename for saved images. Supports format patterns like %seed%, %width%, %height%, %model%, etc.",
                    },
                ),
                "file_format": (
                    ["png", "jpeg", "webp"],
                    {
                        "tooltip": "Image format to save as. PNG preserves quality, JPEG is smaller, WebP balances size and quality."
                    },
                ),
            },
            "optional": {
                "lossless_webp": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "When enabled, saves WebP images with lossless compression. Results in larger files but no quality loss.",
                    },
                ),
                "quality": (
                    "INT",
                    {
                        "default": 100,
                        "min": 1,
                        "max": 100,
                        "tooltip": "Compression quality for JPEG and lossy WebP formats (1-100). Higher values mean better quality but larger files.",
                    },
                ),
                "embed_workflow": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Embeds the complete workflow data into the image metadata. Only works with PNG and WebP formats.",
                    },
                ),
                "save_with_metadata": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "When enabled, embeds generation parameters into the saved image metadata. Disable to skip writing generation metadata.",
                    },
                ),
                "add_counter_to_filename": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "Adds an incremental counter to filenames to prevent overwriting previous images.",
                    },
                ),
                "save_as_recipe": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Also saves each generated image as a LoRA Manager recipe.",
                    },
                ),
            },
            "hidden": {
                "id": "UNIQUE_ID",
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "process_image"
    OUTPUT_NODE = True

    def get_lora_hash(self, lora_name):
        """Get the lora hash from cache"""
        scanner = ServiceRegistry.get_service_sync("lora_scanner")

        # Use the new direct filename lookup method
        if scanner is not None:
            hash_value = scanner.get_hash_by_filename(lora_name)
            if hash_value:
                return hash_value

        return None

    def get_checkpoint_hash(self, checkpoint_path):
        """Get the checkpoint hash from cache"""
        scanner = ServiceRegistry.get_service_sync("checkpoint_scanner")

        if not checkpoint_path:
            return None

        # Extract basename without extension
        checkpoint_name = os.path.basename(checkpoint_path)
        checkpoint_name = os.path.splitext(checkpoint_name)[0]

        # Try direct filename lookup first
        if scanner is not None:
            hash_value = scanner.get_hash_by_filename(checkpoint_name)
            if hash_value:
                return hash_value

        return None

    def format_metadata(self, metadata_dict):
        """Format metadata in the requested format similar to userComment example"""
        if not metadata_dict:
            return ""

        # Helper function to only add parameter if value is not None
        def add_param_if_not_none(param_list, label, value):
            if value is not None:
                param_list.append(f"{label}: {value}")

        # Extract the prompt and negative prompt
        prompt = metadata_dict.get("prompt", "")
        negative_prompt = metadata_dict.get("negative_prompt", "")

        # Extract loras from the prompt if present
        loras_text = metadata_dict.get("loras", "")
        lora_hashes = {}

        # If loras are found, add them on a new line after the prompt
        if loras_text:
            prompt_with_loras = f"{prompt}\n{loras_text}"

            # Extract lora names from the format <lora:name:strength>
            lora_matches = re.findall(r"<lora:([^:]+):([^>]+)>", loras_text)

            # Get hash for each lora
            for lora_name, strength in lora_matches:
                hash_value = self.get_lora_hash(lora_name)
                if hash_value:
                    lora_hashes[lora_name] = hash_value
        else:
            prompt_with_loras = prompt

        # Format the first part (prompt and loras)
        metadata_parts = [prompt_with_loras]

        # Add negative prompt
        if negative_prompt:
            metadata_parts.append(f"Negative prompt: {negative_prompt}")

        # Format the second part (generation parameters)
        params = []

        # Add standard parameters in the correct order
        if "steps" in metadata_dict:
            add_param_if_not_none(params, "Steps", metadata_dict.get("steps"))

        # Combine sampler and scheduler information
        sampler_name = None
        scheduler_name = None

        if "sampler" in metadata_dict:
            sampler = metadata_dict.get("sampler")
            # Convert ComfyUI sampler names to user-friendly names
            sampler_mapping = {
                "euler": "Euler",
                "euler_ancestral": "Euler a",
                "dpm_2": "DPM2",
                "dpm_2_ancestral": "DPM2 a",
                "heun": "Heun",
                "dpm_fast": "DPM fast",
                "dpm_adaptive": "DPM adaptive",
                "lms": "LMS",
                "dpmpp_2s_ancestral": "DPM++ 2S a",
                "dpmpp_sde": "DPM++ SDE",
                "dpmpp_sde_gpu": "DPM++ SDE",
                "dpmpp_2m": "DPM++ 2M",
                "dpmpp_2m_sde": "DPM++ 2M SDE",
                "dpmpp_2m_sde_gpu": "DPM++ 2M SDE",
                "ddim": "DDIM",
            }
            sampler_name = sampler_mapping.get(sampler, sampler)

        if "scheduler" in metadata_dict:
            scheduler = metadata_dict.get("scheduler")
            scheduler_mapping = {
                "normal": "Simple",
                "karras": "Karras",
                "exponential": "Exponential",
                "sgm_uniform": "SGM Uniform",
                "sgm_quadratic": "SGM Quadratic",
            }
            scheduler_name = scheduler_mapping.get(scheduler, scheduler)

        # Add combined sampler and scheduler information
        if sampler_name:
            if scheduler_name:
                params.append(f"Sampler: {sampler_name} {scheduler_name}")
            else:
                params.append(f"Sampler: {sampler_name}")

        # CFG scale (Use guidance if available, otherwise fall back to cfg_scale or cfg)
        if "guidance" in metadata_dict:
            add_param_if_not_none(params, "CFG scale", metadata_dict.get("guidance"))
        elif "cfg_scale" in metadata_dict:
            add_param_if_not_none(params, "CFG scale", metadata_dict.get("cfg_scale"))
        elif "cfg" in metadata_dict:
            add_param_if_not_none(params, "CFG scale", metadata_dict.get("cfg"))

        # Seed
        if "seed" in metadata_dict:
            add_param_if_not_none(params, "Seed", metadata_dict.get("seed"))

        # Size
        if "size" in metadata_dict:
            add_param_if_not_none(params, "Size", metadata_dict.get("size"))

        # Model info
        if "checkpoint" in metadata_dict:
            # Ensure checkpoint is a string before processing
            checkpoint = metadata_dict.get("checkpoint")
            if checkpoint is not None:
                # Get model hash
                model_hash = self.get_checkpoint_hash(checkpoint)

                # Extract basename without path
                checkpoint_name = os.path.basename(checkpoint)
                # Remove extension if present
                checkpoint_name = os.path.splitext(checkpoint_name)[0]

                # Add model hash if available
                if model_hash:
                    params.append(
                        f"Model hash: {model_hash[:10]}, Model: {checkpoint_name}"
                    )
                else:
                    params.append(f"Model: {checkpoint_name}")

        # Add LoRA hashes if available
        if lora_hashes:
            lora_hash_parts = []
            for lora_name, hash_value in lora_hashes.items():
                lora_hash_parts.append(f"{lora_name}: {hash_value[:10]}")

            if lora_hash_parts:
                params.append(f'Lora hashes: "{", ".join(lora_hash_parts)}"')

        # Combine all parameters with commas
        metadata_parts.append(", ".join(params))

        # Join all parts with a new line
        return "\n".join(metadata_parts)

    # credit to nkchocoai
    # Add format_filename method to handle pattern substitution
    def format_filename(self, filename, metadata_dict):
        """Format filename with metadata values"""
        if not metadata_dict:
            return filename

        result = re.findall(self.pattern_format, filename)
        for segment in result:
            parts = segment.replace("%", "").split(":")
            key = parts[0]

            if key == "seed" and "seed" in metadata_dict:
                filename = filename.replace(segment, str(metadata_dict.get("seed", "")))
            elif key == "width" and "size" in metadata_dict:
                size = metadata_dict.get("size", "x")
                w = size.split("x")[0] if isinstance(size, str) else size[0]
                filename = filename.replace(segment, str(w))
            elif key == "height" and "size" in metadata_dict:
                size = metadata_dict.get("size", "x")
                h = size.split("x")[1] if isinstance(size, str) else size[1]
                filename = filename.replace(segment, str(h))
            elif key == "pprompt" and "prompt" in metadata_dict:
                prompt = metadata_dict.get("prompt", "").replace("\n", " ")
                if len(parts) >= 2:
                    length = int(parts[1])
                    prompt = prompt[:length]
                filename = filename.replace(segment, prompt.strip())
            elif key == "nprompt" and "negative_prompt" in metadata_dict:
                prompt = metadata_dict.get("negative_prompt", "").replace("\n", " ")
                if len(parts) >= 2:
                    length = int(parts[1])
                    prompt = prompt[:length]
                filename = filename.replace(segment, prompt.strip())
            elif key == "model":
                model_value = metadata_dict.get("checkpoint")
                if isinstance(model_value, (bytes, os.PathLike)):
                    model_value = str(model_value)

                if not isinstance(model_value, str) or not model_value:
                    model = "model_unavailable"
                else:
                    model = os.path.splitext(os.path.basename(model_value))[0]
                if len(parts) >= 2:
                    length = int(parts[1])
                    model = model[:length]
                filename = filename.replace(segment, model)
            elif key == "date":
                from datetime import datetime

                now = datetime.now()
                date_table = {
                    "yyyy": f"{now.year:04d}",
                    "yy": f"{now.year % 100:02d}",
                    "MM": f"{now.month:02d}",
                    "dd": f"{now.day:02d}",
                    "hh": f"{now.hour:02d}",
                    "mm": f"{now.minute:02d}",
                    "ss": f"{now.second:02d}",
                }
                if len(parts) >= 2:
                    date_format = parts[1]
                    for k, v in date_table.items():
                        date_format = date_format.replace(k, v)
                    filename = filename.replace(segment, date_format)
                else:
                    date_format = "yyyyMMddhhmmss"
                    for k, v in date_table.items():
                        date_format = date_format.replace(k, v)
                    filename = filename.replace(segment, date_format)

        return filename

    @staticmethod
    def _get_cached_model_by_name(scanner, name):
        cache = getattr(scanner, "_cache", None)
        if cache is None or not name:
            return None

        candidates = [
            name,
            os.path.basename(name),
            os.path.splitext(os.path.basename(name))[0],
        ]
        for model in getattr(cache, "raw_data", []):
            file_name = model.get("file_name")
            if file_name in candidates:
                return model
        return None

    def _build_recipe_loras(self, recipe_scanner, lora_stack):
        lora_matches = re.findall(r"<lora:([^:]+):([^>]+)>", lora_stack or "")
        lora_scanner = getattr(recipe_scanner, "_lora_scanner", None)
        loras_data = []
        base_model_counts = {}

        for name, strength in lora_matches:
            lora_info = self._get_cached_model_by_name(lora_scanner, name)
            civitai = (lora_info or {}).get("civitai") or {}
            civitai_model = civitai.get("model") or {}
            try:
                parsed_strength = float(strength)
            except (TypeError, ValueError):
                parsed_strength = 1.0

            loras_data.append(
                {
                    "file_name": name,
                    "strength": parsed_strength,
                    "hash": ((lora_info or {}).get("sha256") or "").lower(),
                    "modelVersionId": civitai.get("id", 0),
                    "modelName": civitai_model.get("name", name) if lora_info else "",
                    "modelVersionName": civitai.get("name", "") if lora_info else "",
                    "isDeleted": False,
                    "exclude": False,
                }
            )

            base_model = (lora_info or {}).get("base_model")
            if base_model:
                base_model_counts[base_model] = base_model_counts.get(base_model, 0) + 1

        return lora_matches, loras_data, base_model_counts

    def _build_recipe_checkpoint(self, recipe_scanner, checkpoint_raw):
        if not isinstance(checkpoint_raw, str) or not checkpoint_raw.strip():
            return None

        checkpoint_name = checkpoint_raw.strip()
        file_name = os.path.splitext(os.path.basename(checkpoint_name))[0]
        checkpoint_scanner = getattr(recipe_scanner, "_checkpoint_scanner", None)
        checkpoint_info = self._get_cached_model_by_name(
            checkpoint_scanner, checkpoint_name
        )

        if not checkpoint_info:
            return {
                "type": "checkpoint",
                "name": checkpoint_name,
                "file_name": file_name,
                "hash": self.get_checkpoint_hash(checkpoint_name) or "",
            }

        civitai = checkpoint_info.get("civitai") or {}
        civitai_model = civitai.get("model") or {}
        file_path = checkpoint_info.get("file_path") or checkpoint_info.get("path") or ""
        cached_file_name = (
            checkpoint_info.get("file_name")
            or (os.path.splitext(os.path.basename(file_path))[0] if file_path else "")
            or file_name
        )

        return {
            "type": "checkpoint",
            "modelId": civitai_model.get("id", 0),
            "modelVersionId": civitai.get("id", 0),
            "name": civitai_model.get("name")
            or checkpoint_info.get("model_name")
            or checkpoint_name,
            "version": civitai.get("name", ""),
            "hash": (
                checkpoint_info.get("sha256") or checkpoint_info.get("hash") or ""
            ).lower(),
            "file_name": cached_file_name,
            "modelName": civitai_model.get("name", ""),
            "modelVersionName": civitai.get("name", ""),
            "baseModel": checkpoint_info.get("base_model")
            or civitai.get("baseModel", ""),
        }

    @staticmethod
    def _derive_recipe_name(lora_matches):
        recipe_name_parts = [
            f"{name.strip()}-{float(strength):.2f}" for name, strength in lora_matches[:3]
        ]
        return "_".join(recipe_name_parts) or "recipe"

    @staticmethod
    def _sync_recipe_cache(recipe_scanner, recipe_data, json_path):
        cache = getattr(recipe_scanner, "_cache", None)
        if cache is not None:
            cache.raw_data.append(recipe_data)
            cache.sorted_by_name = sorted(
                cache.raw_data, key=lambda item: item.get("title", "").lower()
            )
            cache.sorted_by_date = sorted(
                cache.raw_data,
                key=lambda item: (
                    item.get("modified", item.get("created_date", 0)),
                    item.get("file_path", ""),
                ),
                reverse=True,
            )
            recipe_scanner._update_folder_metadata(cache)
            recipe_scanner._update_fts_index_for_recipe(recipe_data, "add")

        recipe_id = str(recipe_data.get("id", ""))
        if recipe_id:
            recipe_scanner._json_path_map[recipe_id] = json_path
        persistent_cache = getattr(recipe_scanner, "_persistent_cache", None)
        if persistent_cache:
            persistent_cache.update_recipe(recipe_data, json_path)

    def _save_image_as_recipe(self, file_path, metadata_dict):
        if not metadata_dict:
            raise ValueError("No generation metadata found")

        recipe_scanner = ServiceRegistry.get_service_sync("recipe_scanner")
        if recipe_scanner is None:
            raise RuntimeError("Recipe scanner unavailable")

        recipes_dir = recipe_scanner.recipes_dir
        if not recipes_dir:
            raise RuntimeError("Recipes directory unavailable")
        os.makedirs(recipes_dir, exist_ok=True)

        recipe_id = str(uuid.uuid4())
        optimized_image, extension = ExifUtils.optimize_image(
            image_data=file_path,
            target_width=CARD_PREVIEW_WIDTH,
            format="webp",
            quality=85,
            preserve_metadata=True,
        )
        image_path = os.path.normpath(os.path.join(recipes_dir, f"{recipe_id}{extension}"))
        with open(image_path, "wb") as file_obj:
            file_obj.write(optimized_image)

        lora_stack = metadata_dict.get("loras", "")
        lora_matches, loras_data, base_model_counts = self._build_recipe_loras(
            recipe_scanner, lora_stack
        )
        checkpoint_entry = self._build_recipe_checkpoint(
            recipe_scanner, metadata_dict.get("checkpoint")
        )
        most_common_base_model = (
            max(base_model_counts.items(), key=lambda item: item[1])[0]
            if base_model_counts
            else ""
        )
        current_time = time.time()
        recipe_data = {
            "id": recipe_id,
            "file_path": image_path,
            "title": self._derive_recipe_name(lora_matches),
            "modified": current_time,
            "created_date": current_time,
            "base_model": most_common_base_model
            or (checkpoint_entry or {}).get("baseModel", ""),
            "loras": loras_data,
            "gen_params": {
                key: value
                for key, value in metadata_dict.items()
                if key not in ["checkpoint", "loras"]
            },
            "loras_stack": lora_stack,
            "fingerprint": calculate_recipe_fingerprint(loras_data),
        }
        if checkpoint_entry:
            recipe_data["checkpoint"] = checkpoint_entry

        json_path = os.path.normpath(
            os.path.join(recipes_dir, f"{recipe_id}.recipe.json")
        )
        with open(json_path, "w", encoding="utf-8") as file_obj:
            json.dump(recipe_data, file_obj, indent=4, ensure_ascii=False)

        ExifUtils.append_recipe_metadata(image_path, recipe_data)
        self._sync_recipe_cache(recipe_scanner, recipe_data, json_path)

    def save_images(
        self,
        images,
        filename_prefix,
        file_format,
        id,
        prompt=None,
        extra_pnginfo=None,
        lossless_webp=True,
        quality=100,
        embed_workflow=False,
        save_with_metadata=True,
        add_counter_to_filename=True,
        save_as_recipe=False,
    ):
        """Save images with metadata"""
        results = []

        # Get metadata using the metadata collector
        raw_metadata = get_metadata()
        metadata_dict = MetadataProcessor.to_dict(raw_metadata, id)

        metadata = self.format_metadata(metadata_dict)

        # Process filename_prefix with pattern substitution
        filename_prefix = self.format_filename(filename_prefix, metadata_dict)

        # Get initial save path info once for the batch
        full_output_folder, filename, counter, subfolder, processed_prefix = (
            folder_paths.get_save_image_path(
                filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0]
            )
        )

        # Create directory if it doesn't exist
        if not os.path.exists(full_output_folder):
            os.makedirs(full_output_folder, exist_ok=True)

        # Process each image with incrementing counter
        for i, image in enumerate(images):
            # Convert the tensor image to numpy array
            img = 255.0 * image.cpu().numpy()
            img = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))

            # Generate filename with counter if needed
            base_filename = filename
            if add_counter_to_filename:
                # Use counter + i to ensure unique filenames for all images in batch
                current_counter = counter + i
                base_filename += f"_{current_counter:05}_"

            # Set file extension and prepare saving parameters
            file: str
            save_kwargs: Dict[str, Any]
            pnginfo: Optional[PngImagePlugin.PngInfo] = None
            if file_format == "png":
                file = base_filename + ".png"
                file_extension = ".png"
                # Remove "optimize": True to match built-in node behavior
                save_kwargs = {"compress_level": self.compress_level}
                pnginfo = PngImagePlugin.PngInfo()
            elif file_format == "jpeg":
                file = base_filename + ".jpg"
                file_extension = ".jpg"
                save_kwargs = {"quality": quality, "optimize": True}
            elif file_format == "webp":
                file = base_filename + ".webp"
                file_extension = ".webp"
                # Add optimization param to control performance
                save_kwargs = {
                    "quality": quality,
                    "lossless": lossless_webp,
                    "method": 0,
                }
            else:
                raise ValueError(f"Unsupported file format: {file_format}")

            # Full save path
            file_path = os.path.join(full_output_folder, file)

            # Save the image with metadata
            try:
                if file_format == "png":
                    assert pnginfo is not None
                    if save_with_metadata and metadata:
                        pnginfo.add_text("parameters", metadata)
                    if embed_workflow and extra_pnginfo is not None:
                        workflow_json = json.dumps(extra_pnginfo["workflow"])
                        pnginfo.add_text("workflow", workflow_json)
                    save_kwargs["pnginfo"] = pnginfo
                    img.save(file_path, format="PNG", **save_kwargs)
                elif file_format == "jpeg":
                    # For JPEG, use piexif
                    if save_with_metadata and metadata:
                        try:
                            exif_dict = {
                                "Exif": {
                                    piexif.ExifIFD.UserComment: b"UNICODE\0"
                                    + metadata.encode("utf-16be")
                                }
                            }
                            exif_bytes = piexif.dump(exif_dict)
                            save_kwargs["exif"] = exif_bytes
                        except Exception as e:
                            logger.error(f"Error adding EXIF data: {e}")
                    img.save(file_path, format="JPEG", **save_kwargs)
                elif file_format == "webp":
                    try:
                        # For WebP, use piexif for metadata
                        exif_dict = {}

                        if save_with_metadata and metadata:
                            exif_dict["Exif"] = {
                                piexif.ExifIFD.UserComment: b"UNICODE\0"
                                + metadata.encode("utf-16be")
                            }

                        # Add workflow if needed
                        if embed_workflow and extra_pnginfo is not None:
                            workflow_json = json.dumps(extra_pnginfo["workflow"])
                            exif_dict["0th"] = {
                                piexif.ImageIFD.ImageDescription: "Workflow:"
                                + workflow_json
                            }

                        exif_bytes = piexif.dump(exif_dict)
                        save_kwargs["exif"] = exif_bytes
                    except Exception as e:
                        logger.error(f"Error adding EXIF data: {e}")

                    img.save(file_path, format="WEBP", **save_kwargs)

                if save_as_recipe:
                    try:
                        self._save_image_as_recipe(file_path, metadata_dict)
                    except Exception as e:
                        logger.warning(
                            "Failed to save image as recipe: %s", e, exc_info=True
                        )

                results.append(
                    {"filename": file, "subfolder": subfolder, "type": self.type}
                )

            except Exception as e:
                logger.error(f"Error saving image: {e}")

        return results

    def process_image(
        self,
        images,
        id,
        filename_prefix="ComfyUI",
        file_format="png",
        prompt=None,
        extra_pnginfo=None,
        lossless_webp=True,
        quality=100,
        embed_workflow=False,
        save_with_metadata=True,
        add_counter_to_filename=True,
        save_as_recipe=False,
    ):
        """Process and save image with metadata"""
        # Make sure the output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

        # If images is already a list or array of images, do nothing; otherwise, convert to list
        if isinstance(images, (list, np.ndarray)):
            pass
        else:
            # Ensure images is always a list of images
            if len(images.shape) == 3:  # Single image (height, width, channels)
                images = [images]
            else:  # Multiple images (batch, height, width, channels)
                images = [img for img in images]

        # Save all images
        results = self.save_images(
            images,
            filename_prefix,
            file_format,
            id,
            prompt,
            extra_pnginfo,
            lossless_webp,
            quality,
            embed_workflow,
            save_with_metadata,
            add_counter_to_filename,
            save_as_recipe,
        )

        return {
            "result": (images,),
            "ui": {"images": results},
        }
