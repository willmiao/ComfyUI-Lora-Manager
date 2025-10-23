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
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional, Dict, Tuple, Callable, Union, Awaitable
from ..services.settings_manager import get_settings_manager
from .errors import RateLimitError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadProgress:
    """Snapshot of a download transfer at a moment in time."""

    percent_complete: float
    bytes_downloaded: int
    total_bytes: Optional[int]
    bytes_per_second: float
    timestamp: float


class DownloadStreamControl:
    """Synchronize pause/resume requests and reconnect hints for a download."""

    def __init__(self, *, stall_timeout: Optional[float] = None) -> None:
        self._event = asyncio.Event()
        self._event.set()
        self._reconnect_requested = False
        self.last_progress_timestamp: Optional[float] = None
        self.stall_timeout: float = float(stall_timeout) if stall_timeout is not None else 120.0

    def is_set(self) -> bool:
        return self._event.is_set()

    def is_paused(self) -> bool:
        return not self._event.is_set()

    def set(self) -> None:
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    async def wait(self) -> None:
        await self._event.wait()

    def pause(self) -> None:
        self.clear()

    def resume(self, *, force_reconnect: bool = False) -> None:
        if force_reconnect:
            self._reconnect_requested = True
        self.set()

    def request_reconnect(self) -> None:
        self._reconnect_requested = True
        self.set()

    def has_reconnect_request(self) -> bool:
        return self._reconnect_requested

    def consume_reconnect_request(self) -> bool:
        reconnect = self._reconnect_requested
        self._reconnect_requested = False
        return reconnect

    def mark_progress(self, timestamp: Optional[float] = None) -> None:
        self.last_progress_timestamp = timestamp or datetime.now().timestamp()
        self._reconnect_requested = False

    def time_since_last_progress(self, *, now: Optional[float] = None) -> Optional[float]:
        if self.last_progress_timestamp is None:
            return None
        reference = now if now is not None else datetime.now().timestamp()
        return max(0.0, reference - self.last_progress_timestamp)

    def update_stall_timeout(self, stall_timeout: float) -> None:
        self.stall_timeout = float(stall_timeout)


class DownloadRestartRequested(Exception):
    """Raised when a caller explicitly requests a fresh HTTP stream."""


