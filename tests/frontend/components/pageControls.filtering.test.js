import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const loadMoreWithVirtualScrollMock = vi.fn();
const refreshModelsMock = vi.fn();
const fetchCivitaiMetadataMock = vi.fn();
const resetAndReloadMock = vi.fn();
const getModelApiClientMock = vi.fn();
const apiClientMock = {
  loadMoreWithVirtualScroll: loadMoreWithVirtualScrollMock,
  refreshModels: refreshModelsMock,
  fetchCivitaiMetadata: fetchCivitaiMetadataMock,
};

const showToastMock = vi.fn();
const updatePanelPositionsMock = vi.fn();
const downloadManagerMock = {
  showDownloadModal: vi.fn(),
};

const sidebarManagerMock = {
  initialize: vi.fn(async () => {
    sidebarManagerMock.isInitialized = true;
  }),
  refresh: vi.fn(async () => {}),
  cleanup: vi.fn(),
  isInitialized: false,
};

const createAlphabetBarMock = vi.fn(() => ({ destroy: vi.fn() }));

const performModelUpdateCheckMock = vi.fn();

getModelApiClientMock.mockReturnValue(apiClientMock);

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: getModelApiClientMock,
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  updatePanelPositions: updatePanelPositionsMock,
}));

vi.mock('../../../static/js/managers/DownloadManager.js', () => ({
  downloadManager: downloadManagerMock,
}));

vi.mock('../../../static/js/components/SidebarManager.js', () => ({
  sidebarManager: sidebarManagerMock,
}));

vi.mock('../../../static/js/components/alphabet/index.js', () => ({
  createAlphabetBar: createAlphabetBarMock,
}));

vi.mock('../../../static/js/utils/updateCheckHelpers.js', () => ({
  performModelUpdateCheck: performModelUpdateCheckMock,
}));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();

  loadMoreWithVirtualScrollMock.mockResolvedValue(undefined);
  refreshModelsMock.mockResolvedValue(undefined);
  fetchCivitaiMetadataMock.mockResolvedValue(undefined);
  resetAndReloadMock.mockResolvedValue(undefined);
  getModelApiClientMock.mockReturnValue(apiClientMock);
  performModelUpdateCheckMock.mockResolvedValue({ status: 'success', displayName: 'LoRA', records: [] });

  sidebarManagerMock.isInitialized = false;
  sidebarManagerMock.initialize.mockImplementation(async () => {
    sidebarManagerMock.isInitialized = true;
  });

  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ success: true, base_models: [] }),
  });
});

afterEach(() => {
  delete window.modelDuplicatesManager;
  delete global.fetch;
  vi.useRealTimers();
});

