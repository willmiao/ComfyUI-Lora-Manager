"""Services responsible for recipe metadata analysis."""
from __future__ import annotations

import base64
import io
import os
import re
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np
from PIL import Image

from ...utils.utils import calculate_recipe_fingerprint
from .errors import (
    RecipeDownloadError,
    RecipeNotFoundError,
    RecipeServiceError,
    RecipeValidationError,
)


@dataclass(frozen=True)
class AnalysisResult:
    """Return payload from analysis operations."""

    payload: dict[str, Any]
    status: int = 200


class RecipeAnalysisService:
    """Extract recipe metadata from various image sources."""

    def __init__(
        self,
        *,
        exif_utils,
        recipe_parser_factory,
        downloader_factory: Callable[[], Any],
        metadata_collector: Optional[Callable[[], Any]] = None,
        metadata_processor_cls: Optional[type] = None,
        metadata_registry_cls: Optional[type] = None,
        standalone_mode: bool = False,
        logger,
    ) -> None:
        self._exif_utils = exif_utils
        self._recipe_parser_factory = recipe_parser_factory
        self._downloader_factory = downloader_factory
        self._metadata_collector = metadata_collector
        self._metadata_processor_cls = metadata_processor_cls
        self._metadata_registry_cls = metadata_registry_cls
        self._standalone_mode = standalone_mode
        self._logger = logger

    async def analyze_uploaded_image(
        self,
        *,
        image_bytes: bytes | None,
        recipe_scanner,
    ) -> AnalysisResult:
        """Analyze an uploaded image payload."""

        if not image_bytes:
            raise RecipeValidationError("No image data provided")

        temp_path = self._write_temp_file(image_bytes)
        try:
            metadata = self._exif_utils.extract_image_metadata(temp_path)
            if not metadata:
                return AnalysisResult({"error": "No metadata found in this image", "loras": []})

            return await self._parse_metadata(
                metadata,
                recipe_scanner=recipe_scanner,
                image_path=None,
                include_image_base64=False,
            )
        finally:
            self._safe_cleanup(temp_path)

    async def analyze_remote_image(
        self,
        *,
        url: str | None,
        recipe_scanner,
        civitai_client,
    ) -> AnalysisResult:
        """Analyze an image accessible via URL, including Civitai integration."""

        if not url:
            raise RecipeValidationError("No URL provided")

        if civitai_client is None:
            raise RecipeServiceError("Civitai client unavailable")

        temp_path = self._create_temp_path()
        metadata: Optional[dict[str, Any]] = None
        try:
            civitai_match = re.match(r"https://civitai\.com/images/(\d+)", url)
            if civitai_match:
                image_info = await civitai_client.get_image_info(civitai_match.group(1))
                if not image_info:
                    raise RecipeDownloadError("Failed to fetch image information from Civitai")
                image_url = image_info.get("url")
                if not image_url:
                    raise RecipeDownloadError("No image URL found in Civitai response")
                await self._download_image(image_url, temp_path)
                metadata = image_info.get("meta") if "meta" in image_info else None
            else:
                await self._download_image(url, temp_path)

            if metadata is None:
                metadata = self._exif_utils.extract_image_metadata(temp_path)

            if not metadata:
                return self._metadata_not_found_response(temp_path)

            return await self._parse_metadata(
                metadata,
                recipe_scanner=recipe_scanner,
                image_path=temp_path,
                include_image_base64=True,
            )
        finally:
            self._safe_cleanup(temp_path)

    async def analyze_local_image(
        self,
        *,
        file_path: str | None,
        recipe_scanner,
    ) -> AnalysisResult:
        """Analyze a file already present on disk."""

        if not file_path:
            raise RecipeValidationError("No file path provided")

        normalized_path = os.path.normpath(file_path.strip('"').strip("'"))
        if not os.path.isfile(normalized_path):
            raise RecipeNotFoundError("File not found")

        metadata = self._exif_utils.extract_image_metadata(normalized_path)
        if not metadata:
            return self._metadata_not_found_response(normalized_path)

        return await self._parse_metadata(
            metadata,
            recipe_scanner=recipe_scanner,
            image_path=normalized_path,
            include_image_base64=True,
        )

    async def analyze_widget_metadata(self, *, recipe_scanner) -> AnalysisResult:
        """Analyse the most recent generation metadata for widget saves."""

        if self._metadata_collector is None or self._metadata_processor_cls is None:
            raise RecipeValidationError("Metadata collection not available")

        raw_metadata = self._metadata_collector()
        metadata_dict = self._metadata_processor_cls.to_dict(raw_metadata)
        if not metadata_dict:
            raise RecipeValidationError("No generation metadata found")

        latest_image = None
        if not self._standalone_mode and self._metadata_registry_cls is not None:
            metadata_registry = self._metadata_registry_cls()
            latest_image = metadata_registry.get_first_decoded_image()

        if latest_image is None:
            raise RecipeValidationError(
                "No recent images found to use for recipe. Try generating an image first."
            )

        image_bytes = self._convert_tensor_to_png_bytes(latest_image)
        if image_bytes is None:
            raise RecipeValidationError("Cannot handle this data shape from metadata registry")

        return AnalysisResult(
            {
                "metadata": metadata_dict,
                "image_bytes": image_bytes,
            }
        )

    # Internal helpers -------------------------------------------------

    async def _parse_metadata(
        self,
        metadata: dict[str, Any],
        *,
        recipe_scanner,
        image_path: Optional[str],
        include_image_base64: bool,
    ) -> AnalysisResult:
        parser = self._recipe_parser_factory.create_parser(metadata)
        if parser is None:
            payload = {"error": "No parser found for this image", "loras": []}
            if include_image_base64 and image_path:
                payload["image_base64"] = self._encode_file(image_path)
            return AnalysisResult(payload)

        result = await parser.parse_metadata(metadata, recipe_scanner=recipe_scanner)

        if include_image_base64 and image_path:
            result["image_base64"] = self._encode_file(image_path)

        if "error" in result and not result.get("loras"):
            return AnalysisResult(result)

        fingerprint = calculate_recipe_fingerprint(result.get("loras", []))
        result["fingerprint"] = fingerprint

        matching_recipes: list[str] = []
        if fingerprint:
            matching_recipes = await recipe_scanner.find_recipes_by_fingerprint(fingerprint)
        result["matching_recipes"] = matching_recipes

        return AnalysisResult(result)

    async def _download_image(self, url: str, temp_path: str) -> None:
        downloader = await self._downloader_factory()
        success, result = await downloader.download_file(url, temp_path, use_auth=False)
        if not success:
            raise RecipeDownloadError(f"Failed to download image from URL: {result}")

    def _metadata_not_found_response(self, path: str) -> AnalysisResult:
        payload: dict[str, Any] = {"error": "No metadata found in this image", "loras": []}
        if os.path.exists(path):
            payload["image_base64"] = self._encode_file(path)
        return AnalysisResult(payload)

    def _write_temp_file(self, data: bytes) -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            temp_file.write(data)
            return temp_file.name

    def _create_temp_path(self) -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            return temp_file.name

    def _safe_cleanup(self, path: Optional[str]) -> None:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.error("Error deleting temporary file: %s", exc)

    def _encode_file(self, path: str) -> str:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _convert_tensor_to_png_bytes(self, latest_image: Any) -> Optional[bytes]:
        try:
            if isinstance(latest_image, tuple):
                tensor_image = latest_image[0] if latest_image else None
                if tensor_image is None:
                    return None
            else:
                tensor_image = latest_image

            if hasattr(tensor_image, "shape"):
                self._logger.debug(
                    "Tensor shape: %s, dtype: %s", tensor_image.shape, getattr(tensor_image, "dtype", None)
                )

            import torch  # type: ignore[import-not-found]

            if isinstance(tensor_image, torch.Tensor):
                image_np = tensor_image.cpu().numpy()
            else:
                image_np = np.array(tensor_image)

            while len(image_np.shape) > 3:
                image_np = image_np[0]

            if image_np.dtype in (np.float32, np.float64) and image_np.max() <= 1.0:
                image_np = (image_np * 255).astype(np.uint8)

            if len(image_np.shape) == 3 and image_np.shape[2] == 3:
                pil_image = Image.fromarray(image_np)
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format="PNG")
                return img_byte_arr.getvalue()
        except Exception as exc:  # pragma: no cover - defensive logging path
            self._logger.error("Error processing image data: %s", exc, exc_info=True)
            return None

        return None
