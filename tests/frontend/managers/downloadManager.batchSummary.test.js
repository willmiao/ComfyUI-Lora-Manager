import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  DOWNLOAD_MANAGER_MODULE,
  MODAL_MANAGER_MODULE,
  UI_HELPERS_MODULE,
  STATE_MODULE,
  LOADING_MANAGER_MODULE,
  API_FACTORY_MODULE,
  STORAGE_HELPERS_MODULE,
  FOLDER_TREE_MANAGER_MODULE,
  I18N_HELPERS_MODULE,
  SUMMARY_MODULE,
  mockApiClient,
  mockLoadingManager,
  showToastMock,
  showDownloadBatchSummaryMock,
  resetAndReloadMock,
} = vi.hoisted(() => {
  // Shared API client returned by the mocked getModelApiClient factory.
  const mockApiClient = {
    apiConfig: {
      config: {
        displayName: 'LoRA',
        singularName: 'lora',
      },
    },
    downloadModel: vi.fn(),
    downloadHfModel: vi.fn(),
    cancelDownload: vi.fn(),
  };

  // Shared loading manager served both via state.loadingManager and the
  // LoadingManager constructor mock.
  const mockLoadingManager = {
    showSimpleLoading: vi.fn(),
    hide: vi.fn(),
    restoreProgressBar: vi.fn(),
    showDownloadProgress: vi.fn(() => vi.fn()),
    setStatus: vi.fn(),
    showCancelButton: vi.fn(),
  };

  return {
    DOWNLOAD_MANAGER_MODULE: new URL('../../../static/js/managers/DownloadManager.js', import.meta.url).pathname,
    MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
    UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
    STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
    LOADING_MANAGER_MODULE: new URL('../../../static/js/managers/LoadingManager.js', import.meta.url).pathname,
    API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
    STORAGE_HELPERS_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
    FOLDER_TREE_MANAGER_MODULE: new URL('../../../static/js/components/FolderTreeManager.js', import.meta.url).pathname,
    I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
    SUMMARY_MODULE: new URL('../../../static/js/components/DownloadBatchSummaryModal.js', import.meta.url).pathname,
    mockApiClient,
    mockLoadingManager,
    showToastMock: vi.fn(),
    showDownloadBatchSummaryMock: vi.fn(),
    resetAndReloadMock: vi.fn(),
  };
});

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: {
    showModal: vi.fn(),
    closeModal: vi.fn(),
  },
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
}));

vi.mock(STATE_MODULE, () => ({
  state: {
    global: {
      settings: {},
    },
    loadingManager: mockLoadingManager,
  },
}));

vi.mock(LOADING_MANAGER_MODULE, () => ({
  LoadingManager: vi.fn(() => mockLoadingManager),
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(() => mockApiClient),
  resetAndReload: resetAndReloadMock,
}));

vi.mock(STORAGE_HELPERS_MODULE, () => ({
  getStorageItem: vi.fn((_key, defaultValue) => defaultValue),
  setStorageItem: vi.fn(),
}));

vi.mock(FOLDER_TREE_MANAGER_MODULE, () => ({
  FolderTreeManager: vi.fn(() => ({
    clearSelection: vi.fn(),
    init: vi.fn(),
  })),
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((_, __, fallback) => fallback ?? ''),
}));

vi.mock(SUMMARY_MODULE, () => ({
  showDownloadBatchSummary: showDownloadBatchSummaryMock,
}));

/**
 * Fake WebSocket used by executeBatchDownload. Resolves `onopen` on the
 * microtask queue right after construction (which happens after the real
 * code has assigned `onopen`), so the open promise resolves deterministically
 * without real timers.
 */
class FakeWebSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.close = vi.fn();
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => {
      if (this.onopen) this.onopen();
    });
  }

  static get lastInstance() {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
  }
}

