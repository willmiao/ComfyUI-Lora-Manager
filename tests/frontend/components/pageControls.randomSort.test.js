import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';
import { applySortToSelect } from '../../../static/js/components/controls/SortDropdown.js';

const resetAndReloadMock = vi.fn();
const getModelApiClientMock = vi.fn();

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: getModelApiClientMock,
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: vi.fn(),
  openCivitaiByMetadata: vi.fn(),
  updatePanelPositions: vi.fn(),
}));

vi.mock('../../../static/js/managers/DownloadManager.js', () => ({
  downloadManager: { showDownloadModal: vi.fn() },
}));

vi.mock('../../../static/js/components/SidebarManager.js', () => ({
  sidebarManager: {
    setHostPageControls: vi.fn(),
    initialize: vi.fn(async () => {}),
    refresh: vi.fn(async () => {}),
    cleanup: vi.fn(),
    isInitialized: false,
  },
}));

vi.mock('../../../static/js/components/alphabet/index.js', () => ({
  createAlphabetBar: vi.fn(() => ({ destroy: vi.fn() })),
}));

vi.mock('../../../static/js/utils/updateCheckHelpers.js', () => ({
  performModelUpdateCheck: vi.fn(async () => ({ status: 'success', displayName: 'LoRA', records: [] })),
}));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();

  resetAndReloadMock.mockResolvedValue(undefined);
  getModelApiClientMock.mockReturnValue({});

  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ success: true, base_models: [] }),
  });
});

afterEach(() => {
  delete window.bulkManager;
  delete window.modelDuplicatesManager;
  delete global.fetch;
});

function renderControlsDom(pageKey) {
  document.body.dataset.page = pageKey;
  document.body.innerHTML = `
    <div class="controls">
      <div id="excludedViewBanner" class="excluded-view-banner hidden">
        <button id="excludedViewBackBtn">Back</button>
      </div>
      <div class="actions">
        <div class="action-buttons">
          <div class="control-group">
            <select id="sortSelect">
              <option value="name:asc">Name Asc</option>
              <option value="name:desc">Name Desc</option>
              <option value="random">Randomize (shuffle)</option>
            </select>
          </div>
          <div class="control-group dropdown-group">
            <button data-action="refresh" class="dropdown-main"></button>
            <button class="dropdown-toggle"></button>
            <div class="dropdown-menu">
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
              <span>Updates</span>
            </button>
            <button id="updateFilterMenuToggle" class="dropdown-toggle"></button>
            <div class="dropdown-menu">
              <div id="checkUpdatesMenuItem" class="dropdown-item" data-action="check-updates">
                <span>Check updates</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div id="customFilterIndicator" class="control-group hidden">
      <div class="filter-active">
        <span class="customFilterText" title=""></span>
        <i class="fas fa-times-circle clear-filter"></i>
      </div>
    </div>
    <div id="breadcrumbContainer"></div>
    <div id="duplicatesBanner" style="display: none;"></div>
    <div class="alphabet-bar-container"></div>
  `;
}

async function createControls() {
  const stateModule = await import('../../../static/js/state/index.js');
  stateModule.initPageState('loras');
  const { LorasControls } = await import('../../../static/js/components/controls/LorasControls.js');
  return { stateModule, controls: new LorasControls() };
}

describe('Random sort option', () => {
  it('generates a seeded sort value when Random is picked', async () => {
    renderControlsDom('loras');
    const { controls } = await createControls();
    const sortSelect = document.getElementById('sortSelect');
    const randomOpt = sortSelect.querySelector('option[value="random"]');

    sortSelect.value = 'random';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(controls.pageState.sortBy).toMatch(/^random:[a-z0-9]+$/);
    expect(localStorage.getItem('lora_manager_loras_sort')).toBe(controls.pageState.sortBy);
    expect(randomOpt.value).toBe(controls.pageState.sortBy);
    expect(sortSelect.value).toBe(controls.pageState.sortBy);
    expect(resetAndReloadMock).toHaveBeenCalled();
  });

  it('reshuffles with a fresh seed every time Random is picked again', async () => {
    renderControlsDom('loras');
    const { controls } = await createControls();
    const sortSelect = document.getElementById('sortSelect');
    const randomOpt = sortSelect.querySelector('option[value="random"]');

    // First pick
    sortSelect.value = 'random';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();
    const firstSeed = controls.pageState.sortBy;

    // Second pick: the option now carries the seeded value, like a menu click
    sortSelect.value = randomOpt.value;
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(controls.pageState.sortBy).toMatch(/^random:[a-z0-9]+$/);
    expect(controls.pageState.sortBy).not.toBe(firstSeed);
  });

  it('restores a persisted seeded random sort on load', async () => {
    renderControlsDom('loras');
    const savedSort = 'random:persistedseed';
    localStorage.setItem('lora_manager_loras_sort', savedSort);

    const { controls } = await createControls();
    const sortSelect = document.getElementById('sortSelect');

    expect(controls.pageState.sortBy).toBe(savedSort);
    expect(sortSelect.value).toBe(savedSort);
    expect(sortSelect.querySelector('option[value="random:persistedseed"]')).not.toBeNull();
  });

  it('applies a non-random sort back to the plain random option', async () => {
    renderControlsDom('loras');
    const { controls } = await createControls();
    const sortSelect = document.getElementById('sortSelect');
    const randomOpt = sortSelect.querySelector('option[value="random"]');

    // Seed a random sort, then switch to a normal sort
    sortSelect.value = 'random';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();
    applySortToSelect('name:desc');

    expect(sortSelect.value).toBe('name:desc');
    expect(randomOpt.value).toBe('random');
  });

  it('resets the seeded option when switching away from Random via the dropdown change handler', async () => {
    renderControlsDom('loras');
    const { controls } = await createControls();
    const sortSelect = document.getElementById('sortSelect');
    const randomOpt = sortSelect.querySelector('option[value="random"]');

    // Pick Random: the option is now seeded
    sortSelect.value = 'random';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();
    expect(randomOpt.value).toMatch(/^random:[a-z0-9]+$/);

    // Switch to a non-random sort through the change handler (as a menu
    // click does); the option must go back to the plain "random" value
    sortSelect.value = 'name:desc';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(controls.pageState.sortBy).toBe('name:desc');
    expect(sortSelect.value).toBe('name:desc');
    expect(randomOpt.value).toBe('random');
  });
});
