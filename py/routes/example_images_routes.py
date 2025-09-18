import logging
from ..utils.example_images_download_manager import DownloadManager
from ..utils.example_images_processor import ExampleImagesProcessor
from ..utils.example_images_file_manager import ExampleImagesFileManager
from ..services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

class ExampleImagesRoutes:
    """Routes for example images related functionality"""
    
    @staticmethod
    def setup_routes(app):
        """Register example images routes"""
        app.router.add_post('/api/lm/download-example-images', ExampleImagesRoutes.download_example_images)
        app.router.add_post('/api/lm/import-example-images', ExampleImagesRoutes.import_example_images)
        app.router.add_get('/api/lm/example-images-status', ExampleImagesRoutes.get_example_images_status)
        app.router.add_post('/api/lm/pause-example-images', ExampleImagesRoutes.pause_example_images)
        app.router.add_post('/api/lm/resume-example-images', ExampleImagesRoutes.resume_example_images)
        app.router.add_post('/api/lm/open-example-images-folder', ExampleImagesRoutes.open_example_images_folder)
        app.router.add_get('/api/lm/example-image-files', ExampleImagesRoutes.get_example_image_files)
        app.router.add_get('/api/lm/has-example-images', ExampleImagesRoutes.has_example_images)
        app.router.add_post('/api/lm/delete-example-image', ExampleImagesRoutes.delete_example_image)
        app.router.add_post('/api/lm/force-download-example-images', ExampleImagesRoutes.force_download_example_images)

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