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

_DEFAULT_MODELS_FILE = os.path.join(
    os.path.dirname(__file__), "test_data", "hf_lora_models_with_safetensors.txt"
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

# ---------------------------------------------------------------------------
# Base model resolution — dynamically fetched from production code
# ---------------------------------------------------------------------------

# Module-level cache — populated by init_supported_base_models().
# Falls back to a comprehensive hardcoded list when the live fetch fails.
SUPPORTED_BASE_MODELS: List[str] = []

# Fallback base models when the production list_base_models() is unavailable.
_FALLBACK_BASE_MODELS: List[str] = [
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


async def init_supported_base_models() -> None:
    """Populate ``SUPPORTED_BASE_MODELS`` from the production codebase.

    Calls ``py.metadata_ops.list_base_models()`` which merges a hardcoded
    fallback with models fetched from the CivitAI API.  When the call
    fails (e.g. offline, API error), falls back to ``_FALLBACK_BASE_MODELS``.

    Must be called from within an async event loop (i.e. during
    ``run_validation.main()``, not at module level).
    """
    try:
        from py.metadata_ops import list_base_models

        models = await list_base_models()
        if models:
            SUPPORTED_BASE_MODELS[:] = models
            logger.info("Loaded %d base models from production code", len(models))
            return
        logger.warning("list_base_models returned empty list, using fallback")
    except Exception as exc:
        logger.warning("Failed to load base models from production: %s", exc)

    SUPPORTED_BASE_MODELS[:] = _FALLBACK_BASE_MODELS
    logger.info("Using fallback base model list (%d entries)", len(SUPPORTED_BASE_MODELS))


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
