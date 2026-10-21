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
    fetchCivitaiModelByVersion: vi.fn(),
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
    DOWNLOAD_MANAGER_MODULE: new URL('../../../static/js/managers/DownloadManager.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
    MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
    UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
    STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
    LOADING_MANAGER_MODULE: new URL('../../../static/js/managers/LoadingManager.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
    API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
    STORAGE_HELPERS_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
    FOLDER_TREE_MANAGER_MODULE: new URL('../../../static/js/components/FolderTreeManager.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
    I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
    SUMMARY_MODULE: new URL('../../../static/js/components/DownloadBatchSummaryModal.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
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
    getSelectedPath: vi.fn(() => ''),
  })),
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((key, _, fallback) => fallback ?? key),
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
      <div class="download-step" id="downloadLocationStep"></div>
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


describe('DownloadManager Civitai download URLs', () => {
  let DownloadManager;
  let manager;
  let requestedVersion;
  const url = 'https://civitai.com/api/download/models/3409322?fileId=3301284';

  beforeEach(async () => {
    vi.clearAllMocks();
    setupDownloadDom();
    vi.resetModules();
    ({ DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE));
    manager = new DownloadManager();
    manager.apiClient = mockApiClient;
    requestedVersion = makeVersion(3409322, 'requested');
    requestedVersion.files = [
      { id: 1, type: 'Model', name: 'primary.safetensors', primary: true },
      { id: 3301284, type: 'Model', name: 'requested.safetensors' },
    ];
    mockApiClient.fetchCivitaiModelByVersion.mockReset().mockResolvedValue({ modelId: 123 });
    mockApiClient.fetchCivitaiVersions.mockReset().mockResolvedValue([
      makeVersion(9999999, 'latest'), requestedVersion,
    ]);
  });

  it('resolves the reported link and preselects its non-primary file', async () => {
    document.getElementById('modelUrl').value = url;
    await manager.validateAndFetchVersions();
    expect(mockApiClient.fetchCivitaiModelByVersion).toHaveBeenCalledWith('3409322');
    expect(mockApiClient.fetchCivitaiVersions).toHaveBeenCalledWith('123', null);
    expect(manager.currentVersion.id).toBe(3409322);
    expect(manager.selectedFile.id).toBe(3301284);
    expect(manager.selectedFiles.map(file => file.id)).toEqual([3301284]);
    expect(document.querySelector('input[value="3301284"]').checked).toBe(true);
    expect(document.getElementById('fileSelectionStep').style.display).toBe('block');
    expect(document.getElementById('urlError').textContent).toBe('');
  });

  it('accepts a version download URL without fileId', async () => {
    document.getElementById('modelUrl').value = url.split('?')[0];
    await manager.validateAndFetchVersions();
    expect(manager.modelId).toBe('123');
    expect(manager.currentVersion.id).toBe(3409322);
    expect(manager.selectedFile).toBeNull();
  });

  it('shows lookup failures without fetching versions for the version ID', async () => {
    mockApiClient.fetchCivitaiModelByVersion.mockRejectedValue(new Error('Version not found'));
    document.getElementById('modelUrl').value = url;
    await manager.validateAndFetchVersions();
    expect(document.getElementById('urlError').textContent).toBe('Version not found');
    expect(mockApiClient.fetchCivitaiVersions).not.toHaveBeenCalled();
    expect(mockLoadingManager.hide).toHaveBeenCalled();
  });

  it('does not fall back to the primary file when fileId is absent from the version', async () => {
    document.getElementById('modelUrl').value = url.replace('3301284', '42');
    await manager.validateAndFetchVersions();
    expect(document.getElementById('urlError').textContent).toContain('42');
    expect(manager.selectedFile).toBeNull();
  });

  it('clears a previous linked-file selection when a model page is entered', async () => {
    document.getElementById('modelUrl').value = url;
    await manager.validateAndFetchVersions();
    document.getElementById('modelUrl').value = 'https://civitai.com/models/123';
    await manager.validateAndFetchVersions();
    expect(manager.currentVersion.id).toBe(9999999);
    expect(manager.selectedFile).toBeNull();
    expect(manager.selectedFiles).toEqual([]);
  });

  it('keeps distinct linked files in a batch and deduplicates identical links', async () => {
    document.getElementById('modelUrl').value = `${url}\n${url.replace('3301284', '1')}\n${url}`;
    await manager.validateAndFetchVersions();
    expect(manager.batchModels).toHaveLength(2);
    expect(manager.batchModels.map(item => item.modelId)).toEqual(['123', '123']);
    expect(manager.batchModels.map(item => item.selectedVersion.id)).toEqual([3409322, 3409322]);
    expect(manager.batchModels.map(item => item.selectedFile.id)).toEqual([3301284, 1]);
  });

  it('passes the linked file ID to the single-download request', async () => {
    document.getElementById('modelUrl').value = url;
    await manager.validateAndFetchVersions();
    document.getElementById('modelRoot').value = '/models/loras';
    manager.folderTreeManager.getSelectedPath = vi.fn(() => '');
    const execute = vi.spyOn(manager, 'executeDownloadWithProgress').mockResolvedValue({ success: true });
    await manager.startDownload();
    expect(execute).toHaveBeenCalledWith(expect.objectContaining({
      modelId: '123', versionId: 3409322,
      fileParams: expect.objectContaining({ id: 3301284, name: 'requested.safetensors' }),
    }));
  });

  it('passes each linked file ID to batch-download requests', async () => {
    document.getElementById('modelUrl').value = `${url}\n${url.replace('3301284', '1')}`;
    await manager.validateAndFetchVersions();
    const originalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = class {
      constructor() { queueMicrotask(() => this.onopen?.()); }
      close() {}
    };
    mockApiClient.downloadModel.mockResolvedValue({ success: true });
    vi.spyOn(manager, '_reconcileBatchViewAfterDownload').mockResolvedValue(undefined);
    try {
      await manager.executeBatchDownload(manager.batchModels, {
        modelRoot: '/models/loras', targetFolder: '', useDefaultPaths: false,
      });
      expect(mockApiClient.downloadModel.mock.calls.map(call => call[7].id)).toEqual([3301284, 1]);
    } finally {
      globalThis.WebSocket = originalWebSocket;
    }
  });

  it('does not substitute the latest version when a download version is missing', async () => {
    mockApiClient.fetchCivitaiVersions.mockResolvedValue([makeVersion(9999999, 'latest')]);
    document.getElementById('modelUrl').value = url.split('?')[0];
    await manager.validateAndFetchVersions();
    expect(manager.currentVersion).toBeUndefined();
    expect(document.getElementById('urlError').textContent).toBe('modals.download.errors.noVersions');
    expect(document.getElementById('versionStep').style.display).not.toBe('block');
  });

  it('opens the version list for a model page with an unknown version ID', async () => {
    document.getElementById('modelUrl').value = 'https://civitai.com/models/123?modelVersionId=777';
    await manager.validateAndFetchVersions();
    expect(document.getElementById('urlError').textContent).toBe('');
    expect(document.getElementById('versionStep').style.display).toBe('block');
    expect(document.querySelectorAll('.version-item')).toHaveLength(2);
    expect(document.querySelector('.version-item.selected')).toBeNull();
    expect(manager.currentVersion).toBeUndefined();
    expect(mockApiClient.fetchCivitaiModelByVersion).not.toHaveBeenCalled();
  });

  it.each([true, false])('downloads only the missing linked file when existsLocally is %s', async (existsLocally) => {
    requestedVersion.existsLocally = existsLocally;
    requestedVersion.downloadedFiles = [{ fileId: 1 }];
    document.getElementById('modelUrl').value = `${url}\n${url.replace('3301284', '1')}`;
    await manager.validateAndFetchVersions();
    expect(manager.batchModels).toHaveLength(2);
    document.getElementById('modelRoot').value = '/models/loras';
    const execute = vi.spyOn(manager, 'executeBatchDownload').mockResolvedValue(undefined);
    await manager.startDownload();
    expect(execute).toHaveBeenCalledTimes(1);
    const [items] = execute.mock.calls[0];
    expect(items.map(item => item.selectedFile.id)).toEqual([3301284]);
  });

  it('does not preselect a linked file already present in the library', async () => {
    requestedVersion.downloadedFiles = [{ fileId: 3301284 }];
    document.getElementById('modelUrl').value = url;
    await manager.validateAndFetchVersions();
    expect(manager.selectedFile).toBeNull();
    expect(document.querySelector('input[value="3301284"]').disabled).toBe(true);
  });

  it('clears the linked file when another version is selected', async () => {
    document.getElementById('modelUrl').value = url;
    await manager.validateAndFetchVersions();
    manager.selectVersion('9999999');
    expect(manager.selectedFile).toBeNull();
    expect(manager.selectedFiles).toEqual([]);
  });

  it.each([
    'https://civitai.com/api/download/models/3409322?fileId=invalid',
    'https://civitai.com.evil.test/api/download/models/3409322?fileId=3301284',
    'https://example.com/api/download/models/3409322?fileId=3301284',
    'https://civitai.com/api/download/models/3409322invalid?fileId=3301284',
  ])('does not resolve untrusted or malformed download URLs: %s', async (invalidUrl) => {
    document.getElementById('modelUrl').value = invalidUrl;
    await manager.validateAndFetchVersions();
    expect(mockApiClient.fetchCivitaiModelByVersion).not.toHaveBeenCalled();
    expect(mockApiClient.fetchCivitaiVersions).not.toHaveBeenCalled();
  });

  it.each([
    'https://www.civitai.com/api/download/models/3409322?fileId=3301284',
    'https://civitai.red/api/download/models/3409322?fileId=3301284',
    'https://civitai.green/api/download/models/3409322?fileId=3301284',
  ])('resolves download URLs on mirror and www-prefixed hosts: %s', async (mirrorUrl) => {
    document.getElementById('modelUrl').value = mirrorUrl;
    await manager.validateAndFetchVersions();
    expect(mockApiClient.fetchCivitaiModelByVersion).toHaveBeenCalledWith('3409322');
    expect(manager.currentVersion.id).toBe(3409322);
    expect(manager.selectedFile.id).toBe(3301284);
  });

  it('reports a linked fileId that exists but is not a model weight file', async () => {
    requestedVersion.files.push({ id: 555, type: 'Training Data', name: 'dataset.zip' });
    document.getElementById('modelUrl').value = url.replace('3301284', '555');
    await manager.validateAndFetchVersions();
    expect(document.getElementById('urlError').textContent).toBe(
      'File 555 is not a downloadable model file.');
    expect(manager.selectedFile).toBeNull();
  });
});
