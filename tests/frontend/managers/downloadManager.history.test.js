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

describe('DownloadManager version history badges', () => {
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

  it('shows downloaded badge only for versions missing locally', () => {
    const manager = new DownloadManager();
    manager.versions = [
      {
        id: 101,
        name: 'History only',
        images: [],
        files: [{ sizeKB: 2048 }],
        createdAt: '2026-01-01T00:00:00Z',
        existsLocally: false,
        hasBeenDownloaded: true,
      },
      {
        id: 102,
        name: 'Still local',
        images: [],
        files: [{ sizeKB: 2048 }],
        createdAt: '2026-01-01T00:00:00Z',
        existsLocally: true,
        hasBeenDownloaded: true,
        localPath: '/models/still-local.safetensors',
      },
    ];

    manager.showVersionStep();

    const items = document.querySelectorAll('.version-item');
    expect(items).toHaveLength(2);

    expect(items[0].querySelector('.downloaded-badge')?.textContent).toContain('Downloaded');
    expect(items[0].querySelector('.downloaded-badge')?.getAttribute('title')).toContain(
      'Previously downloaded, but it is not currently in your library.'
    );
    expect(items[0].querySelector('.local-badge')).toBeNull();

    expect(items[1].querySelector('.local-badge')).not.toBeNull();
    expect(items[1].querySelector('.local-path')?.textContent).toContain('/models/still-local.safetensors');
    expect(items[1].querySelector('.downloaded-badge')).toBeNull();
  });
});
