"""Tests for download cancel and remove functionality."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from py.services.download_coordinator import DownloadCoordinator
from py.services.download_manager import DownloadManager


@dataclass
class StubWebSocketManager:
    """Stub WebSocket manager for testing."""
    progress: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    broadcasts: List[tuple[str, Dict[str, Any]]] = field(default_factory=list)

    def generate_download_id(self) -> str:
        return "generated"

    def get_download_progress(self, download_id: str) -> Dict[str, Any] | None:
        return self.progress.get(download_id)

    async def broadcast_download_progress(self, download_id: str, payload: Dict[str, Any]) -> None:
        self.broadcasts.append((download_id, payload))


@pytest.fixture
def reset_download_manager():
    """Ensure each test operates on a fresh singleton."""
    DownloadManager._instance = None
    yield
    DownloadManager._instance = None


@pytest.fixture
def mock_download_manager():
    """Create a mock download manager with realistic behavior."""
    manager = MagicMock(spec=DownloadManager)
    manager._active_downloads = {}
    manager._download_tasks = {}
    manager._pause_events = {}
    
    async def cancel_download(download_id: str) -> Dict[str, Any]:
        if download_id not in manager._download_tasks:
            return {'success': False, 'error': 'Download task not found'}
        
        # Simulate cancellation - remove from tracking immediately
        task = manager._download_tasks.get(download_id)
        if task:
            task.cancel()
        
        # Remove cancelled download from active downloads immediately (as per new behavior)
        manager._active_downloads.pop(download_id, None)
        manager._download_tasks.pop(download_id, None)
        manager._pause_events.pop(download_id, None)
        
        return {'success': True, 'message': 'Download cancelled successfully'}
    
    async def remove_queued_download(download_id: str) -> Dict[str, Any]:
        if download_id not in manager._active_downloads:
            return {'success': False, 'error': 'Download not found'}
        
        download_info = manager._active_downloads[download_id]
        status = download_info.get('status', 'unknown')
        
        if status == 'downloading':
            return {'success': False, 'error': 'Cannot remove active download. Use cancel instead.'}
        
        # Remove from tracking
        task = manager._download_tasks.get(download_id)
        if task:
            task.cancel()
        
        manager._active_downloads.pop(download_id, None)
        manager._download_tasks.pop(download_id, None)
        manager._pause_events.pop(download_id, None)
        
        return {'success': True, 'message': 'Queued download removed successfully'}
    
    async def get_active_downloads() -> Dict[str, Any]:
        # Filter out cancelled/completed downloads - only return active, waiting, or queued
        active_statuses = {'downloading', 'waiting', 'queued'}
        return {
            'downloads': [
                {
                    'download_id': task_id,
                    'model_id': info.get('model_id'),
                    'model_version_id': info.get('model_version_id'),
                    'model_name': info.get('model_name', ''),
                    'version_name': info.get('version_name', ''),
                    'progress': info.get('progress', 0),
                    'status': info.get('status', 'unknown'),
                    'error': info.get('error', None),
                    'bytes_downloaded': info.get('bytes_downloaded', 0),
                    'total_bytes': info.get('total_bytes'),
                    'bytes_per_second': info.get('bytes_per_second', 0.0),
                }
                for task_id, info in manager._active_downloads.items()
                if info.get('status', 'unknown') in active_statuses
            ]
        }
    
    manager.cancel_download = AsyncMock(side_effect=cancel_download)
    manager.remove_queued_download = AsyncMock(side_effect=remove_queued_download)
    manager.get_active_downloads = AsyncMock(side_effect=get_active_downloads)
    
    return manager


@pytest.fixture
def coordinator(mock_download_manager):
    """Create a download coordinator with mocked dependencies."""
    ws_manager = StubWebSocketManager()
    
    async def factory():
        return mock_download_manager
    
    return DownloadCoordinator(ws_manager=ws_manager, download_manager_factory=factory)


# ==================== Cancel Download Tests ====================

async def test_cancel_active_download_success(coordinator, mock_download_manager):
    """Test successfully canceling an active download."""
    download_id = "dl-123"
    
    # Setup: Add an active download
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    
    result = await coordinator.cancel_download(download_id)
    
    assert result['success'] is True
    assert mock_download_manager.cancel_download.called
    assert len(coordinator._ws_manager.broadcasts) == 1
    
    broadcast = coordinator._ws_manager.broadcasts[0]
    assert broadcast[0] == download_id
    assert broadcast[1]['status'] == 'cancelled'
    assert broadcast[1]['download_id'] == download_id


async def test_cancel_download_not_found(coordinator, mock_download_manager):
    """Test canceling a download that doesn't exist."""
    download_id = "dl-nonexistent"
    
    result = await coordinator.cancel_download(download_id)
    
    assert result['success'] is False
    assert 'not found' in result['error'].lower()
    # Note: Coordinator always broadcasts cancellation, even on failure
    # This is by design to notify clients of the cancellation attempt
    assert len(coordinator._ws_manager.broadcasts) == 1


