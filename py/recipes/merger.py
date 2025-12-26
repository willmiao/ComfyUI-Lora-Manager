from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class GenParamsMerger:
    """Utility to merge generation parameters from multiple sources with priority."""

    BLACKLISTED_KEYS = {
        "id", "url", "userId", "username", "createdAt", "updatedAt", "hash", "meta",
        "draft", "extra", "width", "height", "process", "quantity", "workflow",
        "baseModel", "resources", "disablePoi", "aspectRatio", "Created Date",
        "experimental", "civitaiResources", "civitai_resources", "Civitai resources",
        "modelVersionId", "modelId", "hashes", "Model", "Model hash", "checkpoint_hash",
        "checkpoint", "checksum", "model_checksum"
    }
    
    NORMALIZATION_MAPPING = {
        # Civitai specific
        "cfgScale": "cfg_scale",
        "clipSkip": "clip_skip",
        "negativePrompt": "negative_prompt",
        # Case variations
        "Sampler": "sampler",
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
        embedded_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Merge generation parameters from three sources.
        
        Priority: request_params > civitai_meta > embedded_metadata
        
        Args:
            request_params: Params provided directly in the import request
            civitai_meta: Params from Civitai Image API 'meta' field
            embedded_metadata: Params extracted from image EXIF/embedded metadata
            
        Returns:
            Merged parameters dictionary
        """
        result = {}

        # 1. Start with embedded metadata (lowest priority)
        if embedded_metadata:
            # If it's a full recipe metadata, we use its gen_params
            if "gen_params" in embedded_metadata and isinstance(embedded_metadata["gen_params"], dict):
                GenParamsMerger._update_normalized(result, embedded_metadata["gen_params"])
            else:
                # Otherwise assume the dict itself contains gen_params
                GenParamsMerger._update_normalized(result, embedded_metadata)

        # 2. Layer Civitai meta (medium priority)
        if civitai_meta:
            GenParamsMerger._update_normalized(result, civitai_meta)

        # 3. Layer request params (highest priority)
        if request_params:
            GenParamsMerger._update_normalized(result, request_params)

        # Filter out blacklisted keys and also the original camelCase keys if they were normalized
        final_result = {}
        for k, v in result.items():
            if k in GenParamsMerger.BLACKLISTED_KEYS:
                continue
            if k in GenParamsMerger.NORMALIZATION_MAPPING:
                continue
            final_result[k] = v
            
        return final_result

    @staticmethod
    def _update_normalized(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """Update target dict with normalized keys from source."""
        for k, v in source.items():
            normalized_key = GenParamsMerger.NORMALIZATION_MAPPING.get(k, k)
            target[normalized_key] = v
            # Also keep the original key for now if it's not the same, 
            # so we can filter at the end or avoid losing it if it wasn't supposed to be renamed?
            # Actually, if we rename it, we should probably NOT keep both in 'target' 
            # because we want to filter them out at the end anyway.
            if normalized_key != k:
                # If we are overwriting an existing snake_case key with a camelCase one's value,
                # that's fine because of the priority order of calls to _update_normalized.
                pass
            target[k] = v
