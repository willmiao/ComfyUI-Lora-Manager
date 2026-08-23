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
  mockFolderTreeManager,
  showToastMock,
} = vi.hoisted(() => {
  const mockApiClient = {
    modelType: 'loras',
    apiConfig: {
      config: {
        displayName: 'LoRA',
        singularName: 'lora',
      },
    },
    fetchModelRoots: vi.fn(async () => ({ roots: ['/models/loras'] })),
    fetchUnifiedFolderTree: vi.fn(async () => ({ success: true, tree: {} })),
  };

  const mockLoadingManager = {
    showSimpleLoading: vi.fn(),
    setStatus: vi.fn(),
    hide: vi.fn(),
    restoreProgressBar: vi.fn(),
    showDownloadProgress: vi.fn(() => vi.fn()),
    showCancelButton: vi.fn(),
  };

  const mockFolderTreeManager = {
    clearSelection: vi.fn(),
    init: vi.fn(),
    loadTree: vi.fn(async () => {}),
    getSelectedPath: vi.fn(() => ''),
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
    mockFolderTreeManager,
    showToastMock: vi.fn(),
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
  setupAutoNewlineOnPaste: vi.fn(),
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
  resetAndReload: vi.fn(),
}));

vi.mock(STORAGE_HELPERS_MODULE, () => ({
  getStorageItem: vi.fn((_key, defaultValue) => defaultValue),
  setStorageItem: vi.fn(),
}));

vi.mock(FOLDER_TREE_MANAGER_MODULE, () => ({
  FolderTreeManager: vi.fn(() => mockFolderTreeManager),
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((_, __, fallback) => fallback ?? ''),
}));

vi.mock(SUMMARY_MODULE, () => ({
  showDownloadBatchSummary: vi.fn(),
}));

describe('DownloadManager folder tree', () => {
  let DownloadManager;

  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();
    ({ DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE));
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('should fetch the folder tree including empty directories', async () => {
    const manager = new DownloadManager();
    manager.apiClient = mockApiClient;

    await manager.initializeFolderTree();

    expect(mockApiClient.fetchUnifiedFolderTree).toHaveBeenCalledWith({ includeEmpty: true });
    expect(mockFolderTreeManager.loadTree).toHaveBeenCalledWith({});
  });
});
