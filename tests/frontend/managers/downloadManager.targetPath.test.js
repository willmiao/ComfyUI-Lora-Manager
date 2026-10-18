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
  mockState,
} = vi.hoisted(() => {
  const mockApiClient = {
    modelType: 'loras',
    apiConfig: {
      config: {
        displayName: 'LoRA',
        singularName: 'lora',
      },
    },
  };

  const mockLoadingManager = {
    showSimpleLoading: vi.fn(),
    setStatus: vi.fn(),
    hide: vi.fn(),
  };

  const mockFolderTreeManager = {
    getSelectedPath: vi.fn(() => ''),
  };

  const mockState = {
    global: {
      settings: {
        download_path_templates: {},
      },
    },
    loadingManager: mockLoadingManager,
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
    mockState,
  };
});

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: {
    showModal: vi.fn(),
    closeModal: vi.fn(),
  },
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
  showActionToast: vi.fn(),
  setupAutoNewlineOnPaste: vi.fn(),
}));

vi.mock(STATE_MODULE, () => ({
  state: mockState,
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

describe('DownloadManager default-path preview', () => {
  let DownloadManager;

  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();
    ({ DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE));

    document.body.innerHTML = `
      <select id="modelRoot"><option value="/models/vae">/models/vae</option></select>
      <div id="targetPathDisplay"></div>
    `;
    document.getElementById('modelRoot').value = '/models/vae';

    mockState.global.settings.download_path_templates = {};
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  function useOtherClient(manager) {
    mockApiClient.modelType = 'other';
    mockApiClient.apiConfig.config = { displayName: 'Other Model', singularName: 'other' };
    manager.apiClient = mockApiClient;
  }

  it('renders the bare root for a flat (empty) other template', () => {
    mockState.global.settings.download_path_templates = { other: '' };
    const manager = new DownloadManager();
    useOtherClient(manager);
    manager.useDefaultPath = true;

    manager.updateTargetPath();

    const text = document.getElementById('targetPathDisplay').textContent;
    expect(text).toBe('/models/vae');
    expect(text).not.toContain('undefined');
  });

  it('renders the bare root when the other template key is absent', () => {
    mockState.global.settings.download_path_templates = {};
    const manager = new DownloadManager();
    useOtherClient(manager);
    manager.useDefaultPath = true;

    manager.updateTargetPath();

    const text = document.getElementById('targetPathDisplay').textContent;
    expect(text).toBe('/models/vae');
    expect(text).not.toContain('undefined');
  });

  it('appends a configured template to the root', () => {
    mockState.global.settings.download_path_templates = { other: '{base_model}' };
    const manager = new DownloadManager();
    useOtherClient(manager);
    manager.useDefaultPath = true;

    manager.updateTargetPath();

    expect(document.getElementById('targetPathDisplay').textContent).toBe('/models/vae/{base_model}');
  });

  it('renders the manual selection when default paths are off', () => {
    mockFolderTreeManager.getSelectedPath.mockReturnValue('nested/folder');
    const manager = new DownloadManager();
    useOtherClient(manager);
    manager.useDefaultPath = false;

    manager.updateTargetPath();

    expect(document.getElementById('targetPathDisplay').textContent).toBe('/models/vae/nested/folder');
  });
});
