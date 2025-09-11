import os
import logging
from typing import List
from pathlib import Path

from ..utils.constants import PREVIEW_EXTENSIONS

logger = logging.getLogger(__name__)


class ModelFileService:
    """Service for handling model file operations"""
    
    def __init__(self):
        """Initialize the file service"""
        pass
    
    async def delete_model_files(self, target_dir: str, file_name: str) -> List[str]:
        """Delete model and associated files
        
        Args:
            target_dir: Directory containing the model files
            file_name: Base name of the model file without extension
            
        Returns:
            List[str]: List of deleted file paths
        """
        patterns = [
            f"{file_name}.safetensors",
            f"{file_name}.metadata.json",
        ]
        
        # Add all preview file extensions
        for ext in PREVIEW_EXTENSIONS:
            patterns.append(f"{file_name}{ext}")
        
        deleted = []
        main_file = patterns[0]
        main_path = os.path.join(target_dir, main_file).replace(os.sep, '/')
        
        if os.path.exists(main_path):
            try:
                os.remove(main_path)
                deleted.append(main_path)
                logger.info(f"Deleted main file: {main_path}")
            except OSError as e:
                logger.error(f"Error deleting main file {main_path}: {e}")
                raise
        else:
            logger.warning(f"Main file not found: {main_path}")
            # Still try to delete associated files even if main file doesn't exist
            
        # Delete optional files
        for pattern in patterns[1:]:
            file_path = os.path.join(target_dir, pattern).replace(os.sep, '/')
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    deleted.append(file_path)
                    logger.info(f"Deleted associated file: {file_path}")
                except OSError as e:
                    logger.warning(f"Error deleting associated file {file_path}: {e}")
                    
        return deleted
    
    def get_multipart_ext(self, filename: str) -> str:
        """Get extension that may have multiple parts like .metadata.json or .metadata.json.bak
        
        Args:
            filename: The filename to extract extension from
            
        Returns:
            str: The extension
        """
        parts = filename.split(".")
        if len(parts) == 3:
            return f".{parts[1]}.{parts[2]}"
        elif len(parts) >= 4:
            return f".{parts[1]}.{parts[2]}.{parts[3]}"
        return os.path.splitext(filename)[1]
    
    async def move_model_file(self, source_path: str, target_path: str) -> bool:
        """Move a model file from source to target path
        
        Args:
            source_path: Source file path
            target_path: Target file path
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure target directory exists
            target_dir = os.path.dirname(target_path)
            os.makedirs(target_dir, exist_ok=True)
            
            # Move the file
            os.rename(source_path, target_path)
            logger.info(f"Moved file from {source_path} to {target_path}")
            return True
            
        except OSError as e:
            logger.error(f"Error moving file from {source_path} to {target_path}: {e}")
            return False
    
    async def copy_model_file(self, source_path: str, target_path: str) -> bool:
        """Copy a model file from source to target path
        
        Args:
            source_path: Source file path
            target_path: Target file path
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import shutil
            
            # Ensure target directory exists
            target_dir = os.path.dirname(target_path)
            os.makedirs(target_dir, exist_ok=True)
            
            # Copy the file
            shutil.copy2(source_path, target_path)
            logger.info(f"Copied file from {source_path} to {target_path}")
            return True
            
        except (OSError, IOError) as e:
            logger.error(f"Error copying file from {source_path} to {target_path}: {e}")
            return False
    
    def file_exists(self, file_path: str) -> bool:
        """Check if a file exists
        
        Args:
            file_path: Path to check
            
        Returns:
            bool: True if file exists, False otherwise
        """
        return os.path.exists(file_path) and os.path.isfile(file_path)
    
    def get_file_size(self, file_path: str) -> int:
        """Get file size in bytes
        
        Args:
            file_path: Path to the file
            
        Returns:
            int: File size in bytes, or 0 if file doesn't exist
        """
        try:
            return os.path.getsize(file_path)
        except OSError:
            return 0
    
    def get_file_extension(self, file_path: str) -> str:
        """Get file extension
        
        Args:
            file_path: Path to the file
            
        Returns:
            str: File extension including the dot
        """
        return Path(file_path).suffix
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to remove invalid characters
        
        Args:
            filename: Original filename
            
        Returns:
            str: Sanitized filename
        """
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remove leading/trailing whitespace and dots
        filename = filename.strip(' .')
        
        # Ensure filename is not empty
        if not filename:
            filename = "untitled"
        
        return filename
