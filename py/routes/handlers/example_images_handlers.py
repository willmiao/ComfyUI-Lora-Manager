"""Handler set for example image routes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from aiohttp import web


class ExampleImagesDownloadHandler:
    """HTTP adapters for download-related example image endpoints."""

    def __init__(self, download_manager) -> None:
        self._download_manager = download_manager

    async def download_example_images(self, request: web.Request) -> web.StreamResponse:
        return await self._download_manager.start_download(request)

    async def get_example_images_status(self, request: web.Request) -> web.StreamResponse:
        return await self._download_manager.get_status(request)

    async def pause_example_images(self, request: web.Request) -> web.StreamResponse:
        return await self._download_manager.pause_download(request)

    async def resume_example_images(self, request: web.Request) -> web.StreamResponse:
        return await self._download_manager.resume_download(request)

    async def force_download_example_images(self, request: web.Request) -> web.StreamResponse:
        return await self._download_manager.start_force_download(request)


class ExampleImagesManagementHandler:
    """HTTP adapters for import/delete endpoints."""

    def __init__(self, processor) -> None:
        self._processor = processor

    async def import_example_images(self, request: web.Request) -> web.StreamResponse:
        return await self._processor.import_images(request)

    async def delete_example_image(self, request: web.Request) -> web.StreamResponse:
        return await self._processor.delete_custom_image(request)


class ExampleImagesFileHandler:
    """HTTP adapters for filesystem-centric endpoints."""

    def __init__(self, file_manager) -> None:
        self._file_manager = file_manager

    async def open_example_images_folder(self, request: web.Request) -> web.StreamResponse:
        return await self._file_manager.open_folder(request)

    async def get_example_image_files(self, request: web.Request) -> web.StreamResponse:
        return await self._file_manager.get_files(request)

    async def has_example_images(self, request: web.Request) -> web.StreamResponse:
        return await self._file_manager.has_images(request)


@dataclass(frozen=True)
class ExampleImagesHandlerSet:
    """Aggregate of handlers exposed to the registrar."""

    download: ExampleImagesDownloadHandler
    management: ExampleImagesManagementHandler
    files: ExampleImagesFileHandler

    def to_route_mapping(self) -> Mapping[str, Callable[[web.Request], web.StreamResponse]]:
        """Flatten handler methods into the registrar mapping."""

        return {
            "download_example_images": self.download.download_example_images,
            "get_example_images_status": self.download.get_example_images_status,
            "pause_example_images": self.download.pause_example_images,
            "resume_example_images": self.download.resume_example_images,
            "force_download_example_images": self.download.force_download_example_images,
            "import_example_images": self.management.import_example_images,
            "delete_example_image": self.management.delete_example_image,
            "open_example_images_folder": self.files.open_example_images_folder,
            "get_example_image_files": self.files.get_example_image_files,
            "has_example_images": self.files.has_example_images,
        }
