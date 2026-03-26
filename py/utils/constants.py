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
]

# Card preview image width
CARD_PREVIEW_WIDTH = 480

# Width for optimized example images
EXAMPLE_IMAGE_WIDTH = 832

# Supported media extensions for example downloads
SUPPORTED_MEDIA_EXTENSIONS = {
    "images": [".jpg", ".jpeg", ".png", ".webp", ".gif"],
    "videos": [".mp4", ".webm"],
}

# Valid sub-types for each scanner type
VALID_LORA_SUB_TYPES = ["lora", "locon", "dora"]
VALID_CHECKPOINT_SUB_TYPES = ["checkpoint", "diffusion_model"]
VALID_EMBEDDING_SUB_TYPES = ["embedding"]

# Backward compatibility alias
VALID_LORA_TYPES = VALID_LORA_SUB_TYPES

# Supported Civitai model types for user model queries (case-insensitive)
CIVITAI_USER_MODEL_TYPES = [
    *VALID_LORA_TYPES,
    "textualinversion",
    "checkpoint",
]

# Default chunk size in megabytes used for hashing large files.
DEFAULT_HASH_CHUNK_SIZE_MB = 4

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

# Default priority tag configuration strings for each model type
DEFAULT_PRIORITY_TAG_CONFIG = {
    "lora": ", ".join(CIVITAI_MODEL_TAGS),
    "checkpoint": ", ".join(CIVITAI_MODEL_TAGS),
    "embedding": ", ".join(CIVITAI_MODEL_TAGS),
}

# baseModel values from CivitAI that should be treated as diffusion models (unet)
# These model types are incorrectly labeled as "checkpoint" by CivitAI but are actually diffusion models
DIFFUSION_MODEL_BASE_MODELS = frozenset(
    [
        "ZImageTurbo",
        "Wan Video 1.3B t2v",
        "Wan Video 14B t2v",
        "Wan Video 14B i2v 480p",
        "Wan Video 14B i2v 720p",
        "Wan Video 2.2 TI2V-5B",
        "Wan Video 2.2 I2V-A14B",
        "Wan Video 2.2 T2V-A14B",
        "Wan Video 2.5 T2V",
        "Wan Video 2.5 I2V",
        "Qwen",
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
        "HiDream",
        "Qwen",
        "ZImageTurbo",
        "ZImageBase",
        "SVD",
        "LTXV",
        "LTXV2",
        "Wan Video",
        "Wan Video 1.3B t2v",
        "Wan Video 14B t2v",
        "Wan Video 14B i2v 480p",
        "Wan Video 14B i2v 720p",
        "Wan Video 2.2 TI2V-5B",
        "Wan Video 2.2 T2V-A14B",
        "Wan Video 2.2 I2V-A14B",
        "Hunyuan Video",
    ]
)