async def test_cancel_download_with_queued_items(coordinator, mock_download_manager):
    """Test canceling when there are queued downloads - next should auto-start."""
    active_id = "dl-active"
    queued_id = "dl-queued"
    
    # Setup: Active download and queued download
    mock_task_active = MagicMock()
    mock_task_queued = MagicMock()
    
    mock_download_manager._download_tasks[active_id] = mock_task_active
    mock_download_manager._download_tasks[queued_id] = mock_task_queued
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[queued_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'waiting',  # Next in queue
        'progress': 0,
    }
    
    result = await coordinator.cancel_download(active_id)
    
    assert result['success'] is True
    # Should broadcast cancellation
    assert len(coordinator._ws_manager.broadcasts) == 1
    # Note: Backend semaphore will automatically start next download
    # Frontend should refresh queue to see the transition


async def test_cancel_download_broadcasts_cancellation(coordinator, mock_download_manager):
    """Test that cancellation broadcasts the correct message."""
    download_id = "dl-123"
    
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 75,
    }
    
    await coordinator.cancel_download(download_id)
    
    assert len(coordinator._ws_manager.broadcasts) == 1
    broadcast = coordinator._ws_manager.broadcasts[0]
    
    assert broadcast[1]['status'] == 'cancelled'
    assert broadcast[1]['progress'] == 0
    assert broadcast[1]['message'] == 'Download cancelled by user'


# ==================== Remove Queued Download Tests ====================

async def test_remove_queued_download_success(coordinator, mock_download_manager):
    """Test successfully removing a queued download."""
    download_id = "dl-queued"
    
    # Setup: Add a queued download
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'queued',
        'progress': 0,
    }
    
    result = await coordinator.remove_queued_download(download_id)
    
    assert result['success'] is True
    assert download_id not in mock_download_manager._active_downloads
    assert download_id not in mock_download_manager._download_tasks
    assert len(coordinator._ws_manager.broadcasts) == 1
    
    broadcast = coordinator._ws_manager.broadcasts[0]
    assert broadcast[0] == download_id
    assert broadcast[1]['status'] == 'removed'


async def test_remove_waiting_download_success(coordinator, mock_download_manager):
    """Test successfully removing a waiting download."""
    download_id = "dl-waiting"
    
    # Setup: Add a waiting download (next in queue)
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'waiting',
        'progress': 0,
    }
    
    result = await coordinator.remove_queued_download(download_id)
    
    assert result['success'] is True
    assert download_id not in mock_download_manager._active_downloads


async def test_remove_active_download_fails(coordinator, mock_download_manager):
    """Test that removing an active download fails."""
    download_id = "dl-active"
    
    # Setup: Add an active download
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    
    result = await coordinator.remove_queued_download(download_id)
    
    assert result['success'] is False
    assert 'cannot remove active' in result['error'].lower()
    # Should still exist
    assert download_id in mock_download_manager._active_downloads
    # Should not broadcast on failure
    assert len(coordinator._ws_manager.broadcasts) == 0


async def test_remove_nonexistent_download(coordinator, mock_download_manager):
    """Test removing a download that doesn't exist."""
    download_id = "dl-nonexistent"
    
    result = await coordinator.remove_queued_download(download_id)
    
    assert result['success'] is False
    assert 'not found' in result['error'].lower()
    assert len(coordinator._ws_manager.broadcasts) == 0


