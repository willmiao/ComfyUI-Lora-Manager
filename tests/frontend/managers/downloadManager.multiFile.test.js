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
} = vi.hoisted(() => ({
  DOWNLOAD_MANAGER_MODULE: new URL('../../../static/js/managers/DownloadManager.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  LOADING_MANAGER_MODULE: new URL('../../../static/js/managers/LoadingManager.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  STORAGE_HELPERS_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  FOLDER_TREE_MANAGER_MODULE: new URL('../../../static/js/components/FolderTreeManager.js', import.meta.url).pathname,
  I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
}));

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: {
    showModal: vi.fn(),
    closeModal: vi.fn(),
  },
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
}));

vi.mock(STATE_MODULE, () => ({
  state: {
    global: {
      settings: {},
    },
  },
}));

vi.mock(LOADING_MANAGER_MODULE, () => ({
  LoadingManager: vi.fn(() => ({
    showSimpleLoading: vi.fn(),
    hide: vi.fn(),
    restoreProgressBar: vi.fn(),
    showDownloadProgress: vi.fn(() => vi.fn()),
    setStatus: vi.fn(),
  })),
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(() => ({
    apiConfig: {
      config: {
        displayName: 'LoRA',
        singularName: 'lora',
      },
    },
  })),
  resetAndReload: vi.fn(),
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

const MULTI_FILE_VERSION = {
  id: 201,
  name: 'Multi-file version',
  images: [],
  files: [
    { id: 1001, type: 'Model', sizeKB: 2048, name: 'file-a.safetensors' },
    { id: 1002, type: 'Model', sizeKB: 2048, name: 'file-b.safetensors' },
  ],
  createdAt: '2026-01-01T00:00:00Z',
};

const SINGLE_FILE_VERSION = {
  id: 202,
  name: 'Single-file version',
  images: [],
  files: [{ id: 1003, type: 'Model', sizeKB: 2048, name: 'file-c.safetensors' }],
  createdAt: '2026-01-01T00:00:00Z',
};

describe('DownloadManager multi-file version badge (#1058)', () => {
  let DownloadManager;

  beforeEach(async () => {
    vi.resetModules();
    document.body.innerHTML = `
      <div id="urlStep"></div>
      <div id="versionStep"></div>
      <div id="versionList"></div>
      <button id="nextFromVersion"></button>
    `;
    ({ DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE));
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('shows the file-select badge for a multi-file version already in library', () => {
    const manager = new DownloadManager();
    manager.versions = [
      {
        ...MULTI_FILE_VERSION,
        existsLocally: true,
        localPath: '/models/loras/file-a.safetensors',
      },
    ];

    manager.showVersionStep();

    const badge = document.querySelector('.file-select-badge');
    expect(badge).not.toBeNull();
    expect(badge.dataset.versionId).toBe('201');
    expect(badge.textContent).toContain('2');
    // The in-library badge is still shown alongside
    expect(document.querySelector('.local-badge')).not.toBeNull();
  });

  it('still shows the file-select badge for a multi-file version not in library', () => {
    const manager = new DownloadManager();
    manager.versions = [{ ...MULTI_FILE_VERSION, existsLocally: false }];

    manager.showVersionStep();

    const badge = document.querySelector('.file-select-badge');
    expect(badge).not.toBeNull();
    expect(badge.dataset.versionId).toBe('201');
  });

  it('does not show the file-select badge for a single-file version in library', () => {
    const manager = new DownloadManager();
    manager.versions = [
      {
        ...SINGLE_FILE_VERSION,
        existsLocally: true,
        localPath: '/models/loras/file-c.safetensors',
      },
    ];

    manager.showVersionStep();

    expect(document.querySelector('.file-select-badge')).toBeNull();
  });
});
