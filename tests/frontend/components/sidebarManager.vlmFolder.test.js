import { describe, it, expect, vi } from 'vitest';

const {
  SIDEBAR_MANAGER_MODULE,
  STORAGE_HELPERS_MODULE,
  MODEL_API_FACTORY_MODULE,
  I18N_MODULE,
  BULK_MANAGER_MODULE,
  UI_HELPERS_MODULE,
  UPDATE_CHECK_MODULE,
} = vi.hoisted(() => ({
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
  STORAGE_HELPERS_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  MODEL_API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  BULK_MANAGER_MODULE: new URL('../../../static/js/managers/BulkManager.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  UPDATE_CHECK_MODULE: new URL('../../../static/js/utils/updateCheckHelpers.js', import.meta.url).pathname,
}));

vi.mock(MODEL_API_FACTORY_MODULE, () => ({ getModelApiClient: vi.fn() }));
vi.mock(I18N_MODULE, () => ({ translate: (key, _args, fallback) => fallback || key }));
vi.mock(BULK_MANAGER_MODULE, () => ({ bulkManager: {} }));
vi.mock(UI_HELPERS_MODULE, () => ({ showToast: vi.fn(), showActionToast: vi.fn() }));
vi.mock(UPDATE_CHECK_MODULE, () => ({ performFolderUpdateCheck: vi.fn() }));

const { SidebarManager } = await import(SIDEBAR_MANAGER_MODULE);
const { setStorageItem, getStorageItem } = await import(STORAGE_HELPERS_MODULE);

function createManager({ isVlmActive = false, isInitialized = true } = {}) {
  const manager = new SidebarManager();
  manager.pageType = 'loras';
  manager.selectedPath = 'Styles';
  manager.treeData = {};
  manager.displayMode = 'tree';
  manager.isInitialized = isInitialized;
  manager.updateTreeSelection = vi.fn();
  manager.updateBreadcrumbs = vi.fn();
  manager.updateSidebarHeader = vi.fn();

  const resetAndReload = vi.fn(async () => {});
  manager.pageControls = {
    pageState: { activeFolder: 'Styles' },
    isVlmActive: vi.fn(() => isVlmActive),
    exitVlmForNavigation: vi.fn(),
    resetAndReload,
  };

  setStorageItem('loras_activeFolder', 'Styles');
  return { manager, resetAndReload };
}

describe('SidebarManager View Local Versions folder handoff', () => {
  it('leaves View Local Versions before applying a picked folder', async () => {
    const { manager, resetAndReload } = createManager({ isVlmActive: true });

    await manager.selectFolder('Pets');

    // VLM is library-wide: picking a folder must end it, not be ignored
    expect(manager.pageControls.exitVlmForNavigation).toHaveBeenCalledTimes(1);
    expect(manager.pageControls.pageState.activeFolder).toBe('Pets');
    expect(manager.selectedPath).toBe('Pets');
    expect(getStorageItem('loras_activeFolder')).toBe('Pets');
    expect(resetAndReload).toHaveBeenCalledTimes(1);
  });

  it('leaves the View Local Versions state alone when it is inactive', async () => {
    const { manager } = createManager({ isVlmActive: false });

    await manager.selectFolder('Pets');

    expect(manager.pageControls.exitVlmForNavigation).not.toHaveBeenCalled();
  });

  it('follows a folder chosen outside the sidebar without reloading', () => {
    const { manager, resetAndReload } = createManager();

    manager.applyFolderSelection(null);

    expect(manager.selectedPath).toBe('');
    expect(manager.updateTreeSelection).toHaveBeenCalled();
    expect(manager.updateBreadcrumbs).toHaveBeenCalled();
    expect(manager.updateSidebarHeader).toHaveBeenCalled();
    expect(resetAndReload).not.toHaveBeenCalled();
    // The sidebar only mirrors the selection; PageControls owns persistence
    expect(getStorageItem('loras_activeFolder')).toBe('Styles');
  });

  it('selects a restored folder', () => {
    const { manager } = createManager();
    manager.selectedPath = '';

    manager.applyFolderSelection('Styles');

    expect(manager.selectedPath).toBe('Styles');
  });

  it('only records the selection before the sidebar is initialized', () => {
    const { manager } = createManager({ isInitialized: false });

    // initialize() restores the persisted selection itself; painting now would
    // touch a tree without data (and updateBreadcrumbs without an API client)
    manager.applyFolderSelection(null);

    expect(manager.selectedPath).toBe('');
    expect(manager.updateTreeSelection).not.toHaveBeenCalled();
    expect(manager.updateBreadcrumbs).not.toHaveBeenCalled();
  });
});
