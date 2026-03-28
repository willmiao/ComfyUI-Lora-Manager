"""Tests for CivitaiBaseModelService."""

import pytest
from unittest.mock import patch

from py.services.civitai_base_model_service import CivitaiBaseModelService


class TestCivitaiBaseModelService:
    """Test suite for CivitaiBaseModelService."""

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Create a fresh service instance for each test."""
        self.service = CivitaiBaseModelService()
        # Reset cache
        self.service._cache = None
        self.service._cache_timestamp = None
        yield

    def test_generate_abbreviation_known_models(self):
        """Test abbreviation generation for known models."""
        test_cases = [
            ("SD 1.5", "SD1"),
            ("SDXL 1.0", "XL"),
            ("Flux.1 D", "F1D"),
            ("Wan Video 2.5 T2V", "WAN"),
            ("Pony V7", "PNY7"),
            ("CogVideoX", "CVX"),
            ("Mochi", "MCHI"),
            ("Anima", "ANI"),
        ]

        for model_name, expected in test_cases:
            result = self.service.generate_abbreviation(model_name)
            assert result == expected, (
                f"Failed for {model_name}: got {result}, expected {expected}"
            )

    def test_generate_abbreviation_unknown_models(self):
        """Test abbreviation generation for unknown models."""
        result = self.service.generate_abbreviation("New Model 2.0")
        assert len(result) <= 4
        assert result.isupper()

    def test_generate_abbreviation_edge_cases(self):
        """Test abbreviation generation edge cases."""
        assert self.service.generate_abbreviation("") == "OTH"
        assert self.service.generate_abbreviation(None) == "OTH"

    def test_cache_status_no_cache(self):
        """Test cache status when no cache exists."""
        status = self.service.get_cache_status()

        assert status["has_cache"] is False
        assert status["last_updated"] is None
        assert status["is_expired"] is True
        assert status["age_seconds"] is None

    @pytest.mark.asyncio
    async def test_get_base_models_fallback(self):
        """Test that fallback to hardcoded models works."""
        with patch.object(self.service, "_fetch_from_civitai", return_value=None):
            result = await self.service.get_base_models()

        assert result["source"] == "fallback"
        assert len(result["models"]) > 0
        assert result["hardcoded_count"] > 0
        assert result["remote_count"] == 0

    @pytest.mark.asyncio
    async def test_get_base_models_from_api(self):
        """Test fetching models from API."""
        mock_models = {"SD 1.5", "SDXL 1.0", "New Model"}

        with patch.object(
            self.service, "_fetch_from_civitai", return_value=mock_models
        ):
            result = await self.service.get_base_models()

        assert result["source"] == "api"
        assert result["remote_count"] == 3
        assert "New Model" in result["models"]

    @pytest.mark.asyncio
    async def test_get_base_models_uses_cache(self):
        """Test that cached data is used when available and not expired."""
        # First call - populate cache
        mock_models = {"SD 1.5", "SDXL 1.0"}
        with patch.object(
            self.service, "_fetch_from_civitai", return_value=mock_models
        ):
            await self.service.get_base_models()

        # Second call - should use cache
        with patch.object(self.service, "_fetch_from_civitai") as mock_fetch:
            result = await self.service.get_base_models()
            mock_fetch.assert_not_called()

        assert result["source"] == "cache"

    @pytest.mark.asyncio
    async def test_refresh_cache(self):
        """Test force refresh clears cache and fetches fresh data."""
        # Populate cache
        mock_models = {"SD 1.5"}
        with patch.object(
            self.service, "_fetch_from_civitai", return_value=mock_models
        ):
            await self.service.get_base_models()

        # Force refresh with different data
        new_models = {"SD 1.5", "SDXL 1.0", "New Model"}
        with patch.object(self.service, "_fetch_from_civitai", return_value=new_models):
            result = await self.service.refresh_cache()

        assert result["source"] == "api"
        assert result["remote_count"] == 3

    def test_get_model_categories(self):
        """Test model categories are returned."""
        categories = self.service.get_model_categories()

        assert "Stable Diffusion 1.x" in categories
        assert "Video Models" in categories
        assert "Flux Models" in categories
        assert "Other Models" in categories

        # Check that video models include new additions
        video_models = categories["Video Models"]
        assert "CogVideoX" in video_models
        assert "Mochi" in video_models
        assert "Wan Video 2.5 T2V" in video_models
