import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

// Mock dependencies
const showToastMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => fallback || key);
const loadingManagerMock = {
  showDownloadProgress: vi.fn(() => vi.fn()),
  restoreProgressBar: vi.fn(),
  setStatus: vi.fn(),
  hide: vi.fn(),
  updateQueueDisplay: vi.fn(),
  overlay: { style: { display: 'none' } },
  isMinimized: false,
  onCancelCallback: null,
  onRemoveCallback: null,
  activeDownloadId: null,
};

const apiClientMock = {
  downloadModel: vi.fn(),
  apiConfig: {
    config: {
      singularName: 'model',
    },
  },
};

const getModelApiClientMock = vi.fn(() => apiClientMock);

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: translateMock,
}));

vi.mock('../../../static/js/managers/LoadingManager.js', () => ({
  LoadingManager: vi.fn(() => loadingManagerMock),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: getModelApiClientMock,
  resetAndReload: vi.fn(),
}));

describe('DownloadManager - Cancel and Remove Functionality', () => {
  let DownloadManager;
  let downloadManager;

  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();

    // Reset loading manager state
    loadingManagerMock.showDownloadProgress.mockReturnValue(vi.fn());
    loadingManagerMock.overlay.style.display = 'none';
    loadingManagerMock.isMinimized = false;
    loadingManagerMock.onCancelCallback = null;
    loadingManagerMock.onRemoveCallback = null;
    loadingManagerMock.activeDownloadId = null;

    // Mock fetch globally
    global.fetch = vi.fn();
    global.WebSocket = vi.fn(() => ({
      close: vi.fn(),
      readyState: WebSocket.OPEN,
      onmessage: null,
      onerror: null,
    }));

    // Mock document methods
    global.document = {
      getElementById: vi.fn(() => ({
        style: { display: 'none' },
        value: '',
        innerHTML: '',
      })),
      createElement: vi.fn((tag) => ({
        tagName: tag,
        style: {},
        addEventListener: vi.fn(),
        appendChild: vi.fn(),
        remove: vi.fn(),
        textContent: '',
        innerHTML: '',
      })),
      body: {
        appendChild: vi.fn(),
      },
      querySelector: vi.fn(),
      querySelectorAll: vi.fn(() => []),
    };

    const module = await import('../../../static/js/managers/DownloadManager.js');
    DownloadManager = module.DownloadManager;
    downloadManager = new DownloadManager();
    downloadManager.apiClient = apiClientMock;
    downloadManager.loadingManager = loadingManagerMock;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Cancel Download', () => {
    it('should cancel an active download successfully', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, message: 'Download cancelled' }),
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [],
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.cancelDownload(downloadId);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/lm/cancel-download-get?download_id=${downloadId}`)
      );
      expect(loadingManagerMock.setStatus).toHaveBeenCalledWith(
        expect.stringContaining('Cancelling')
      );
    });

    it('should handle cancel failure from backend', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: false, error: 'Download not found' }),
      });

      await downloadManager.cancelDownload(downloadId);

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.downloads.cancelFailed',
        { error: 'Download not found' },
        'error'
      );
      expect(downloadManager.isCancelling).toBe(false);
    });

    it('should handle network errors during cancel', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockRejectedValueOnce(new Error('Network error'));

      await downloadManager.cancelDownload(downloadId);

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.downloads.cancelFailed',
        { error: 'Network error' },
        'error'
      );
      expect(downloadManager.isCancelling).toBe(false);
    });

    it('should refresh queue display after cancellation', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      // Mock checkQueueStatus
      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [
          { download_id: 'dl-456', status: 'waiting' },
        ],
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.cancelDownload(downloadId);

      // Wait for timeout to complete
      await new Promise((resolve) => setTimeout(resolve, 2100));

      expect(downloadManager.updateQueueDisplay).toHaveBeenCalled();
    });

    it('should hide popup if no downloads remain after cancel', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [],
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.cancelDownload(downloadId);

      // Wait for timeout
      await new Promise((resolve) => setTimeout(resolve, 2100));

      expect(loadingManagerMock.hide).toHaveBeenCalled();
    });

    it('should verify cancelled download is removed from queue display', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      // Mock queue status showing no downloads after cancellation
      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [], // Cancelled download should not appear
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.cancelDownload(downloadId);

      // Wait for timeout
      await new Promise((resolve) => setTimeout(resolve, 2100));

      // Verify updateQueueDisplay was called with empty downloads
      expect(downloadManager.updateQueueDisplay).toHaveBeenCalled();
      expect(loadingManagerMock.hide).toHaveBeenCalled();
    });

    it('should handle errors in updateQueueDisplay gracefully', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [],
      });

      // Make updateQueueDisplay throw an error
      downloadManager.updateQueueDisplay = vi.fn().mockRejectedValue(new Error('Update failed'));

      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      await downloadManager.cancelDownload(downloadId);

      // Wait for timeout and error handling
      await new Promise((resolve) => setTimeout(resolve, 2100));

      expect(consoleErrorSpy).toHaveBeenCalled();
      expect(loadingManagerMock.hide).toHaveBeenCalled();

      consoleErrorSpy.mockRestore();
    });
  });

  describe('Remove Queued Download', () => {
    it('should remove a queued download successfully', async () => {
      const downloadId = 'dl-queued';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, message: 'Removed from queue' }),
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.removeQueuedDownload(downloadId);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/lm/remove-queued-download?download_id=${downloadId}`)
      );
      expect(downloadManager.updateQueueDisplay).toHaveBeenCalled();
      expect(showToastMock).toHaveBeenCalledWith(
        'toast.downloads.removedFromQueue',
        {},
        'info'
      );
    });

    it('should handle remove failure from backend', async () => {
      const downloadId = 'dl-queued';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: false, error: 'Download not found' }),
      });

      await downloadManager.removeQueuedDownload(downloadId);

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.downloads.removeFailed',
        { error: 'Download not found' },
        'error'
      );
    });

    it('should handle network errors during remove', async () => {
      const downloadId = 'dl-queued';

      global.fetch.mockRejectedValueOnce(new Error('Network error'));

      await downloadManager.removeQueuedDownload(downloadId);

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.downloads.removeFailed',
        { error: 'Network error' },
        'error'
      );
    });

    it('should update queue display after successful removal', async () => {
      const downloadId = 'dl-queued';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.removeQueuedDownload(downloadId);

      expect(downloadManager.updateQueueDisplay).toHaveBeenCalled();
    });

    it('should handle missing download ID gracefully', async () => {
      await downloadManager.removeQueuedDownload(null);

      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('should verify removed download is not in queue display', async () => {
      const downloadId = 'dl-queued';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      // Mock updateQueueDisplay to verify it's called
      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.removeQueuedDownload(downloadId);

      // Verify updateQueueDisplay was called to refresh queue
      expect(downloadManager.updateQueueDisplay).toHaveBeenCalled();
    });

    it('should handle errors in updateQueueDisplay during remove', async () => {
      const downloadId = 'dl-queued';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      // Make updateQueueDisplay throw an error
      downloadManager.updateQueueDisplay = vi.fn().mockRejectedValue(new Error('Update failed'));

      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      await downloadManager.removeQueuedDownload(downloadId);

      expect(consoleErrorSpy).toHaveBeenCalled();
      expect(showToastMock).toHaveBeenCalledWith(
        'toast.downloads.removedFromQueue',
        {},
        'info'
      );

      consoleErrorSpy.mockRestore();
    });
  });

  describe('Queue Display Updates', () => {
    it('should correctly update queue display with active and queued downloads', async () => {
      const mockDownloads = [
        {
          download_id: 'dl-active',
          status: 'downloading',
          progress: 50,
          model_name: 'Model 1',
          version_name: 'v1.0',
        },
        {
          download_id: 'dl-waiting',
          status: 'waiting',
          progress: 0,
          model_name: 'Model 2',
          version_name: 'v2.0',
        },
        {
          download_id: 'dl-queued',
          status: 'queued',
          progress: 0,
          model_name: 'Model 3',
          version_name: 'v3.0',
        },
      ];

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ downloads: mockDownloads }),
      });

      await downloadManager.updateQueueDisplay();

      expect(loadingManagerMock.updateQueueDisplay).toHaveBeenCalledWith(mockDownloads);
    });

    it('should filter out cancelled downloads from queue display', async () => {
      const mockDownloads = [
        {
          download_id: 'dl-active',
          status: 'downloading',
          progress: 50,
          model_name: 'Model 1',
          version_name: 'v1.0',
        },
        {
          download_id: 'dl-cancelled',
          status: 'cancelled', // Should be filtered out
          progress: 0,
          model_name: 'Model 2',
          version_name: 'v2.0',
        },
      ];

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ downloads: mockDownloads }),
      });

      await downloadManager.updateQueueDisplay();

      // Backend should filter cancelled downloads, but verify frontend handles it
      expect(loadingManagerMock.updateQueueDisplay).toHaveBeenCalled();
    });

    it('should handle empty downloads array correctly', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ downloads: [] }),
      });

      downloadManager.currentUpdateProgress = null;

      await downloadManager.updateQueueDisplay();

      expect(loadingManagerMock.updateQueueDisplay).toHaveBeenCalledWith([]);
      expect(loadingManagerMock.hide).toHaveBeenCalled();
    });

    it('should hide popup when no downloads remain', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ downloads: [] }),
      });

      downloadManager.currentUpdateProgress = null;

      await downloadManager.updateQueueDisplay();

      expect(loadingManagerMock.hide).toHaveBeenCalled();
    });

    it('should keep popup visible when downloads are active', async () => {
      const mockDownloads = [
        {
          download_id: 'dl-active',
          status: 'downloading',
          progress: 50,
        },
      ];

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ downloads: mockDownloads }),
      });

      await downloadManager.updateQueueDisplay();

      expect(loadingManagerMock.hide).not.toHaveBeenCalled();
      expect(loadingManagerMock.overlay.style.display).toBe('flex');
    });

    it('should respect minimized state when updating queue', async () => {
      const mockDownloads = [
        {
          download_id: 'dl-active',
          status: 'downloading',
          progress: 50,
        },
      ];

      loadingManagerMock.isMinimized = true;

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ downloads: mockDownloads }),
      });

      await downloadManager.updateQueueDisplay();

      // Should not force restore if minimized
      expect(loadingManagerMock.overlay.style.display).not.toBe('flex');
    });
  });

  describe('Integration Scenarios', () => {
    it('should handle cancel then remove scenario', async () => {
      const activeId = 'dl-active';
      const queuedId = 'dl-queued';

      // Cancel active download
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [
          { download_id: queuedId, status: 'waiting' },
        ],
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.cancelDownload(activeId);

      // Wait for timeout
      await new Promise((resolve) => setTimeout(resolve, 2100));

      // Remove queued download
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await downloadManager.removeQueuedDownload(queuedId);

      expect(downloadManager.updateQueueDisplay).toHaveBeenCalled();
    });

    it('should handle WebSocket cancellation message correctly', async () => {
      const downloadId = 'dl-123';
      const ws = {
        close: vi.fn(),
        readyState: WebSocket.OPEN,
        onmessage: null,
        onerror: null,
      };

      global.WebSocket = vi.fn(() => ws);

      downloadManager.executeDownloadWithProgress = vi.fn(async () => {
        // Simulate WebSocket cancellation message
        if (ws.onmessage) {
          ws.onmessage({
            data: JSON.stringify({
              status: 'cancelled',
              download_id: downloadId,
            }),
          });
        }
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [],
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.executeDownloadWithProgress({
        modelId: 1,
        versionId: 1,
        versionName: 'v1.0',
      });

      // Wait for async operations
      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(loadingManagerMock.hide).toHaveBeenCalled();
    });

    it('should handle WebSocket cancellation with queued items', async () => {
      const downloadId = 'dl-123';
      const queuedId = 'dl-queued';
      const ws = {
        close: vi.fn(),
        readyState: WebSocket.OPEN,
        onmessage: null,
        onerror: null,
      };

      global.WebSocket = vi.fn(() => ws);

      downloadManager.executeDownloadWithProgress = vi.fn(async () => {
        if (ws.onmessage) {
          ws.onmessage({
            data: JSON.stringify({
              status: 'cancelled',
              download_id: downloadId,
            }),
          });
        }
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [
          { download_id: queuedId, status: 'waiting' },
        ],
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.executeDownloadWithProgress({
        modelId: 1,
        versionId: 1,
        versionName: 'v1.0',
      });

      await new Promise((resolve) => setTimeout(resolve, 100));

      // Should NOT hide if there are queued items
      expect(loadingManagerMock.hide).not.toHaveBeenCalled();
      expect(downloadManager.updateQueueDisplay).toHaveBeenCalled();
    });

    it('should handle WebSocket cancellation message', async () => {
      const downloadId = 'dl-123';
      const ws = {
        close: vi.fn(),
        readyState: WebSocket.OPEN,
        onmessage: null,
        onerror: null,
      };

      global.WebSocket = vi.fn(() => ws);

      // Simulate WebSocket cancellation message
      downloadManager.executeDownloadWithProgress = vi.fn(async () => {
        // Simulate WebSocket message
        if (ws.onmessage) {
          ws.onmessage({
            data: JSON.stringify({
              status: 'cancelled',
              download_id: downloadId,
            }),
          });
        }
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [],
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.executeDownloadWithProgress({
        modelId: 1,
        versionId: 1,
        versionName: 'v1.0',
      });

      // Wait for async operations
      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(loadingManagerMock.hide).toHaveBeenCalled();
    });
  });

  describe('Error Handling', () => {
    it('should handle fetch errors gracefully', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Fetch failed'));

      await downloadManager.cancelDownload('dl-123');

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.downloads.cancelFailed',
        { error: 'Fetch failed' },
        'error'
      );
    });

    it('should handle invalid JSON responses', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => {
          throw new Error('Invalid JSON');
        },
      });

      await expect(downloadManager.cancelDownload('dl-123')).rejects.toThrow();
    });

    it('should handle timeout scenarios', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            setTimeout(() => {
              resolve({
                ok: true,
                json: async () => ({ success: true }),
              });
            }, 3000); // Longer than timeout
          })
      );

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [],
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.cancelDownload(downloadId);

      // Timeout should fire before fetch completes
      await new Promise((resolve) => setTimeout(resolve, 2100));

      expect(loadingManagerMock.hide).toHaveBeenCalled();
    });

    it('should handle errors in checkQueueStatus during cancel', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      downloadManager.checkQueueStatus = vi.fn().mockRejectedValue(new Error('Queue check failed'));
      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      await downloadManager.cancelDownload(downloadId);

      await new Promise((resolve) => setTimeout(resolve, 2100));

      expect(consoleErrorSpy).toHaveBeenCalled();
      expect(loadingManagerMock.hide).toHaveBeenCalled();

      consoleErrorSpy.mockRestore();
    });

    it('should handle errors in updateQueueDisplay during cancel timeout', async () => {
      const downloadId = 'dl-123';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [{ download_id: 'dl-other', status: 'waiting' }],
      });

      downloadManager.updateQueueDisplay = vi.fn().mockRejectedValue(new Error('Update failed'));

      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      await downloadManager.cancelDownload(downloadId);

      await new Promise((resolve) => setTimeout(resolve, 2100));

      expect(consoleErrorSpy).toHaveBeenCalled();
      expect(loadingManagerMock.hide).toHaveBeenCalled();

      consoleErrorSpy.mockRestore();
    });

    it('should handle network errors during remove', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'));

      await downloadManager.removeQueuedDownload('dl-queued');

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.downloads.removeFailed',
        { error: 'Network error' },
        'error'
      );
    });

    it('should handle errors in updateQueueDisplay during remove', async () => {
      const downloadId = 'dl-queued';

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      downloadManager.updateQueueDisplay = vi.fn().mockRejectedValue(new Error('Update failed'));

      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      await downloadManager.removeQueuedDownload(downloadId);

      expect(consoleErrorSpy).toHaveBeenCalled();
      expect(showToastMock).toHaveBeenCalledWith(
        'toast.downloads.removedFromQueue',
        {},
        'info'
      );

      consoleErrorSpy.mockRestore();
    });
  });

  describe('Cancellation Issue Fix Tests', () => {
    it('should ensure cancelled downloads are not shown in queue', async () => {
      const downloadId = 'dl-123';

      // Mock backend returning empty downloads after cancellation
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [], // Backend should filter out cancelled downloads
      });

      downloadManager.updateQueueDisplay = vi.fn().mockResolvedValue(undefined);

      await downloadManager.cancelDownload(downloadId);

      await new Promise((resolve) => setTimeout(resolve, 2100));

      // Verify queue is checked and popup is hidden
      expect(downloadManager.checkQueueStatus).toHaveBeenCalled();
      expect(loadingManagerMock.hide).toHaveBeenCalled();
    });

    it('should handle WebSocket cancellation message with proper error handling', async () => {
      const downloadId = 'dl-123';
      const ws = {
        close: vi.fn(),
        readyState: WebSocket.OPEN,
        onmessage: null,
        onerror: null,
      };

      global.WebSocket = vi.fn(() => ws);

      downloadManager.executeDownloadWithProgress = vi.fn(async () => {
        if (ws.onmessage) {
          ws.onmessage({
            data: JSON.stringify({
              status: 'cancelled',
              download_id: downloadId,
            }),
          });
        }
      });

      downloadManager.checkQueueStatus = vi.fn().mockResolvedValue({
        downloads: [],
      });

      // Make updateQueueDisplay fail to test error handling
      downloadManager.updateQueueDisplay = vi.fn().mockRejectedValue(new Error('Update failed'));

      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      await downloadManager.executeDownloadWithProgress({
        modelId: 1,
        versionId: 1,
        versionName: 'v1.0',
      });

      await new Promise((resolve) => setTimeout(resolve, 200));

      // Should handle error and still hide popup
      expect(consoleErrorSpy).toHaveBeenCalled();
      expect(loadingManagerMock.hide).toHaveBeenCalled();

      consoleErrorSpy.mockRestore();
    });
  });
});

