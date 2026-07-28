"""Constants used by the metadata collector"""

# Sentinel value for clip_skip to distinguish "unconnected / widget default"
# from "user wired value 0".  Both ComfyUI CLIPSetLastLayer (-24..-1) and
# A1111 conventions treat 0 as meaningless for clip skipping, but users may
# explicitly wire 0 to the overwrite node to express "no clip skip / default".
CLIP_SKIP_SENTINEL = -25

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
    "sampler", "scheduler", "model", "loras", "size",
    "clip_skip", "additional_data",
)

# Complete list of categories to track
METADATA_CATEGORIES = [MODELS, PROMPTS, SAMPLING, LORAS, EMBEDDINGS, SIZE, IMAGES, OVERWRITE]
