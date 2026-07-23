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
from ..utils.utils import calculate_recipe_fingerprint, sanitize_folder_name
from PIL import Image, PngImagePlugin
import piexif
import logging

# Civitai-compatible sampler name mapping: ComfyUI internal → A1111 display name
CIVITAI_SAMPLER_MAP = {
    "euler": "Euler",
    "euler_ancestral": "Euler a",
    "lms": "LMS",
    "heun": "Heun",
    "dpm_2": "DPM2",
    "dpm_2_ancestral": "DPM2 a",
    "dpmpp_2s_ancestral": "DPM++ 2S a",
    "dpmpp_2m": "DPM++ 2M",
    "dpmpp_sde": "DPM++ SDE",
    "dpmpp_sde_gpu": "DPM++ SDE",
    "dpmpp_2m_sde": "DPM++ 2M SDE",
    "dpmpp_2m_sde_gpu": "DPM++ 2M SDE",
    "dpmpp_3m_sde": "DPM++ 3M SDE",
    "dpm_fast": "DPM fast",
    "dpm_adaptive": "DPM adaptive",
    "ddim": "DDIM",
    "plms": "PLMS",
    "uni_pc_bh2": "UniPC",
    "uni_pc": "UniPC",
    "lcm": "LCM",
}

# Base model display name → AIR URN slug
# Sourced from civitai source: src/shared/constants/basemodel.constants.ts
BASE_MODEL_AIR_SLUG = {
    # Stable Diffusion family
    "SD 1.4": "sd1",
    "SD 1.5": "sd1",
    "SD 1.5 LCM": "sd1",
    "SD 1.5 Hyper": "sd1",
    "SD 2.0": "sd2",
    "SD 2.0 768": "sd2",
    "SD 2.1": "sd2",
    "SD 2.1 768": "sd2",
    "SD 2.1 Unclip": "sd2",
    "SD 3.0": "sd3",
    "SD 3.5": "sd35",
    "SD 3.5 Large": "sd35",
    "SD 3.5 Large Turbo": "sd35",
    "SD 3.5 Medium": "sd35",
    "SDXL 0.9": "sdxl",
    "SDXL 1.0": "sdxl",
    "SDXL 1.0 LCM": "sdxl",
    "SDXL Lightning": "sdxl",
    "SDXL Hyper": "sdxl",
    "SDXL Turbo": "sdxl",
    "SDXL Distilled": "sdxldistilled",
    "Stable Cascade": "scascade",
    "Stable Video Diffusion": "svd",
    "SVD": "svd",
    "SVD XT": "svdxt",

    # SDXL community fine-tunes
    "Pony": "pony",
    "Pony Diffusion": "pony",
    "Illustrious": "illustrious",
    "NoobAI": "noobai",
    "Animagine": "illustrious",

    # Flux family
    "Flux.1": "flux1",
    "Flux.1 D": "flux1",
    "Flux.1 S": "flux1",
    "Flux.1 Krea": "fluxkrea",
    "Flux.1 Kontext": "flux1kontext",
    "Flux.2": "flux2",
    "Flux.2 D": "flux2",
    "Flux.2 Klein 9B": "flux2klein_9b",
    "Flux.2 Klein 9B Base": "flux2klein_9b_base",
    "Flux.2 Klein 4B": "flux2klein_4b",
    "Flux.2 Klein 4B Base": "flux2klein_4b_base",

    # Other image models (sorted alphabetically)
    "AuraFlow": "auraflow",
    "Chroma": "chroma",
    "HiDream": "hidream",
    "HiDream-O1": "hidream-o1",
    "Hunyuan DiT": "hydit1",
    "Hunyuan Video": "hyv1",
    "Kolors": "kolors",
    "Lumina": "lumina",
    "Mochi": "mochi",
    "ODOR": "odor",
    "PixArt Alpha": "pixarta",
    "PixArt Sigma": "pixarte",
    "Playground v2": "playgroundv2",
    "Playground v2.5": "playgroundv2",
    "Pony Diffusion V7": "ponyv7",

    # Video models
    "CogVideoX": "cogvideox",
    "LTX Video": "ltxv",
    "LTX Video 2": "ltxv2",
    "LTX Video 2.3": "ltxv23",
    "Wan Video": "wanvideo",
    "Wan Video 1.3B T2V": "wanvideo_13b_t2v",
    "Wan Video 14B T2V": "wanvideo_14b_t2v",
    "Wan Video 14B I2V 480p": "wanvideo_14b_i2v_480p",
    "Wan Video 14B I2V 720p": "wanvideo_14b_i2v_720p",

    # Third-party / proprietary image models
    "Boogu": "boogu",
    "Ernie": "ernie",
    "Grok": "grok",
    "HappyHorse": "happyhorse",
    "Ideogram": "ideogram",
    "Ideogram 4.0": "ideogram",
    "Imagen": "imagen4",
    "Imagen 4": "imagen4",
    "Krea": "krea2",
    "Krea 2": "krea2",
    "Lens": "lens",
    "MAI": "mai",
    "Nano Banana": "nanobanana",
    "OpenAI": "openai",
    "Reve": "reve",
    "Reve 2": "reve",
    "Reve 2.1": "reve",
    "Seedream": "seedream",
    "Sora": "sora2",
    "Sora 2": "sora2",
    "Veo": "veo3",
    "Veo 2": "veo3",
    "Veo 3": "veo3",
    "ZImageTurbo": "zimageturbo",
    "ZImageBase": "zimagebase",
    "ZImage": "zimagebase",

    # Third-party video models
    "Hailuo by MiniMax": "minimax",
    "Haiper": "haiper",
    "Kling": "kling",
    "Lightricks": "lightricks",
    "Seedance": "seedance",
    "Vidu": "vidu",

    # Qwen family
    "Qwen": "qwen",
    "Qwen 2": "qwen2",

    # Anima
    "Anima": "anima",

    # Special
    "Upscaler": "upscaler",
    "Other": "other",
}

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

    def _resolve_model_cache_entry(self, scanner_type: str, name: str):
        """Resolve model hash, civitai metadata, and base_model from scanner cache.
        Returns (hash_str, civitai_dict, base_model_str). All values are empty defaults when not found."""
        scanner = ServiceRegistry.get_service_sync(scanner_type)
        if scanner is None or not name:
            return "", {}, ""

        entry = self._get_cached_model_by_name(scanner, name)
        if entry is None:
            basename = os.path.splitext(os.path.basename(name))[0]
            hash_val = scanner.get_hash_by_filename(basename)
            return (hash_val or "").lower(), {}, ""

        hash_val = (entry.get("sha256") or "").lower()
        civitai = entry.get("civitai") or {}
        base_model = entry.get("base_model") or ""
        return hash_val, civitai, base_model

    @staticmethod
    def _get_civitai_sampler_name(sampler_name: str, scheduler: str) -> str:
        if sampler_name in CIVITAI_SAMPLER_MAP:
            civitai_name = CIVITAI_SAMPLER_MAP[sampler_name]
            if scheduler == "karras":
                civitai_name += " Karras"
            elif scheduler == "exponential":
                civitai_name += " Exponential"
            return civitai_name
        else:
            if scheduler and scheduler != "normal":
                return f"{sampler_name}_{scheduler}"
            return sampler_name

    @staticmethod
    def _build_air_string(base_model: str, model_type: str, model_id: int, version_id: int) -> str:
        slug = BASE_MODEL_AIR_SLUG.get(base_model, "other")
        type_lower = model_type.lower() if model_type else "other"
        return f"urn:air:{slug}:{type_lower}:civitai:{model_id}@{version_id}"

    def format_metadata(self, metadata_dict: dict) -> str:
        """Format metadata as A1111-compatible parameters string with Hashes JSON and Civitai resources."""
        if not metadata_dict: return ""

        prompt = metadata_dict.get("prompt", "")
        negative_prompt = metadata_dict.get("negative_prompt", "")
        steps = metadata_dict.get("steps")
        cfg = metadata_dict.get("guidance")
        if cfg is None:
            cfg = metadata_dict.get("cfg_scale")
        if cfg is None:
            cfg = metadata_dict.get("cfg")
        seed = metadata_dict.get("seed")
        size = metadata_dict.get("size")
        sampler = metadata_dict.get("sampler") or ""
        scheduler = metadata_dict.get("scheduler") or "normal"
        checkpoint = metadata_dict.get("checkpoint") or ""
        loras_text = metadata_dict.get("loras", "")
        clip_skip = metadata_dict.get("clip_skip")

        # Parse LoRA entries from <lora:name:strength> format
        lora_entries: list[tuple[str, float]] = []
        if loras_text:
            for match in re.findall(r"<lora:([^:]+):([^>]+)>", loras_text):
                lora_name, strength_str = match
                try:
                    strength = float(strength_str)
                except (ValueError, TypeError):
                    strength = 1.0
                lora_entries.append((lora_name, strength))

        # Resolve checkpoint hash and Civitai data from local cache
        ckpt_hash, ckpt_civitai, ckpt_base_model = "", {}, ""
        ckpt_display_name = ""
        if checkpoint:
            ckpt_hash, ckpt_civitai, ckpt_base_model = self._resolve_model_cache_entry(
                "checkpoint_scanner", checkpoint
            )
            ckpt_display_name = os.path.splitext(os.path.basename(checkpoint))[0]

        # Resolve LoRA hash and Civitai data from local cache
        loras_data: list[dict] = []
        for lora_name, strength in lora_entries:
            lora_hash, lora_civitai, lora_base_model = self._resolve_model_cache_entry(
                "lora_scanner", lora_name
            )
            loras_data.append({
                "name": lora_name,
                "strength": strength,
                "hash": lora_hash,
                "civitai": lora_civitai,
                "base_model": lora_base_model,
            })

        # Build Hashes JSON (A1111 / Civitai standard format)
        hashes: dict[str, str] = {}
        if ckpt_hash:
            hashes["model"] = ckpt_hash[:10].upper()
        for lora in loras_data:
            if lora["hash"]:
                hashes[f"LORA:{lora['name']}"] = lora["hash"][:10].upper()

        # Build Civitai resources JSON array
        civitai_resources: list[dict] = []
        if ckpt_civitai.get("id", 0) > 0:
            ckpt_resource: dict = {}
            ckpt_type = (ckpt_civitai.get("model") or {}).get("type", "Checkpoint")
            model_id = ckpt_civitai.get("modelId", 0)
            version_id = ckpt_civitai.get("id", 0)
            if model_id and version_id:
                ckpt_resource["air"] = self._build_air_string(
                    ckpt_base_model, ckpt_type, int(model_id), int(version_id)
                )
            elif version_id:
                ckpt_resource["modelVersionId"] = int(version_id)
            if ckpt_civitai.get("name"):
                ckpt_resource["versionName"] = ckpt_civitai["name"]
            if ckpt_resource:
                civitai_resources.append(ckpt_resource)

        for lora in loras_data:
            lora_civitai = lora["civitai"]
            if not lora_civitai or lora_civitai.get("id", 0) <= 0:
                continue
            lora_resource: dict = {"weight": lora["strength"]}
            lora_type = (lora_civitai.get("model") or {}).get("type", "LORA")
            model_id = lora_civitai.get("modelId", 0)
            version_id = lora_civitai.get("id", 0)
            if model_id and version_id:
                lora_resource["air"] = self._build_air_string(
                    lora["base_model"], lora_type, int(model_id), int(version_id)
                )
            elif version_id:
                lora_resource["modelVersionId"] = int(version_id)
            if lora_civitai.get("name"):
                lora_resource["versionName"] = lora_civitai["name"]
            civitai_resources.append(lora_resource)

        sampler_display = self._get_civitai_sampler_name(sampler, scheduler)

        # Build output lines
        lines = [prompt] if prompt else [""]
        if negative_prompt:
            lines.append(f"Negative prompt: {negative_prompt}")

        params: list[str] = []
        if steps is not None:
            params.append(f"Steps: {steps}")
        if sampler_display:
            params.append(f"Sampler: {sampler_display}")
        if cfg is not None:
            params.append(f"CFG scale: {cfg}")
        if seed is not None:
            params.append(f"Seed: {seed}")
        if size:
            params.append(f"Size: {size}")
        if clip_skip:
            try:
                cs = int(clip_skip)
                if cs != 0:
                    params.append(f"Clip skip: {abs(cs)}")
            except (ValueError, TypeError):
                pass
        if ckpt_hash:
            params.append(f"Model hash: {ckpt_hash[:10].upper()}")
        if ckpt_display_name:
            params.append(f"Model: {ckpt_display_name}")
        if hashes:
            params.append(f"Hashes: {json.dumps(hashes, separators=(',', ':'))}")
        params.append("Version: ComfyUI")
        if civitai_resources:
            params.append(
                f"Civitai resources: {json.dumps(civitai_resources, separators=(',', ':'))}"
            )

        lines.append(", ".join(params))
        return "\n".join(lines)

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
                seed_value = metadata_dict.get("seed")
                if seed_value is not None:
                    filename = filename.replace(segment, str(seed_value))
                else:
                    # Fallback if seed was not captured by metadata collector
                    filename = filename.replace(segment, "0")
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
                prompt = sanitize_folder_name(prompt)
                if len(parts) >= 2:
                    length = int(parts[1])
                    prompt = prompt[:length]
                filename = filename.replace(segment, prompt.strip())
            elif key == "nprompt" and "negative_prompt" in metadata_dict:
                prompt = metadata_dict.get("negative_prompt", "").replace("\n", " ")
                prompt = sanitize_folder_name(prompt)
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
                    model = sanitize_folder_name(model)
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
            base_filename = filename.replace("%batch_num%", str(i))
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
