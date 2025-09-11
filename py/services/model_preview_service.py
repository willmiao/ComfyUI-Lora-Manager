import os
import logging
import base64
from typing import Optional, Dict, Any
from pathlib import Path

from ..utils.constants import PREVIEW_EXTENSIONS, CARD_PREVIEW_WIDTH
from ..utils.exif_utils import ExifUtils
from ..services.websocket_manager import ws_manager
from ..config import config

logger = logging.getLogger(__name__)


class ModelPreviewService:
    """Service for handling model preview operations"""
    
    def __init__(self):
        """Initialize the preview service"""
        pass
    
    async def replace_preview(self, model_path: str, preview_data: str, nsfw_level: Optional[str] = None) -> Dict[str, Any]:
        """Replace model preview image
        
        Args:
            model_path: Path to the model file
            preview_data: Base64 encoded image data or URL
            nsfw_level: NSFW level for the preview
            
        Returns:
            Dict: Result with success status and preview URL
        """
        try:
            model_dir = os.path.dirname(model_path)
            model_name = os.path.splitext(os.path.basename(model_path))[0]
            
            # Determine preview file extension and path
            preview_ext = '.jpg'  # Default to jpg
            if preview_data.startswith('data:image/'):
                # Extract format from data URL
                format_part = preview_data.split(';')[0].split('/')[1]
                if format_part in ['png', 'jpeg', 'jpg', 'webp']:
                    preview_ext = f'.{format_part}' if format_part != 'jpeg' else '.jpg'
            
            preview_path = os.path.join(model_dir, f"{model_name}{preview_ext}")
            
            # Handle base64 data
            if preview_data.startswith('data:image/'):
                # Remove data URL prefix
                image_data = preview_data.split(',')[1]
                image_bytes = base64.b64decode(image_data)
                
                # Save the image
                with open(preview_path, 'wb') as f:
                    f.write(image_bytes)
                    
                logger.info(f"Saved preview image to {preview_path}")
                
            else:
                # Handle URL - download the image
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(preview_data) as response:
                        if response.status == 200:
                            image_bytes = await response.read()
                            with open(preview_path, 'wb') as f:
                                f.write(image_bytes)
                            logger.info(f"Downloaded and saved preview image to {preview_path}")
                        else:
                            raise Exception(f"Failed to download image: HTTP {response.status}")
            
            # Add NSFW metadata if provided
            if nsfw_level:
                await self._add_nsfw_metadata(preview_path, nsfw_level)
            
            # Generate relative URL for response
            relative_path = os.path.relpath(preview_path, config.static_path).replace(os.sep, '/')
            preview_url = f"/static/{relative_path}"
            
            return {
                'success': True,
                'preview_url': preview_url,
                'message': 'Preview image updated successfully'
            }
            
        except Exception as e:
            logger.error(f"Error replacing preview for {model_path}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _add_nsfw_metadata(self, image_path: str, nsfw_level: str) -> None:
        """Add NSFW metadata to image EXIF data
        
        Args:
            image_path: Path to the image file
            nsfw_level: NSFW level to add
        """
        try:
            exif_utils = ExifUtils()
            await exif_utils.add_nsfw_metadata(image_path, nsfw_level)
            logger.debug(f"Added NSFW metadata ({nsfw_level}) to {image_path}")
        except Exception as e:
            logger.warning(f"Failed to add NSFW metadata to {image_path}: {e}")
    
    def get_preview_path(self, model_path: str) -> Optional[str]:
        """Get the preview image path for a model
        
        Args:
            model_path: Path to the model file
            
        Returns:
            Optional[str]: Path to preview image if found, None otherwise
        """
        model_dir = os.path.dirname(model_path)
        model_name = os.path.splitext(os.path.basename(model_path))[0]
        
        # Check for preview files with different extensions
        for ext in PREVIEW_EXTENSIONS:
            preview_path = os.path.join(model_dir, f"{model_name}{ext}")
            if os.path.exists(preview_path):
                return preview_path
        
        return None
    
    def get_preview_url(self, model_path: str) -> Optional[str]:
        """Get the preview URL for a model
        
        Args:
            model_path: Path to the model file
            
        Returns:
            Optional[str]: Preview URL if found, None otherwise
        """
        preview_path = self.get_preview_path(model_path)
        if preview_path:
            try:
                relative_path = os.path.relpath(preview_path, config.static_path).replace(os.sep, '/')
                return f"/static/{relative_path}"
            except ValueError:
                # Path is not relative to static path
                logger.warning(f"Preview path {preview_path} is not within static directory")
        
        return None
    
    def has_preview(self, model_path: str) -> bool:
        """Check if a model has a preview image
        
        Args:
            model_path: Path to the model file
            
        Returns:
            bool: True if preview exists, False otherwise
        """
        return self.get_preview_path(model_path) is not None
    
    async def delete_preview(self, model_path: str) -> bool:
        """Delete preview image for a model
        
        Args:
            model_path: Path to the model file
            
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        preview_path = self.get_preview_path(model_path)
        if preview_path:
            try:
                os.remove(preview_path)
                logger.info(f"Deleted preview image: {preview_path}")
                return True
            except OSError as e:
                logger.error(f"Error deleting preview {preview_path}: {e}")
                return False
        
        return False
    
    async def resize_preview(self, preview_path: str, max_width: int = CARD_PREVIEW_WIDTH) -> bool:
        """Resize preview image to specified width while maintaining aspect ratio
        
        Args:
            preview_path: Path to the preview image
            max_width: Maximum width for the resized image
            
        Returns:
            bool: True if resized successfully, False otherwise
        """
        try:
            from PIL import Image
            
            with Image.open(preview_path) as img:
                # Calculate new dimensions
                width, height = img.size
                if width <= max_width:
                    return True  # No need to resize
                
                ratio = max_width / width
                new_height = int(height * ratio)
                
                # Resize image
                resized_img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                
                # Save back to the same path
                resized_img.save(preview_path, optimize=True, quality=85)
                logger.info(f"Resized preview {preview_path} to {max_width}x{new_height}")
                return True
                
        except ImportError:
            logger.warning("PIL not available for image resizing")
            return False
        except Exception as e:
            logger.error(f"Error resizing preview {preview_path}: {e}")
            return False
