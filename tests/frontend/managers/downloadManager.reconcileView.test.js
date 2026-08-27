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
  SIDEBAR_MANAGER_MODULE,
  mockApiClient,
  mockScroller,
  stateMock,
  mockLoadingManager,
  showToastMock,
  resetAndReloadMock,
  setStorageItemMock,
  sidebarRefreshMock,
} = vi.hoisted(() => {
  const mockScroller = {
    items: [],
    removeItemByFilePath: vi.fn(),
    removeMultipleItemsByFilePath: vi.fn(),
    updateSingleItem: vi.fn(),
  };

  const stateMock = {
    currentPageType: 'loras',
    global: { settings: {} },
    loadingManager: null,
    virtualScroller: mockScroller,
  };

  const mockApiClient = {
    apiConfig: {
      config: {
        displayName: 'LoRA',
        singularName: 'lora',
      },
    },
    modelType: 'loras',
    getPageState: vi.fn(() => ({})),
    downloadModel: vi.fn(),
    downloadHfModel: vi.fn(),
    cancelDownload: vi.fn(),
  };

  const mockLoadingManager = {
    showSimpleLoading: vi.fn(),
    setStatus: vi.fn(),
    hide: vi.fn(),
    restoreProgressBar: vi.fn(),
    showDownloadProgress: vi.fn(() => vi.fn()),
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
    SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
    mockApiClient,
    mockScroller,
    stateMock,
    mockLoadingManager,
    showToastMock: vi.fn(),
    resetAndReloadMock: vi.fn(),
    setStorageItemMock: vi.fn(),
    sidebarRefreshMock: vi.fn(),
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
  state: stateMock,
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
  setStorageItem: setStorageItemMock,
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
  showDownloadBatchSummary: vi.fn(),
}));

vi.mock(SIDEBAR_MANAGER_MODULE, () => ({
  sidebarManager: { refresh: sidebarRefreshMock },
}));

/** Minimal WebSocket stub: executeDownloadWithProgress never awaits open. */
class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 0; // CONNECTING
  }
  close() {}
}

/** Build a card item as returned by the backend listing endpoint. */
function makeItem(filePath, modelId, base) {
  return {
    file_path: filePath,
    civitai: { modelId, ...(base ? { baseModel: base } : {}) },
    update_available: true,
  };
}