function renderControlsDom(pageKey) {
  document.body.dataset.page = pageKey;
  document.body.innerHTML = `
    <div class="header-search">
      <div class="search-container">
        <input id="searchInput" />
        <i class="fas fa-search search-icon"></i>
        <button id="searchOptionsToggle" class="search-options-toggle"></button>
        <button id="filterButton" class="search-filter-toggle">
          <span id="activeFiltersCount" class="filter-badge" style="display: none">0</span>
        </button>
      </div>
    </div>
    <div id="searchOptionsPanel" class="search-options-panel hidden">
      <button id="closeSearchOptions"></button>
      <div class="search-option-tag active" data-option="filename"></div>
    </div>
    <div id="filterPanel" class="filter-panel hidden">
      <div id="baseModelTags" class="filter-tags"></div>
      <div id="modelTagsFilter" class="filter-tags"></div>
      <button class="clear-filter"></button>
    </div>
    <div class="controls">
      <div class="actions">
        <div class="action-buttons">
          <div class="control-group">
            <select id="sortSelect">
              <option value="name:asc">Name Asc</option>
              <option value="name:desc">Name Desc</option>
              <option value="date:desc">Date Desc</option>
              <option value="date:asc">Date Asc</option>
            </select>
          </div>
          <div class="control-group dropdown-group">
            <button data-action="refresh" class="dropdown-main"></button>
            <button class="dropdown-toggle"></button>
            <div class="dropdown-menu">
              <div class="dropdown-item" data-action="quick-refresh"></div>
              <div class="dropdown-item" data-action="full-rebuild"></div>
            </div>
          </div>
          <div class="control-group">
            <button data-action="fetch"></button>
          </div>
          <div class="control-group">
            <button data-action="download"></button>
          </div>
          <div class="control-group">
            <button data-action="bulk"></button>
          </div>
          <div class="control-group">
            <button data-action="find-duplicates"></button>
          </div>
          <div class="control-group">
            <button id="favoriteFilterBtn" class="favorite-filter"></button>
          </div>
          <div class="control-group dropdown-group update-filter-group">
            <button id="updateFilterBtn" class="dropdown-main update-filter" aria-busy="false">
              <i class="fas fa-exclamation-circle"></i>
              <span>Updates</span>
            </button>
            <button id="updateFilterMenuToggle" class="dropdown-toggle">
              <i class="fas fa-caret-down"></i>
            </button>
            <div class="dropdown-menu">
              <div id="checkUpdatesMenuItem" class="dropdown-item" data-action="check-updates">
                <i class="fas fa-sync-alt"></i>
                <span>Check updates</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div id="customFilterIndicator" class="control-group hidden">
      <div class="filter-active">
        <i class="fas fa-times-circle clear-filter"></i>
      </div>
    </div>
  `;
}

function createDeferred() {
  let resolve;
  const promise = new Promise((res) => {
    resolve = res;
  });

  return { promise, resolve };
}

describe('SearchManager filtering scenarios', () => {
  it.each([
    ['loras'],
    ['checkpoints'],
  ])('updates filters and reloads results for %s page', async (pageKey) => {
    vi.useFakeTimers();

    renderControlsDom(pageKey);
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState(pageKey);
    const { getCurrentPageState } = stateModule;
    const { SearchManager } = await import('../../../static/js/managers/SearchManager.js');

    new SearchManager({ page: pageKey, searchDelay: 0 });

    const input = document.getElementById('searchInput');
    input.value = 'flux';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    await vi.runAllTimersAsync();

    expect(getCurrentPageState().filters.search).toBe('flux');
    expect(loadMoreWithVirtualScrollMock).toHaveBeenCalledWith(true, false);
    expect(loadMoreWithVirtualScrollMock).toHaveBeenCalledTimes(1);
  });
});

