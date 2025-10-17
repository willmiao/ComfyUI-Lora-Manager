export const BASE_MODELS = {
    // Stable Diffusion 1.x models
    SD_1_4: "SD 1.4",
    SD_1_5: "SD 1.5",
    SD_1_5_LCM: "SD 1.5 LCM",
    SD_1_5_HYPER: "SD 1.5 Hyper",
    
    // Stable Diffusion 2.x models
    SD_2_0: "SD 2.0",
    SD_2_1: "SD 2.1",
    
    // Stable Diffusion 3.x models
    SD_3: "SD 3",
    SD_3_5: "SD 3.5",
    SD_3_5_MEDIUM: "SD 3.5 Medium",
    SD_3_5_LARGE: "SD 3.5 Large",
    SD_3_5_LARGE_TURBO: "SD 3.5 Large Turbo",
    
    // SDXL models
    SDXL: "SDXL 1.0",
    SDXL_LIGHTNING: "SDXL Lightning",
    SDXL_HYPER: "SDXL Hyper",

    // Other models
    FLUX_1_D: "Flux.1 D",
    FLUX_1_S: "Flux.1 S",
    FLUX_1_KREA: "Flux.1 Krea",
    FLUX_1_KONTEXT: "Flux.1 Kontext",
    AURAFLOW: "AuraFlow",
    CHROMA: "Chroma",
    PIXART_A: "PixArt a",
    PIXART_E: "PixArt E",
    HUNYUAN_1: "Hunyuan 1",
    LUMINA: "Lumina",
    KOLORS: "Kolors",
    NOOBAI: "NoobAI",
    ILLUSTRIOUS: "Illustrious",
    PONY: "Pony",
    HIDREAM: "HiDream",
    QWEN: "Qwen",
    
    // Video models
    SVD: "SVD",
    LTXV: "LTXV",
    WAN_VIDEO: "Wan Video",
    WAN_VIDEO_1_3B_T2V: "Wan Video 1.3B t2v",
    WAN_VIDEO_14B_T2V: "Wan Video 14B t2v",
    WAN_VIDEO_14B_I2V_480P: "Wan Video 14B i2v 480p",
    WAN_VIDEO_14B_I2V_720P: "Wan Video 14B i2v 720p",
    WAN_VIDEO_2_2_TI2V_5B: "Wan Video 2.2 TI2V-5B",
    WAN_VIDEO_2_2_T2V_A14B: "Wan Video 2.2 T2V-A14B",
    WAN_VIDEO_2_2_I2V_A14B: "Wan Video 2.2 I2V-A14B",
    HUNYUAN_VIDEO: "Hunyuan Video",
    // Default
    UNKNOWN: "Other"
};

// Path template constants for download organization
export const DOWNLOAD_PATH_TEMPLATES = {
    FLAT: {
        value: '',
        label: 'Flat Structure',
        description: 'Download directly to root folder',
        example: 'model-name.safetensors'
    },
    BASE_MODEL: {
        value: '{base_model}',
        label: 'By Base Model',
        description: 'Organize by base model type',
        example: 'Flux.1 D/model-name.safetensors'
    },
    AUTHOR: {
        value: '{author}',
        label: 'By Author',
        description: 'Organize by model author',
        example: 'authorname/model-name.safetensors'
    },
    FIRST_TAG: {
        value: '{first_tag}',
        label: 'By First Tag',
        description: 'Organize by primary tag/category',
        example: 'style/model-name.safetensors'
    },
    BASE_MODEL_TAG: {
        value: '{base_model}/{first_tag}',
        label: 'Base Model + First Tag',
        description: 'Organize by base model and primary tag',
        example: 'Flux.1 D/style/model-name.safetensors'
    },
    BASE_MODEL_AUTHOR: {
        value: '{base_model}/{author}',
        label: 'Base Model + Author',
        description: 'Organize by base model and author',
        example: 'Flux.1 D/authorname/model-name.safetensors'
    },
    BASE_MODEL_AUTHOR_TAG: {
        value: '{base_model}/{author}/{first_tag}',
        label: 'Base Model + Author + First Tag',
        description: 'Organize by base model, author, and primary tag',
        example: 'Flux.1 D/authorname/style/model-name.safetensors'
    },
    AUTHOR_TAG: {
        value: '{author}/{first_tag}',
        label: 'Author + First Tag',
        description: 'Organize by author and primary tag',
        example: 'authorname/style/model-name.safetensors'
    },
    CUSTOM: {
        value: 'custom',
        label: 'Custom Template',
        description: 'Create your own path structure',
        example: 'Enter custom template...'
    }
};

// Valid placeholders for path templates
export const PATH_TEMPLATE_PLACEHOLDERS = [
    '{base_model}',
    '{author}',
    '{first_tag}',
    '{model_name}',
    '{version_name}'
];

