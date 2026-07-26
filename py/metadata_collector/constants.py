"""Constants used by the metadata collector"""

# Metadata categories
MODELS = "models"
PROMPTS = "prompts"
SAMPLING = "sampling"
LORAS = "loras"
EMBEDDINGS = "embeddings"
SIZE = "size"
IMAGES = "images"
IS_SAMPLER = "is_sampler"  # New constant to mark sampler nodes
OVERWRITE = "overwrite"  # Manual metadata overwrite from MetadataOverwriteLM node

# Field names that the MetadataOverwriteLM node and its extractor share
METADATA_OVERWRITE_FIELDS = (
    "prompt", "negative_prompt", "seed", "steps", "cfg_scale",
    "sampler", "scheduler", "checkpoint", "loras", "size",
    "clip_skip", "additional_data",
)

# Complete list of categories to track
METADATA_CATEGORIES = [MODELS, PROMPTS, SAMPLING, LORAS, EMBEDDINGS, SIZE, IMAGES, OVERWRITE]