describe('FilterManager tag and base model filters', () => {
  it.each([
    ['loras'],
    ['checkpoints'],
  ])('toggles tag chips and persists filters for %s page', async (pageKey) => {
    renderControlsDom(pageKey);
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState(pageKey);
    const { getCurrentPageState } = stateModule;
    const { FilterManager } = await import('../../../static/js/managers/FilterManager.js');

    const manager = new FilterManager({ page: pageKey });
    manager.createTagFilterElements([{ tag: 'style', count: 5 }]);

    const tagChip = document.querySelector('.filter-tag.tag-filter');
    expect(tagChip).not.toBeNull();

    tagChip.dispatchEvent(new Event('click', { bubbles: true }));
    await vi.waitFor(() => expect(loadMoreWithVirtualScrollMock).toHaveBeenCalledTimes(1));

    expect(getCurrentPageState().filters.tags).toEqual(['style']);
    expect(tagChip.classList.contains('active')).toBe(true);
    expect(document.getElementById('activeFiltersCount').textContent).toBe('1');
    expect(document.getElementById('activeFiltersCount').style.display).toBe('inline-flex');

    const storageKey = `lora_manager_${pageKey}_filters`;
    const storedFilters = JSON.parse(localStorage.getItem(storageKey));
    expect(storedFilters.tags).toEqual(['style']);

    loadMoreWithVirtualScrollMock.mockClear();

    tagChip.dispatchEvent(new Event('click', { bubbles: true }));
    await vi.waitFor(() => expect(loadMoreWithVirtualScrollMock).toHaveBeenCalledTimes(1));

    expect(getCurrentPageState().filters.tags).toEqual([]);
    expect(document.getElementById('activeFiltersCount').style.display).toBe('none');
  });

  it.each([
    ['loras'],
    ['checkpoints'],
  ])('toggles base model chips and reloads %s results', async (pageKey) => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        base_models: [{ name: 'SDXL', count: 2 }],
      }),
    });

    renderControlsDom(pageKey);
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState(pageKey);
    const { getCurrentPageState } = stateModule;
    const { FilterManager } = await import('../../../static/js/managers/FilterManager.js');

    const manager = new FilterManager({ page: pageKey });

    await vi.waitFor(() => {
      const chip = document.querySelector('[data-base-model="SDXL"]');
      expect(chip).not.toBeNull();
    });

    const baseModelChip = document.querySelector('[data-base-model="SDXL"]');

    baseModelChip.dispatchEvent(new Event('click', { bubbles: true }));
    await vi.waitFor(() => expect(loadMoreWithVirtualScrollMock).toHaveBeenCalledTimes(1));

    expect(getCurrentPageState().filters.baseModel).toEqual(['SDXL']);
    expect(baseModelChip.classList.contains('active')).toBe(true);

    const storageKey = `lora_manager_${pageKey}_filters`;
    const storedFilters = JSON.parse(localStorage.getItem(storageKey));
    expect(storedFilters.baseModel).toEqual(['SDXL']);

    loadMoreWithVirtualScrollMock.mockClear();

    baseModelChip.dispatchEvent(new Event('click', { bubbles: true }));
    await vi.waitFor(() => expect(loadMoreWithVirtualScrollMock).toHaveBeenCalledTimes(1));

    expect(getCurrentPageState().filters.baseModel).toEqual([]);
    expect(baseModelChip.classList.contains('active')).toBe(false);
  });
});

