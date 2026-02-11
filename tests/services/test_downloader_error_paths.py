"""Error path tests for downloader module.

Tests HTTP error handling and network error scenarios.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import aiohttp

from py.services.downloader import Downloader, DownloadStalledError, DownloadRestartRequested


class TestDownloadStreamControl:
    """Test DownloadStreamControl functionality."""
    
    def test_pause_clears_event(self):
        """Verify pause() clears the event."""
        from py.services.downloader import DownloadStreamControl
        
        control = DownloadStreamControl()
        assert control.is_set() is True  # Initially set
        
        control.pause()
        assert control.is_set() is False
        assert control.is_paused() is True
    
    def test_resume_sets_event(self):
        """Verify resume() sets the event."""
        from py.services.downloader import DownloadStreamControl
        
        control = DownloadStreamControl()
        control.pause()
        assert control.is_set() is False
        
        control.resume()
        assert control.is_set() is True
        assert control.is_paused() is False
    
    def test_reconnect_request_tracking(self):
        """Verify reconnect request tracking works correctly."""
        from py.services.downloader import DownloadStreamControl
        
        control = DownloadStreamControl()
        assert control.has_reconnect_request() is False
        
        control.request_reconnect()
        assert control.has_reconnect_request() is True
        
        # Consume the request
        consumed = control.consume_reconnect_request()
        assert consumed is True
        assert control.has_reconnect_request() is False
    
    def test_mark_progress_clears_reconnect(self):
        """Verify mark_progress clears reconnect requests."""
        from py.services.downloader import DownloadStreamControl
        
        control = DownloadStreamControl()
        control.request_reconnect()
        assert control.has_reconnect_request() is True
        
        control.mark_progress()
        assert control.has_reconnect_request() is False
        assert control.last_progress_timestamp is not None
    
    def test_time_since_last_progress(self):
        """Verify time_since_last_progress calculation."""
        from py.services.downloader import DownloadStreamControl
        import time
        
        control = DownloadStreamControl()
        
        # Initially None
        assert control.time_since_last_progress() is None
        
        # After marking progress
        now = time.time()
        control.mark_progress(timestamp=now)
        
        elapsed = control.time_since_last_progress(now=now + 5)
        assert elapsed == 5.0
    
    @pytest.mark.asyncio
    async def test_wait_for_resume(self):
        """Verify wait() blocks until resumed."""
        from py.services.downloader import DownloadStreamControl
        import asyncio
        
        control = DownloadStreamControl()
        control.pause()
        
        # Start a task that will wait
        wait_task = asyncio.create_task(control.wait())
        
        # Give it a moment to start waiting
        await asyncio.sleep(0.01)
        assert not wait_task.done()
        
        # Resume should unblock
        control.resume()
        await asyncio.wait_for(wait_task, timeout=0.1)


class TestDownloaderConfiguration:
    """Test downloader configuration and initialization."""
    
    def test_downloader_singleton_pattern(self):
        """Verify Downloader follows singleton pattern."""
        # Reset first
        Downloader._instance = None
        
        # Both should return same instance
        async def get_instances():
            instance1 = await Downloader.get_instance()
            instance2 = await Downloader.get_instance()
            return instance1, instance2
        
        import asyncio
        instance1, instance2 = asyncio.run(get_instances())
        
        assert instance1 is instance2
        
        # Cleanup
        Downloader._instance = None
    
    def test_default_configuration_values(self):
        """Verify default configuration values are set correctly."""
        Downloader._instance = None
        
        downloader = Downloader()
        
        assert downloader.chunk_size == 4 * 1024 * 1024  # 4MB
        assert downloader.max_retries == 5
        assert downloader.base_delay == 2.0
        assert downloader.session_timeout == 300
        
        # Cleanup
        Downloader._instance = None
    
    def test_default_headers_include_user_agent(self):
        """Verify default headers include User-Agent."""
        Downloader._instance = None
        
        downloader = Downloader()
        
        assert 'User-Agent' in downloader.default_headers
        assert 'ComfyUI-LoRA-Manager' in downloader.default_headers['User-Agent']
        assert downloader.default_headers['Accept-Encoding'] == 'identity'
        
        # Cleanup
        Downloader._instance = None
    
    def test_stall_timeout_resolution(self):
        """Verify stall timeout is resolved correctly."""
        Downloader._instance = None
        
        downloader = Downloader()
        timeout = downloader._resolve_stall_timeout()
        
        # Should be at least 30 seconds
        assert timeout >= 30.0
        
        # Cleanup
        Downloader._instance = None


class TestDownloadProgress:
    """Test DownloadProgress dataclass."""
    
    def test_download_progress_creation(self):
        """Verify DownloadProgress can be created with correct values."""
        from py.services.downloader import DownloadProgress
        from datetime import datetime
        
        progress = DownloadProgress(
            percent_complete=50.0,
            bytes_downloaded=500,
            total_bytes=1000,
            bytes_per_second=100.5,
            timestamp=datetime.now().timestamp(),
        )
        
        assert progress.percent_complete == 50.0
        assert progress.bytes_downloaded == 500
        assert progress.total_bytes == 1000
        assert progress.bytes_per_second == 100.5
        assert progress.timestamp is not None


class TestDownloaderExceptions:
    """Test custom exception classes."""
    
    def test_download_stalled_error(self):
        """Verify DownloadStalledError can be raised and caught."""
        with pytest.raises(DownloadStalledError) as exc_info:
            raise DownloadStalledError("Download stalled for 120 seconds")
        
        assert "stalled" in str(exc_info.value).lower()
    
    def test_download_restart_requested_error(self):
        """Verify DownloadRestartRequested can be raised and caught."""
        with pytest.raises(DownloadRestartRequested) as exc_info:
            raise DownloadRestartRequested("Reconnect requested after resume")
        
        assert "reconnect" in str(exc_info.value).lower() or "restart" in str(exc_info.value).lower()


class TestDownloaderAuthHeaders:
    """Test authentication header generation."""
    
    def test_get_auth_headers_without_auth(self):
        """Verify auth headers without authentication."""
        Downloader._instance = None
        downloader = Downloader()
        
        headers = downloader._get_auth_headers(use_auth=False)
        
        assert 'User-Agent' in headers
        assert 'Authorization' not in headers
        
        Downloader._instance = None
    
    def test_get_auth_headers_with_auth_no_api_key(self, monkeypatch):
        """Verify auth headers with auth but no API key configured."""
        Downloader._instance = None
        downloader = Downloader()
        
        # Mock settings manager to return no API key
        mock_settings = MagicMock()
        mock_settings.get.return_value = None
        
        with patch('py.services.downloader.get_settings_manager', return_value=mock_settings):
            headers = downloader._get_auth_headers(use_auth=True)
            
            # Should still have User-Agent but no Authorization
            assert 'User-Agent' in headers
            assert 'Authorization' not in headers
        
        Downloader._instance = None
    
    def test_get_auth_headers_with_auth_and_api_key(self, monkeypatch):
        """Verify auth headers with auth and API key configured."""
        Downloader._instance = None
        downloader = Downloader()
        
        # Mock settings manager to return API key
        mock_settings = MagicMock()
        mock_settings.get.return_value = "test-api-key-12345"
        
        with patch('py.services.downloader.get_settings_manager', return_value=mock_settings):
            headers = downloader._get_auth_headers(use_auth=True)
            
            # Should have both User-Agent and Authorization
            assert 'User-Agent' in headers
            assert 'Authorization' in headers
            assert 'test-api-key-12345' in headers['Authorization']
            assert headers['Content-Type'] == 'application/json'
        
        Downloader._instance = None


class TestDownloaderSessionManagement:
    """Test session management functionality."""
    
    @pytest.mark.asyncio
    async def test_should_refresh_session_when_none(self):
        """Verify session refresh is needed when session is None."""
        Downloader._instance = None
        downloader = Downloader()
        
        # Initially should need refresh
        assert downloader._should_refresh_session() is True
        
        Downloader._instance = None
    
    def test_should_not_refresh_new_session(self):
        """Verify new session doesn't need refresh."""
        Downloader._instance = None
        downloader = Downloader()
        
        # Simulate a fresh session
        downloader._session_created_at = MagicMock()
        downloader._session = MagicMock()
        
        # Mock datetime to return current time
        from datetime import datetime, timedelta
        current_time = datetime.now()
        downloader._session_created_at = current_time
        
        # Should not need refresh for new session
        assert downloader._should_refresh_session() is False
        
        Downloader._instance = None
    
    def test_should_refresh_old_session(self):
        """Verify old session needs refresh."""
        Downloader._instance = None
        downloader = Downloader()
        
        # Simulate an old session (older than timeout)
        from datetime import datetime, timedelta
        old_time = datetime.now() - timedelta(seconds=downloader.session_timeout + 1)
        downloader._session_created_at = old_time
        downloader._session = MagicMock()
        
        # Should need refresh for old session
        assert downloader._should_refresh_session() is True
        
        Downloader._instance = None