async def test_remove_last_queued_item_updates_queue_count(coordinator, mock_download_manager):
    """Test that removing the last queued item correctly updates queue count."""
    active_id = "dl-active"
    queued_id = "dl-queued"
    
    # Setup: Active download and one queued download
    mock_download_manager._download_tasks[active_id] = MagicMock()
    mock_download_manager._download_tasks[queued_id] = MagicMock()
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[queued_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'queued',
        'progress': 0,
    }
    
    # Get initial count
    initial_downloads = await mock_download_manager.get_active_downloads()
    assert len(initial_downloads['downloads']) == 2
    
    # Remove queued item
    result = await coordinator.remove_queued_download(queued_id)
    assert result['success'] is True
    
    # Get updated count
    updated_downloads = await mock_download_manager.get_active_downloads()
    assert len(updated_downloads['downloads']) == 1
    assert updated_downloads['downloads'][0]['download_id'] == active_id


async def test_remove_middle_queued_item_updates_order(coordinator, mock_download_manager):
    """Test that removing a middle queued item correctly updates queue order."""
    active_id = "dl-active"
    queued1_id = "dl-queued-1"
    queued2_id = "dl-queued-2"
    queued3_id = "dl-queued-3"
    
    # Setup: Active download and three queued downloads
    for dl_id in [active_id, queued1_id, queued2_id, queued3_id]:
        mock_download_manager._download_tasks[dl_id] = MagicMock()
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[queued1_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'waiting',
        'progress': 0,
    }
    mock_download_manager._active_downloads[queued2_id] = {
        'model_id': 3,
        'model_version_id': 3,
        'status': 'queued',
        'progress': 0,
    }
    mock_download_manager._active_downloads[queued3_id] = {
        'model_id': 4,
        'model_version_id': 4,
        'status': 'queued',
        'progress': 0,
    }
    
    # Get initial downloads
    initial_downloads = await mock_download_manager.get_active_downloads()
    assert len(initial_downloads['downloads']) == 4
    
    # Remove middle queued item
    result = await coordinator.remove_queued_download(queued2_id)
    assert result['success'] is True
    
    # Get updated downloads
    updated_downloads = await mock_download_manager.get_active_downloads()
    assert len(updated_downloads['downloads']) == 3
    
    # Verify remaining downloads
    remaining_ids = {d['download_id'] for d in updated_downloads['downloads']}
    assert active_id in remaining_ids
    assert queued1_id in remaining_ids
    assert queued3_id in remaining_ids
    assert queued2_id not in remaining_ids


async def test_remove_broadcasts_removal_event(coordinator, mock_download_manager):
    """Test that removal broadcasts the correct event."""
    download_id = "dl-queued"
    
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'queued',
        'progress': 0,
    }
    
    await coordinator.remove_queued_download(download_id)
    
    assert len(coordinator._ws_manager.broadcasts) == 1
    broadcast = coordinator._ws_manager.broadcasts[0]
    
    assert broadcast[1]['status'] == 'removed'
    assert broadcast[1]['message'] == 'Download removed from queue'


async def test_remove_does_not_broadcast_on_failure(coordinator, mock_download_manager):
    """Test that removal failures don't broadcast."""
    download_id = "dl-nonexistent"
    
    result = await coordinator.remove_queued_download(download_id)
    
    assert result['success'] is False
    assert len(coordinator._ws_manager.broadcasts) == 0


# ==================== Integration Scenarios ====================

async def test_cancel_then_remove_scenario(coordinator, mock_download_manager):
    """Test scenario: Cancel active download, then remove a queued one."""
    active_id = "dl-active"
    queued1_id = "dl-queued-1"
    queued2_id = "dl-queued-2"
    
    # Setup: One active, two queued
    for dl_id in [active_id, queued1_id, queued2_id]:
        mock_download_manager._download_tasks[dl_id] = MagicMock()
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[queued1_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'waiting',
        'progress': 0,
    }
    mock_download_manager._active_downloads[queued2_id] = {
        'model_id': 3,
        'model_version_id': 3,
        'status': 'queued',
        'progress': 0,
    }
    
    # Cancel active
    cancel_result = await coordinator.cancel_download(active_id)
    assert cancel_result['success'] is True
    
    # Remove one queued
    remove_result = await coordinator.remove_queued_download(queued1_id)
    assert remove_result['success'] is True
    
    # Verify final state
    final_downloads = await mock_download_manager.get_active_downloads()
    assert len(final_downloads['downloads']) == 1
    assert final_downloads['downloads'][0]['download_id'] == queued2_id


