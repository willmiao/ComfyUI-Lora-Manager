"""Handler set for example image routes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from aiohttp import web

from ...services.use_cases.example_images import (
    DownloadExampleImagesConfigurationError,
    DownloadExampleImagesInProgressError,
    DownloadExampleImagesUseCase,
    ImportExampleImagesUseCase,
    ImportExampleImagesValidationError,
)
from ...utils.example_images_download_manager import (
    DownloadConfigurationError,
    DownloadInProgressError,
    DownloadNotRunningError,
    ExampleImagesDownloadError,
)
from ...utils.example_images_processor import ExampleImagesImportError


class ExampleImagesDownloadHandler:
    """HTTP adapters for download-related example image endpoints."""

    def __init__(
        self,
        download_use_case: DownloadExampleImagesUseCase,
        download_manager,
    ) -> None:
        self._download_use_case = download_use_case
        self._download_manager = download_manager

    async def download_example_images(self, request: web.Request) -> web.StreamResponse:
        try:
            payload = await request.json()
            result = await self._download_use_case.execute(payload)
            return web.json_response(result)
        except DownloadExampleImagesInProgressError as exc:
            response = {
                'success': False,
                'error': str(exc),
                'status': exc.progress,
            }
            return web.json_response(response, status=400)
        except DownloadExampleImagesConfigurationError as exc:
            return web.json_response({'success': False, 'error': str(exc)}, status=400)
        except ExampleImagesDownloadError as exc:
            return web.json_response({'success': False, 'error': str(exc)}, status=500)

    async def get_example_images_status(self, request: web.Request) -> web.StreamResponse:
        result = await self._download_manager.get_status(request)
        return web.json_response(result)

    async def pause_example_images(self, request: web.Request) -> web.StreamResponse:
        try:
            result = await self._download_manager.pause_download(request)
            return web.json_response(result)
        except DownloadNotRunningError as exc:
            return web.json_response({'success': False, 'error': str(exc)}, status=400)

    async def resume_example_images(self, request: web.Request) -> web.StreamResponse:
        try:
            result = await self._download_manager.resume_download(request)
            return web.json_response(result)
        except DownloadNotRunningError as exc:
            return web.json_response({'success': False, 'error': str(exc)}, status=400)

    async def stop_example_images(self, request: web.Request) -> web.StreamResponse:
        try:
            result = await self._download_manager.stop_download(request)
            return web.json_response(result)
        except DownloadNotRunningError as exc:
            return web.json_response({'success': False, 'error': str(exc)}, status=400)

    async def force_download_example_images(self, request: web.Request) -> web.StreamResponse:
        try:
            payload = await request.json()
            result = await self._download_manager.start_force_download(payload)
            return web.json_response(result)
        except DownloadInProgressError as exc:
            response = {
                'success': False,
                'error': str(exc),
                'status': exc.progress_snapshot,
            }
            return web.json_response(response, status=400)
        except DownloadConfigurationError as exc:
            return web.json_response({'success': False, 'error': str(exc)}, status=400)
        except ExampleImagesDownloadError as exc:
            return web.json_response({'success': False, 'error': str(exc)}, status=500)


class ExampleImagesManagementHandler:
    """HTTP adapters for import/delete endpoints."""

    def __init__(self, import_use_case: ImportExampleImagesUseCase, processor, cleanup_service) -> None:
        self._import_use_case = import_use_case
        self._processor = processor
        self._cleanup_service = cleanup_service

    async def import_example_images(self, request: web.Request) -> web.StreamResponse:
        try:
            result = await self._import_use_case.execute(request)
            return web.json_response(result)
        except ImportExampleImagesValidationError as exc:
            return web.json_response({'success': False, 'error': str(exc)}, status=400)
        except ExampleImagesImportError as exc:
            return web.json_response({'success': False, 'error': str(exc)}, status=500)

    async def delete_example_image(self, request: web.Request) -> web.StreamResponse:
        return await self._processor.delete_custom_image(request)

    async def cleanup_example_image_folders(self, request: web.Request) -> web.StreamResponse:
        result = await self._cleanup_service.cleanup_example_image_folders()

        if result.get('success') or result.get('partial_success'):
            return web.json_response(result, status=200)

        error_code = result.get('error_code')
        status = 400 if error_code in {'path_not_configured', 'path_not_found'} else 500
        return web.json_response(result, status=status)


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
            "stop_example_images": self.download.stop_example_images,
            "force_download_example_images": self.download.force_download_example_images,
            "import_example_images": self.management.import_example_images,
            "delete_example_image": self.management.delete_example_image,
            "cleanup_example_image_folders": self.management.cleanup_example_image_folders,
            "open_example_images_folder": self.files.open_example_images_folder,
            "get_example_image_files": self.files.get_example_image_files,
            "has_example_images": self.files.has_example_images,
        }
