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
const { setStorageItem } = await import(STORAGE_HELPERS_MODULE);

function createManager(pageType) {
  const manager = new SidebarManager();
  manager.pageType = pageType;
  manager.pageControls = { pageState: { searchOptions: {} } };
  return manager;
}

describe('SidebarManager default visibility', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('hides the folder sidebar by default on the other page', () => {
    const manager = createManager('other');

    manager.restoreSidebarState();

    expect(manager.isDisabledByPage).toBe(true);
  });

  it('keeps the folder sidebar visible by default on the primary pages', () => {
    for (const pageType of ['loras', 'checkpoints', 'embeddings', 'recipes']) {
      const manager = createManager(pageType);

      manager.restoreSidebarState();

      expect(manager.isDisabledByPage, pageType).toBe(false);
    }
  });

  it('lets an explicit stored preference override the other-page default', () => {
    setStorageItem('other_sidebarDisabled', false);
    const shown = createManager('other');
    shown.restoreSidebarState();
    expect(shown.isDisabledByPage).toBe(false);

    setStorageItem('other_sidebarDisabled', true);
    const hidden = createManager('other');
    hidden.restoreSidebarState();
    expect(hidden.isDisabledByPage).toBe(true);
  });
});
