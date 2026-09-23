"""Load an image and expose locally resolved generation settings."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import folder_paths  # pyright: ignore[reportMissingImports]

from ..utils.exif_utils import ExifUtils
from ..utils.generation_metadata import (
    GenerationMetadata,
    MetadataError,
    extract_generation_metadata,
    finite_number,
    split_lora_tags,
)
from ..utils.utils import _format_model_name_for_comfyui
from .checkpoint_loader import CheckpointLoaderLM


DEFAULTS = {
    "positive": "", "negative": "", "seed": 0, "steps": 20, "cfg": 7.0,
    "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
}
# An SDXL-sized starter preset inspired by ComfyUI's bottle example. These
# values are explicitly synthetic, never presented as recovered metadata.
EMPTY_IMAGE_DEFAULTS = {
    **DEFAULTS,
    "positive": "beautiful scenery inside a glass bottle, purple galaxy, intricate miniature landscape, highly detailed",
    "negative": "text, watermark",
    "width": 1024,
    "height": 1024,
}
ALLOWED_OVERRIDES = set(DEFAULTS) | {"model_name", "checkpoint_name", "unet_name", "width", "height", "loras"}


def parse_overrides(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except ValueError as exc:
        raise MetadataError(f"Invalid overrides_json: {exc}") from exc
    if not isinstance(value, dict):
        raise MetadataError("overrides_json must be an object")
    unknown = set(value) - ALLOWED_OVERRIDES
    if unknown:
        raise MetadataError(f"Unknown override keys: {', '.join(sorted(unknown))}")
    model_keys = [key for key in ("model_name", "checkpoint_name", "unet_name") if key in value]
    if len(model_keys) > 1:
        raise MetadataError("Specify only one model_name override (checkpoint_name/unet_name are legacy aliases)")
    if model_keys:
        key = model_keys[0]
        name = value.pop(key)
        if not isinstance(name, str) or not name.strip():
            raise MetadataError("model_name override must be nonempty text")
        value["model_name"] = name.strip()
    return value


_MODEL_FILE_EXTENSIONS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf")


def _model_stem(name: str) -> str:
    """Remove a known file extension, retaining dots in model/version names."""
    for extension in _MODEL_FILE_EXTENSIONS:
        if name.lower().endswith(extension):
            return name[:-len(extension)]
    return name


def resolve_resource(name: str, resources: list[dict[str, Any]], roots: list[str]) -> dict[str, Any]:
    """Match paths, filenames, then exact catalog aliases; never fuzzy-match."""
    if not isinstance(name, str) or not name.strip():
        raise MetadataError("Missing model name")
    normalized = name.strip().replace("\\", "/")
    levels: list[list[dict[str, Any]]] = [[], [], [], []]
    for item in resources:
        file_path = item.get("file_path")
        if not file_path:
            continue
        path = file_path.replace("\\", "/")
        relative = _format_model_name_for_comfyui(file_path, roots).replace("\\", "/")
        exact = normalized in (path, relative, _model_stem(path), _model_stem(relative))
        basename = normalized.rsplit("/", 1)[-1] == path.rsplit("/", 1)[-1]
        stem = _model_stem(normalized.rsplit("/", 1)[-1]) == _model_stem(path.rsplit("/", 1)[-1])
        aliases = [item.get("file_name"), item.get("model_name")]
        alias = any(
            isinstance(value, str) and normalized in (value.strip(), _model_stem(value.strip()))
            for value in aliases
        )
        # Stat only plausible matches, not every file in a large library for
        # each LoRA. Missing cached files must never win a match.
        if not (exact or basename or stem or alias) or not os.path.isfile(file_path):
            continue
        if exact:
            levels[0].append(item)
        if basename:
            levels[1].append(item)
        if stem:
            levels[2].append(item)
        if alias:
            levels[3].append(item)
    for matches in levels:
        unique = {os.path.abspath(item["file_path"]): item for item in matches}
        if len(unique) == 1:
            return next(iter(unique.values()))
        if unique:
            raise MetadataError(f"Ambiguous local model '{name}': {', '.join(unique)}. Specify its relative path in overrides_json.")
    raise MetadataError(f"Model '{name}' could not be matched to an existing file in the local LoRA Manager catalog")


class LoadImageMetadataLM:
    NAME = "Load Image Metadata (LoraManager)"
    CATEGORY = "Lora Manager/loaders"
    DESCRIPTION = (
        "Load an image and recover prompts, LoRAs and sampling settings from its metadata. "
        "Connect lora_stack to Lora Loader. Convert loader/sampler widgets to inputs for the other outputs. "
        "Extraction failures use starter defaults and are shown as ERROR messages in readable_report."
    )
    RETURN_TYPES = (
        "IMAGE", "MASK", "STRING", "STRING", "COMBO", "LORA_STACK", "STRING",
        "INT", "INT", "FLOAT", "COMBO", "COMBO", "INT", "INT", "FLOAT", "STRING", "STRING", "STRING",
    )
    RETURN_NAMES = (
        "image", "mask", "positive", "negative", "model_name", "lora_stack", "lora_stack_text",
        "seed", "steps", "cfg", "sampler_name", "scheduler", "width", "height", "denoise", "report", "readable_report", "missing_files",
    )
    FUNCTION = "load_metadata"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        from nodes import LoadImage  # pyright: ignore[reportMissingImports]

        return {"required": {
            "image": LoadImage.INPUT_TYPES()["required"]["image"],
            "sampler_node_id": ("STRING", {"default": "", "tooltip": "Leave empty for a single sampler. Subgraphs: use the full API ID, e.g. 1481:1783 (or 1481/1783). A container or leaf ID works only when unique."}),
            "missing_settings": (["use_defaults", "strict"], {"tooltip": "Extraction errors always return defaults and an ERROR report, including for saved strict settings. Unresolved files are listed in missing_files."}),
            "overrides_json": ("STRING", {"default": "{}", "multiline": True, "dynamicPrompts": False, "tooltip": 'Explicit replacements, e.g. {"scheduler":"normal", "model_name":"folder/model.safetensors"}. Use "loras": [] to clear the recovered stack.'}),
            "prefer_saved_image_metadata": ("BOOLEAN", {"default": True, "tooltip": "Prefer saved A1111-style generation parameters. Disable to select an active workflow sampler; muted/bypassed samplers are excluded."}),
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, image: str, **kwargs: Any) -> bool | str:
        if not folder_paths.exists_annotated_filepath(image):
            return f"Invalid image file: {image}"
        return True

    @classmethod
    def IS_CHANGED(cls, image: str, **kwargs: Any) -> str:
        digest = hashlib.sha256()
        with open(folder_paths.get_annotated_filepath(image), "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _source_diagnostics(path: str) -> str:
        """Describe the actual selected file without including prompt contents."""
        from PIL import Image

        try:
            with Image.open(path) as source:
                if source.format == "PNG":
                    source.load()
                details = (
                    f"File: {path}\nFormat: {source.format}; "
                    f"size: {os.path.getsize(path)} bytes; "
                    f"metadata keys: {', '.join(sorted(source.info)) or '(none)'}"
                )
            return details
        except (OSError, ValueError) as exc:
            return f"File: {path}\nCould not inspect image metadata: {exc}"

    @staticmethod
    def _library() -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], list[str]]:
        from ..services.service_registry import ServiceRegistry

        async def snapshot() -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], list[str]]:
            models = await ServiceRegistry.get_checkpoint_scanner()
            loras = await ServiceRegistry.get_lora_scanner()
            model_cache = await models.get_cached_data()
            lora_cache = await loras.get_cached_data()
            return list(model_cache.raw_data), models.get_model_roots(), list(lora_cache.raw_data), loras.get_model_roots()

        return CheckpointLoaderLM._run_async(snapshot)

    def load_metadata(
        self, image: str, sampler_node_id: str = "", missing_settings: str = "use_defaults",
        overrides_json: str = "{}", prefer_saved_image_metadata: bool = True,
    ) -> tuple[Any, ...]:
        import comfy.samplers  # pyright: ignore[reportMissingImports]
        from nodes import LoadImage  # pyright: ignore[reportMissingImports]

        overrides = parse_overrides(overrides_json)
        if missing_settings not in ("strict", "use_defaults"):
            raise MetadataError("Invalid missing_settings policy")
        path = folder_paths.get_annotated_filepath(image)
        pixels, mask = LoadImage().load_image(image)
        fields = {}
        no_metadata = False
        try:
            fields = ExifUtils._load_structured_metadata(path)
            no_metadata = not any(fields.values())
            if no_metadata:
                extracted = GenerationMetadata(
                    values=dict(EMPTY_IMAGE_DEFAULTS),
                    notes=[
                        "ERROR: No generation metadata found. Using the SDXL bottle starter preset; these settings were not extracted from the image.",
                        self._source_diagnostics(path),
                    ],
                )
            else:
                extracted = extract_generation_metadata(fields, sampler_node_id, prefer_saved_image_metadata)
        except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
            error = f"ERROR: Metadata extraction failed: {exc}"
            extracted = GenerationMetadata(issues={"source": str(exc)})
            # An unsupported API graph need not make valid saved generation
            # parameters unusable. Do not execute or infer custom graph nodes.
            if (fields.get("prompt") or fields.get("workflow")) and (fields.get("parameters") or fields.get("comment")):
                try:
                    extracted = extract_generation_metadata({
                        "parameters": fields.get("parameters"), "comment": fields.get("comment"),
                    })
                    extracted.notes.append(error + "; recovered saved generation parameters instead.")
                    if sampler_node_id.strip():
                        extracted.notes.append("ERROR: Global saved parameters cannot verify the requested sampler stage; they are an image-level fallback.")
                except (ValueError, TypeError, KeyError, RecursionError) as fallback_exc:
                    extracted.notes.append(f"ERROR: Parameter fallback failed: {fallback_exc}")
            if "source" in extracted.issues:
                extracted.notes.extend([error, self._source_diagnostics(path)])
        source_resources = {"checkpoint_name": extracted.values.get("checkpoint_name"), "unet_name": extracted.values.get("unet_name"), "loras": list(extracted.loras), "resource_hints": extracted.resource_hints}
        values = extracted.values
        notes = extracted.notes
        for key, value in overrides.items():
            values[key] = value
            extracted.issues.pop(key, None)
            notes.append(f"Explicit override: {key}.")
        if "model_name" in overrides:
            extracted.issues.pop("model", None)
            values.pop("checkpoint_name", None)
            values.pop("unet_name", None)
        if "loras" in overrides:
            extracted.loras = self._override_loras(overrides["loras"])
        notes.extend(f"ERROR: {key}: {message}" for key, message in extracted.issues.items())
        # Discard incomplete graph results instead of outputting half a LoRA
        # chain or a prompt known to differ from its conditioning.
        for key in extracted.issues:
            if key not in overrides:
                values.pop(key, None)
        if "loras" in extracted.issues and "loras" not in overrides:
            extracted.loras = []
        if "model" in extracted.issues and "model_name" not in overrides:
            values.pop("checkpoint_name", None)
            values.pop("unet_name", None)
        # Extraction without a recognized latent source (e.g. img2img) leaves
        # width/height unset; the source image dimensions are the best
        # estimate then. The synthetic starter preset keeps its fixed size.
        image_fallback = not no_metadata and "source" not in extracted.issues
        try:
            image_height, image_width = int(pixels.shape[1]), int(pixels.shape[2])
        except (AttributeError, IndexError, TypeError, ValueError):
            image_fallback = False
        for key, default in EMPTY_IMAGE_DEFAULTS.items():
            if key in values:
                continue
            if image_fallback and key in ("width", "height"):
                values[key] = image_width if key == "width" else image_height
                notes.append(f"WARNING Missing {key}; using source image dimension {values[key]}.")
            else:
                values[key] = default
                notes.append(f"ERROR: Missing {key}; using default {default!r}.")
        # Validate independently so one invalid value cannot erase the other
        # successfully extracted settings. Invalid explicit overrides still
        # identify a user configuration error rather than an extraction error.
        for key in EMPTY_IMAGE_DEFAULTS:
            trial = {**EMPTY_IMAGE_DEFAULTS, key: values[key]}
            try:
                self._validate_values(trial, comfy.samplers.KSampler.SAMPLERS, comfy.samplers.KSampler.SCHEDULERS, True, [])
                values[key] = trial[key]
            except (ValueError, TypeError, OverflowError) as exc:
                if key in overrides:
                    raise MetadataError(f"Invalid override {key}: {exc}") from exc
                values[key] = EMPTY_IMAGE_DEFAULTS[key]
                notes.append(f"ERROR: Invalid {key}: {exc}; using default {values[key]!r}.")
        # Only A1111 directives represent LoRA application. In ComfyUI graphs,
        # literal tags in encoder text are not executed by CLIPTextEncode.
        for key in ("positive", "negative"):
            try:
                clean, tags = split_lora_tags(values[key])
            except (ValueError, TypeError) as exc:
                if key in overrides:
                    raise MetadataError(f"Invalid override {key}: {exc}") from exc
                values[key] = EMPTY_IMAGE_DEFAULTS[key]
                notes.append(f"ERROR: Invalid LoRA directive in {key}: {exc}; using starter prompt.")
                continue
            if tags:
                if notes and notes[0] == "A1111/Forge parameters.":
                    if "loras" not in overrides:
                        extracted.loras.extend(tags)
                    values[key] = clean
                else:
                    notes.append(f"Literal LoRA tags retained in {key}; the embedded ComfyUI graph determines the stack.")
        try:
            models, roots, loras, lora_roots = self._library()
        except Exception as exc:
            models, roots, loras, lora_roots = [], [], [], []
            notes.append(f"ERROR: Local library lookup failed: {exc}. Extracted names remain in source_resources.")
        if (no_metadata or "source" in extracted.issues) and "model_name" not in overrides:
            base_candidates = [
                item for item in models
                if item.get("sub_type") == "checkpoint"
                and os.path.basename(item.get("file_path", "")).lower() == "sd_xl_base_1.0.safetensors"
                and os.path.isfile(item["file_path"])
            ]
            if len(base_candidates) == 1:
                values["model_name"] = _format_model_name_for_comfyui(base_candidates[0]["file_path"], roots)
                notes.append("Starter checkpoint: indexed sd_xl_base_1.0.safetensors.")
            else:
                notes.append("Select an SDXL checkpoint manually, or set model_name in overrides_json. No unambiguous SDXL base checkpoint was found.")
        missing_entries = []
        name = values.get("model_name") or values.get("checkpoint_name") or values.get("unet_name")
        values.pop("checkpoint_name", None)
        values.pop("unet_name", None)
        values["model_name"] = ""
        values["model_type"] = ""
        if name:
            try:
                # A1111's generic Model label can refer to either category.
                # Search both together so duplicate names remain ambiguous.
                available_models = [item for item in models if item.get("sub_type") in ("checkpoint", "diffusion_model")]
                item = resolve_resource(name, available_models, roots)
                values["model_name"] = _format_model_name_for_comfyui(item["file_path"], roots)
                values["model_type"] = item["sub_type"]
                notes.append(f"Resolved model_name: {values['model_name']} ({values['model_type']}).")
            except MetadataError as exc:
                missing_entries.append(f"Model: {name} — {exc}")
                notes.append(f"WARNING {exc}; model_name is empty.")
        if not values["model_name"]:
            notes.append("WARNING No model resolved. Select a model manually on your loader.")
        stack = []
        for name, model_strength, clip_strength in extracted.loras:
            try:
                item = resolve_resource(name, loras, lora_roots)
                stack.append((os.path.abspath(item["file_path"]), model_strength, clip_strength))
            except MetadataError as exc:
                missing_entries.append(f"LoRA: {name} | model weight: {model_strength:g} | CLIP weight: {clip_strength:g} — {exc}")
                notes.append(f"WARNING Skipped LoRA: {exc}.")
        notes.append(f"Resolved {len(stack)} LoRA entries; preserve stack order and avoid adding them again in the loader widget.")
        notes.append("Metadata settings do not restore VAE, text encoders, ControlNet, regional conditioning or the original latent pipeline.")
        lora_stack_text = "\n".join(
            f"{path} | model weight: {model_strength:g} | CLIP weight: {clip_strength:g}"
            for path, model_strength, clip_strength in stack
        )
        missing_files = "\n".join(missing_entries)
        report = "\n".join(notes) + "\n\n" + json.dumps({**values, "loras": stack, "lora_stack_text": lora_stack_text, "source_resources": source_resources, "missing_files": missing_files}, ensure_ascii=False, indent=2)
        readable_report = self._readable_report(image, values, extracted.loras, stack, source_resources, notes)
        return (pixels, mask, values["positive"], values["negative"], values["model_name"],
                stack, lora_stack_text, values["seed"], values["steps"],
                values["cfg"], values["sampler_name"], values["scheduler"], values["width"],
                values["height"], values["denoise"], report, readable_report, missing_files)

    @staticmethod
    def _readable_report(
        image: str, values: dict[str, Any], requested_loras: list[tuple[str, float, float]],
        stack: list[tuple[str, float, float]], source: dict[str, Any], notes: list[str],
    ) -> str:
        errors = [note for note in notes if note.startswith("ERROR")]
        lines = ["🖼️ IMAGE GENERATION SETTINGS", f"Image: {image}"]
        if errors:
            lines.extend(["", "❌ ERROR — RECOVERED SETTINGS / DEFAULTS", *errors])
        else:
            lines.append("✅ Metadata extracted")
        lines.extend(["", "📦 MODEL"])
        for key, label in (("checkpoint_name", "Checkpoint"), ("unet_name", "UNet")):
            if source.get(key):
                lines.append(f"{label} recorded in image: {source[key]}")
        if values["model_name"]:
            lines.append(f"Model resolved locally: {values['model_name']} ({values['model_type']})")
        else:
            lines.append("No local model resolved.")
        lines.extend([
            "", "⚙️ SAMPLING", f"Seed: {values['seed']}", f"Steps: {values['steps']}",
            f"CFG: {values['cfg']:g}", f"Sampler: {values['sampler_name']}",
            f"Scheduler: {values['scheduler']}", f"Size: {values['width']} × {values['height']}",
            f"Denoise: {values['denoise']:g}", "", "🧩 LORAS",
        ])
        if requested_loras:
            for name, model_strength, clip_strength in requested_loras:
                lines.append(f"- {name} (model: {model_strength:g}, CLIP: {clip_strength:g})")
        else:
            lines.append("No LoRA entries extracted or selected.")
        for hint in source.get("resource_hints", []):
            if hint.get("name") not in {entry[0] for entry in requested_loras}:
                lines.append(f"- Recorded resource: {hint['name']} (strength unresolved)")
        lines.append(f"Resolved locally: {len(stack)} of {len(requested_loras)} requested entries.")
        lines.extend(["", "➕ POSITIVE PROMPT", values["positive"] or "(empty)",
                      "", "➖ NEGATIVE PROMPT", values["negative"] or "(empty)",
                      "", "📋 NOTES AND WARNINGS"])
        lines.extend(f"{'❌' if note.startswith('ERROR') else '⚠️' if note.startswith('WARNING') else 'ℹ️'} {note}" for note in notes)
        return "\n".join(lines)

    @staticmethod
    def _override_loras(value: Any) -> list[tuple[str, float, float]]:
        if not isinstance(value, list):
            raise MetadataError("loras override must be a list of [name, model_strength, clip_strength]")
        entries = []
        for entry in value:
            if not isinstance(entry, list) or len(entry) != 3 or not isinstance(entry[0], str):
                raise MetadataError("Each LoRA override must be [name, model_strength, clip_strength]")
            entries.append((entry[0], finite_number(entry[1]), finite_number(entry[2])))
        return entries

    @staticmethod
    def _validate_values(values: dict[str, Any], samplers: list[str], schedulers: list[str], strict: bool, notes: list[str]) -> None:
        for key in ("positive", "negative"):
            if not isinstance(values[key], str):
                raise MetadataError(f"{key} must be text")
        for key, low, high in (("seed", 0, 2**64 - 1), ("steps", 1, 10000), ("width", 1, 16384), ("height", 1, 16384)):
            raw = values[key]
            try:
                number = int(raw)
                if isinstance(raw, bool) or (isinstance(raw, float) and raw != number) or not low <= number <= high:
                    raise ValueError()
            except (ValueError, TypeError, OverflowError) as exc:
                raise MetadataError(f"{key} must be an integer between {low} and {high}") from exc
            values[key] = number
        for key, low, high in (("cfg", 0, 100), ("denoise", 0, 1)):
            try:
                number = finite_number(values[key])
                if not low <= number <= high:
                    raise ValueError()
            except (ValueError, TypeError) as exc:
                raise MetadataError(f"{key} must be a finite number between {low} and {high}") from exc
            values[key] = number
        for key, choices in (("sampler_name", samplers), ("scheduler", schedulers)):
            if values[key] not in choices:
                if strict:
                    raise MetadataError(f"Unsupported {key}: {values[key]!r}; set an explicit override")
                fallback = DEFAULTS[key]
                if fallback not in choices:
                    raise MetadataError(f"Default {key} {fallback!r} is unavailable in this ComfyUI installation")
                notes.append(f"WARNING Replaced unsupported {key} {values[key]!r} with {fallback!r}.")
                values[key] = fallback