async def test_remove_all_queued_items_leaves_only_active(coordinator, mock_download_manager):
    """Test removing all queued items leaves only the active download."""
    active_id = "dl-active"
    queued1_id = "dl-queued-1"
    queued2_id = "dl-queued-2"
    
    # Setup
    for dl_id in [active_id, queued1_id, queued2_id]:
        mock_download_manager._download_tasks[dl_id] = MagicMock()
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[queued1_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'waiting',
        'progress': 0,
    }
    mock_download_manager._active_downloads[queued2_id] = {
        'model_id': 3,
        'model_version_id': 3,
        'status': 'queued',
        'progress': 0,
    }
    
    # Remove all queued items
    result1 = await coordinator.remove_queued_download(queued1_id)
    result2 = await coordinator.remove_queued_download(queued2_id)
    
    assert result1['success'] is True
    assert result2['success'] is True
    
    # Verify only active remains
    final_downloads = await mock_download_manager.get_active_downloads()
    assert len(final_downloads['downloads']) == 1
    assert final_downloads['downloads'][0]['download_id'] == active_id
    assert final_downloads['downloads'][0]['status'] == 'downloading'


# ==================== Error Handling Tests ====================

async def test_cancel_handles_backend_error(coordinator, mock_download_manager):
    """Test cancel handles backend errors gracefully."""
    download_id = "dl-123"
    
    # Make cancel_download raise an exception
    mock_download_manager.cancel_download = AsyncMock(side_effect=Exception("Backend error"))
    
    with pytest.raises(Exception):
        await coordinator.cancel_download(download_id)


async def test_remove_handles_backend_error(coordinator, mock_download_manager):
    """Test remove handles backend errors gracefully."""
    download_id = "dl-queued"
    
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'queued',
        'progress': 0,
    }
    
    # Make remove_queued_download raise an exception
    mock_download_manager.remove_queued_download = AsyncMock(side_effect=Exception("Backend error"))
    
    with pytest.raises(Exception):
        await coordinator.remove_queued_download(download_id)


async def test_get_active_downloads_returns_correct_structure(coordinator, mock_download_manager):
    """Test that get_active_downloads returns the correct structure."""
    download_id = "dl-123"
    
    mock_download_manager._download_tasks[download_id] = MagicMock()
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 2,
        'model_name': 'Test Model',
        'version_name': 'v1.0',
        'status': 'downloading',
        'progress': 50,
        'bytes_downloaded': 1024,
        'total_bytes': 2048,
        'bytes_per_second': 256.0,
    }
    
    result = await mock_download_manager.get_active_downloads()
    
    assert 'downloads' in result
    assert len(result['downloads']) == 1
    
    download = result['downloads'][0]
    assert download['download_id'] == download_id
    assert download['model_id'] == 1
    assert download['model_version_id'] == 2
    assert download['model_name'] == 'Test Model'
    assert download['version_name'] == 'v1.0'
    assert download['status'] == 'downloading'
    assert download['progress'] == 50
    assert download['bytes_downloaded'] == 1024
    assert download['total_bytes'] == 2048
    assert download['bytes_per_second'] == 256.0


# ==================== Tests for Cancellation Issue Fix ====================

async def test_cancelled_download_not_in_active_downloads(coordinator, mock_download_manager):
    """Test that cancelled downloads are immediately removed from active_downloads."""
    download_id = "dl-123"
    
    # Setup: Add an active download
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    
    # Verify it's in active downloads before cancellation
    downloads_before = await mock_download_manager.get_active_downloads()
    assert len(downloads_before['downloads']) == 1
    assert downloads_before['downloads'][0]['download_id'] == download_id
    
    # Cancel the download
    result = await coordinator.cancel_download(download_id)
    assert result['success'] is True
    
    # Verify it's NOT in active downloads after cancellation
    downloads_after = await mock_download_manager.get_active_downloads()
    assert len(downloads_after['downloads']) == 0
    assert download_id not in mock_download_manager._active_downloads


async def test_cancelled_download_filtered_from_get_active_downloads(coordinator, mock_download_manager):
    """Test that get_active_downloads filters out cancelled downloads."""
    active_id = "dl-active"
    cancelled_id = "dl-cancelled"
    
    # Setup: One active download and one cancelled download
    mock_download_manager._download_tasks[active_id] = MagicMock()
    mock_download_manager._download_tasks[cancelled_id] = MagicMock()
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[cancelled_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'cancelled',  # Cancelled status
        'progress': 0,
    }
    
    # get_active_downloads should filter out cancelled downloads
    result = await mock_download_manager.get_active_downloads()
    assert len(result['downloads']) == 1
    assert result['downloads'][0]['download_id'] == active_id
    assert cancelled_id not in [d['download_id'] for d in result['downloads']]


