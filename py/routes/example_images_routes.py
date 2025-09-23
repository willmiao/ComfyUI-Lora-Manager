import logging
from typing import Callable

from aiohttp import web

from .example_images_route_registrar import ExampleImagesRouteRegistrar
from ..utils.example_images_download_manager import DownloadManager
from ..utils.example_images_processor import ExampleImagesProcessor
from ..utils.example_images_file_manager import ExampleImagesFileManager
from ..services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


class ExampleImagesRoutes:
    """Routes for example images related functionality"""

    @staticmethod
    def setup_routes(app: web.Application) -> None:
        """Register example images routes using the registrar."""

        registrar = ExampleImagesRouteRegistrar(app)
        registrar.register_routes(ExampleImagesRoutes._route_mapping())

    @staticmethod
    def _route_mapping() -> dict[str, Callable[[web.Request], object]]:
        return {
            "download_example_images": ExampleImagesRoutes.download_example_images,
            "import_example_images": ExampleImagesRoutes.import_example_images,
            "get_example_images_status": ExampleImagesRoutes.get_example_images_status,
            "pause_example_images": ExampleImagesRoutes.pause_example_images,
            "resume_example_images": ExampleImagesRoutes.resume_example_images,
            "open_example_images_folder": ExampleImagesRoutes.open_example_images_folder,
            "get_example_image_files": ExampleImagesRoutes.get_example_image_files,
            "has_example_images": ExampleImagesRoutes.has_example_images,
            "delete_example_image": ExampleImagesRoutes.delete_example_image,
            "force_download_example_images": ExampleImagesRoutes.force_download_example_images,
        }

    @staticmethod
    async def download_example_images(request):
        """Download example images for models from Civitai"""
        return await DownloadManager.start_download(request)

    @staticmethod
    async def get_example_images_status(request):
        """Get the current status of example images download"""
        return await DownloadManager.get_status(request)

    @staticmethod
    async def pause_example_images(request):
        """Pause the example images download"""
        return await DownloadManager.pause_download(request)

    @staticmethod
    async def resume_example_images(request):
        """Resume the example images download"""
        return await DownloadManager.resume_download(request)

    @staticmethod
    async def open_example_images_folder(request):
        """Open the example images folder for a specific model"""
        return await ExampleImagesFileManager.open_folder(request)

    @staticmethod
    async def get_example_image_files(request):
        """Get list of example image files for a specific model"""
        return await ExampleImagesFileManager.get_files(request)

    @staticmethod
    async def import_example_images(request):
        """Import local example images for a model"""
        return await ExampleImagesProcessor.import_images(request)

    @staticmethod
    async def has_example_images(request):
        """Check if example images folder exists and is not empty for a model"""
        return await ExampleImagesFileManager.has_images(request)

    @staticmethod
    async def delete_example_image(request):
        """Delete a custom example image for a model"""
        return await ExampleImagesProcessor.delete_custom_image(request)

    @staticmethod
    async def force_download_example_images(request):
        """Force download example images for specific models"""
        return await DownloadManager.start_force_download(request)
