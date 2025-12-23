from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class GenParamsMerger:
    """Utility to merge generation parameters from multiple sources with priority."""

    BLACKLISTED_KEYS = {"id", "url", "userId", "username", "createdAt", "updatedAt", "hash"}

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
                result.update(embedded_metadata["gen_params"])
            else:
                # Otherwise assume the dict itself contains gen_params
                result.update(embedded_metadata)

        # 2. Layer Civitai meta (medium priority)
        if civitai_meta:
            result.update(civitai_meta)

        # 3. Layer request params (highest priority)
        if request_params:
            result.update(request_params)

        # Filter out blacklisted keys
        return {k: v for k, v in result.items() if k not in GenParamsMerger.BLACKLISTED_KEYS}