async def test_cancelled_download_with_queued_items_removed_correctly(coordinator, mock_download_manager):
    """Test that cancelling an active download removes it but keeps queued items."""
    active_id = "dl-active"
    queued_id = "dl-queued"
    
    # Setup: Active download and queued download
    mock_task_active = MagicMock()
    mock_task_queued = MagicMock()
    
    mock_download_manager._download_tasks[active_id] = mock_task_active
    mock_download_manager._download_tasks[queued_id] = mock_task_queued
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[queued_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'waiting',
        'progress': 0,
    }
    
    # Cancel active download
    result = await coordinator.cancel_download(active_id)
    assert result['success'] is True
    
    # Verify active download is removed
    assert active_id not in mock_download_manager._active_downloads
    
    # Verify queued download is still there
    downloads_after = await mock_download_manager.get_active_downloads()
    assert len(downloads_after['downloads']) == 1
    assert downloads_after['downloads'][0]['download_id'] == queued_id


async def test_get_active_downloads_filters_multiple_statuses(coordinator, mock_download_manager):
    """Test that get_active_downloads filters out various non-active statuses."""
    downloading_id = "dl-downloading"
    waiting_id = "dl-waiting"
    queued_id = "dl-queued"
    cancelled_id = "dl-cancelled"
    completed_id = "dl-completed"
    failed_id = "dl-failed"
    
    # Setup downloads with various statuses
    for dl_id in [downloading_id, waiting_id, queued_id, cancelled_id, completed_id, failed_id]:
        mock_download_manager._download_tasks[dl_id] = MagicMock()
    
    mock_download_manager._active_downloads[downloading_id] = {'status': 'downloading', 'model_id': 1, 'model_version_id': 1}
    mock_download_manager._active_downloads[waiting_id] = {'status': 'waiting', 'model_id': 2, 'model_version_id': 2}
    mock_download_manager._active_downloads[queued_id] = {'status': 'queued', 'model_id': 3, 'model_version_id': 3}
    mock_download_manager._active_downloads[cancelled_id] = {'status': 'cancelled', 'model_id': 4, 'model_version_id': 4}
    mock_download_manager._active_downloads[completed_id] = {'status': 'completed', 'model_id': 5, 'model_version_id': 5}
    mock_download_manager._active_downloads[failed_id] = {'status': 'failed', 'model_id': 6, 'model_version_id': 6}
    
    result = await mock_download_manager.get_active_downloads()
    
    # Should only return downloading, waiting, and queued
    assert len(result['downloads']) == 3
    returned_ids = {d['download_id'] for d in result['downloads']}
    assert downloading_id in returned_ids
    assert waiting_id in returned_ids
    assert queued_id in returned_ids
    assert cancelled_id not in returned_ids
    assert completed_id not in returned_ids
    assert failed_id not in returned_ids


# ==================== Tests for Remove Functionality Issues ====================

async def test_removed_queued_download_not_in_active_downloads(coordinator, mock_download_manager):
    """Test that removed queued downloads are immediately removed from active_downloads."""
    queued_id = "dl-queued"
    
    # Setup: Add a queued download
    mock_task = MagicMock()
    mock_download_manager._download_tasks[queued_id] = mock_task
    mock_download_manager._active_downloads[queued_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'queued',
        'progress': 0,
    }
    
    # Verify it's in active downloads before removal
    downloads_before = await mock_download_manager.get_active_downloads()
    assert len(downloads_before['downloads']) == 1
    assert downloads_before['downloads'][0]['download_id'] == queued_id
    
    # Remove the queued download
    result = await coordinator.remove_queued_download(queued_id)
    assert result['success'] is True
    
    # Verify it's NOT in active downloads after removal
    downloads_after = await mock_download_manager.get_active_downloads()
    assert len(downloads_after['downloads']) == 0
    assert queued_id not in mock_download_manager._active_downloads
    assert queued_id not in mock_download_manager._download_tasks


