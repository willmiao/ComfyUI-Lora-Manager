from typing import Any, Dict, Optional
import logging

from .constants import GEN_PARAM_KEYS

logger = logging.getLogger(__name__)


class GenParamsMerger:
    """Utility to merge generation parameters from multiple sources with priority."""

    ALLOWED_KEYS = set(GEN_PARAM_KEYS)

    BLACKLISTED_KEYS = {
        "id", "url", "userId", "username", "createdAt", "updatedAt", "hash", "meta",
        "draft", "extra", "width", "height", "process", "quantity", "workflow",
        "baseModel", "resources", "disablePoi", "aspectRatio", "Created Date",
        "experimental", "civitaiResources", "civitai_resources", "Civitai resources",
        "modelVersionId", "modelId", "hashes", "Model", "Model hash", "checkpoint_hash",
        "checkpoint", "checksum", "model_checksum", "raw_metadata",
    }

    NORMALIZATION_MAPPING = {
        "cfg": "cfg_scale",
        "cfgScale": "cfg_scale",
        "clipSkip": "clip_skip",
        "negativePrompt": "negative_prompt",
        "Sampler": "sampler",
        "sampler_name": "sampler",
        "scheduler": "sampler",
        "Steps": "steps",
        "Seed": "seed",
        "Size": "size",
        "Prompt": "prompt",
        "Negative prompt": "negative_prompt",
        "Cfg scale": "cfg_scale",
        "Clip skip": "clip_skip",
        "Denoising strength": "denoising_strength",
    }

    @staticmethod
    def merge(
        request_params: Optional[Dict[str, Any]] = None,
        civitai_meta: Optional[Dict[str, Any]] = None,
        embedded_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Merge generation parameters from three sources.

        Priority: request_params > civitai_meta > embedded_metadata
        """
        result: Dict[str, Any] = {}

        if embedded_metadata:
            if "gen_params" in embedded_metadata and isinstance(
                embedded_metadata["gen_params"], dict
            ):
                GenParamsMerger._update_normalized(result, embedded_metadata["gen_params"])
            else:
                GenParamsMerger._update_normalized(result, embedded_metadata)

        if civitai_meta:
            GenParamsMerger._update_normalized(result, civitai_meta)

        if request_params:
            GenParamsMerger._update_normalized(result, request_params)

        return result

    @staticmethod
    def _update_normalized(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """Update target dict with normalized, persistence-safe keys from source."""
        for key, value in source.items():
            if key in GenParamsMerger.BLACKLISTED_KEYS:
                continue

            normalized_key = GenParamsMerger.NORMALIZATION_MAPPING.get(key, key)
            if normalized_key not in GenParamsMerger.ALLOWED_KEYS:
                continue

            target[normalized_key] = value