class DownloadStalledError(Exception):
    """Raised when download progress stalls beyond the configured timeout."""


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
        self._proxy_url = None  # Store proxy URL for current session
        
        # Configuration
        self.chunk_size = 4 * 1024 * 1024  # 4MB chunks for better throughput
        self.max_retries = 5
        self.base_delay = 2.0  # Base delay for exponential backoff
        self.session_timeout = 300  # 5 minutes
        self.stall_timeout = self._resolve_stall_timeout()
        
        # Default headers
        self.default_headers = {
            'User-Agent': 'ComfyUI-LoRA-Manager/1.0',
            # Explicitly request uncompressed payloads so aiohttp doesn't need optional
            # decoders (e.g. zstandard) that may be missing in runtime environments.
            'Accept-Encoding': 'identity',
        }
    
    @property
    async def session(self) -> aiohttp.ClientSession:
        """Get or create the global aiohttp session with optimized settings"""
        if self._session is None or self._should_refresh_session():
            await self._create_session()
        return self._session

    @property
    def proxy_url(self) -> Optional[str]:
        """Get the current proxy URL (initialize if needed)"""
        if not hasattr(self, '_proxy_url'):
            self._proxy_url = None
        return self._proxy_url

    def _resolve_stall_timeout(self) -> float:
        """Determine the stall timeout from settings or environment."""
        default_timeout = 120.0
        settings_timeout = None

        try:
            settings_manager = get_settings_manager()
            settings_timeout = settings_manager.get('download_stall_timeout_seconds')
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("Failed to read stall timeout from settings: %s", exc)

        raw_value = (
            settings_timeout
            if settings_timeout not in (None, "")
            else os.environ.get('COMFYUI_DOWNLOAD_STALL_TIMEOUT')
        )

        try:
            timeout_value = float(raw_value)
        except (TypeError, ValueError):
            timeout_value = default_timeout

        return max(30.0, timeout_value)

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
        
        # Check for app-level proxy settings
        proxy_url = None
        settings_manager = get_settings_manager()
        if settings_manager.get('proxy_enabled', False):
            proxy_host = settings_manager.get('proxy_host', '').strip()
            proxy_port = settings_manager.get('proxy_port', '').strip()
            proxy_type = settings_manager.get('proxy_type', 'http').lower()
            proxy_username = settings_manager.get('proxy_username', '').strip()
            proxy_password = settings_manager.get('proxy_password', '').strip()
            
            if proxy_host and proxy_port:
                # Build proxy URL
                if proxy_username and proxy_password:
                    proxy_url = f"{proxy_type}://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
                else:
                    proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
                
                logger.debug(f"Using app-level proxy: {proxy_type}://{proxy_host}:{proxy_port}")
                logger.debug("Proxy mode: app-level proxy is active.")
        else:
            logger.debug("Proxy mode: system-level proxy (trust_env) will be used if configured in environment.")
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
            sock_read=300  # 5 minute socket read timeout
        )
        
        self._session = aiohttp.ClientSession(
            connector=connector,
            trust_env=proxy_url is None,  # Only use system proxy if no app-level proxy is set
            timeout=timeout
        )
        
        # Store proxy URL for use in requests
        self._proxy_url = proxy_url
        self._session_created_at = datetime.now()
        
        logger.debug("Created new HTTP session with proxy settings. App-level proxy: %s, System-level proxy (trust_env): %s", bool(proxy_url), proxy_url is None)
    
    def _get_auth_headers(self, use_auth: bool = False) -> Dict[str, str]:
        """Get headers with optional authentication"""
        headers = self.default_headers.copy()
        
        if use_auth:
            # Add CivitAI API key if available
            settings_manager = get_settings_manager()
            api_key = settings_manager.get('civitai_api_key')
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
                headers['Content-Type'] = 'application/json'
        
        return headers
    
    async def download_file(
        self,
        url: str,
        save_path: str,
        progress_callback: Optional[Callable[..., Awaitable[None]]] = None,
        use_auth: bool = False,
        custom_headers: Optional[Dict[str, str]] = None,
        allow_resume: bool = True,
        pause_event: Optional[DownloadStreamControl] = None,
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
            pause_event: Optional stream control used to pause/resume and request reconnects
            
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
                # Debug log for proxy mode at request time
                if self.proxy_url:
                    logger.debug(f"[download_file] Using app-level proxy: {self.proxy_url}")
                else:
                    logger.debug("[download_file] Using system-level proxy (trust_env) if configured.")
                
                # Add Range header for resume if we have partial data
                request_headers = headers.copy()
                if allow_resume and resume_offset > 0:
                    request_headers['Range'] = f'bytes={resume_offset}-'
                
                # Disable compression for better chunked downloads
                request_headers['Accept-Encoding'] = 'identity'
                
                logger.debug(f"Download attempt {retry_count + 1}/{self.max_retries + 1} from: {url}")
                if resume_offset > 0:
                    logger.debug(f"Requesting range from byte {resume_offset}")
                
                async with session.get(url, headers=request_headers, allow_redirects=True, proxy=self.proxy_url) as response:
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
                            head_response = await session.head(url, headers=headers, proxy=self.proxy_url)
                            if head_response.status == 200:
                                actual_size = int(head_response.headers.get('content-length', 0))
                                if part_size == actual_size:
                                    # File is complete, just rename it
                                    if allow_resume:
                                        os.rename(part_path, save_path)
                                    if progress_callback:
                                        await self._dispatch_progress_callback(
                                            progress_callback,
                                            DownloadProgress(
                                                percent_complete=100.0,
                                                bytes_downloaded=part_size,
                                                total_bytes=actual_size,
                                                bytes_per_second=0.0,
                                                timestamp=datetime.now().timestamp(),
                                            ),
                                        )
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
                    progress_samples: deque[tuple[datetime, int]] = deque()
                    progress_samples.append((last_progress_report_time, current_size))

                    # Ensure directory exists
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)

                    # Stream download to file with progress updates
                    loop = asyncio.get_running_loop()
                    mode = 'ab' if (allow_resume and resume_offset > 0) else 'wb'
                    control = pause_event

                    if control is not None:
                        control.update_stall_timeout(self.stall_timeout)

                    with open(part_path, mode) as f:
                        while True:
                            active_stall_timeout = control.stall_timeout if control else self.stall_timeout

                            if control is not None:
                                if control.is_paused():
                                    await control.wait()
                                    resume_time = datetime.now()
                                    last_progress_report_time = resume_time
                                    if control.consume_reconnect_request():
                                        raise DownloadRestartRequested(
                                            "Reconnect requested after resume"
                                        )
                                elif control.consume_reconnect_request():
                                    raise DownloadRestartRequested("Reconnect requested")

                            try:
                                chunk = await asyncio.wait_for(
                                    response.content.read(self.chunk_size),
                                    timeout=active_stall_timeout,
                                )
                            except asyncio.TimeoutError as exc:
                                logger.warning(
                                    "Download stalled for %.1f seconds without progress from %s",
                                    active_stall_timeout,
                                    url,
                                )
                                raise DownloadStalledError(
                                    f"No data received for {active_stall_timeout:.1f} seconds"
                                ) from exc

                            if not chunk:
                                break

                            # Run blocking file write in executor
                            await loop.run_in_executor(None, f.write, chunk)
                            current_size += len(chunk)

                            now = datetime.now()
                            if control is not None:
                                control.mark_progress(timestamp=now.timestamp())

                            # Limit progress update frequency to reduce overhead
                            time_diff = (now - last_progress_report_time).total_seconds()

                            if progress_callback and time_diff >= 1.0:
                                progress_samples.append((now, current_size))
                                cutoff = now - timedelta(seconds=5)
                                while progress_samples and progress_samples[0][0] < cutoff:
                                    progress_samples.popleft()

                                percent = (current_size / total_size) * 100 if total_size else 0.0
                                bytes_per_second = 0.0
                                if len(progress_samples) >= 2:
                                    first_time, first_bytes = progress_samples[0]
                                    last_time, last_bytes = progress_samples[-1]
                                    elapsed = (last_time - first_time).total_seconds()
                                    if elapsed > 0:
                                        bytes_per_second = (last_bytes - first_bytes) / elapsed

                                progress_snapshot = DownloadProgress(
                                    percent_complete=percent,
                                    bytes_downloaded=current_size,
                                    total_bytes=total_size or None,
                                    bytes_per_second=bytes_per_second,
                                    timestamp=now.timestamp(),
                                )

                                await self._dispatch_progress_callback(progress_callback, progress_snapshot)
                                last_progress_report_time = now
                    
                    # Download completed successfully
                    # Verify file size integrity before finalizing
                    final_size = os.path.getsize(part_path) if os.path.exists(part_path) else 0
                    expected_size = total_size if total_size > 0 else None

                    integrity_error: Optional[str] = None
                    if final_size <= 0:
                        integrity_error = "Downloaded file is empty"
                    elif expected_size is not None and final_size != expected_size:
                        integrity_error = (
                            f"File size mismatch. Expected: {expected_size}, Got: {final_size}"
                        )

                    if integrity_error is not None:
                        logger.error(
                            "Download integrity check failed for %s: %s",
                            save_path,
                            integrity_error,
                        )

                        # Remove the corrupted payload so future attempts start fresh
                        if os.path.exists(part_path):
                            try:
                                os.remove(part_path)
                            except OSError as remove_error:
                                logger.warning(
                                    "Failed to delete corrupted download %s: %s",
                                    part_path,
                                    remove_error,
                                )
                        if part_path != save_path and os.path.exists(save_path):
                            try:
                                os.remove(save_path)
                            except OSError as remove_error:
                                logger.warning(
                                    "Failed to delete target file %s after integrity error: %s",
                                    save_path,
                                    remove_error,
                                )

                        retry_count += 1
                        if retry_count <= self.max_retries:
                            delay = self.base_delay * (2 ** (retry_count - 1))
                            logger.info(
                                "Retrying download in %s seconds due to integrity check failure",
                                delay,
                            )
                            await asyncio.sleep(delay)
                            resume_offset = 0
                            total_size = 0
                            await self._create_session()
                            continue

                        return False, integrity_error

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

                        final_size = os.path.getsize(save_path)

                    # Ensure 100% progress is reported
                    if progress_callback:
                        final_snapshot = DownloadProgress(
                            percent_complete=100.0,
                            bytes_downloaded=final_size,
                            total_bytes=total_size or final_size,
                            bytes_per_second=0.0,
                            timestamp=datetime.now().timestamp(),
                        )
                        await self._dispatch_progress_callback(progress_callback, final_snapshot)

                    
                    return True, save_path
                    
            except (
                aiohttp.ClientError,
                aiohttp.ClientPayloadError,
                aiohttp.ServerDisconnectedError,
                asyncio.TimeoutError,
                DownloadStalledError,
                DownloadRestartRequested,
            ) as e:
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

    async def _dispatch_progress_callback(
        self,
        progress_callback: Callable[..., Awaitable[None]],
        snapshot: DownloadProgress,
    ) -> None:
        """Invoke a progress callback while preserving backward compatibility."""

        try:
            result = progress_callback(snapshot, snapshot)
        except TypeError:
            result = progress_callback(snapshot.percent_complete)

        if asyncio.iscoroutine(result):
            await result
        elif hasattr(result, "__await__"):
            await result

    async def download_to_memory(
        self,
        url: str,
        use_auth: bool = False,
        custom_headers: Optional[Dict[str, str]] = None,
        return_headers: bool = False
    ) -> Tuple[bool, Union[bytes, str], Optional[Dict]]:
        """
        Download a file to memory (for small files like preview images)
        
        Args:
            url: Download URL
            use_auth: Whether to include authentication headers
            custom_headers: Additional headers to include in request
            return_headers: Whether to return response headers along with content
            
        Returns:
            Tuple[bool, Union[bytes, str], Optional[Dict]]: (success, content or error message, response headers if requested)
        """
        try:
            session = await self.session
            # Debug log for proxy mode at request time
            if self.proxy_url:
                logger.debug(f"[download_to_memory] Using app-level proxy: {self.proxy_url}")
            else:
                logger.debug("[download_to_memory] Using system-level proxy (trust_env) if configured.")
            
            # Prepare headers
            headers = self._get_auth_headers(use_auth)
            if custom_headers:
                headers.update(custom_headers)
            
            async with session.get(url, headers=headers, proxy=self.proxy_url) as response:
                if response.status == 200:
                    content = await response.read()
                    if return_headers:
                        return True, content, dict(response.headers)
                    else:
                        return True, content, None
                elif response.status == 401:
                    error_msg = "Unauthorized access - invalid or missing API key"
                    return False, error_msg, None
                elif response.status == 403:
                    error_msg = "Access forbidden"
                    return False, error_msg, None
                elif response.status == 404:
                    error_msg = "File not found"
                    return False, error_msg, None
                else:
                    error_msg = f"Download failed with status {response.status}"
                    return False, error_msg, None
                    
        except Exception as e:
            logger.error(f"Error downloading to memory from {url}: {e}")
            return False, str(e), None
    
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
            # Debug log for proxy mode at request time
            if self.proxy_url:
                logger.debug(f"[get_response_headers] Using app-level proxy: {self.proxy_url}")
            else:
                logger.debug("[get_response_headers] Using system-level proxy (trust_env) if configured.")
            
            # Prepare headers
            headers = self._get_auth_headers(use_auth)
            if custom_headers:
                headers.update(custom_headers)
            
            async with session.head(url, headers=headers, proxy=self.proxy_url) as response:
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
            # Debug log for proxy mode at request time
            if self.proxy_url:
                logger.debug(f"[make_request] Using app-level proxy: {self.proxy_url}")
            else:
                logger.debug("[make_request] Using system-level proxy (trust_env) if configured.")
            
            # Prepare headers
            headers = self._get_auth_headers(use_auth)
            if custom_headers:
                headers.update(custom_headers)
            
            # Add proxy to kwargs if not already present
            if 'proxy' not in kwargs:
                kwargs['proxy'] = self.proxy_url
            
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
                elif response.status == 429:
                    retry_after = self._extract_retry_after(response.headers)
                    error_msg = "Request rate limited"
                    logger.warning(
                        "Rate limit encountered for %s %s; retry_after=%s",
                        method,
                        url,
                        retry_after,
                    )
                    return False, RateLimitError(
                        error_msg,
                        retry_after=retry_after,
                    )
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
            self._proxy_url = None
            logger.debug("Closed HTTP session")
    
    async def refresh_session(self):
        """Force refresh the HTTP session (useful when proxy settings change)"""
        await self._create_session()
        logger.info("HTTP session refreshed due to settings change")

    @staticmethod
    def _extract_retry_after(headers) -> Optional[float]:
        """Parse the Retry-After header into seconds."""
        if not headers:
            return None

        header_value = headers.get("Retry-After")
        if not header_value:
            return None

        header_value = header_value.strip()
        if not header_value:
            return None

        if header_value.isdigit():
            try:
                seconds = float(header_value)
            except ValueError:
                return None
            return max(0.0, seconds)

        try:
            retry_datetime = parsedate_to_datetime(header_value)
        except (TypeError, ValueError):
            return None

        if retry_datetime.tzinfo is None:
            return None

        delta = retry_datetime - datetime.now(tz=retry_datetime.tzinfo)
        return max(0.0, delta.total_seconds())


# Global instance accessor
async def get_downloader() -> Downloader:
    """Get the global downloader instance"""
    return await Downloader.get_instance()
