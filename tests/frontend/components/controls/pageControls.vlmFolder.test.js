import { describe, it, expect, vi, beforeEach } from 'vitest';

const {
  PAGE_CONTROLS_MODULE,
  STATE_MODULE,
  UI_HELPERS_MODULE,
  UPDATE_CHECK_MODULE,
  SIDEBAR_MODULE,
  API_FACTORY_MODULE,
  SORT_DROPDOWN_MODULE,
  MODEL_TYPE_DROPDOWN_MODULE,
  SCAN_SCOPE_MENU_MODULE,
  ACTION_SHORTCUTS_MODULE,
  STORAGE_MODULE,
  stateMock,
  sidebarManagerMock,
} = vi.hoisted(() => {
  const sidebar = {
    setHostPageControls: vi.fn(),
    initialize: vi.fn(async () => {}),
    refresh: vi.fn(async () => {}),
    applyFolderSelection: vi.fn(),
  };
  return {
    PAGE_CONTROLS_MODULE: new URL('../../../../static/js/components/controls/PageControls.js', import.meta.url).pathname,
    STATE_MODULE: new URL('../../../../static/js/state/index.js', import.meta.url).pathname,
    UI_HELPERS_MODULE: new URL('../../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
    UPDATE_CHECK_MODULE: new URL('../../../../static/js/utils/updateCheckHelpers.js', import.meta.url).pathname,
    SIDEBAR_MODULE: new URL('../../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
    API_FACTORY_MODULE: new URL('../../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
    SORT_DROPDOWN_MODULE: new URL('../../../../static/js/components/controls/SortDropdown.js', import.meta.url).pathname,
    MODEL_TYPE_DROPDOWN_MODULE: new URL('../../../../static/js/components/controls/ModelTypeDropdown.js', import.meta.url).pathname,
    SCAN_SCOPE_MENU_MODULE: new URL('../../../../static/js/components/controls/ScanScopeMenu.js', import.meta.url).pathname,
    ACTION_SHORTCUTS_MODULE: new URL('../../../../static/js/components/controls/ActionShortcuts.js', import.meta.url).pathname,
    STORAGE_MODULE: new URL('../../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
    stateMock: { global: { settings: { group_by_model: false } } },
    sidebarManagerMock: sidebar,
  };
});

vi.mock(STATE_MODULE, () => ({
  state: stateMock,
  getCurrentPageState: vi.fn(() => ({ filters: {} })),
  setCurrentPageType: vi.fn(),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
  openCivitaiByMetadata: vi.fn(),
}));

vi.mock(UPDATE_CHECK_MODULE, () => ({
  performModelUpdateCheck: vi.fn(),
}));

vi.mock(SIDEBAR_MODULE, () => ({ sidebarManager: sidebarManagerMock }));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(),
  resetAndReload: vi.fn(),
}));

vi.mock(SORT_DROPDOWN_MODULE, () => ({
  initSortDropdown: vi.fn(),
  applySortToSelect: vi.fn(),
  randomizeSortValue: vi.fn(),
}));

vi.mock(MODEL_TYPE_DROPDOWN_MODULE, () => ({
  initModelTypeDropdown: vi.fn(),
}));

vi.mock(SCAN_SCOPE_MENU_MODULE, () => ({
  renderScanScopeMenu: vi.fn(),
  resolveScanScopeTarget: vi.fn(),
}));

vi.mock(ACTION_SHORTCUTS_MODULE, () => ({
  handleActionShortcut: vi.fn(),
  registerActionShortcuts: vi.fn(),
}));

const { PageControls } = await import(PAGE_CONTROLS_MODULE);
const { getStorageItem, setStorageItem, getSessionItem, setSessionItem } = await import(STORAGE_MODULE);

function renderDom() {
  document.body.innerHTML = `
    <div id="customFilterIndicator" class="hidden">
      <span class="customFilterText"></span>
      <i class="clear-filter"></i>
    </div>
    <select id="sortSelect">
      <option value="name:asc">Name</option>
    </select>
  `;
}

function makeControls({ activeFolder = 'Styles', sortBy = 'name:asc' } = {}) {
  const controls = Object.create(PageControls.prototype);
  controls.pageType = 'loras';
  controls.pageState = {
    activeFolder,
    sortBy,
    viewMode: 'active',
    filters: { search: '' },
    searchOptions: {
      filename: true,
      modelname: true,
      tags: false,
      creator: false,
      recursive: true,
    },
    excludedViewState: { sortBy: 'name:asc', search: '' },
  };
  controls.sidebarManager = sidebarManagerMock;
  controls.api = { resetAndReload: vi.fn(async () => {}) };
  controls.resetAndReload = vi.fn(async () => {});
  return controls;
}

function activateVlmSession(overrides = {}) {
  setSessionItem('vlm_model_id', '1234');
  setSessionItem('vlm_model_name', 'Pose Pack');
  setSessionItem('vlm_page_type', 'loras');
  Object.entries(overrides).forEach(([key, value]) => setSessionItem(key, value));
}

describe('PageControls View Local Versions folder scope', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    renderDom();
  });

  it('suspends the browsing folder when the view starts', () => {
    const controls = makeControls({ activeFolder: 'Styles' });

    controls.triggerVlmView(1234, 'Pose Pack', undefined, 'loras');

    expect(controls.pageState.activeFolder).toBeNull();
    expect(getStorageItem('loras_activeFolder')).toBeNull();
    expect(sidebarManagerMock.applyFolderSelection).toHaveBeenCalledWith(null);
    // The folder is remembered so clearing the filter can put the user back
    expect(getSessionItem('vlm_prev_folder_loras')).toEqual({ folder: 'Styles' });
    expect(getSessionItem('vlm_model_id')).toBeTruthy();
  });

  it('keeps the folder captured at entry when the page re-checks the filter', () => {
    activateVlmSession({ vlm_prev_folder_loras: { folder: 'Styles' } });
    const controls = makeControls({ activeFolder: null });

    controls.checkVlmFilter();

    // Refreshing while the filter is active must not overwrite the origin
    // folder with the already-cleared one.
    expect(getSessionItem('vlm_prev_folder_loras')).toEqual({ folder: 'Styles' });
    expect(controls.pageState.activeFolder).toBeNull();
  });

  it('restores the suspended folder when the filter is cleared', async () => {
    activateVlmSession({
      vlm_prev_sort: 'name:asc',
      vlm_prev_folder_loras: { folder: 'Styles' },
    });
    setStorageItem('loras_activeFolder', null);
    const controls = makeControls({ activeFolder: null });

    await controls.clearCustomFilter();

    expect(controls.pageState.activeFolder).toBe('Styles');
    expect(getStorageItem('loras_activeFolder')).toBe('Styles');
    expect(sidebarManagerMock.applyFolderSelection).toHaveBeenLastCalledWith('Styles');
    expect(getSessionItem('vlm_model_id')).toBeNull();
    expect(getSessionItem('vlm_prev_folder_loras')).toBeNull();
    expect(controls.resetAndReload).toHaveBeenCalledWith(true);
  });

  it('hands a suspended folder back to the page that owns it', () => {
    activateVlmSession({
      vlm_page_type: 'checkpoints',
      vlm_prev_folder_checkpoints: { folder: 'SDXL' },
    });
    const controls = makeControls({ activeFolder: 'Styles' });

    controls.checkVlmFilter();

    expect(getStorageItem('checkpoints_activeFolder')).toBe('SDXL');
    expect(getSessionItem('vlm_prev_folder_checkpoints')).toBeNull();
    expect(getSessionItem('vlm_model_id')).toBeNull();
    // The page being viewed keeps its own folder
    expect(controls.pageState.activeFolder).toBe('Styles');
    expect(getStorageItem('loras_activeFolder')).toBeNull();
    expect(controls.isVlmActive()).toBe(false);
  });

  it('drops the suspended folder when the user picks a folder instead', () => {
    activateVlmSession({
      vlm_prev_sort: 'date:desc',
      vlm_prev_folder_loras: { folder: 'Styles' },
    });
    const controls = makeControls({ activeFolder: null });

    controls.exitVlmForNavigation();

    expect(getSessionItem('vlm_model_id')).toBeNull();
    expect(getSessionItem('vlm_prev_folder_loras')).toBeNull();
    // No restore: the navigation decides the folder that applies next
    expect(controls.pageState.activeFolder).toBeNull();
    expect(getStorageItem('loras_activeFolder')).toBeNull();
  });
});
