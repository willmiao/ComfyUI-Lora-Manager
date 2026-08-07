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
    fetchCivitaiVersions: vi.fn(),
    downloadModel: vi.fn(),
    downloadHfModel: vi.fn(),
    cancelDownload: vi.fn(),
    getPageState: vi.fn(() => ({})),
  };

  // Shared loading manager served both via state.loadingManager and the
  // LoadingManager constructor mock.
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

/** Minimal DOM used by validateAndFetchVersions / showVersionStep / batch preview. */
function setupDownloadDom() {
  document.body.innerHTML = `
    <div id="downloadModal">
      <div class="download-step" id="urlStep"></div>
      <div class="download-step" id="versionStep"></div>
      <div class="download-step" id="fileSelectionStep"></div>
      <div class="download-step" id="locationStep"></div>
      <div id="batchPreviewStep"></div>
      <textarea id="modelUrl"></textarea>
      <div id="urlError"></div>
      <div id="versionList"></div>
      <div id="fileSelectionList"></div>
      <div id="fileSelectionVersionName"></div>
      <button id="nextFromVersion"></button>
      <button id="nextFromBatchBtn"></button>
      <div id="downloadModalTitle"></div>
      <div id="batchPreviewList"></div>
      <div id="modelRoot"></div>
      <div id="folderPath"></div>
      <div id="targetPathDisplay"></div>
      <input id="useDefaultPath" />
      <div id="manualPathSelection"></div>
    </div>
  `;
}

function makeVersion(id, name) {
  return {
    id,
    name,
    baseModel: 'SDXL',
    createdAt: '2025-01-01T00:00:00Z',
    availability: 'Public',
    images: [{ url: 'https://image.civitai.com/preview.jpg' }],
    files: [{ id: 1, type: 'Model', name: 'model.safetensors', sizeKB: 1000 }],
    modelSizeKB: 1000,
    existsLocally: false,
    hasBeenDownloaded: false,
  };
}

// Newest-first, matching the Civitai API response order. The default selection
// takes the first version, so the newest (largest id) must come first.
const versions = [makeVersion(250, 'v3'), makeVersion(100, 'v1'), makeVersion(30, 'v0')];

describe('DownloadManager latest-version default', () => {
  let DownloadManager;
  let manager;

  beforeEach(async () => {
    document.body.innerHTML = '';
    setupDownloadDom();

    mockApiClient.fetchCivitaiVersions.mockReset();
    mockLoadingManager.showSimpleLoading.mockClear();
    mockLoadingManager.hide.mockClear();

    vi.resetModules();
    ({ DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE));
    manager = new DownloadManager();
    manager.apiClient = mockApiClient;
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  describe('single URL without modelVersionId', () => {
    it('auto-selects the latest version so no manual version click is needed', async () => {
      document.getElementById('modelUrl').value = 'https://civitai.red/models/837884/midjourney-artful-nsfw';
      mockApiClient.fetchCivitaiVersions.mockResolvedValue(versions);

      await manager.validateAndFetchVersions();

      expect(manager.modelId).toBe('837884');
      expect(manager.currentVersion.id).toBe(250);
      // The version step is shown with the latest version pre-selected.
      expect(document.getElementById('versionStep').style.display).toBe('block');
      const selected = document.querySelector('.version-item.selected');
      expect(selected.dataset.versionId).toBe('250');
      expect(document.getElementById('nextFromVersion').disabled).toBe(false);
    });

    it('still honours an explicit modelVersionId from the URL', async () => {
      document.getElementById('modelUrl').value =
        'https://civitai.red/models/837884/midjourney-artful-nsfw?modelVersionId=30';
      mockApiClient.fetchCivitaiVersions.mockResolvedValue(versions);

      await manager.validateAndFetchVersions();

      expect(manager.currentVersion.id).toBe(30);
    });
  });

  describe('fetchVersionsForCurrentModel without modelVersionId', () => {
    it('auto-selects the latest version', async () => {
      manager.modelId = '837884';
      manager.modelVersionId = null;
      mockApiClient.fetchCivitaiVersions.mockResolvedValue(versions);

      await manager.fetchVersionsForCurrentModel();

      expect(manager.currentVersion.id).toBe(250);
    });

    it('still honours an explicit modelVersionId', async () => {
      manager.modelId = '837884';
      manager.modelVersionId = '100';
      mockApiClient.fetchCivitaiVersions.mockResolvedValue(versions);

      await manager.fetchVersionsForCurrentModel();

      expect(manager.currentVersion.id).toBe(100);
    });
  });

  describe('multi-URL batch without modelVersionId', () => {
    it('defaults each item to its latest version (first in API response)', async () => {
      document.getElementById('modelUrl').value =
        'https://civitai.red/models/111/foo\nhttps://civitai.red/models/222/bar';
      const versionsA = [makeVersion(40, 'a2'), makeVersion(10, 'a1')];
      const versionsB = [makeVersion(500, 'b1'), makeVersion(7, 'b2')];
      mockApiClient.fetchCivitaiVersions.mockImplementation(async modelId =>
        modelId === '111' ? versionsA : versionsB
      );

      await manager.validateAndFetchVersions();

      expect(manager.isBatchMode).toBe(true);
      expect(manager.batchModels).toHaveLength(2);
      expect(manager.batchModels[0].selectedVersion.id).toBe(40);
      expect(manager.batchModels[1].selectedVersion.id).toBe(500);
    });

    it('still honours an explicit modelVersionId per URL', async () => {
      document.getElementById('modelUrl').value =
        'https://civitai.red/models/111/foo?modelVersionId=10\nhttps://civitai.red/models/222/bar';
      const versionsA = [makeVersion(40, 'a2'), makeVersion(10, 'a1')];
      const versionsB = [makeVersion(500, 'b1'), makeVersion(7, 'b2')];
      mockApiClient.fetchCivitaiVersions.mockImplementation(async modelId =>
        modelId === '111' ? versionsA : versionsB
      );

      await manager.validateAndFetchVersions();

      expect(manager.batchModels[0].selectedVersion.id).toBe(10);
      expect(manager.batchModels[1].selectedVersion.id).toBe(500);
    });
  });
});