describe('DownloadManager post-download in-place reconciliation (#1078)', () => {
  let DownloadManager;
  let manager;

  beforeEach(async () => {
    document.body.innerHTML = '';
    stateMock.virtualScroller = mockScroller;
    mockScroller.items = [];
    mockScroller.removeItemByFilePath.mockReset();
    mockScroller.removeMultipleItemsByFilePath.mockReset();
    mockScroller.updateSingleItem.mockReset();
    mockApiClient.getPageState.mockReset();
    mockApiClient.getPageState.mockReturnValue({});
    mockApiClient.downloadModel.mockReset();
    resetAndReloadMock.mockReset();
    resetAndReloadMock.mockResolvedValue(undefined);
    sidebarRefreshMock.mockReset();
    sidebarRefreshMock.mockResolvedValue(undefined);
    setStorageItemMock.mockReset();
    showToastMock.mockClear();
    vi.stubGlobal('WebSocket', FakeWebSocket);

    vi.resetModules();
    ({ DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE));
    manager = new DownloadManager();
    manager.apiClient = mockApiClient;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    stateMock.virtualScroller = mockScroller;
  });

  describe('_isVersionLatest', () => {
    it('treats unknown/empty version lists as latest', () => {
      expect(manager._isVersionLatest('250', [])).toBe(true);
      expect(manager._isVersionLatest('250', null)).toBe(true);
      expect(manager._isVersionLatest(undefined, undefined)).toBe(true);
    });

    it('returns true only for the newest known remote version', () => {
      const versions = [{ id: 100 }, { id: 250 }, { id: 30 }];
      expect(manager._isVersionLatest(250, versions)).toBe(true);
      expect(manager._isVersionLatest('250', versions)).toBe(true);
      expect(manager._isVersionLatest(100, versions)).toBe(false);
      expect(manager._isVersionLatest(30, versions)).toBe(false);
    });

    it('supports record-style version objects (versionId field)', () => {
      const versions = [{ versionId: 10 }, { versionId: 20 }];
      expect(manager._isVersionLatest(20, versions)).toBe(true);
      expect(manager._isVersionLatest(10, versions)).toBe(false);
    });

    it('returns true when the target id is unknown', () => {
      const versions = [{ id: 100 }];
      expect(manager._isVersionLatest('not-a-number', versions)).toBe(true);
      expect(manager._isVersionLatest(undefined, versions)).toBe(true);
    });
  });

  describe('_reconcileViewAfterDownload', () => {
    it('removes the model cards in the Updates view when the latest version was installed', async () => {
      stateMock.virtualScroller.items = [
        makeItem('/models/loras/old.safetensors', 837884),
        makeItem('/models/loras/unrelated.safetensors', 999999),
      ];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: true });

      const result = await manager._reconcileViewAfterDownload({ modelId: 837884, isLatestVersion: true });

      expect(result).toBe(true);
      expect(mockScroller.removeMultipleItemsByFilePath).toHaveBeenCalledWith([
        '/models/loras/old.safetensors',
      ]);
      expect(mockScroller.updateSingleItem).not.toHaveBeenCalled();
      expect(resetAndReloadMock).not.toHaveBeenCalled();
      // Sidebar (folder counts) is refreshed, but never the model listing.
      expect(sidebarRefreshMock).toHaveBeenCalledTimes(1);
    });

    it('patches the update flag instead of removing cards in a normal listing', async () => {
      stateMock.virtualScroller.items = [
        makeItem('/models/loras/old.safetensors', 837884),
      ];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: false });

      const result = await manager._reconcileViewAfterDownload({ modelId: 837884, isLatestVersion: true });

      expect(result).toBe(true);
      expect(mockScroller.updateSingleItem).toHaveBeenCalledWith(
        '/models/loras/old.safetensors',
        { update_available: false }
      );
      expect(mockScroller.removeMultipleItemsByFilePath).not.toHaveBeenCalled();
      expect(resetAndReloadMock).not.toHaveBeenCalled();
      expect(sidebarRefreshMock).toHaveBeenCalledTimes(1);
    });

    it('leaves the list untouched when an older version was deliberately downloaded', async () => {
      stateMock.virtualScroller.items = [makeItem('/models/loras/old.safetensors', 837884)];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: true });

      const result = await manager._reconcileViewAfterDownload({ modelId: 837884, isLatestVersion: false });

      expect(result).toBe(true);
      expect(mockScroller.removeMultipleItemsByFilePath).not.toHaveBeenCalled();
      expect(mockScroller.updateSingleItem).not.toHaveBeenCalled();
      expect(resetAndReloadMock).not.toHaveBeenCalled();
      expect(sidebarRefreshMock).toHaveBeenCalledTimes(1);
    });

    it('keeps the listing untouched when the downloaded model is not in the current view', async () => {
      stateMock.virtualScroller.items = [makeItem('/models/loras/other.safetensors', 999999)];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: true });

      const result = await manager._reconcileViewAfterDownload({ modelId: 837884, isLatestVersion: true });

      expect(result).toBe(false);
      expect(mockScroller.removeMultipleItemsByFilePath).not.toHaveBeenCalled();
      expect(mockScroller.updateSingleItem).not.toHaveBeenCalled();
      expect(resetAndReloadMock).not.toHaveBeenCalled();
      expect(sidebarRefreshMock).toHaveBeenCalledTimes(1);
    });

    it('no-ops for models without a CivitAI identity (HF downloads)', async () => {
      stateMock.virtualScroller.items = [makeItem('/models/loras/a.safetensors', 123)];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: true });

      const result = await manager._reconcileViewAfterDownload({ modelId: null, isLatestVersion: true });

      expect(result).toBe(false);
      expect(mockScroller.removeMultipleItemsByFilePath).not.toHaveBeenCalled();
      expect(resetAndReloadMock).not.toHaveBeenCalled();
      expect(sidebarRefreshMock).toHaveBeenCalledTimes(1);
    });

    it('falls back to a full reload when no virtual scroller is available', async () => {
      stateMock.virtualScroller = undefined;

      const result = await manager._reconcileViewAfterDownload({ modelId: 837884, isLatestVersion: true });

      expect(result).toBe(false);
      expect(resetAndReloadMock).toHaveBeenCalledWith(true);
      expect(mockScroller.removeMultipleItemsByFilePath).not.toHaveBeenCalled();
      expect(sidebarRefreshMock).not.toHaveBeenCalled();
    });
  });

  describe('_reconcileBatchViewAfterDownload', () => {
    it('reconciles each distinct successful CivitAI model and refreshes the sidebar once', async () => {
      stateMock.virtualScroller.items = [
        makeItem('/models/loras/a.safetensors', 111),
        makeItem('/models/loras/b.safetensors', 222),
      ];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: true });

      await manager._reconcileBatchViewAfterDownload([
        { modelId: '111', selectedVersion: { id: 40 }, versions: [{ id: 40 }, { id: 10 }] },
        { modelId: '111', selectedVersion: { id: 40 }, versions: [{ id: 40 }, { id: 10 }] },
        { modelId: '222', selectedVersion: { id: 7 }, versions: [{ id: 7 }] },
      ], 0);

      expect(mockScroller.removeMultipleItemsByFilePath).toHaveBeenCalledTimes(2);
      expect(mockScroller.removeMultipleItemsByFilePath).toHaveBeenCalledWith(['/models/loras/a.safetensors']);
      expect(mockScroller.removeMultipleItemsByFilePath).toHaveBeenCalledWith(['/models/loras/b.safetensors']);
      // One sidebar refresh for the whole batch, not one per model.
      expect(sidebarRefreshMock).toHaveBeenCalledTimes(1);
      expect(resetAndReloadMock).not.toHaveBeenCalled();
    });

    it('falls back to a full reload when any HF download completed', async () => {
      stateMock.virtualScroller.items = [makeItem('/models/loras/a.safetensors', 111)];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: true });

      await manager._reconcileBatchViewAfterDownload([
        { modelId: '111', selectedVersion: { id: 40 }, versions: [{ id: 40 }, { id: 10 }] },
      ], 1);

      expect(resetAndReloadMock).toHaveBeenCalledWith(true);
      expect(mockScroller.removeMultipleItemsByFilePath).not.toHaveBeenCalled();
      expect(sidebarRefreshMock).not.toHaveBeenCalled();
    });

    it('falls back to a full reload when no virtual scroller exists', async () => {
      stateMock.virtualScroller = undefined;

      await manager._reconcileBatchViewAfterDownload([
        { modelId: '111', selectedVersion: { id: 40 }, versions: [{ id: 40 }, { id: 10 }] },
      ], 0);

      expect(resetAndReloadMock).toHaveBeenCalledWith(true);
    });
  });

  describe('executeDownloadWithProgress success path', () => {
    it('reconciles in place instead of hijacking the active folder or reloading', async () => {
      stateMock.virtualScroller.items = [makeItem('/models/loras/old.safetensors', 837884)];
      const pageState = { showUpdateAvailableOnly: true };
      mockApiClient.getPageState.mockReturnValue(pageState);
      mockApiClient.downloadModel.mockResolvedValue({ success: true });
      manager.versions = [{ id: 250 }, { id: 100 }];

      const result = await manager.executeDownloadWithProgress({
        modelId: 837884,
        versionId: 250,
        versionName: 'v2',
        targetFolder: 'Some/SubFolder',
        useDefaultPaths: false,
        source: 'civitai',
      });

      expect(result).toBe(true);
      // The download destination folder must never become the active folder.
      expect(pageState).toEqual({ showUpdateAvailableOnly: true });
      expect(setStorageItemMock).not.toHaveBeenCalledWith(
        expect.stringContaining('_activeFolder'),
        expect.anything()
      );
      // Card reconciled in place; no full page reload, no scroll reset.
      expect(mockScroller.removeMultipleItemsByFilePath).toHaveBeenCalledWith([
        '/models/loras/old.safetensors',
      ]);
      expect(resetAndReloadMock).not.toHaveBeenCalled();
      expect(sidebarRefreshMock).toHaveBeenCalledTimes(1);
    });

    it('falls back to a full reload when no virtual scroller is available', async () => {
      stateMock.virtualScroller = undefined;
      mockApiClient.downloadModel.mockResolvedValue({ success: true });

      const result = await manager.executeDownloadWithProgress({
        modelId: 837884,
        versionId: 250,
        source: 'civitai',
      });

      expect(result).toBe(true);
      expect(resetAndReloadMock).toHaveBeenCalledWith(true);
    });

    it('passes through an explicit isLatestVersion flag', async () => {
      stateMock.virtualScroller.items = [makeItem('/models/loras/old.safetensors', 837884)];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: true });
      mockApiClient.downloadModel.mockResolvedValue({ success: true });
      manager.versions = [{ id: 250 }];

      await manager.executeDownloadWithProgress({
        modelId: 837884,
        versionId: 100,
        source: 'civitai',
        isLatestVersion: false,
      });

      // Deliberately downloading an older version keeps the card.
      expect(mockScroller.removeMultipleItemsByFilePath).not.toHaveBeenCalled();
      expect(mockScroller.updateSingleItem).not.toHaveBeenCalled();
      expect(resetAndReloadMock).not.toHaveBeenCalled();
    });
  });

  describe('_downloadSelectedFilesSequentially success path', () => {
    it('reconciles in place once all files of the latest version are downloaded', async () => {
      stateMock.virtualScroller.items = [makeItem('/models/loras/old.safetensors', 837884)];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: true });
      mockApiClient.downloadModel.mockResolvedValue({ success: true });
      manager.modelId = '837884';
      manager.currentVersion = { id: 201 };
      manager.versions = [{ id: 201 }, { id: 100 }];
      manager.source = 'civitai';
      manager.selectedFiles = [
        { id: 1, name: 'a.safetensors', type: 'Model', sizeKB: 10 },
        { id: 2, name: 'b.safetensors', type: 'Model', sizeKB: 10 },
      ];

      const result = await manager._downloadSelectedFilesSequentially({
        modelRoot: '/models/loras',
        targetFolder: '',
        useDefaultPaths: true,
      });

      expect(result).toBe(true);
      expect(resetAndReloadMock).not.toHaveBeenCalled();
      expect(mockScroller.removeMultipleItemsByFilePath).toHaveBeenCalledWith([
        '/models/loras/old.safetensors',
      ]);
      expect(sidebarRefreshMock).toHaveBeenCalledTimes(1);
    });

    it('keeps the listing untouched on partial multi-file failure', async () => {
      stateMock.virtualScroller.items = [makeItem('/models/loras/old.safetensors', 837884)];
      mockApiClient.getPageState.mockReturnValue({ showUpdateAvailableOnly: true });
      mockApiClient.downloadModel
        .mockResolvedValueOnce({ success: true })
        .mockResolvedValueOnce({ success: false, error: 'rate limited' });
      manager.modelId = '837884';
      manager.currentVersion = { id: 201 };
      manager.versions = [{ id: 201 }, { id: 100 }];
      manager.source = 'civitai';
      manager.selectedFiles = [
        { id: 1, name: 'a.safetensors', type: 'Model', sizeKB: 10 },
        { id: 2, name: 'b.safetensors', type: 'Model', sizeKB: 10 },
      ];

      const result = await manager._downloadSelectedFilesSequentially({
        modelRoot: '/models/loras',
        targetFolder: '',
        useDefaultPaths: true,
      });

      expect(result).toBe(false);
      expect(mockScroller.removeMultipleItemsByFilePath).not.toHaveBeenCalled();
      expect(resetAndReloadMock).not.toHaveBeenCalled();
    });
  });
});