async def test_removed_waiting_download_not_in_active_downloads(coordinator, mock_download_manager):
    """Test that removed waiting downloads are immediately removed from active_downloads."""
    waiting_id = "dl-waiting"
    
    # Setup: Add a waiting download
    mock_task = MagicMock()
    mock_download_manager._download_tasks[waiting_id] = mock_task
    mock_download_manager._active_downloads[waiting_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'waiting',
        'progress': 0,
    }
    
    # Remove the waiting download
    result = await coordinator.remove_queued_download(waiting_id)
    assert result['success'] is True
    
    # Verify it's NOT in active downloads after removal
    downloads_after = await mock_download_manager.get_active_downloads()
    assert len(downloads_after['downloads']) == 0
    assert waiting_id not in mock_download_manager._active_downloads


async def test_remove_queued_download_with_other_downloads_present(coordinator, mock_download_manager):
    """Test removing a queued download when other downloads are present."""
    active_id = "dl-active"
    queued1_id = "dl-queued-1"
    queued2_id = "dl-queued-2"
    
    # Setup: One active and two queued downloads
    for dl_id in [active_id, queued1_id, queued2_id]:
        mock_download_manager._download_tasks[dl_id] = MagicMock()
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[queued1_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'queued',
        'progress': 0,
    }
    mock_download_manager._active_downloads[queued2_id] = {
        'model_id': 3,
        'model_version_id': 3,
        'status': 'queued',
        'progress': 0,
    }
    
    # Remove one queued download
    result = await coordinator.remove_queued_download(queued1_id)
    assert result['success'] is True
    
    # Verify removed download is gone
    assert queued1_id not in mock_download_manager._active_downloads
    
    # Verify other downloads are still present
    downloads_after = await mock_download_manager.get_active_downloads()
    assert len(downloads_after['downloads']) == 2
    returned_ids = {d['download_id'] for d in downloads_after['downloads']}
    assert active_id in returned_ids
    assert queued2_id in returned_ids
    assert queued1_id not in returned_ids


async def test_remove_last_queued_download_leaves_only_active(coordinator, mock_download_manager):
    """Test that removing the last queued download leaves only the active download."""
    active_id = "dl-active"
    queued_id = "dl-queued"
    
    # Setup: One active and one queued download
    mock_download_manager._download_tasks[active_id] = MagicMock()
    mock_download_manager._download_tasks[queued_id] = MagicMock()
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[queued_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'queued',
        'progress': 0,
    }
    
    # Remove queued download
    result = await coordinator.remove_queued_download(queued_id)
    assert result['success'] is True
    
    # Verify only active download remains
    downloads_after = await mock_download_manager.get_active_downloads()
    assert len(downloads_after['downloads']) == 1
    assert downloads_after['downloads'][0]['download_id'] == active_id
    assert queued_id not in mock_download_manager._active_downloads


async def test_remove_all_queued_downloads_removes_all_from_tracking(coordinator, mock_download_manager):
    """Test that removing all queued downloads removes them all from tracking."""
    queued1_id = "dl-queued-1"
    queued2_id = "dl-queued-2"
    queued3_id = "dl-queued-3"
    
    # Setup: Three queued downloads
    for dl_id in [queued1_id, queued2_id, queued3_id]:
        mock_download_manager._download_tasks[dl_id] = MagicMock()
        mock_download_manager._active_downloads[dl_id] = {
            'model_id': 1,
            'model_version_id': 1,
            'status': 'queued',
            'progress': 0,
        }
    
    # Remove all queued downloads
    result1 = await coordinator.remove_queued_download(queued1_id)
    result2 = await coordinator.remove_queued_download(queued2_id)
    result3 = await coordinator.remove_queued_download(queued3_id)
    
    assert result1['success'] is True
    assert result2['success'] is True
    assert result3['success'] is True
    
    # Verify all are removed from tracking
    assert queued1_id not in mock_download_manager._active_downloads
    assert queued2_id not in mock_download_manager._active_downloads
    assert queued3_id not in mock_download_manager._active_downloads
    assert queued1_id not in mock_download_manager._download_tasks
    assert queued2_id not in mock_download_manager._download_tasks
    assert queued3_id not in mock_download_manager._download_tasks
    
    # Verify no downloads remain
    downloads_after = await mock_download_manager.get_active_downloads()
    assert len(downloads_after['downloads']) == 0


# ==================== Edge Case Tests ====================

async def test_cancel_then_remove_same_download_id(coordinator, mock_download_manager):
    """Test edge case: Try to cancel then remove the same download."""
    download_id = "dl-123"
    
    # Setup: Add an active download
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    
    # Cancel the download
    cancel_result = await coordinator.cancel_download(download_id)
    assert cancel_result['success'] is True
    
    # Try to remove it (should fail - not found)
    remove_result = await coordinator.remove_queued_download(download_id)
    assert remove_result['success'] is False
    assert 'not found' in remove_result['error'].lower()


