from typing import Any, Dict, List

NSFW_LEVELS = {
    "PG": 1,
    "PG13": 2,
    "R": 4,
    "X": 8,
    "XXX": 16,
    "Blocked": 32,  # Probably not actually visible through the API without being logged in on model owner account?
}

# Node type constants
NODE_TYPES = {
    "Lora Loader (LoraManager)": 1,
    "Lora Stacker (LoraManager)": 2,
    "WanVideo Lora Select (LoraManager)": 3,
    "Create Hook LoRA (LoraManager)": 4,
}

# Default ComfyUI node color when bgcolor is null
DEFAULT_NODE_COLOR = "#353535"

# preview extensions
PREVIEW_EXTENSIONS = [
    ".webp",
    ".preview.webp",
    ".preview.png",
    ".preview.jpeg",
    ".preview.jpg",
    ".preview.mp4",
    ".png",
    ".jpeg",
    ".jpg",
    ".mp4",
    ".gif",
    ".webm",
    ".avif",
    ".jxl",
]

# Card preview image width
CARD_PREVIEW_WIDTH = 480

# Width for optimized example images
EXAMPLE_IMAGE_WIDTH = 832

# Supported media extensions for example downloads
SUPPORTED_MEDIA_EXTENSIONS = {
    "images": [".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".jxl"],
    "videos": [".mp4", ".webm"],
}

# Model weight file extensions recognised by scanners.
# This is the union of all scanner extensions (lora, checkpoint, embedding).
MODEL_FILE_EXTENSIONS = {
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pt2",
    ".bin",
    ".pth",
    ".pkl",
    ".sft",
    ".gguf",
}

# CivitAI ModelFile.type values eligible as the main download file.
# Mirrors CivitAI's getPrimaryFile() (model-helpers.ts): weight types are
# preferred, but any file CivitAI marks `primary` is accepted — newer types
# like 'Enhancement LoRA' (Anima/AIR image-editing LoRAs) are valid primary
# files despite not being in the traditional weights allowlist.
MODEL_WEIGHT_FILE_TYPES = (
    "Model",
    "Pruned Model",
    "Negative",
    "UNet",
    "Diffusion Model",
    "Enhancement LoRA",
)

# Valid sub-types for each scanner type
VALID_LORA_SUB_TYPES = ["lora", "locon", "dora"]
VALID_CHECKPOINT_SUB_TYPES = ["checkpoint", "diffusion_model"]
VALID_EMBEDDING_SUB_TYPES = ["embedding"]

# folder_paths key -> sub_type; single source of truth for extensibility.
# Adding support for a new ComfyUI folder category is a one-line change here.
OTHER_MODEL_FOLDER_SUBTYPES = {
    "vae": "vae",
    "upscale_models": "upscaler",
    "text_encoders": "text_encoder",
    "clip": "text_encoder",  # legacy ComfyUI key
    "clip_vision": "clip_vision",
    "controlnet": "controlnet",
}
VALID_OTHER_SUB_TYPES = ["vae", "upscaler", "text_encoder", "clip_vision", "controlnet"]
# Sub-types managed when the (opt-in) Other Models feature is switched on.
# The feature itself defaults to off (``enable_other_models`` = False), so
# nothing here is scanned until the user enables it.
#
# The default set is deliberately limited to the dependency-style assets every
# pipeline needs and where "which one am I actually using" is the real problem:
# VAE, upscalers and text encoders. ``clip_vision`` and ``controlnet`` are
# workflow-driven instead (IPAdapter/SVD, per-workflow ControlNet variants) and
# ControlNet libraries routinely run to dozens of files, so both stay opt-in
# and are treated symmetrically.
DEFAULT_ENABLED_OTHER_SUB_TYPES: List[str] = [
    "vae",
    "upscaler",
    "text_encoder",
]


def other_sub_type_folder_keys() -> Dict[str, List[str]]:
    """Invert OTHER_MODEL_FOLDER_SUBTYPES into sub_type -> folder_paths keys.

    ``text_encoder`` maps to two folder keys (``text_encoders`` and the legacy
    ``clip``), so every consumer that resolves a sub_type back to folders must
    merge both.
    """
    mapping: Dict[str, List[str]] = {}
    for folder_key, sub_type in OTHER_MODEL_FOLDER_SUBTYPES.items():
        mapping.setdefault(sub_type, []).append(folder_key)
    return mapping


# Precomputed inverse of OTHER_MODEL_FOLDER_SUBTYPES, keeping the table order.
OTHER_SUB_TYPE_FOLDER_KEYS: Dict[str, List[str]] = other_sub_type_folder_keys()

# Core folder_paths keys every LoRA Manager installation understands.
CORE_FOLDER_PATH_KEYS: List[str] = ["loras", "checkpoints", "unet", "embeddings"]


def folder_path_schema() -> List[Dict[str, Any]]:
    """Ordered schema describing the editable folder_paths keys.

    Drives the standalone-only Model Paths settings UI: the frontend renders
    one multi-path editor per entry and resolves labels via the
    ``settings.modelPaths.folderKeys.<key>`` i18n keys, so adding a new model
    category is a constants + locale change only. ``sub_type`` lets the UI
    hide editors for other-model categories the user has not enabled.
    """
    schema: List[Dict[str, Any]] = [
        {"key": key, "category": "core", "sub_type": None}
        for key in CORE_FOLDER_PATH_KEYS
    ]
    schema.extend(
        {"key": folder_key, "category": "other", "sub_type": sub_type}
        for folder_key, sub_type in OTHER_MODEL_FOLDER_SUBTYPES.items()
    )
    return schema


def normalize_other_sub_types(value: Any) -> List[str]:
    """Normalize a stored/requested enabled-sub_type list.

    Unknown values and duplicates are dropped; the result follows the
    canonical VALID_OTHER_SUB_TYPES order so the stored setting and the UI
    stay stable. Non-list input falls back to the defaults.
    """
    if isinstance(value, str):
        candidates: Any = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = value
    else:
        return list(DEFAULT_ENABLED_OTHER_SUB_TYPES)

    allowed = {item for item in candidates if isinstance(item, str)}
    return [sub_type for sub_type in VALID_OTHER_SUB_TYPES if sub_type in allowed]
# CivitAI model.type values accepted by the "other" page's fetch-metadata
# validation (lowercased). CLIP/CLIPVision are retired upstream but still
# appear on grandfathered models.
VALID_OTHER_CIVITAI_TYPES = {
    "vae",
    "upscaler",
    "textencoder",
    "clip",
    "clipvision",
    "controlnet",
    "other",
}
# CivitAI model.type -> internal sub_type for the "other" model page.
CIVITAI_TYPE_TO_OTHER_SUB_TYPE = {
    "vae": "vae",
    "upscaler": "upscaler",
    "textencoder": "text_encoder",
    "clip": "text_encoder",
    "clipvision": "clip_vision",
    "controlnet": "controlnet",
}

# CivitAI ModelFile.type values -> internal sub_type for the "other" model
# page. Used for download routing only, and strictly as an explicit user file
# pick or a fallback when model.type maps to nothing — checkpoint models
# routinely bundle VAE/Text Encoder component files, so file types must never
# override a mapped model.type.
CIVITAI_FILE_TYPE_TO_OTHER_SUB_TYPE = {
    "VAE": "vae",
    "Upscaler": "upscaler",
    "Text Encoder": "text_encoder",
    "Vision Encoder": "clip_vision",
    "CLIPVision": "clip_vision",
    "ControlNet": "controlnet",
}

# Backward compatibility alias
VALID_LORA_TYPES = VALID_LORA_SUB_TYPES

# Supported Civitai model types for user model queries (case-insensitive)
CIVITAI_USER_MODEL_TYPES = [
    *VALID_LORA_TYPES,
    "textualinversion",
    "checkpoint",
    *sorted(VALID_OTHER_CIVITAI_TYPES),
]

# Default chunk size in megabytes used for hashing large files.
DEFAULT_HASH_CHUNK_SIZE_MB = 4

# Upper bound for a safetensors header block (bytes). Real headers are at most
# a few MB (tensor name/shape lists); the cap prevents a crafted file with an
# absurd 64-bit header length from forcing a multi-GB allocation during scan.
MAX_SAFETENSORS_HEADER_BYTES = 64 * 1024 * 1024

# SHA256 of an empty byte string. Some (re-packaging) training tools write a
# truncated form of this placeholder into safetensors metadata (as
# ``modelspec.hash_sha256`` / ``sshs_model_hash``), and hashing an empty or
# unreadable file produces it directly. It must never be treated as a valid
# hash: several broken models share it, CivitAI's by-hash index can contain
# such polluted entries, and matching it falsely attributes recipes.
EMPTY_HASH_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
INVALID_AUTOV3_EMPTY_HASH = EMPTY_HASH_SHA256[:12]
INVALID_AUTOV2_EMPTY_HASH = EMPTY_HASH_SHA256[:10]


def is_empty_placeholder_hash(value: Any) -> bool:
    """True for a 10/12/64-hex-char spelling of the empty-hash placeholder.

    These are the AutoV2, AutoV3 and full-SHA256 forms of the placeholder;
    such values identify no real model and must never be resolved against
    local files or CivitAI.
    """
    if not isinstance(value, str):
        return False
    v = value.strip().lower()
    if len(v) not in (10, 12, 64):
        return False
    return v == EMPTY_HASH_SHA256[: len(v)]

# Auto-organize settings
AUTO_ORGANIZE_BATCH_SIZE = (
    50  # Process models in batches to avoid overwhelming the system
)

# Civitai model tags in priority order for subfolder organization
CIVITAI_MODEL_TAGS = [
    "character",
    "concept",
    "clothing",
    "realistic",
    "anime",
    "toon",
    "furry",
    "style",
    "poses",
    "background",
    "tool",
    "vehicle",
    "buildings",
    "objects",
    "assets",
    "animal",
    "action",
]

# Civitai tags that describe the listing rather than the model's content.
# Uploaders can also set these by hand, so they must not be picked as an
# automatic folder name; a user who wants one can still name it explicitly in
# their priority tag list.
CIVITAI_META_TAGS = frozenset(
    {
        "base model",
    }
)

# Default priority tag configuration strings for each model type
DEFAULT_PRIORITY_TAG_CONFIG = {
    "lora": ", ".join(CIVITAI_MODEL_TAGS),
    "checkpoint": ", ".join(CIVITAI_MODEL_TAGS),
    "embedding": ", ".join(CIVITAI_MODEL_TAGS),
}

# Default download path template for each model type. "other" defaults to a
# flat layout (empty template) on purpose: other-model downloads are already
# separated by sub_type roots (default_other_roots), and priority_tags has no
# "other" entry, so {first_tag} would resolve to an arbitrary CivitAI tag and
# scatter files into unstable folders. Users can still opt in to a template by
# writing "other" into download_path_templates in settings.json.
DEFAULT_DOWNLOAD_PATH_TEMPLATES: Dict[str, str] = {
    "lora": "{base_model}/{first_tag}",
    "checkpoint": "{base_model}/{first_tag}",
    "embedding": "{base_model}/{first_tag}",
    "other": "",
}

# Length guards for template placeholders that end up in file and folder names.
# Windows enforces MAX_PATH (260 characters) on the full path and 255 on a
# single path component. A model folder also holds the model file, the
# ".metadata.json" sidecar written by LoRA Manager, preview images and the
# metadata files other tools drop next to the model (for example
# ".civitai.info", which LoRA Manager only reads), so names stay well below
# those limits.
#
# Tags get a much tighter budget than other names: some CivitAI uploaders dump
# their whole keyword list into a single tag (see issue #1119), and such a tag
# is only useful as a folder name after truncation.
MAX_FOLDER_NAME_LENGTH = 100
MAX_PATH_TAG_LENGTH = 50
MAX_FILENAME_STEM_LENGTH = 150

# baseModel values from CivitAI that should be treated as diffusion models (unet)
# These model types are incorrectly labeled as "checkpoint" by CivitAI but are actually diffusion models
DIFFUSION_MODEL_BASE_MODELS = frozenset(
    [
        "Anima",
        # Flux series — DiT architecture, loaded via UNETLoader in ComfyUI
        "Flux.1 D",
        "Flux.1 S",
        "Flux.1 Krea",
        "Flux.1 Kontext",
        "Flux.2 D",
        "Flux.2 Klein 9B",
        "Flux.2 Klein 9B-base",
        "Flux.2 Klein 4B",
        "Flux.2 Klein 4B-base",
        # Non-UNet / DiT image diffusion models
        "AuraFlow",
        "Chroma",
        "HiDream",
        "Hunyuan 1",
        "Kolors",
        "Lumina",
        "PixArt a",
        "PixArt E",
        # Video diffusion models
        "CogVideoX",
        "Hunyuan Video",
        "LTXV",
        "LTXV2",
        "LTXV 2.3",
        "Mochi",
        "SVD",
        "Wan Video",
        "Wan Video 1.3B t2v",
        "Wan Video 14B t2v",
        "Wan Video 14B i2v 480p",
        "Wan Video 14B i2v 720p",
        "Wan Video 2.2 TI2V-5B",
        "Wan Video 2.2 I2V-A14B",
        "Wan Video 2.2 T2V-A14B",
        "Wan Video 2.5 T2V",
        "Wan Video 2.5 I2V",
        # Other diffusion models
        "Ernie",
        "Ernie Turbo",
        "Nucleus",
        "Qwen",
        "ZImageBase",
        "ZImageTurbo",
        # Krea 2 — loaded via UNETLoader in ComfyUI
        "Krea 2",
    ]
)

# Supported baseModel values for download exclusion settings.
# Keep this aligned with static/js/utils/constants.js, excluding the generic "Other" value.
SUPPORTED_DOWNLOAD_SKIP_BASE_MODELS = frozenset(
    [
        "SD 1.4",
        "SD 1.5",
        "SD 1.5 LCM",
        "SD 1.5 Hyper",
        "SD 2.0",
        "SD 2.1",
        "SD 3",
        "SD 3.5",
        "SD 3.5 Medium",
        "SD 3.5 Large",
        "SD 3.5 Large Turbo",
        "SDXL 1.0",
        "SDXL Lightning",
        "SDXL Hyper",
        "Flux.1 D",
        "Flux.1 S",
        "Flux.1 Krea",
        "Flux.1 Kontext",
        "Flux.2 D",
        "Flux.2 Klein 9B",
        "Flux.2 Klein 9B-base",
        "Flux.2 Klein 4B",
        "Flux.2 Klein 4B-base",
        "AuraFlow",
        "Chroma",
        "PixArt a",
        "PixArt E",
        "Hunyuan 1",
        "Lumina",
        "Kolors",
        "NoobAI",
        "Illustrious",
        "Pony",
        "Pony V7",
        "HiDream",
        "Qwen",
        "ZImageTurbo",
        "ZImageBase",
        "SVD",
        "LTXV",
        "LTXV2",
        "LTXV 2.3",
        "CogVideoX",
        "Mochi",
        "Wan Video",
        "Wan Video 1.3B t2v",
        "Wan Video 14B t2v",
        "Wan Video 14B i2v 480p",
        "Wan Video 14B i2v 720p",
        "Wan Video 2.2 TI2V-5B",
        "Wan Video 2.2 T2V-A14B",
        "Wan Video 2.2 I2V-A14B",
        "Wan Video 2.5 T2V",
        "Wan Video 2.5 I2V",
        "Hunyuan Video",
        "Anima",
        "ACE Audio",
        "Boogu",
        "Ernie",
        "Ernie Turbo",
        "Grok",
        "HappyHorse",
        "HiDream-O1",
        "Ideogram 4.0",
        "Krea 2",
        "Lens",
        "MAI",
        "Nucleus",
        "Qwen 2",
        "Upscaler",
        "Wan Image 2.7",
        "Wan Video 2.7",
    ]
)
