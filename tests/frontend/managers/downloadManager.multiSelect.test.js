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
    modelType: 'loras',
    apiConfig: {
      config: {
        displayName: 'LoRA',
        singularName: 'lora',
      },
    },
    fetchCivitaiVersions: vi.fn(),
    fetchModelRoots: vi.fn(async () => ({ roots: ['/models/loras'] })),
    fetchUnifiedFolderTree: vi.fn(async () => ({ success: false })),
    downloadModel: vi.fn(),
    cancelDownload: vi.fn(),
    getPageState: vi.fn(() => ({})),
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
  translate: vi.fn((_, __, fallback) => fallback ?? ''),
}));

vi.mock(SUMMARY_MODULE, () => ({
  showDownloadBatchSummary: showDownloadBatchSummaryMock,
}));

/** DOM covering the file-selection, version and location steps. */
function setupDownloadDom() {
  document.body.innerHTML = `
    <div id="downloadModal">
      <div class="download-step" id="urlStep"></div>
      <div class="download-step" id="versionStep"></div>
      <div class="download-step" id="fileSelectionStep"></div>
      <div class="download-step" id="downloadLocationStep"></div>
      <div id="fileSelectionList"></div>
      <div id="fileSelectionVersionName"></div>
      <button id="nextFromVersion"></button>
      <div id="downloadModalTitle"></div>
      <select id="modelRoot"></select>
      <input id="folderPath" />
      <div id="targetPathDisplay"></div>
      <input id="useDefaultPath" type="checkbox" />
      <div id="manualPathSelection"></div>
    </div>
  `;
}

function makeMultiFileVersion(overrides = {}) {
  return {
    id: 201,
    name: 'Multi-file version',
    baseModel: 'SDXL',
    images: [],
    files: [
      { id: 1001, type: 'Model', sizeKB: 2048, name: 'file-a.safetensors' },
      { id: 1002, type: 'Model', sizeKB: 2048, name: 'file-b.safetensors' },
      { id: 1003, type: 'Model', sizeKB: 2048, name: 'file-c.safetensors' },
    ],
    createdAt: '2026-01-01T00:00:00Z',
    existsLocally: true,
    ...overrides,
  };
}

function getFileOption(fileId) {
  return document.querySelector(`.file-option[data-file-id="${fileId}"]`);
}

