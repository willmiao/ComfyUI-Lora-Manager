from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.constants import SUPPORTED_DOWNLOAD_SKIP_BASE_MODELS
from .downloader import get_downloader

logger = logging.getLogger(__name__)


class CivitaiBaseModelService:
    """Service for fetching and managing Civitai base models.

    This service provides:
    - Fetching base models from Civitai API
    - Caching with TTL (7 days default)
    - Merging hardcoded and remote base models
    - Generating abbreviations for new/unknown models
    """

    _instance: Optional[CivitaiBaseModelService] = None
    _lock = asyncio.Lock()

    # Default TTL for cache in seconds (7 days)
    DEFAULT_CACHE_TTL = 7 * 24 * 60 * 60

    # Civitai API endpoint for enums
    CIVITAI_ENUMS_URL = "https://civitai.com/api/v1/enums"

    @classmethod
    async def get_instance(cls) -> CivitaiBaseModelService:
        """Get singleton instance of the service."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        """Initialize the service."""
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # Cache storage
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = self.DEFAULT_CACHE_TTL

        # Hardcoded models for fallback
        self._hardcoded_models = set(SUPPORTED_DOWNLOAD_SKIP_BASE_MODELS)

        logger.info("CivitaiBaseModelService initialized")

    async def get_base_models(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get merged base models (hardcoded + remote).

        Args:
            force_refresh: If True, fetch from API regardless of cache state.

        Returns:
            Dictionary containing:
            - models: List of merged base model names
            - source: 'cache', 'api', or 'fallback'
            - last_updated: ISO timestamp of last successful API fetch
            - hardcoded_count: Number of hardcoded models
            - remote_count: Number of remote models
            - merged_count: Total unique models
        """
        # Check if cache is valid
        if not force_refresh and self._is_cache_valid():
            logger.debug("Returning cached base models")
            return self._build_response("cache")

        # Try to fetch from API
        try:
            remote_models = await self._fetch_from_civitai()
            if remote_models:
                self._update_cache(remote_models)
                return self._build_response("api")
        except Exception as e:
            logger.error(f"Failed to fetch base models from Civitai: {e}")

        # Fallback to hardcoded models
        return self._build_response("fallback")

    async def refresh_cache(self) -> Dict[str, Any]:
        """Force refresh the cache from Civitai API.

        Returns:
            Response dict same as get_base_models()
        """
        return await self.get_base_models(force_refresh=True)

    def get_cache_status(self) -> Dict[str, Any]:
        """Get current cache status.

        Returns:
            Dictionary containing:
            - has_cache: Whether cache exists
            - last_updated: ISO timestamp or None
            - is_expired: Whether cache is expired
            - ttl_seconds: TTL in seconds
            - age_seconds: Age of cache in seconds (if exists)
        """
        if self._cache is None or self._cache_timestamp is None:
            return {
                "has_cache": False,
                "last_updated": None,
                "is_expired": True,
                "ttl_seconds": self._cache_ttl,
                "age_seconds": None,
            }

        age = (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
        return {
            "has_cache": True,
            "last_updated": self._cache_timestamp.isoformat(),
            "is_expired": age > self._cache_ttl,
            "ttl_seconds": self._cache_ttl,
            "age_seconds": int(age),
        }

    def generate_abbreviation(self, model_name: str) -> str:
        """Generate abbreviation for a base model name.

        Algorithm:
        1. Extract version patterns (e.g., "2.5" from "Wan Video 2.5")
        2. Extract main acronym (e.g., "SD" from "SD 1.5")
        3. Handle special cases (Flux, Wan, etc.)
        4. Fallback to first letters of words (max 4 chars)

        Args:
            model_name: Full base model name

        Returns:
            Generated abbreviation (max 4 characters)
        """
        if not model_name or not isinstance(model_name, str):
            return "OTH"

        name = model_name.strip()
        if not name:
            return "OTH"

        # Check if it's already in hardcoded abbreviations
        # This is a simplified check - in practice you'd have a mapping
        lower_name = name.lower()

        # Special cases
        special_cases = {
            "sd 1.4": "SD1",
            "sd 1.5": "SD1",
            "sd 1.5 lcm": "SD1",
            "sd 1.5 hyper": "SD1",
            "sd 2.0": "SD2",
            "sd 2.1": "SD2",
            "sd 3": "SD3",
            "sd 3.5": "SD3",
            "sd 3.5 medium": "SD3",
            "sd 3.5 large": "SD3",
            "sd 3.5 large turbo": "SD3",
            "sdxl 1.0": "XL",
            "sdxl lightning": "XL",
            "sdxl hyper": "XL",
            "flux.1 d": "F1D",
            "flux.1 s": "F1S",
            "flux.1 krea": "F1KR",
            "flux.1 kontext": "F1KX",
            "flux.2 d": "F2D",
            "flux.2 klein 9b": "FK9",
            "flux.2 klein 9b-base": "FK9B",
            "flux.2 klein 4b": "FK4",
            "flux.2 klein 4b-base": "FK4B",
            "auraflow": "AF",
            "chroma": "CHR",
            "pixart a": "PXA",
            "pixart e": "PXE",
            "hunyuan 1": "HY",
            "hunyuan video": "HYV",
            "lumina": "L",
            "kolors": "KLR",
            "noobai": "NAI",
            "illustrious": "IL",
            "pony": "PONY",
            "pony v7": "PNY7",
            "hidream": "HID",
            "qwen": "QWEN",
            "zimageturbo": "ZIT",
            "zimagebase": "ZIB",
            "anima": "ANI",
            "svd": "SVD",
            "ltxv": "LTXV",
            "ltxv2": "LTV2",
            "ltxv 2.3": "LTX",
            "cogvideox": "CVX",
            "mochi": "MCHI",
            "wan video": "WAN",
            "wan video 1.3b t2v": "WAN",
            "wan video 14b t2v": "WAN",
            "wan video 14b i2v 480p": "WAN",
            "wan video 14b i2v 720p": "WAN",
            "wan video 2.2 ti2v-5b": "WAN",
            "wan video 2.2 t2v-a14b": "WAN",
            "wan video 2.2 i2v-a14b": "WAN",
            "wan video 2.5 t2v": "WAN",
            "wan video 2.5 i2v": "WAN",
        }

        if lower_name in special_cases:
            return special_cases[lower_name]

        # Try to extract acronym from version pattern
        # e.g., "Model Name 2.5" -> "MN25"
        version_match = re.search(r"(\d+(?:\.\d+)?)", name)
        version = version_match.group(1) if version_match else ""

        # Remove version and common words
        words = re.sub(r"\d+(?:\.\d+)?", "", name)
        words = re.sub(
            r"\b(model|video|diffusion|checkpoint|textualinversion)\b",
            "",
            words,
            flags=re.I,
        )
        words = words.strip()

        # Get first letters of remaining words
        tokens = re.findall(r"[A-Za-z]+", words)
        if tokens:
            # Build abbreviation from first letters
            abbrev = "".join(token[0].upper() for token in tokens)
            # Add version if present
            if version:
                # Clean version (remove dots for abbreviation)
                version_clean = version.replace(".", "")
                abbrev = abbrev[: 4 - len(version_clean)] + version_clean
            return abbrev[:4]

        # Final fallback: just take first 4 alphanumeric chars
        alphanumeric = re.sub(r"[^A-Za-z0-9]", "", name)
        if alphanumeric:
            return alphanumeric[:4].upper()

        return "OTH"

    async def _fetch_from_civitai(self) -> Optional[Set[str]]:
        """Fetch base models from Civitai API.

        Returns:
            Set of base model names, or None if failed
        """
        try:
            downloader = await get_downloader()
            success, result = await downloader.make_request(
                "GET",
                self.CIVITAI_ENUMS_URL,
                use_auth=False,  # enums endpoint doesn't require auth
            )

            if not success:
                logger.warning(f"Failed to fetch enums from Civitai: {result}")
                return None

            if isinstance(result, str):
                data = json.loads(result)
            else:
                data = result

            # Extract base models from response
            base_models = set()

            # Use ActiveBaseModel if available (recommended active models)
            if "ActiveBaseModel" in data:
                base_models.update(data["ActiveBaseModel"])
                logger.info(f"Fetched {len(base_models)} models from ActiveBaseModel")
            # Fallback to full BaseModel list
            elif "BaseModel" in data:
                base_models.update(data["BaseModel"])
                logger.info(f"Fetched {len(base_models)} models from BaseModel")
            else:
                logger.warning("No base model data found in Civitai response")
                return None

            return base_models

        except Exception as e:
            logger.error(f"Error fetching from Civitai: {e}")
            return None

    def _update_cache(self, remote_models: Set[str]) -> None:
        """Update internal cache with fetched models.

        Args:
            remote_models: Set of base model names from API
        """
        self._cache = {
            "remote_models": sorted(remote_models),
            "hardcoded_models": sorted(self._hardcoded_models),
        }
        self._cache_timestamp = datetime.now(timezone.utc)
        logger.info(f"Cache updated with {len(remote_models)} remote models")

    def _is_cache_valid(self) -> bool:
        """Check if current cache is valid (not expired).

        Returns:
            True if cache exists and is not expired
        """
        if self._cache is None or self._cache_timestamp is None:
            return False

        age = (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
        return age <= self._cache_ttl

    def _build_response(self, source: str) -> Dict[str, Any]:
        """Build response dictionary.

        Args:
            source: 'cache', 'api', or 'fallback'

        Returns:
            Response dictionary
        """
        if source == "fallback" or self._cache is None:
            # Use only hardcoded models
            merged = sorted(self._hardcoded_models)
            return {
                "models": merged,
                "source": source,
                "last_updated": None,
                "hardcoded_count": len(self._hardcoded_models),
                "remote_count": 0,
                "merged_count": len(merged),
            }

        # Merge hardcoded and remote models
        remote_set = set(self._cache.get("remote_models", []))
        merged = sorted(self._hardcoded_models | remote_set)

        return {
            "models": merged,
            "source": source,
            "last_updated": self._cache_timestamp.isoformat()
            if self._cache_timestamp
            else None,
            "hardcoded_count": len(self._hardcoded_models),
            "remote_count": len(remote_set),
            "merged_count": len(merged),
        }

    def get_model_categories(self) -> Dict[str, List[str]]:
        """Get categorized base models.

        Returns:
            Dictionary mapping category names to lists of model names
        """
        # Define category patterns
        categories = {
            "Stable Diffusion 1.x": ["SD 1.4", "SD 1.5", "SD 1.5 LCM", "SD 1.5 Hyper"],
            "Stable Diffusion 2.x": ["SD 2.0", "SD 2.1"],
            "Stable Diffusion 3.x": [
                "SD 3",
                "SD 3.5",
                "SD 3.5 Medium",
                "SD 3.5 Large",
                "SD 3.5 Large Turbo",
            ],
            "SDXL": ["SDXL 1.0", "SDXL Lightning", "SDXL Hyper"],
            "Flux Models": [
                "Flux.1 D",
                "Flux.1 S",
                "Flux.1 Krea",
                "Flux.1 Kontext",
                "Flux.2 D",
                "Flux.2 Klein 9B",
                "Flux.2 Klein 9B-base",
                "Flux.2 Klein 4B",
                "Flux.2 Klein 4B-base",
            ],
            "Video Models": [
                "SVD",
                "LTXV",
                "LTXV2",
                "LTXV 2.3",
                "CogVideoX",
                "Mochi",
                "Hunyuan Video",
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
            ],
            "Other Models": [
                "Illustrious",
                "Pony",
                "Pony V7",
                "HiDream",
                "Qwen",
                "AuraFlow",
                "Chroma",
                "ZImageTurbo",
                "ZImageBase",
                "PixArt a",
                "PixArt E",
                "Hunyuan 1",
                "Lumina",
                "Kolors",
                "NoobAI",
                "Anima",
            ],
        }

        return categories


# Convenience function for getting the singleton instance
async def get_civitai_base_model_service() -> CivitaiBaseModelService:
    """Get the singleton instance of CivitaiBaseModelService."""
    return await CivitaiBaseModelService.get_instance()