describe('PageControls favorites, sorting, and duplicates scenarios', () => {
  it('persists favorites toggle for LoRAs and triggers reload', async () => {
    renderControlsDom('loras');
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState('loras');
    const { LorasControls } = await import('../../../static/js/components/controls/LorasControls.js');

    const controls = new LorasControls();

    await controls.toggleFavoritesOnly();

    expect(sessionStorage.getItem('lora_manager_show_favorites_only_loras')).toBe('true');
    expect(stateModule.getCurrentPageState().showFavoritesOnly).toBe(true);
    expect(document.getElementById('favoriteFilterBtn').classList.contains('active')).toBe(true);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);

    resetAndReloadMock.mockClear();

    await controls.toggleFavoritesOnly();

    expect(sessionStorage.getItem('lora_manager_show_favorites_only_loras')).toBe('false');
    expect(stateModule.getCurrentPageState().showFavoritesOnly).toBe(false);
    expect(document.getElementById('favoriteFilterBtn').classList.contains('active')).toBe(false);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('persists favorites toggle for checkpoints and triggers reload', async () => {
    renderControlsDom('checkpoints');
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState('checkpoints');
    const { CheckpointsControls } = await import('../../../static/js/components/controls/CheckpointsControls.js');

    const controls = new CheckpointsControls();

    await controls.toggleFavoritesOnly();

    expect(sessionStorage.getItem('lora_manager_show_favorites_only_checkpoints')).toBe('true');
    expect(stateModule.getCurrentPageState().showFavoritesOnly).toBe(true);
    expect(document.getElementById('favoriteFilterBtn').classList.contains('active')).toBe(true);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);

    resetAndReloadMock.mockClear();

    await controls.toggleFavoritesOnly();

    expect(sessionStorage.getItem('lora_manager_show_favorites_only_checkpoints')).toBe('false');
    expect(stateModule.getCurrentPageState().showFavoritesOnly).toBe(false);
    expect(document.getElementById('favoriteFilterBtn').classList.contains('active')).toBe(false);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('persists update-available toggle for LoRAs and triggers reload', async () => {
    renderControlsDom('loras');
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState('loras');
    const { LorasControls } = await import('../../../static/js/components/controls/LorasControls.js');

    const controls = new LorasControls();

    await controls.toggleUpdateAvailableOnly();

    expect(sessionStorage.getItem('lora_manager_show_update_available_only_loras')).toBe('true');
    expect(stateModule.getCurrentPageState().showUpdateAvailableOnly).toBe(true);
    expect(document.getElementById('updateFilterBtn').classList.contains('active')).toBe(true);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);

    resetAndReloadMock.mockClear();

    await controls.toggleUpdateAvailableOnly();

    expect(sessionStorage.getItem('lora_manager_show_update_available_only_loras')).toBe('false');
    expect(stateModule.getCurrentPageState().showUpdateAvailableOnly).toBe(false);
    expect(document.getElementById('updateFilterBtn').classList.contains('active')).toBe(false);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('does not change filter badge or button when toggling update availability', async () => {
    renderControlsDom('loras');
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState('loras');
    const { LorasControls } = await import('../../../static/js/components/controls/LorasControls.js');

    const controls = new LorasControls();

    const filterBadge = document.getElementById('activeFiltersCount');
    const filterButton = document.getElementById('filterButton');

    expect(filterBadge.style.display).toBe('none');
    expect(filterBadge.textContent).toBe('0');
    expect(filterButton.classList.contains('active')).toBe(false);

    await controls.toggleUpdateAvailableOnly();

    expect(filterBadge.style.display).toBe('none');
    expect(filterBadge.textContent).toBe('0');
    expect(filterButton.classList.contains('active')).toBe(false);

    await controls.toggleUpdateAvailableOnly();

    expect(filterBadge.style.display).toBe('none');
    expect(filterBadge.textContent).toBe('0');
    expect(filterButton.classList.contains('active')).toBe(false);
  });

  it('persists update-available toggle for checkpoints and triggers reload', async () => {
    renderControlsDom('checkpoints');
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState('checkpoints');
    const { CheckpointsControls } = await import('../../../static/js/components/controls/CheckpointsControls.js');

    const controls = new CheckpointsControls();

    await controls.toggleUpdateAvailableOnly();

    expect(sessionStorage.getItem('lora_manager_show_update_available_only_checkpoints')).toBe('true');
    expect(stateModule.getCurrentPageState().showUpdateAvailableOnly).toBe(true);
    expect(document.getElementById('updateFilterBtn').classList.contains('active')).toBe(true);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);

    resetAndReloadMock.mockClear();

    await controls.toggleUpdateAvailableOnly();

    expect(sessionStorage.getItem('lora_manager_show_update_available_only_checkpoints')).toBe('false');
    expect(stateModule.getCurrentPageState().showUpdateAvailableOnly).toBe(false);
    expect(document.getElementById('updateFilterBtn').classList.contains('active')).toBe(false);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('disables update controls while checking for model updates and restores them afterwards', async () => {
    const deferred = createDeferred();
    performModelUpdateCheckMock.mockImplementation(async () => {
      await deferred.promise;
      return { status: 'success', displayName: 'LoRA', records: [] };
    });

    renderControlsDom('loras');
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState('loras');
    const { LorasControls } = await import('../../../static/js/components/controls/LorasControls.js');

    new LorasControls();

    const updateButton = document.getElementById('updateFilterBtn');
    const toggleButton = document.getElementById('updateFilterMenuToggle');
    const menuItem = document.getElementById('checkUpdatesMenuItem');
    const dropdownGroup = menuItem.closest('.dropdown-group');
    const icon = updateButton.querySelector('i');

    expect(updateButton.disabled).toBe(false);
    expect(toggleButton.disabled).toBe(false);
    expect(menuItem.classList.contains('disabled')).toBe(false);

    menuItem.dispatchEvent(new Event('click', { bubbles: true }));

    expect(performModelUpdateCheckMock).toHaveBeenCalledTimes(1);
    expect(updateButton.disabled).toBe(true);
    expect(updateButton.classList.contains('loading')).toBe(true);
    expect(updateButton.getAttribute('aria-busy')).toBe('true');
    expect(toggleButton.disabled).toBe(true);
    expect(toggleButton.classList.contains('loading')).toBe(true);
    expect(menuItem.classList.contains('disabled')).toBe(true);
    expect(menuItem.getAttribute('aria-disabled')).toBe('true');
    expect(icon.classList.contains('fa-spinner')).toBe(true);
    expect(icon.classList.contains('fa-spin')).toBe(true);

    deferred.resolve();
    await performModelUpdateCheckMock.mock.results[0].value;
    await Promise.resolve();

    await vi.waitFor(() => {
      expect(updateButton.disabled).toBe(false);
      expect(updateButton.classList.contains('loading')).toBe(false);
      expect(toggleButton.disabled).toBe(false);
      expect(toggleButton.classList.contains('loading')).toBe(false);
      expect(menuItem.classList.contains('disabled')).toBe(false);
    });

    expect(updateButton.getAttribute('aria-busy')).toBe('false');
    expect(menuItem.hasAttribute('aria-disabled')).toBe(false);
    expect(icon.classList.contains('fa-spinner')).toBe(false);
    expect(icon.classList.contains('fa-spin')).toBe(false);
    expect(icon.classList.contains('fa-exclamation-circle')).toBe(true);
    expect(dropdownGroup.classList.contains('active')).toBe(false);
  });

  it('saves sort selection and reloads models', async () => {
    renderControlsDom('loras');
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState('loras');
    const { LorasControls } = await import('../../../static/js/components/controls/LorasControls.js');

    new LorasControls();

    const sortSelect = document.getElementById('sortSelect');
    sortSelect.value = 'date:asc';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(resetAndReloadMock).toHaveBeenCalledTimes(1));
    expect(localStorage.getItem('lora_manager_loras_sort')).toBe('date:asc');
    expect(stateModule.getCurrentPageState().sortBy).toBe('date:asc');
  });

  it('converts legacy sort preference on initialization', async () => {
    localStorage.setItem('loras_sort', 'date');

    renderControlsDom('loras');
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState('loras');
    const { LorasControls } = await import('../../../static/js/components/controls/LorasControls.js');

    new LorasControls();

    const sortSelect = document.getElementById('sortSelect');
    expect(sortSelect.value).toBe('date:desc');
    expect(stateModule.getCurrentPageState().sortBy).toBe('date:desc');
  });

  it('updates duplicate badge after refresh and toggles duplicate mode from controls', async () => {
    renderControlsDom('checkpoints');
    const stateModule = await import('../../../static/js/state/index.js');
    stateModule.initPageState('checkpoints');
    const { CheckpointsControls } = await import('../../../static/js/components/controls/CheckpointsControls.js');

    const controls = new CheckpointsControls();

    const toggleDuplicateMode = vi.fn();
    const updateDuplicatesBadgeAfterRefresh = vi.fn();
    window.modelDuplicatesManager = {
      toggleDuplicateMode,
      updateDuplicatesBadgeAfterRefresh,
    };

    await controls.refreshModels(true);
    expect(refreshModelsMock).toHaveBeenCalledWith(true);
    expect(updateDuplicatesBadgeAfterRefresh).toHaveBeenCalledTimes(1);

    const duplicateButton = document.querySelector('[data-action="find-duplicates"]');
    duplicateButton.click();
    expect(toggleDuplicateMode).toHaveBeenCalledTimes(1);
  });
});
