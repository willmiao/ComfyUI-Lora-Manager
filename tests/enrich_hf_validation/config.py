"""Configuration for the HF metadata enrichment validation suite.

Loads user settings, defines paths, and pulls constants from the main
codebase (``py.utils.constants``).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_DEFAULT_MODELS_FILE = os.path.expanduser(
    "~/Documents/hf_lora_models.txt"
)
_DEFAULT_SETTINGS_PATH = os.path.expanduser(
    "~/.config/ComfyUI-LoRA-Manager/settings.json"
)
_DEFAULT_OUTPUT_DIR = "/tmp/hf_enrich_validation"

# ---------------------------------------------------------------------------
# Constants from the main codebase (copied at import time)
# ---------------------------------------------------------------------------

# Priority tags used in the LLM prompt for tag selection guidance.
CIVITAI_MODEL_TAGS: List[str] = [
    "character", "concept", "clothing", "realistic", "anime", "toon",
    "furry", "style", "poses", "background", "tool", "vehicle",
    "buildings", "objects", "assets", "animal", "action",
]

# Base models recognised as valid values.
SUPPORTED_BASE_MODELS: List[str] = [
    "SD 1.4", "SD 1.5", "SD 1.5 LCM", "SD 1.5 Hyper",
    "SD 2.0", "SD 2.1",
    "SD 3", "SD 3.5", "SD 3.5 Medium", "SD 3.5 Large", "SD 3.5 Large Turbo",
    "SDXL 1.0", "SDXL Lightning", "SDXL Hyper",
    "Flux.1 D", "Flux.1 S", "Flux.1 Krea", "Flux.1 Kontext",
    "Flux.2 D", "Flux.2 Klein 9B", "Flux.2 Klein 9B-base",
    "Flux.2 Klein 4B", "Flux.2 Klein 4B-base",
    "AuraFlow", "Chroma", "PixArt a", "PixArt E",
    "Hunyuan 1", "Lumina", "Kolors",
    "NoobAI", "Illustrious", "Pony", "Pony V7",
    "HiDream", "Qwen", "ZImageTurbo", "ZImageBase",
    "SVD", "LTXV", "LTXV2", "LTXV 2.3",
    "CogVideoX", "Mochi",
    "Wan Video", "Wan Video 1.3B t2v", "Wan Video 14B t2v",
    "Wan Video 14B i2v 480p", "Wan Video 14B i2v 720p",
    "Wan Video 2.2 TI2V-5B", "Wan Video 2.2 T2V-A14B",
    "Wan Video 2.2 I2V-A14B",
    "Wan Video 2.5 T2V", "Wan Video 2.5 I2V",
    "Hunyuan Video", "Anima", "Ernie", "Ernie Turbo",
    "Nucleus", "Krea 2",
]

# Placeholder values the LLM sometimes emits that should count as "empty".
PLACEHOLDER_VALUES = frozenset({
    "none", "null", "n/a", "unknown", "not available",
    "not specified", "no trigger words", "no trigger word",
})


# ---------------------------------------------------------------------------
# User settings loader
# ---------------------------------------------------------------------------

def load_settings(settings_path: str) -> Dict[str, Any]:
    """Load LoRA Manager settings from *settings_path*.

    Returns a flat dict with the LLM configuration fields that the
    enrichment pipeline depends on.
    """
    path = os.path.expanduser(settings_path)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Settings file not found: {path}\n"
            "Please provide a valid --settings path."
        )

    with open(path, "r", encoding="utf-8") as fh:
        raw: Dict[str, Any] = json.load(fh)

    # Extract LLM-relevant config
    return {
        "llm_provider": raw.get("llm_provider", "ollama"),
        "llm_model": raw.get("llm_model", "qwen3.5:9b"),
        "llm_api_base": raw.get("llm_api_base", "http://localhost:11434/v1"),
        "llm_api_key": raw.get("llm_api_key", ""),
        "settings_path": path,
    }
