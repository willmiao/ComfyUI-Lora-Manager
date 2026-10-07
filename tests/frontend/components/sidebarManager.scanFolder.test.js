import { describe, it, beforeEach, expect, vi } from 'vitest';

const {
  SIDEBAR_MANAGER_MODULE,
  STORAGE_HELPERS_MODULE,
  MODEL_API_FACTORY_MODULE,
  I18N_MODULE,
  BULK_MANAGER_MODULE,
  UI_HELPERS_MODULE,
  UPDATE_CHECK_MODULE,
  STATE_MODULE,
  MODAL_MANAGER_MODULE,
} = vi.hoisted(() => ({
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
  STORAGE_HELPERS_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  MODEL_API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  BULK_MANAGER_MODULE: new URL('../../../static/js/managers/BulkManager.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  UPDATE_CHECK_MODULE: new URL('../../../static/js/utils/updateCheckHelpers.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
}));

vi.mock(MODEL_API_FACTORY_MODULE, () => ({ getModelApiClient: vi.fn() }));
vi.mock(I18N_MODULE, () => ({ translate: (key, _args, fallback) => fallback || key }));
vi.mock(BULK_MANAGER_MODULE, () => ({ bulkManager: {} }));
vi.mock(UI_HELPERS_MODULE, () => ({ showToast: vi.fn(), showActionToast: vi.fn() }));
vi.mock(UPDATE_CHECK_MODULE, () => ({ performFolderUpdateCheck: vi.fn() }));
vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));

const { SidebarManager } = await import(SIDEBAR_MANAGER_MODULE);
const { showToast } = await import(UI_HELPERS_MODULE);

function createApiClient(overrides = {}) {
  return {
    apiConfig: {
      config: {
        displayName: 'LoRA',
        singularName: 'lora',
        supportsMove: true,
        supportsFolderManagement: true,
      },
    },
    fetchModelRoots: vi.fn().mockResolvedValue({ roots: ['/models/loras', '/mnt/usb/loras'] }),
    resolveFolder: vi.fn().mockResolvedValue({
      success: true,
      folder: 'pack',
      candidates: [
        { folder_path: '/models/loras/pack', root: '/models/loras', is_symlink: false },
        { folder_path: '/mnt/usb/loras/pack', root: '/mnt/usb/loras', is_symlink: false },
      ],
    }),
    ...overrides,
  };
}

function createManager(apiClient) {
  const manager = new SidebarManager();
  manager.pageType = 'loras';
  manager.apiClient = apiClient;
  manager.renderFolderDisplay = vi.fn();
  manager.renderEmptyState = vi.fn();
  return manager;
}

describe('SidebarManager folder scan', () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = '';
    showToast.mockClear();
  });

  it('scans the relative folder instead of guessing a root', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    const refreshModels = vi.fn().mockResolvedValue(undefined);
    manager.pageControls = { refreshModels };

    await manager.scanFolder('pack');

    // The backend walks this relative path under every root that holds it, so
    // the request carries no root at all.
    expect(refreshModels).toHaveBeenCalledWith(false, { folder: 'pack' });
    expect(showToast).not.toHaveBeenCalled();
  });

  it('falls back to the registered page controls after a re-init', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.pageControls = null;
    manager.lastPageControls = { refreshModels: vi.fn().mockResolvedValue(undefined) };

    await manager.scanFolder('pack');

    expect(manager.lastPageControls.refreshModels).toHaveBeenCalledWith(false, { folder: 'pack' });
  });

  it('explains a folder that no root holds any more', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({ success: true, folder: 'gone', candidates: [] }),
    });
    const manager = createManager(apiClient);
    const refreshModels = vi.fn();
    manager.pageControls = { refreshModels };

    await manager.scanFolder('gone');

    expect(refreshModels).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith('sidebar.scanFolderResult.missing', {}, 'warning');
  });

  it('reports a failed resolution without scanning', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockRejectedValue(new Error('offline')),
      fetchModelRoots: vi.fn().mockResolvedValue({ roots: ['/models/loras', '/mnt/usb/loras'] }),
    });
    const manager = createManager(apiClient);
    const refreshModels = vi.fn();
    manager.pageControls = { refreshModels };

    await manager.scanFolder('pack');

    // Multi-root + no resolver: guessing a root is exactly what the folder
    // operations refuse to do, and a scan must not guess either.
    expect(refreshModels).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith('sidebar.scanFolderResult.missing', {}, 'warning');
  });

  it('does nothing when no page controls are registered', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.pageControls = null;
    manager.lastPageControls = null;

    await manager.scanFolder('pack');

    expect(showToast).not.toHaveBeenCalled();
  });
});