async def test_remove_then_cancel_same_download_id(coordinator, mock_download_manager):
    """Test edge case: Try to remove then cancel the same download."""
    download_id = "dl-123"
    
    # Setup: Add a queued download
    mock_task = MagicMock()
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'queued',
        'progress': 0,
    }
    
    # Remove the download
    remove_result = await coordinator.remove_queued_download(download_id)
    assert remove_result['success'] is True
    
    # Try to cancel it (should fail - not found)
    cancel_result = await coordinator.cancel_download(download_id)
    assert cancel_result['success'] is False
    assert 'not found' in cancel_result['error'].lower()


async def test_concurrent_cancel_and_remove_operations(coordinator, mock_download_manager):
    """Test concurrent cancel and remove operations don't cause issues."""
    active_id = "dl-active"
    queued_id = "dl-queued"
    
    # Setup: One active and one queued download
    mock_download_manager._download_tasks[active_id] = MagicMock()
    mock_download_manager._download_tasks[queued_id] = MagicMock()
    
    mock_download_manager._active_downloads[active_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    mock_download_manager._active_downloads[queued_id] = {
        'model_id': 2,
        'model_version_id': 2,
        'status': 'queued',
        'progress': 0,
    }
    
    # Perform cancel and remove concurrently
    import asyncio
    cancel_task = asyncio.create_task(coordinator.cancel_download(active_id))
    remove_task = asyncio.create_task(coordinator.remove_queued_download(queued_id))
    
    cancel_result, remove_result = await asyncio.gather(cancel_task, remove_task)
    
    assert cancel_result['success'] is True
    assert remove_result['success'] is True
    
    # Verify both are removed
    downloads_after = await mock_download_manager.get_active_downloads()
    assert len(downloads_after['downloads']) == 0


async def test_get_active_downloads_empty_after_all_removed(coordinator, mock_download_manager):
    """Test that get_active_downloads returns empty list when all downloads are removed."""
    queued_id = "dl-queued"
    
    # Setup: One queued download
    mock_download_manager._download_tasks[queued_id] = MagicMock()
    mock_download_manager._active_downloads[queued_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'queued',
        'progress': 0,
    }
    
    # Remove it
    result = await coordinator.remove_queued_download(queued_id)
    assert result['success'] is True
    
    # Verify get_active_downloads returns empty list
    downloads_after = await mock_download_manager.get_active_downloads()
    assert len(downloads_after['downloads']) == 0
    assert downloads_after['downloads'] == []


async def test_cancel_download_removes_from_all_tracking_dicts(coordinator, mock_download_manager):
    """Test that cancel removes download from all tracking dictionaries."""
    download_id = "dl-123"
    
    # Setup: Add download to all tracking dicts
    mock_task = MagicMock()
    mock_pause_event = MagicMock()
    
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._pause_events[download_id] = mock_pause_event
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'downloading',
        'progress': 50,
    }
    
    # Cancel the download
    result = await coordinator.cancel_download(download_id)
    assert result['success'] is True
    
    # Verify removed from all tracking dicts
    assert download_id not in mock_download_manager._active_downloads
    assert download_id not in mock_download_manager._download_tasks
    assert download_id not in mock_download_manager._pause_events


async def test_remove_download_removes_from_all_tracking_dicts(coordinator, mock_download_manager):
    """Test that remove removes download from all tracking dictionaries."""
    download_id = "dl-queued"
    
    # Setup: Add download to all tracking dicts
    mock_task = MagicMock()
    mock_pause_event = MagicMock()
    
    mock_download_manager._download_tasks[download_id] = mock_task
    mock_download_manager._pause_events[download_id] = mock_pause_event
    mock_download_manager._active_downloads[download_id] = {
        'model_id': 1,
        'model_version_id': 1,
        'status': 'queued',
        'progress': 0,
    }
    
    # Remove the download
    result = await coordinator.remove_queued_download(download_id)
    assert result['success'] is True
    
    # Verify removed from all tracking dicts
    assert download_id not in mock_download_manager._active_downloads
    assert download_id not in mock_download_manager._download_tasks
    assert download_id not in mock_download_manager._pause_events