// Default templates for each model type
export const DEFAULT_PATH_TEMPLATES = {
    lora: '{base_model}/{first_tag}',
    checkpoint: '{base_model}',
    embedding: '{first_tag}'
};

// Model type labels for UI
export const MODEL_TYPE_LABELS = {
    lora: 'LoRA Models',
    checkpoint: 'Checkpoint Models',
    embedding: 'Embedding Models'
};

// Base models available for path mapping (for UI selection)
export const MAPPABLE_BASE_MODELS = Object.values(BASE_MODELS).sort();

export const NSFW_LEVELS = {
    UNKNOWN: 0,
    PG: 1,
    PG13: 2,
    R: 4,
    X: 8,
    XXX: 16,
    BLOCKED: 32
};

// Node type constants
export const NODE_TYPES = {
    LORA_LOADER: 1,
    LORA_STACKER: 2,
    WAN_VIDEO_LORA_SELECT: 3
};

// Node type names to IDs mapping
export const NODE_TYPE_NAMES = {
    "Lora Loader (LoraManager)": NODE_TYPES.LORA_LOADER,
    "Lora Stacker (LoraManager)": NODE_TYPES.LORA_STACKER,
    "WanVideo Lora Select (LoraManager)": NODE_TYPES.WAN_VIDEO_LORA_SELECT
};

// Node type icons
export const NODE_TYPE_ICONS = {
    [NODE_TYPES.LORA_LOADER]: "fas fa-l",
    [NODE_TYPES.LORA_STACKER]: "fas fa-s",
    [NODE_TYPES.WAN_VIDEO_LORA_SELECT]: "fas fa-w"
};

// Default ComfyUI node color when bgcolor is null
export const DEFAULT_NODE_COLOR = "#353535";

// Base model categories for organized selection
export const BASE_MODEL_CATEGORIES = {
    'Stable Diffusion 1.x': [BASE_MODELS.SD_1_4, BASE_MODELS.SD_1_5, BASE_MODELS.SD_1_5_LCM, BASE_MODELS.SD_1_5_HYPER],
    'Stable Diffusion 2.x': [BASE_MODELS.SD_2_0, BASE_MODELS.SD_2_1],
    'Stable Diffusion 3.x': [BASE_MODELS.SD_3, BASE_MODELS.SD_3_5, BASE_MODELS.SD_3_5_MEDIUM, BASE_MODELS.SD_3_5_LARGE, BASE_MODELS.SD_3_5_LARGE_TURBO],
    'SDXL': [BASE_MODELS.SDXL, BASE_MODELS.SDXL_LIGHTNING, BASE_MODELS.SDXL_HYPER],
    'Video Models': [
        BASE_MODELS.SVD, BASE_MODELS.LTXV, BASE_MODELS.HUNYUAN_VIDEO, BASE_MODELS.WAN_VIDEO, 
        BASE_MODELS.WAN_VIDEO_1_3B_T2V, BASE_MODELS.WAN_VIDEO_14B_T2V,
        BASE_MODELS.WAN_VIDEO_14B_I2V_480P, BASE_MODELS.WAN_VIDEO_14B_I2V_720P,
        BASE_MODELS.WAN_VIDEO_2_2_TI2V_5B, BASE_MODELS.WAN_VIDEO_2_2_T2V_A14B,
        BASE_MODELS.WAN_VIDEO_2_2_I2V_A14B
    ],
    'Flux Models': [BASE_MODELS.FLUX_1_D, BASE_MODELS.FLUX_1_S, BASE_MODELS.FLUX_1_KONTEXT, BASE_MODELS.FLUX_1_KREA],
    'Other Models': [
        BASE_MODELS.ILLUSTRIOUS, BASE_MODELS.PONY, BASE_MODELS.HIDREAM,
        BASE_MODELS.QWEN, BASE_MODELS.AURAFLOW, BASE_MODELS.CHROMA,
        BASE_MODELS.PIXART_A, BASE_MODELS.PIXART_E, BASE_MODELS.HUNYUAN_1,
        BASE_MODELS.LUMINA, BASE_MODELS.KOLORS, BASE_MODELS.NOOBAI,
        BASE_MODELS.UNKNOWN
    ]
};

// Default priority tag entries for fallback suggestions and initial settings
export const DEFAULT_PRIORITY_TAG_ENTRIES = [
    'character', 'concept', 'clothing',
    'realistic', 'anime', 'toon', 'furry', 'style',
    'poses', 'background', 'tool', 'vehicle', 'buildings',
    'objects', 'assets', 'animal', 'action'
];

export const DEFAULT_PRIORITY_TAG_CONFIG = {
    lora: DEFAULT_PRIORITY_TAG_ENTRIES.join(', '),
    checkpoint: DEFAULT_PRIORITY_TAG_ENTRIES.join(', '),
    embedding: DEFAULT_PRIORITY_TAG_ENTRIES.join(', ')
};
