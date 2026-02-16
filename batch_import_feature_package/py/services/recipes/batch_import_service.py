"""Service for batch importing and analyzing multiple recipe images."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from .analysis_service import AnalysisResult


logger = logging.getLogger(__name__)


class BatchImportService:
    """Handle batch import of multiple recipe images."""

    def __init__(
        self,
        *,
        analysis_service,
        persistence_service,
    ) -> None:
        self._analysis_service = analysis_service
        self._persistence_service = persistence_service

    async def import_batch_from_directory(
        self,
        *,
        directory_path: str,
        recipe_scanner,
        civitai_client,
        max_concurrent: int = 3,
    ) -> dict[str, Any]:
        """Import and generate recipes for all images in a directory.
        
        Args:
            directory_path: Path to directory containing images
            recipe_scanner: Recipe scanner instance
            civitai_client: Civitai client instance
            max_concurrent: Maximum concurrent analysis tasks
            
        Returns:
            Dictionary containing results with keys:
            - success: bool
            - total_files: int
            - processed: int
            - failed: int
            - results: list of individual import results
            - errors: list of error messages
        """
        results = {
            "success": True,
            "total_files": 0,
            "processed": 0,
            "failed": 0,
            "results": [],
            "errors": [],
            "skipped": 0,
        }

        # Validate directory
        dir_path = Path(directory_path)
        if not dir_path.exists():
            results["success"] = False
            results["errors"].append(f"Directory does not exist: {directory_path}")
            return results

        if not dir_path.is_dir():
            results["success"] = False
            results["errors"].append(f"Path is not a directory: {directory_path}")
            return results

        # Find all image files
        image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
        image_files = [
            f for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        ]

        results["total_files"] = len(image_files)

        if not image_files:
            results["errors"].append(f"No image files found in {directory_path}")
            return results

        logger.info(f"Starting batch import of {len(image_files)} images from {directory_path}")

        # Process images with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_image_with_semaphore(file_path: Path) -> dict[str, Any]:
            async with semaphore:
                return await self._process_single_image(
                    file_path,
                    recipe_scanner,
                    civitai_client,
                )

        # Run all tasks
        tasks = [process_image_with_semaphore(f) for f in image_files]
        import_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for result in import_results:
            if isinstance(result, Exception):
                results["failed"] += 1
                results["errors"].append(str(result))
            elif isinstance(result, dict):
                if result.get("success"):
                    results["processed"] += 1
                    results["results"].append(result)
                elif result.get("skipped"):
                    results["skipped"] += 1
                else:
                    results["failed"] += 1
                    if "error" in result:
                        results["errors"].append(result["error"])

        results["success"] = results["failed"] == 0

        logger.info(
            f"Batch import complete: {results['processed']} processed, "
            f"{results['failed']} failed, {results['skipped']} skipped"
        )

        return results

    async def _process_single_image(
        self,
        file_path: Path,
        recipe_scanner,
        civitai_client,
    ) -> dict[str, Any]:
        """Process a single image file.
        
        Returns:
            Dictionary with keys:
            - success: bool
            - file_name: str
            - file_path: str
            - recipe_id: Optional[str]
            - error: Optional[str]
            - skipped: Optional[bool]
        """
        result: dict[str, Any] = {
            "file_name": file_path.name,
            "file_path": str(file_path),
            "success": False,
        }

        try:
            # Read image file
            with open(file_path, "rb") as f:
                image_bytes = f.read()

            # Analyze image
            analysis_result = await self._analysis_service.analyze_uploaded_image(
                image_bytes=image_bytes,
                recipe_scanner=recipe_scanner,
            )

            if analysis_result.status != 200:
                result["error"] = f"Analysis failed: {analysis_result.payload.get('error', 'Unknown error')}"
                return result

            analysis_data = analysis_result.payload

            # Check if metadata was found
            if analysis_data.get("error"):
                result["skipped"] = True
                result["error"] = analysis_data.get("error", "No metadata found")
                return result

            # Prepare recipe metadata
            metadata: dict[str, Any] = {
                "base_model": analysis_data.get("base_model", ""),
                "loras": analysis_data.get("loras", []),
                "gen_params": analysis_data.get("gen_params", {}),
                "checkpoint": analysis_data.get("checkpoint"),
            }

            # Generate recipe name from filename
            recipe_name = file_path.stem

            # Save recipe
            try:
                save_result = await self._persistence_service.save_recipe(
                    recipe_scanner=recipe_scanner,
                    image_bytes=image_bytes,
                    image_base64=None,
                    name=recipe_name,
                    tags=analysis_data.get("tags", []),
                    metadata=metadata,
                    extension=file_path.suffix,
                )

                if save_result.status == 201 or save_result.status == 200:
                    result["success"] = True
                    result["recipe_id"] = save_result.payload.get("id")
                    logger.info(f"Successfully imported recipe from {file_path.name}")
                else:
                    result["error"] = f"Failed to save recipe: {save_result.payload.get('error', 'Unknown error')}"

            except Exception as e:
                result["error"] = f"Failed to save recipe: {str(e)}"
                logger.error(f"Error saving recipe from {file_path.name}: {e}")

        except FileNotFoundError:
            result["error"] = f"File not found: {file_path}"
        except IOError as e:
            result["error"] = f"Failed to read file: {str(e)}"
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)

        return result

    async def import_batch_from_urls(
        self,
        *,
        urls: list[str],
        recipe_scanner,
        civitai_client,
        max_concurrent: int = 3,
    ) -> dict[str, Any]:
        """Import and generate recipes from a list of URLs.
        
        Args:
            urls: List of image URLs
            recipe_scanner: Recipe scanner instance
            civitai_client: Civitai client instance
            max_concurrent: Maximum concurrent analysis tasks
            
        Returns:
            Dictionary containing batch results
        """
        results = {
            "success": True,
            "total_urls": len(urls),
            "processed": 0,
            "failed": 0,
            "results": [],
            "errors": [],
            "skipped": 0,
        }

        if not urls:
            results["success"] = False
            results["errors"].append("No URLs provided")
            return results

        logger.info(f"Starting batch import from {len(urls)} URLs")

        # Process URLs with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_url_with_semaphore(url: str) -> dict[str, Any]:
            async with semaphore:
                return await self._process_single_url(
                    url,
                    recipe_scanner,
                    civitai_client,
                )

        # Run all tasks
        tasks = [process_url_with_semaphore(url) for url in urls]
        import_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for result in import_results:
            if isinstance(result, Exception):
                results["failed"] += 1
                results["errors"].append(str(result))
            elif isinstance(result, dict):
                if result.get("success"):
                    results["processed"] += 1
                    results["results"].append(result)
                elif result.get("skipped"):
                    results["skipped"] += 1
                else:
                    results["failed"] += 1
                    if "error" in result:
                        results["errors"].append(result["error"])

        results["success"] = results["failed"] == 0

        logger.info(
            f"Batch URL import complete: {results['processed']} processed, "
            f"{results['failed']} failed, {results['skipped']} skipped"
        )

        return results

    async def _process_single_url(
        self,
        url: str,
        recipe_scanner,
        civitai_client,
    ) -> dict[str, Any]:
        """Process a single URL."""
        result: dict[str, Any] = {
            "url": url,
            "success": False,
        }

        try:
            # Analyze remote image
            analysis_result = await self._analysis_service.analyze_remote_image(
                url=url,
                recipe_scanner=recipe_scanner,
                civitai_client=civitai_client,
            )

            if analysis_result.status != 200:
                result["error"] = f"Analysis failed: {analysis_result.payload.get('error', 'Unknown error')}"
                return result

            analysis_data = analysis_result.payload

            # Check if metadata was found
            if analysis_data.get("error"):
                result["skipped"] = True
                result["error"] = analysis_data.get("error", "No metadata found")
                return result

            # Extract image bytes from base64 if available
            image_bytes = None
            if "image_base64" in analysis_data:
                import base64
                try:
                    image_bytes = base64.b64decode(analysis_data["image_base64"])
                except Exception as e:
                    logger.warning(f"Failed to decode base64 image from {url}: {e}")

            # Prepare recipe metadata
            metadata: dict[str, Any] = {
                "base_model": analysis_data.get("base_model", ""),
                "loras": analysis_data.get("loras", []),
                "gen_params": analysis_data.get("gen_params", {}),
                "checkpoint": analysis_data.get("checkpoint"),
                "source_url": url,
            }

            # Generate recipe name from URL
            recipe_name = url.split("/")[-1].split("?")[0] or "imported_recipe"

            # Save recipe
            try:
                save_result = await self._persistence_service.save_recipe(
                    recipe_scanner=recipe_scanner,
                    image_bytes=image_bytes,
                    image_base64=analysis_data.get("image_base64"),
                    name=recipe_name,
                    tags=analysis_data.get("tags", []),
                    metadata=metadata,
                    extension=".jpg",
                )

                if save_result.status == 201 or save_result.status == 200:
                    result["success"] = True
                    result["recipe_id"] = save_result.payload.get("id")
                    logger.info(f"Successfully imported recipe from URL: {url}")
                else:
                    result["error"] = f"Failed to save recipe: {save_result.payload.get('error', 'Unknown error')}"

            except Exception as e:
                result["error"] = f"Failed to save recipe: {str(e)}"
                logger.error(f"Error saving recipe from URL {url}: {e}")

        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            logger.error(f"Error processing URL {url}: {e}", exc_info=True)

        return result