describe('DownloadManager batch download summary flow', () => {
  let DownloadManager;
  let manager;

  const options = { modelRoot: '/models/loras', targetFolder: '', useDefaultPaths: true };

  const makeItem = (modelId, versionId, name) => ({
    modelId,
    displayName: name,
    selectedVersion: { id: versionId, name, existsLocally: false },
  });

  const item0 = makeItem('111', 'v1', 'Model A');
  const item1 = makeItem('222', 'v2', 'Model B');

  beforeEach(async () => {
    document.body.innerHTML = '';
    FakeWebSocket.instances = [];

    // Reset the shared mocks so mockResolvedValueOnce queues and call
    // history never leak between tests.
    mockApiClient.downloadModel.mockReset();
    mockApiClient.downloadHfModel.mockReset();
    mockApiClient.cancelDownload.mockReset();
    showToastMock.mockClear();
    showDownloadBatchSummaryMock.mockClear();
    resetAndReloadMock.mockClear();
    mockLoadingManager.hide.mockClear();
    mockLoadingManager.setStatus.mockClear();
    mockLoadingManager.showCancelButton.mockClear();
    mockLoadingManager.showDownloadProgress.mockClear();

    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.resetModules();
    ({ DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE));
    manager = new DownloadManager();
    // The constructor leaves apiClient null; executeBatchDownload reads it
    // directly, so point it at the shared mocked client.
    manager.apiClient = mockApiClient;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
  });

  it('shows the success toast when every item downloads successfully', async () => {
    mockApiClient.downloadModel.mockResolvedValue({ success: true });

    await manager.executeBatchDownload([item0, item1], options);

    expect(mockApiClient.downloadModel).toHaveBeenCalledTimes(2);
    // Each item is downloaded with its own modelId + versionId.
    expect(mockApiClient.downloadModel.mock.calls[0][0]).toBe('111');
    expect(mockApiClient.downloadModel.mock.calls[0][1]).toBe('v1');
    expect(mockApiClient.downloadModel.mock.calls[1][0]).toBe('222');
    expect(mockApiClient.downloadModel.mock.calls[1][1]).toBe('v2');

    expect(showDownloadBatchSummaryMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.loras.allDownloadSuccessful', { count: 2 }, 'success');
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('shows a partial-failure summary when some items fail', async () => {
    // The failing item has no displayName/filename, so the resolved entry
    // name falls back to the selected version name.
    const unnamedItem = { modelId: '333', selectedVersion: { id: 'v3', name: 'V3', existsLocally: false } };
    mockApiClient.downloadModel
      .mockResolvedValueOnce({ success: false, error: 'rate limited' })
      .mockResolvedValueOnce({ success: true });

    await manager.executeBatchDownload([unnamedItem, item1], options);

    expect(showDownloadBatchSummaryMock).toHaveBeenCalledTimes(1);
    const summary = showDownloadBatchSummaryMock.mock.calls[0][0];
    expect(summary.total).toBe(2);
    expect(summary.completed).toBe(1);
    expect(summary.failedItems).toHaveLength(1);
    expect(summary.failedItems[0].item).toBe(unnamedItem);
    expect(summary.failedItems[0].error).toBe('rate limited');
    // The resolved display name is carried on the failed entry.
    expect(summary.failedItems[0].name).toBe('V3');
    expect(summary.onRetry).toEqual(expect.any(Function));

    // No success toast and no downloadPartialSuccess toast for this path.
    expect(showToastMock).not.toHaveBeenCalledWith('toast.loras.allDownloadSuccessful', expect.anything(), 'success');
    expect(showToastMock).not.toHaveBeenCalledWith('toast.loras.downloadPartialSuccess', expect.anything(), expect.anything());
  });

  it('shows an all-failed summary when every item fails', async () => {
    mockApiClient.downloadModel.mockResolvedValue({ success: false, error: 'x' });

    await manager.executeBatchDownload([item0, item1], options);

    expect(showDownloadBatchSummaryMock).toHaveBeenCalledTimes(1);
    const summary = showDownloadBatchSummaryMock.mock.calls[0][0];
    expect(summary.total).toBe(2);
    expect(summary.completed).toBe(0);
    expect(summary.failedItems).toHaveLength(2);
    expect(summary.failedItems[0].item).toBe(item0);
    expect(summary.failedItems[1].item).toBe(item1);
    expect(showToastMock).not.toHaveBeenCalledWith('toast.loras.allDownloadSuccessful', expect.anything(), expect.anything());
  });

  it('records the error message when downloadModel rejects', async () => {
    // The item carries a filename but no displayName, so the resolved entry
    // name comes from the filename.
    const filenameItem = { modelId: '444', filename: 'model.safetensors', selectedVersion: { id: 'v4' } };
    mockApiClient.downloadModel.mockRejectedValue(new Error('network down'));

    await manager.executeBatchDownload([filenameItem], options);

    expect(showDownloadBatchSummaryMock).toHaveBeenCalledTimes(1);
    const summary = showDownloadBatchSummaryMock.mock.calls[0][0];
    expect(summary.total).toBe(1);
    expect(summary.completed).toBe(0);
    expect(summary.failedItems).toHaveLength(1);
    expect(summary.failedItems[0].item).toBe(filenameItem);
    expect(summary.failedItems[0].error).toBe('network down');
    expect(summary.failedItems[0].name).toBe('model.safetensors');
  });

  it('retries the failed subset through onRetry with unwrapped items', async () => {
    mockApiClient.downloadModel
      .mockResolvedValueOnce({ success: false, error: 'rate limited' })
      .mockResolvedValueOnce({ success: true });

    await manager.executeBatchDownload([item0, item1], options);

    expect(showDownloadBatchSummaryMock).toHaveBeenCalledTimes(1);
    const summary = showDownloadBatchSummaryMock.mock.calls[0][0];
    expect(summary.failedItems).toHaveLength(1);

    // Retry the exact failed subset returned by the summary. The onRetry
    // callback unwraps the { item, error } entries back into raw model items
    // before re-running executeBatchDownload. Make the retried item fail
    // again so a second summary is produced.
    mockApiClient.downloadModel.mockResolvedValueOnce({ success: false, error: 'still rate limited' });
    await summary.onRetry(summary.failedItems);

    // downloadModel is called a third time — only for the failed item (item0),
    // NOT for the item that already succeeded (item1).
    expect(mockApiClient.downloadModel).toHaveBeenCalledTimes(3);
    const retryCall = mockApiClient.downloadModel.mock.calls[2];
    expect(retryCall[0]).toBe(item0.modelId);
    expect(retryCall[1]).toBe(item0.selectedVersion.id);

    // A fresh summary is produced for the retry run (call count 1 -> 2).
    expect(showDownloadBatchSummaryMock).toHaveBeenCalledTimes(2);
    const retrySummary = showDownloadBatchSummaryMock.mock.calls[1][0];
    expect(retrySummary.total).toBe(1);
    expect(retrySummary.completed).toBe(0);
    expect(retrySummary.failedItems).toHaveLength(1);
    expect(retrySummary.failedItems[0].item).toBe(item0);
    expect(retrySummary.failedItems[0].error).toBe('still rate limited');
  });

  it('stops the batch without showing a summary when cancelled before downloads start', async () => {
    const downloadPromise = manager.executeBatchDownload([item0, item1], options);

    // showCancelButton captured the cancel callback synchronously. Invoking it
    // sets `cancelled = true` before the download loop runs (the loop only
    // starts after the WebSocket open promise resolves on the microtask queue).
    const cancelCallback = mockLoadingManager.showCancelButton.mock.calls[0][0];
    const cancelPromise = cancelCallback();

    await Promise.all([downloadPromise, cancelPromise]);

    expect(mockApiClient.downloadModel).not.toHaveBeenCalled();
    expect(showDownloadBatchSummaryMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.downloads.downloadStopped',
      expect.anything(),
      'info',
      expect.stringContaining('Download cancelled')
    );
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });
});
