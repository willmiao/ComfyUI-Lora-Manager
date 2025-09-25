"""Use case for importing example images."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from typing import Any, Dict, List

from aiohttp import web

from ....utils.example_images_processor import (
    ExampleImagesImportError,
    ExampleImagesProcessor,
    ExampleImagesValidationError,
)


class ImportExampleImagesValidationError(ValueError):
    """Raised when request validation fails."""


class ImportExampleImagesUseCase:
    """Parse upload payloads and delegate to the processor service."""

    def __init__(self, *, processor: ExampleImagesProcessor) -> None:
        self._processor = processor

    async def execute(self, request: web.Request) -> Dict[str, Any]:
        model_hash: str | None = None
        files_to_import: List[str] = []
        temp_files: List[str] = []

        try:
            if request.content_type and "multipart/form-data" in request.content_type:
                reader = await request.multipart()

                first_field = await reader.next()
                if first_field and first_field.name == "model_hash":
                    model_hash = await first_field.text()
                else:
                    # Support clients that send files first and hash later
                    if first_field is not None:
                        await self._collect_upload_file(first_field, files_to_import, temp_files)

                async for field in reader:
                    if field.name == "model_hash" and not model_hash:
                        model_hash = await field.text()
                    elif field.name == "files":
                        await self._collect_upload_file(field, files_to_import, temp_files)
            else:
                data = await request.json()
                model_hash = data.get("model_hash")
                files_to_import = list(data.get("file_paths", []))

            result = await self._processor.import_images(model_hash, files_to_import)
            return result
        except ExampleImagesValidationError as exc:
            raise ImportExampleImagesValidationError(str(exc)) from exc
        except ExampleImagesImportError:
            raise
        finally:
            for path in temp_files:
                with suppress(Exception):
                    os.remove(path)

    async def _collect_upload_file(
        self,
        field: Any,
        files_to_import: List[str],
        temp_files: List[str],
    ) -> None:
        """Persist an uploaded file to disk and add it to the import list."""

        filename = field.filename or "upload"
        file_ext = os.path.splitext(filename)[1].lower()

        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp_file:
            temp_files.append(tmp_file.name)
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                tmp_file.write(chunk)

        files_to_import.append(tmp_file.name)
