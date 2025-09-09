"""
Unified download manager for all HTTP/HTTPS downloads in the application.

This module provides a centralized download service with:
- Singleton pattern for global session management
- Support for authenticated downloads (e.g., CivitAI API key)
- Resumable downloads with automatic retry
- Progress tracking and callbacks
- Optimized connection pooling and timeouts
- Unified error handling and logging
"""

import os
import logging
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict, Tuple, Callable, Union
from ..services.settings_manager import settings

logger = logging.getLogger(__name__)


class Downloader:
    """Unified downloader for all HTTP/HTTPS downloads in the application."""
    
    _instance = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_instance(cls):
        """Get singleton instance of Downloader"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    def __init__(self):
        """Initialize the downloader with optimal settings"""
        # Check if already initialized for singleton pattern
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # Session management
        self._session = None
        self._session_created_at = None
        
        # Configuration
        self.chunk_size = 4 * 1024 * 1024  # 4MB chunks for better throughput
        self.max_retries = 5
        self.base_delay = 2.0  # Base delay for exponential backoff
        self.session_timeout = 300  # 5 minutes
        
        # Default headers
        self.default_headers = {
            'User-Agent': 'ComfyUI-LoRA-Manager/1.0'
        }
    
    @property
    async def session(self) -> aiohttp.ClientSession:
        """Get or create the global aiohttp session with optimized settings"""
        if self._session is None or self._should_refresh_session():
            await self._create_session()
        return self._session
    
    def _should_refresh_session(self) -> bool:
        """Check if session should be refreshed"""
        if self._session is None:
            return True
        
        if not hasattr(self, '_session_created_at') or self._session_created_at is None:
            return True
        
        # Refresh if session is older than timeout
        if (datetime.now() - self._session_created_at).total_seconds() > self.session_timeout:
            return True
        
        return False
    
    async def _create_session(self):
        """Create a new aiohttp session with optimized settings"""
        # Close existing session if any
        if self._session is not None:
            await self._session.close()
        
        # Optimize TCP connection parameters
        connector = aiohttp.TCPConnector(
            ssl=True,
            limit=8,  # Concurrent connections
            ttl_dns_cache=300,  # DNS cache timeout
            force_close=False,  # Keep connections for reuse
            enable_cleanup_closed=True
        )
        
        # Configure timeout parameters
        timeout = aiohttp.ClientTimeout(
            total=None,  # No total timeout for large downloads
            connect=60,  # Connection timeout
            sock_read=None  # No socket read timeout
        )
        
        self._session = aiohttp.ClientSession(
            connector=connector,
            trust_env=True,  # Use system proxy settings
            timeout=timeout
        )
        self._session_created_at = datetime.now()
        
        logger.debug("Created new HTTP session")
    
    def _get_auth_headers(self, use_auth: bool = False) -> Dict[str, str]:
        """Get headers with optional authentication"""
        headers = self.default_headers.copy()
        
        if use_auth:
            # Add CivitAI API key if available
            api_key = settings.get('civitai_api_key')
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
                headers['Content-Type'] = 'application/json'
        
        return headers
    
    async def download_file(
        self,
        url: str,
        save_path: str,
        progress_callback: Optional[Callable[[float], None]] = None,
        use_auth: bool = False,
        custom_headers: Optional[Dict[str, str]] = None,
        allow_resume: bool = True
    ) -> Tuple[bool, str]:
        """
        Download a file with resumable downloads and retry mechanism
        
        Args:
            url: Download URL
            save_path: Full path where the file should be saved
            progress_callback: Optional callback for progress updates (0-100)
            use_auth: Whether to include authentication headers (e.g., CivitAI API key)
            custom_headers: Additional headers to include in request
            allow_resume: Whether to support resumable downloads
            
        Returns:
            Tuple[bool, str]: (success, save_path or error message)
        """
        retry_count = 0
        part_path = save_path + '.part' if allow_resume else save_path
        
        # Prepare headers
        headers = self._get_auth_headers(use_auth)
        if custom_headers:
            headers.update(custom_headers)
        
        # Get existing file size for resume
        resume_offset = 0
        if allow_resume and os.path.exists(part_path):
            resume_offset = os.path.getsize(part_path)
            logger.info(f"Resuming download from offset {resume_offset} bytes")
        
        total_size = 0
        
        while retry_count <= self.max_retries:
            try:
                session = await self.session
                
                # Add Range header for resume if we have partial data
                request_headers = headers.copy()
                if allow_resume and resume_offset > 0:
                    request_headers['Range'] = f'bytes={resume_offset}-'
                
                # Disable compression for better chunked downloads
                request_headers['Accept-Encoding'] = 'identity'
                
                logger.debug(f"Download attempt {retry_count + 1}/{self.max_retries + 1} from: {url}")
                if resume_offset > 0:
                    logger.debug(f"Requesting range from byte {resume_offset}")
                
                async with session.get(url, headers=request_headers, allow_redirects=True) as response:
                    # Handle different response codes
                    if response.status == 200:
                        # Full content response
                        if resume_offset > 0:
                            # Server doesn't support ranges, restart from beginning
                            logger.warning("Server doesn't support range requests, restarting download")
                            resume_offset = 0
                            if os.path.exists(part_path):
                                os.remove(part_path)
                    elif response.status == 206:
                        # Partial content response (resume successful)
                        content_range = response.headers.get('Content-Range')
                        if content_range:
                            # Parse total size from Content-Range header (e.g., "bytes 1024-2047/2048")
                            range_parts = content_range.split('/')
                            if len(range_parts) == 2:
                                total_size = int(range_parts[1])
                        logger.info(f"Successfully resumed download from byte {resume_offset}")
                    elif response.status == 416:
                        # Range not satisfiable - file might be complete or corrupted
                        if allow_resume and os.path.exists(part_path):
                            part_size = os.path.getsize(part_path)
                            logger.warning(f"Range not satisfiable. Part file size: {part_size}")
                            # Try to get actual file size
                            head_response = await session.head(url, headers=headers)
                            if head_response.status == 200:
                                actual_size = int(head_response.headers.get('content-length', 0))
                                if part_size == actual_size:
                                    # File is complete, just rename it
                                    if allow_resume:
                                        os.rename(part_path, save_path)
                                    if progress_callback:
                                        await progress_callback(100)
                                    return True, save_path
                            # Remove corrupted part file and restart
                            os.remove(part_path)
                            resume_offset = 0
                            continue
                    elif response.status == 401:
                        logger.warning(f"Unauthorized access to resource: {url} (Status 401)")
                        return False, "Invalid or missing API key, or early access restriction."
                    elif response.status == 403:
                        logger.warning(f"Forbidden access to resource: {url} (Status 403)")
                        return False, "Access forbidden: You don't have permission to download this file."
                    elif response.status == 404:
                        logger.warning(f"Resource not found: {url} (Status 404)")
                        return False, "File not found - the download link may be invalid or expired."
                    else:
                        logger.error(f"Download failed for {url} with status {response.status}")
                        return False, f"Download failed with status {response.status}"
                    
                    # Get total file size for progress calculation (if not set from Content-Range)
                    if total_size == 0:
                        total_size = int(response.headers.get('content-length', 0))
                        if response.status == 206:
                            # For partial content, add the offset to get total file size
                            total_size += resume_offset
                    
                    current_size = resume_offset
                    last_progress_report_time = datetime.now()
                    
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    
                    # Stream download to file with progress updates
                    loop = asyncio.get_running_loop()
                    mode = 'ab' if (allow_resume and resume_offset > 0) else 'wb'
                    with open(part_path, mode) as f:
                        async for chunk in response.content.iter_chunked(self.chunk_size):
                            if chunk:
                                # Run blocking file write in executor
                                await loop.run_in_executor(None, f.write, chunk)
                                current_size += len(chunk)
                                
                                # Limit progress update frequency to reduce overhead
                                now = datetime.now()
                                time_diff = (now - last_progress_report_time).total_seconds()
                                
                                if progress_callback and total_size and time_diff >= 1.0:
                                    progress = (current_size / total_size) * 100
                                    await progress_callback(progress)
                                    last_progress_report_time = now
                    
                    # Download completed successfully
                    # Verify file size if total_size was provided
                    final_size = os.path.getsize(part_path)
                    if total_size > 0 and final_size != total_size:
                        logger.warning(f"File size mismatch. Expected: {total_size}, Got: {final_size}")
                        # Don't treat this as fatal error, continue anyway
                    
                    # Atomically rename .part to final file (only if using resume)
                    if allow_resume and part_path != save_path:
                        max_rename_attempts = 5
                        rename_attempt = 0
                        rename_success = False
                        
                        while rename_attempt < max_rename_attempts and not rename_success:
                            try:
                                # If the destination file exists, remove it first (Windows safe)
                                if os.path.exists(save_path):
                                    os.remove(save_path)

                                os.rename(part_path, save_path)
                                rename_success = True
                            except PermissionError as e:
                                rename_attempt += 1
                                if rename_attempt < max_rename_attempts:
                                    logger.info(f"File still in use, retrying rename in 2 seconds (attempt {rename_attempt}/{max_rename_attempts})")
                                    await asyncio.sleep(2)
                                else:
                                    logger.error(f"Failed to rename file after {max_rename_attempts} attempts: {e}")
                                    return False, f"Failed to finalize download: {str(e)}"
                    
                    # Ensure 100% progress is reported
                    if progress_callback:
                        await progress_callback(100)
                    
                    return True, save_path
                    
            except (aiohttp.ClientError, aiohttp.ClientPayloadError,
                    aiohttp.ServerDisconnectedError, asyncio.TimeoutError) as e:
                retry_count += 1
                logger.warning(f"Network error during download (attempt {retry_count}/{self.max_retries + 1}): {e}")
                
                if retry_count <= self.max_retries:
                    # Calculate delay with exponential backoff
                    delay = self.base_delay * (2 ** (retry_count - 1))
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    
                    # Update resume offset for next attempt
                    if allow_resume and os.path.exists(part_path):
                        resume_offset = os.path.getsize(part_path)
                        logger.info(f"Will resume from byte {resume_offset}")
                    
                    # Refresh session to get new connection
                    await self._create_session()
                    continue
                else:
                    logger.error(f"Max retries exceeded for download: {e}")
                    return False, f"Network error after {self.max_retries + 1} attempts: {str(e)}"
                    
            except Exception as e:
                logger.error(f"Unexpected download error: {e}")
                return False, str(e)
        
        return False, f"Download failed after {self.max_retries + 1} attempts"
    
    async def download_to_memory(
        self,
        url: str,
        use_auth: bool = False,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, Union[bytes, str]]:
        """
        Download a file to memory (for small files like preview images)
        
        Args:
            url: Download URL
            use_auth: Whether to include authentication headers
            custom_headers: Additional headers to include in request
            
        Returns:
            Tuple[bool, Union[bytes, str]]: (success, content or error message)
        """
        try:
            session = await self.session
            
            # Prepare headers
            headers = self._get_auth_headers(use_auth)
            if custom_headers:
                headers.update(custom_headers)
            
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    content = await response.read()
                    return True, content
                elif response.status == 401:
                    return False, "Unauthorized access - invalid or missing API key"
                elif response.status == 403:
                    return False, "Access forbidden"
                elif response.status == 404:
                    return False, "File not found"
                else:
                    return False, f"Download failed with status {response.status}"
                    
        except Exception as e:
            logger.error(f"Error downloading to memory from {url}: {e}")
            return False, str(e)
    
    async def get_response_headers(
        self,
        url: str,
        use_auth: bool = False,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Get response headers without downloading the full content
        
        Args:
            url: URL to check
            use_auth: Whether to include authentication headers
            custom_headers: Additional headers to include in request
            
        Returns:
            Tuple[bool, Union[Dict, str]]: (success, headers dict or error message)
        """
        try:
            session = await self.session
            
            # Prepare headers
            headers = self._get_auth_headers(use_auth)
            if custom_headers:
                headers.update(custom_headers)
            
            async with session.head(url, headers=headers) as response:
                if response.status == 200:
                    return True, dict(response.headers)
                else:
                    return False, f"Head request failed with status {response.status}"
                    
        except Exception as e:
            logger.error(f"Error getting headers from {url}: {e}")
            return False, str(e)
    
    async def make_request(
        self,
        method: str,
        url: str,
        use_auth: bool = False,
        custom_headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Make a generic HTTP request and return JSON response
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            use_auth: Whether to include authentication headers
            custom_headers: Additional headers to include in request
            **kwargs: Additional arguments for aiohttp request
            
        Returns:
            Tuple[bool, Union[Dict, str]]: (success, response data or error message)
        """
        try:
            session = await self.session
            
            # Prepare headers
            headers = self._get_auth_headers(use_auth)
            if custom_headers:
                headers.update(custom_headers)
            
            async with session.request(method, url, headers=headers, **kwargs) as response:
                if response.status == 200:
                    # Try to parse as JSON, fall back to text
                    try:
                        data = await response.json()
                        return True, data
                    except:
                        text = await response.text()
                        return True, text
                elif response.status == 401:
                    return False, "Unauthorized access - invalid or missing API key"
                elif response.status == 403:
                    return False, "Access forbidden"
                elif response.status == 404:
                    return False, "Resource not found"
                else:
                    return False, f"Request failed with status {response.status}"
                    
        except Exception as e:
            logger.error(f"Error making {method} request to {url}: {e}")
            return False, str(e)
    
    async def close(self):
        """Close the HTTP session"""
        if self._session is not None:
            await self._session.close()
            self._session = None
            self._session_created_at = None
            logger.debug("Closed HTTP session")


# Global instance accessor
async def get_downloader() -> Downloader:
    """Get the global downloader instance"""
    return await Downloader.get_instance()
