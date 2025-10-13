import zipfile
import logging
import asyncio
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
    
    def __init__(self, base_path: str):
        """Initialize with base path where files will be stored"""
        self.base_path = Path(base_path)
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
            self.base_path.mkdir(parents=True, exist_ok=True)
            self.civitai_folder.mkdir(parents=True, exist_ok=True)
            
            # Download the archive
            if not await self._download_archive(progress_callback):
                return False
                
            # Extract the archive
            if not await self._extract_archive(progress_callback):
                return False
                
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
        
    async def _extract_archive(self, progress_callback=None) -> bool:
        """Extract the zip archive to the civitai folder"""
        try:
            if progress_callback:
                progress_callback("extract", "Extracting archive...")
                
            # Run extraction in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._extract_zip_sync)
            
            if progress_callback:
                progress_callback("extract", "Extraction completed")
                
            return True
            
        except Exception as e:
            logger.error(f"Error extracting archive: {e}", exc_info=True)
            return False
            
    def _extract_zip_sync(self):
        """Synchronous zip extraction (runs in thread pool)"""
        with zipfile.ZipFile(self.archive_path, 'r') as archive:
            archive.extractall(path=self.base_path)
            
    async def remove_database(self) -> bool:
        """Remove the metadata database and folder"""
        try:
            if self.civitai_folder.exists():
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
