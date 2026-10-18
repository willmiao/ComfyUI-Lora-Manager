import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync } from 'fs';
import path from 'path';

const {
  PAGE_CONTROLS_MODULE,
  STATE_MODULE,
  STORAGE_MODULE,
  UI_HELPERS_MODULE,
  EVENT_MANAGER_MODULE,
  UPDATE_CHECK_MODULE,
  SIDEBAR_MODULE,
  SORT_DROPDOWN_MODULE,
  API_FACTORY_MODULE,
  I18N_MODULE,
} = vi.hoisted(() => ({
  PAGE_CONTROLS_MODULE: new URL('../../../../static/js/components/controls/PageControls.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../../static/js/state/index.js', import.meta.url).pathname,
  STORAGE_MODULE: new URL('../../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  EVENT_MANAGER_MODULE: new URL('../../../../static/js/utils/EventManager.js', import.meta.url).pathname,
  UPDATE_CHECK_MODULE: new URL('../../../../static/js/utils/updateCheckHelpers.js', import.meta.url).pathname,
  SIDEBAR_MODULE: new URL('../../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
  SORT_DROPDOWN_MODULE: new URL('../../../../static/js/components/controls/SortDropdown.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
}));

const CONTROLS_TEMPLATE = path.resolve(
  __dirname,
  '../../../../templates/components/controls.html'
);

const showToastMock = vi.fn();
const modelClient = {
  fetchModelRoots: vi.fn(),
  refreshModels: vi.fn(),
};

vi.mock(STATE_MODULE, () => ({
  state: {},
  getCurrentPageState: vi.fn(() => ({ filters: {} })),
  setCurrentPageType: vi.fn(),
}));

vi.mock(STORAGE_MODULE, () => ({
  getStorageItem: vi.fn(),
  setStorageItem: vi.fn(),
  removeStorageItem: vi.fn(),
  getSessionItem: vi.fn(),
  setSessionItem: vi.fn(),
  removeSessionItem: vi.fn(),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
  openCivitaiByMetadata: vi.fn(),
  isTypingContext: vi.fn(() => false),
}));

vi.mock(EVENT_MANAGER_MODULE, () => ({
  eventManager: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}));

vi.mock(UPDATE_CHECK_MODULE, () => ({
  performModelUpdateCheck: vi.fn(),
}));

vi.mock(SIDEBAR_MODULE, () => ({
  sidebarManager: {
    setHostPageControls: vi.fn(),
    initialize: vi.fn(async () => {}),
    refresh: vi.fn(async () => {}),
  },
}));

vi.mock(SORT_DROPDOWN_MODULE, () => ({
  initSortDropdown: vi.fn(),
  applySortToSelect: vi.fn(),
  randomizeSortValue: vi.fn(),
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: () => modelClient,
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key, params, fallback) => {
    if (!fallback) {
      return key;
    }
    return Object.entries(params || {}).reduce(
      (text, [name, value]) => text.replaceAll(`{${name}}`, value),
      fallback
    );
  }),
}));

const { PageControls } = await import(PAGE_CONTROLS_MODULE);

const ROOT_DETAILS = [
  { path: '/mnt/a/loras', label: 'a/loras', reachable: true, models: 12 },
  { path: '/mnt/b/loras', label: 'b/loras', reachable: false, models: 3 },
];

function buildControlsDom() {
  document.body.innerHTML = `
    <div class="dropdown-group">
      <button data-action="refresh" class="dropdown-main"></button>
      <button class="dropdown-toggle"></button>
      <div class="dropdown-menu">
        <div class="dropdown-item" data-action="full-rebuild"></div>
        <div class="dropdown-separator"></div>
        <div class="dropdown-section-title">Scan one folder</div>
        <div id="refreshScopeMenu" class="dropdown-scope-list"></div>
      </div>
    </div>`;
}

function bareControls(api = {}) {
  const controls = Object.create(PageControls.prototype);
  controls.pageType = 'loras';
  controls.api = api;
  controls._scanScopeDetails = null;
  controls._scanScopeLoading = false;
  controls.refreshModels = vi.fn();
  controls.sidebarManager = {
    setHostPageControls: vi.fn(),
    initialize: vi.fn(async () => {}),
  };
  return controls;
}

describe('PageControls refresh scope menu', () => {
  beforeEach(() => {
    showToastMock.mockReset();
    modelClient.fetchModelRoots.mockReset();
    modelClient.refreshModels.mockReset();
    modelClient.fetchModelRoots.mockResolvedValue({ root_details: ROOT_DETAILS });
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('keeps the scope container in the controls template (non-recipes pages)', () => {
    const html = readFileSync(CONTROLS_TEMPLATE, 'utf-8');
    const rebuildIndex = html.indexOf('data-action="full-rebuild"');
    const scopeIndex = html.indexOf('id="refreshScopeMenu"');

    expect(rebuildIndex).toBeGreaterThan(-1);
    // Same dropdown, after the rebuild entry.
    expect(scopeIndex).toBeGreaterThan(rebuildIndex);
    expect(html).toContain('loras.controls.refresh.scopeSection');
    // The recipes page has no model roots, so the section is gated.
    expect(html.slice(rebuildIndex, scopeIndex)).toContain("{% if page_id != 'recipes' %}");
  });

  it('registers the scan-scope API for every page through registerAPI', async () => {
    const controls = bareControls();
    controls.registerAPI({});

    expect(typeof controls.api.fetchModelRoots).toBe('function');
    expect(typeof controls.api.refreshModels).toBe('function');

    await controls.api.fetchModelRoots();
    expect(modelClient.fetchModelRoots).toHaveBeenCalled();

    // The page facades used to drop the second argument, which silently turned
    // a scoped scan into a full refresh.
    await controls.api.refreshModels(false, { roots: ['/mnt/a/loras'] });
    expect(modelClient.refreshModels).toHaveBeenCalledWith(false, { roots: ['/mnt/a/loras'] });
  });

  it('renders the root rows when the dropdown is opened', async () => {
    buildControlsDom();
    const controls = bareControls({
      fetchModelRoots: vi.fn(async () => ({ root_details: ROOT_DETAILS })),
      refreshModels: vi.fn(),
    });

    controls.initDropdowns();
    document.querySelector('.dropdown-toggle').click();

    await vi.waitFor(() => {
      expect(document.querySelectorAll('.scan-root-item').length).toBe(2);
    });
    expect(document.querySelector('.scan-root-item').dataset.root).toBe('/mnt/a/loras');
    expect(document.querySelector('.scan-root-count').textContent).toBe('12 models');
    expect(document.querySelectorAll('.scan-root-item')[1].classList.contains('is-offline')).toBe(true);
  });

  it('scans the clicked root only', async () => {
    buildControlsDom();
    const controls = bareControls({
      fetchModelRoots: vi.fn(async () => ({ root_details: ROOT_DETAILS })),
      refreshModels: vi.fn(),
    });

    controls.initDropdowns();
    document.querySelector('.dropdown-toggle').click();
    await vi.waitFor(() => {
      expect(document.querySelectorAll('.scan-root-item').length).toBe(2);
    });

    document.querySelectorAll('.scan-root-item')[0].click();

    expect(controls.refreshModels).toHaveBeenCalledWith(false, { roots: ['/mnt/a/loras'] });
    expect(showToastMock).not.toHaveBeenCalled();
  });

  it('explains an offline root instead of scanning it', async () => {
    buildControlsDom();
    const controls = bareControls({
      fetchModelRoots: vi.fn(async () => ({ root_details: ROOT_DETAILS })),
      refreshModels: vi.fn(),
    });

    controls.initDropdowns();
    document.querySelector('.dropdown-toggle').click();
    await vi.waitFor(() => {
      expect(document.querySelectorAll('.scan-root-item').length).toBe(2);
    });

    document.querySelectorAll('.scan-root-item')[1].click();

    expect(controls.refreshModels).not.toHaveBeenCalled();
    // Exactly three arguments: key, params, type. A 4th "fallback" argument
    // pushed the sentence into the type slot and rendered an unstyled toast.
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.scanRootUnreachable',
      { scope: 'b/loras' },
      'info'
    );
  });
});
