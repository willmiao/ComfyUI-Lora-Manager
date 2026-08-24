import { describe, it, beforeEach, expect, vi } from 'vitest';

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
vi.mock(UI_HELPERS_MODULE, () => ({ showToast: vi.fn() }));
vi.mock(UPDATE_CHECK_MODULE, () => ({ performFolderUpdateCheck: vi.fn() }));

const { SidebarManager } = await import(SIDEBAR_MANAGER_MODULE);
const { setStorageItem, getStorageItem } = await import(STORAGE_HELPERS_MODULE);

function createManager({
  treeData = {},
  foldersList = [],
  displayMode = 'tree',
  folderTreeLoaded = true,
  isInitialized = true,
  persistedFolder = 'Civitai/_Missing',
} = {}) {
  const manager = new SidebarManager();
  manager.pageType = 'recipes';
  manager.displayMode = displayMode;
  manager.treeData = treeData;
  manager.foldersList = foldersList;
  manager.folderTreeLoaded = folderTreeLoaded;
  manager.isInitialized = isInitialized;
  manager.updateTreeSelection = vi.fn();
  manager.updateBreadcrumbs = vi.fn();
  manager.updateSidebarHeader = vi.fn();

  const resetAndReload = vi.fn().mockResolvedValue(undefined);
  manager.pageControls = {
    pageState: { activeFolder: persistedFolder },
    resetAndReload,
  };

  if (persistedFolder !== null) {
    setStorageItem('recipes_activeFolder', persistedFolder);
  }

  return { manager, resetAndReload };
}

describe('SidebarManager.restoreSelectedFolder', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('falls back to root and reloads when the persisted folder is missing', () => {
    const { manager, resetAndReload } = createManager({
      treeData: { Civitai: {} },
    });

    manager.restoreSelectedFolder();

    expect(manager.selectedPath).toBe('');
    expect(manager.pageControls.pageState.activeFolder).toBe('');
    expect(getStorageItem('recipes_activeFolder')).toBe('');
    expect(resetAndReload).toHaveBeenCalledTimes(1);
  });

  it('keeps the persisted folder when it exists in the tree', () => {
    const { manager, resetAndReload } = createManager({
      treeData: { Civitai: { _Missing: {} } },
    });

    manager.restoreSelectedFolder();

    expect(manager.selectedPath).toBe('Civitai/_Missing');
    expect(manager.pageControls.pageState.activeFolder).toBe('Civitai/_Missing');
    expect(resetAndReload).not.toHaveBeenCalled();
  });

  it('resets without reloading during initial initialization', () => {
    const { manager, resetAndReload } = createManager({
      treeData: { Civitai: {} },
      isInitialized: false,
    });

    manager.restoreSelectedFolder();

    expect(manager.selectedPath).toBe('');
    expect(resetAndReload).not.toHaveBeenCalled();
  });

  it('keeps the persisted folder when the tree failed to load', () => {
    const { manager, resetAndReload } = createManager({
      treeData: {},
      folderTreeLoaded: false,
    });

    manager.restoreSelectedFolder();

    expect(manager.selectedPath).toBe('Civitai/_Missing');
    expect(resetAndReload).not.toHaveBeenCalled();
  });

  it('validates against the folder list in list display mode', () => {
    const { manager, resetAndReload } = createManager({
      displayMode: 'list',
      foldersList: ['Civitai'],
    });

    manager.restoreSelectedFolder();

    expect(manager.selectedPath).toBe('');
    expect(resetAndReload).toHaveBeenCalledTimes(1);
  });
});