describe('DownloadManager multi-select file dialog (#1058)', () => {
  let DownloadManager;

  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();
    setupDownloadDom();
    ({ DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE));
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders downloaded files disabled with an In Library tag', () => {
    const manager = new DownloadManager();
    manager.versions = [makeMultiFileVersion({
      downloadedFiles: [
        { fileId: 1001, fileName: 'file-a.safetensors', filePath: '/models/loras/file-a.safetensors' },
      ],
    })];

    manager.showFileSelectionStep('201');

    const downloadedOption = getFileOption('1001');
    expect(downloadedOption.classList.contains('disabled')).toBe(true);
    expect(downloadedOption.querySelector('input[type="checkbox"]').disabled).toBe(true);
    expect(downloadedOption.querySelector('.file-tag.in-library').textContent).toBe('In Library');

    // Remaining files stay selectable
    const otherOption = getFileOption('1002');
    expect(otherOption.classList.contains('disabled')).toBe(false);
    expect(otherOption.querySelector('input[type="checkbox"]').disabled).toBe(false);
  });

  it('ignores clicks on already-downloaded options', () => {
    const manager = new DownloadManager();
    manager.versions = [makeMultiFileVersion({
      downloadedFiles: [
        { fileId: 1001, fileName: 'file-a.safetensors', filePath: '/models/loras/file-a.safetensors' },
      ],
    })];

    manager.showFileSelectionStep('201');

    getFileOption('1001').click();

    expect(getFileOption('1001').querySelector('input[type="checkbox"]').checked).toBe(false);
    expect(manager.selectedFiles).toHaveLength(0);
  });

  it('confirmFileSelection collects multiple checked files into selectedFiles', () => {
    const manager = new DownloadManager();
    manager.apiClient = mockApiClient;
    manager.versions = [makeMultiFileVersion({ downloadedFiles: [] })];

    manager.showFileSelectionStep('201');

    getFileOption('1001').click();
    getFileOption('1003').click();

    manager.confirmFileSelection();

    expect(manager.selectedFiles.map(f => f.id)).toEqual([1001, 1003]);
    // selectedFile stays the first selected file for single-file flows
    expect(manager.selectedFile?.id).toBe(1001);
    expect(document.getElementById('fileSelectionStep').style.display).toBe('none');
    expect(document.getElementById('downloadLocationStep').style.display).toBe('block');
  });

  it('confirmFileSelection warns when nothing is selected', () => {
    const manager = new DownloadManager();
    manager.versions = [makeMultiFileVersion({ downloadedFiles: [] })];

    manager.showFileSelectionStep('201');
    manager.confirmFileSelection();

    expect(showToastMock).toHaveBeenCalledWith('toast.loras.pleaseSelectFile', {}, 'error');
    expect(manager.selectedFiles).toHaveLength(0);
    expect(document.getElementById('downloadLocationStep').style.display).not.toBe('block');
  });

  it('disables the other routing group once a file is checked and re-enables when unchecked', () => {
    const manager = new DownloadManager();
    manager.versions = [makeMultiFileVersion({
      downloadedFiles: [],
      files: [
        { id: 1001, type: 'UNet', sizeKB: 2048, name: 'unet-a.safetensors' },
        { id: 1002, type: 'Model', sizeKB: 2048, name: 'file-b.safetensors' },
        { id: 1003, type: 'Model', sizeKB: 2048, name: 'file-c.safetensors' },
      ],
    })];

    manager.showFileSelectionStep('201');

    // Checking a regular Model file disables the UNet option
    getFileOption('1002').click();
    expect(getFileOption('1001').classList.contains('group-disabled')).toBe(true);
    expect(getFileOption('1001').querySelector('input[type="checkbox"]').disabled).toBe(true);
    expect(getFileOption('1003').classList.contains('group-disabled')).toBe(false);

    // Clicking a group-disabled option does nothing
    getFileOption('1001').click();
    expect(manager.selectedFiles.map(f => f.id)).toEqual([1002]);

    // Unchecking everything re-enables the other group
    getFileOption('1002').click();
    expect(manager.selectedFiles).toHaveLength(0);
    expect(getFileOption('1001').classList.contains('group-disabled')).toBe(false);
    expect(getFileOption('1001').querySelector('input[type="checkbox"]').disabled).toBe(false);
  });

  it('keeps Next enabled for a partially downloaded multi-file version', () => {
    const manager = new DownloadManager();
    manager.currentVersion = makeMultiFileVersion({
      downloadedFiles: [
        { fileId: 1001, fileName: 'file-a.safetensors', filePath: '/models/loras/file-a.safetensors' },
      ],
    });

    manager.updateNextButtonState();

    const nextButton = document.getElementById('nextFromVersion');
    expect(nextButton.disabled).toBe(false);
    expect(nextButton.classList.contains('disabled')).toBe(false);
  });

  it('disables Next when every weight file is already downloaded', () => {
    const manager = new DownloadManager();
    manager.currentVersion = makeMultiFileVersion({
      downloadedFiles: [
        { fileId: 1001, fileName: 'file-a.safetensors', filePath: '/models/loras/file-a.safetensors' },
        { fileId: 1002, fileName: 'file-b.safetensors', filePath: '/models/loras/file-b.safetensors' },
        { fileId: 1003, fileName: 'file-c.safetensors', filePath: '/models/loras/file-c.safetensors' },
      ],
    });

    manager.updateNextButtonState();

    const nextButton = document.getElementById('nextFromVersion');
    expect(nextButton.disabled).toBe(true);
    expect(nextButton.classList.contains('disabled')).toBe(true);
  });

  it('disables Next for an in-library single-file version', () => {
    const manager = new DownloadManager();
    manager.currentVersion = {
      id: 202,
      name: 'Single-file version',
      files: [{ id: 1004, type: 'Model', sizeKB: 2048, name: 'file-d.safetensors' }],
      existsLocally: true,
      downloadedFiles: [],
    };

    manager.updateNextButtonState();

    const nextButton = document.getElementById('nextFromVersion');
    expect(nextButton.disabled).toBe(true);
  });

  it('hides every other step (including the URL step) when the file dialog shows', () => {
    // Regression: entering via openFileSelectionForVersion (ModelVersionsTab)
    // left the URL step visible alongside the file selection step (#1058).
    const manager = new DownloadManager();
    manager.versions = [makeMultiFileVersion()];
    document.getElementById('urlStep').style.display = 'block';
    document.getElementById('versionStep').style.display = 'block';

    manager.showFileSelectionStep('201');

    expect(document.getElementById('urlStep').style.display).toBe('none');
    expect(document.getElementById('versionStep').style.display).toBe('none');
    expect(document.getElementById('fileSelectionStep').style.display).toBe('block');
  });
});
