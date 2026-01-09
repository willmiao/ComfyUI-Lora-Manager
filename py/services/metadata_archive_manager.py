import zipfile
import logging
import asyncio
import shutil
from pathlib import Path
from typing import Optional
from .downloader import get_downloader, DownloadProgress

logger = logging.getLogger(__name__)

class MetadataArchiveManager:
    """Manages downloading and extracting Civitai metadata archive database"""
    
    DOWNLOAD_URLS = [
        "https://github.com/willmiao/civitai-metadata-archive-db/releases/download/db-2025-08-08/civitai.zip",
        "https://huggingface.co/datasets/willmiao/civitai-metadata-archive-db/blob/main/civitai.zip"
    ]
    
    def __init__(self, base_path: str, custom_db_path: Optional[str] = None):
        """Initialize with base path where files will be stored
        
        Args:
            base_path: Default base path (used if custom_db_path is not provided)
            custom_db_path: Optional custom path to the database file or directory. 
                          If it's a directory, will append "civitai.sqlite" to it.
        """
        self.base_path = Path(base_path)
        
        if custom_db_path:
            custom_path_obj = Path(custom_db_path)
            # Check if it's a directory (exists and is a directory, or has no extension)
            if custom_path_obj.exists() and custom_path_obj.is_dir():
                # It's a directory, append the database filename
                self.custom_db_path = custom_path_obj / "civitai.sqlite"
                logger.debug(f"Custom path is a directory, using: {self.custom_db_path}")
            elif not custom_path_obj.suffix:
                # No extension, assume it's a directory path
                self.custom_db_path = custom_path_obj / "civitai.sqlite"
                logger.debug(f"Custom path has no extension, treating as directory: {self.custom_db_path}")
            else:
                # Use as-is (should be a file path)
                self.custom_db_path = custom_path_obj
        else:
            self.custom_db_path = None
        
        if self.custom_db_path:
            # Use custom path as the database file
            self.db_path = self.custom_db_path
            # For archive operations, use the parent directory
            self.civitai_folder = self.db_path.parent
            self.archive_path = self.civitai_folder / "civitai.zip"
        else:
            # Use default structure
            self.civitai_folder = self.base_path / "civitai"
            self.archive_path = self.base_path / "civitai.zip"
            self.db_path = self.civitai_folder / "civitai.sqlite"
        
    def is_database_available(self) -> bool:
        """Check if the SQLite database is available and valid"""
        return self.db_path.exists() and self.db_path.stat().st_size > 0
        
    def get_database_path(self) -> Optional[str]:
        """Get the path to the SQLite database if available"""
        if self.is_database_available():
            return str(self.db_path)
        return None
        
    async def download_and_extract_database(self, progress_callback=None) -> bool:
        """Download and extract the metadata archive database
        
        Args:
            progress_callback: Optional callback function to report progress
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create directories if they don't exist
            if self.custom_db_path:
                # For custom path, ensure parent directory exists
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                # Use parent directory for archive operations
                temp_extract_path = self.db_path.parent
            else:
                # Default structure
                self.base_path.mkdir(parents=True, exist_ok=True)
                self.civitai_folder.mkdir(parents=True, exist_ok=True)
                temp_extract_path = self.base_path
            
            # Download the archive
            if not await self._download_archive(progress_callback):
                return False
                
            # Extract the archive
            if not await self._extract_archive(progress_callback, temp_extract_path):
                return False
            
            # If using custom path, move the database file to the custom location
            if self.custom_db_path:
                extracted_db = temp_extract_path / "civitai" / "civitai.sqlite"
                if extracted_db.exists():
                    shutil.move(str(extracted_db), str(self.db_path))
                    # Clean up extracted civitai folder if empty
                    try:
                        civitai_folder = temp_extract_path / "civitai"
                        if civitai_folder.exists():
                            # Remove any remaining files
                            for item in civitai_folder.iterdir():
                                if item.is_file():
                                    item.unlink()
                                elif item.is_dir():
                                    shutil.rmtree(item)
                            civitai_folder.rmdir()
                    except Exception:
                        pass  # Ignore cleanup errors
                
            # Clean up the archive file
            if self.archive_path.exists():
                self.archive_path.unlink()
                
            logger.info(f"Successfully downloaded and extracted metadata database to {self.db_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading and extracting metadata database: {e}", exc_info=True)
            return False
            
    async def _download_archive(self, progress_callback=None) -> bool:
        """Download the zip archive from one of the available URLs"""
        downloader = await get_downloader()
        
        for url in self.DOWNLOAD_URLS:
            try:
                logger.info(f"Attempting to download from {url}")
                
                if progress_callback:
                    progress_callback("download", f"Downloading from {url}")
                
                # Custom progress callback to report download progress
                async def download_progress(progress, snapshot=None):
                    if progress_callback:
                        if isinstance(progress, DownloadProgress):
                            percent = progress.percent_complete
                        elif isinstance(snapshot, DownloadProgress):
                            percent = snapshot.percent_complete
                        else:
                            percent = float(progress or 0)
                        progress_callback("download", f"Downloading archive... {percent:.1f}%")
                
                success, result = await downloader.download_file(
                    url=url,
                    save_path=str(self.archive_path),
                    progress_callback=download_progress,
                    use_auth=False,  # Public download, no auth needed
                    allow_resume=True
                )
                
                if success:
                    logger.info(f"Successfully downloaded archive from {url}")
                    return True
                else:
                    logger.warning(f"Failed to download from {url}: {result}")
                    continue
                            
            except Exception as e:
                logger.warning(f"Error downloading from {url}: {e}")
                continue
                
        logger.error("Failed to download archive from any URL")
        return False
        
    async def _extract_archive(self, progress_callback=None, extract_path=None) -> bool:
        """Extract the zip archive to the specified path
        
        Args:
            progress_callback: Optional callback function to report progress
            extract_path: Path to extract to (defaults to base_path)
        """
        try:
            if progress_callback:
                progress_callback("extract", "Extracting archive...")
            
            extract_to = Path(extract_path) if extract_path else self.base_path
                
            # Run extraction in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._extract_zip_sync, extract_to)
            
            if progress_callback:
                progress_callback("extract", "Extraction completed")
            
            return True
            
        except Exception as e:
            logger.error(f"Error extracting archive: {e}", exc_info=True)
            return False
            
    def _extract_zip_sync(self, extract_path: Path):
        """Synchronous zip extraction (runs in thread pool)"""
        with zipfile.ZipFile(self.archive_path, 'r') as archive:
            archive.extractall(path=extract_path)
            
    async def remove_database(self) -> bool:
        """Remove the metadata database and folder"""
        try:
            if self.custom_db_path and self.db_path.exists():
                # If using custom path, just remove the database file
                self.db_path.unlink()
                logger.info(f"Removed custom database file: {self.db_path}")
            elif self.civitai_folder.exists():
                # Remove all files in the civitai folder
                for file_path in self.civitai_folder.iterdir():
                    if file_path.is_file():
                        file_path.unlink()
                        
                # Remove the folder itself
                self.civitai_folder.rmdir()
            
            # Also remove the archive file if it exists
            if self.archive_path.exists():
                self.archive_path.unlink()
            
            logger.info("Successfully removed metadata database")
            return True
            
        except Exception as e:
            logger.error(f"Error removing metadata database: {e}", exc_info=True)
            return False
    
    def move_database(self, new_path: str) -> bool:
        """Move the database to a new location
        
        Args:
            new_path: New path for the database file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            new_db_path = Path(new_path)
            
            # Ensure the new directory exists
            new_db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if database exists at current location
            if not self.db_path.exists():
                logger.warning(f"Database not found at {self.db_path}, nothing to move")
                return False
            
            # Move the database file
            shutil.move(str(self.db_path), str(new_db_path))
            logger.info(f"Moved database from {self.db_path} to {new_db_path}")
            
            # Update internal path
            self.db_path = new_db_path
            self.custom_db_path = new_db_path
            self.civitai_folder = new_db_path.parent
            self.archive_path = self.civitai_folder / "civitai.zip"
            
            # Clean up old folder if it's empty (for default structure)
            old_folder = self.base_path / "civitai"
            if old_folder.exists() and old_folder != self.civitai_folder:
                try:
                    # Check if folder is empty
                    if not any(old_folder.iterdir()):
                        old_folder.rmdir()
                        logger.info(f"Removed empty old folder: {old_folder}")
                except Exception:
                    pass  # Ignore errors cleaning up old folder
            
            return True
            
        except Exception as e:
            logger.error(f"Error moving database: {e}", exc_info=True)
            return False
