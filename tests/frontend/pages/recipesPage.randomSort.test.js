import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderRecipesPage } from '../utils/pageFixtures.js';
import { applySortToSelect } from '../../../static/js/components/controls/SortDropdown.js';

const initializeAppMock = vi.fn();
const initializePageFeaturesMock = vi.fn();
const getCurrentPageStateMock = vi.fn();
const getSessionItemMock = vi.fn();
const removeSessionItemMock = vi.fn();
const getStorageItemMock = vi.fn();
const setStorageItemMock = vi.fn();
const removeStorageItemMock = vi.fn();
const refreshVirtualScrollMock = vi.fn();
const refreshRecipesMock = vi.fn();

let importManagerInstance;
let recipeModalInstance;
let duplicatesManagerInstance;

const ImportManagerMock = vi.fn(() => importManagerInstance);
const RecipeModalMock = vi.fn(() => recipeModalInstance);
const DuplicatesManagerMock = vi.fn(() => duplicatesManagerInstance);

vi.mock('../../../static/js/core.js', () => ({
  appCore: {
    initialize: initializeAppMock,
    initializePageFeatures: initializePageFeaturesMock,
  },
}));

vi.mock('../../../static/js/managers/ImportManager.js', () => ({
  ImportManager: ImportManagerMock,
}));

vi.mock('../../../static/js/components/RecipeModal.js', () => ({
  RecipeModal: RecipeModalMock,
}));

vi.mock('../../../static/js/state/index.js', () => ({
  getCurrentPageState: getCurrentPageStateMock,
  state: {
    currentPageType: 'recipes',
    global: { settings: {} },
    virtualScroller: {
      removeItemByFilePath: vi.fn(),
      updateSingleItem: vi.fn(),
      refreshWithData: vi.fn(),
    },
  },
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
  getSessionItem: getSessionItemMock,
  removeSessionItem: removeSessionItemMock,
  getStorageItem: getStorageItemMock,
  setStorageItem: setStorageItemMock,
  removeStorageItem: removeStorageItemMock,
}));

vi.mock('../../../static/js/components/ContextMenu/index.js', () => ({
  RecipeContextMenu: vi.fn(),
}));

vi.mock('../../../static/js/components/DuplicatesManager.js', () => ({
  DuplicatesManager: DuplicatesManagerMock,
}));

vi.mock('../../../static/js/utils/infiniteScroll.js', () => ({
  refreshVirtualScroll: refreshVirtualScrollMock,
  recreateVirtualScroll: vi.fn(),
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  refreshRecipes: refreshRecipesMock,
  RecipeSidebarApiClient: vi.fn(() => ({
    apiConfig: { config: { displayName: 'Recipes', supportsMove: true } },
    fetchUnifiedFolderTree: vi.fn().mockResolvedValue({ success: true, tree: {} }),
    fetchModelFolders: vi.fn().mockResolvedValue({ success: true, folders: [] }),
    fetchModelRoots: vi.fn().mockResolvedValue({ roots: ['/recipes'] }),
    moveBulkModels: vi.fn(),
    moveSingleModel: vi.fn(),
  })),
}));

vi.mock('../../../static/js/components/SidebarManager.js', () => ({
  sidebarManager: {
    setHostPageControls: vi.fn(),
    initialize: vi.fn(async () => {}),
    refresh: vi.fn(async () => {}),
    cleanup: vi.fn(),
  },
}));

function renderSortSelect() {
  const sortSelectElement = document.createElement('select');
  sortSelectElement.id = 'sortSelect';
  sortSelectElement.innerHTML = `
    <option value="date:desc">Newest</option>
    <option value="name:asc">Name A-Z</option>
    <option value="random">Randomize (shuffle)</option>
  `;
  document.body.appendChild(sortSelectElement);
  return sortSelectElement;
}

describe('RecipeManager Random sort', () => {
  let RecipeManager;
  let pageState;

  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();

    importManagerInstance = { showImportModal: vi.fn() };
    recipeModalInstance = { showRecipeDetails: vi.fn() };
    duplicatesManagerInstance = {
      findDuplicates: vi.fn(),
      selectLatestDuplicates: vi.fn(),
      deleteSelectedDuplicates: vi.fn(),
      confirmDeleteDuplicates: vi.fn(),
      exitDuplicateMode: vi.fn(),
    };

    pageState = {
      sortBy: 'date:desc',
      searchOptions: undefined,
      customFilter: undefined,
      duplicatesMode: false,
    };

    getCurrentPageStateMock.mockImplementation(() => pageState);
    initializeAppMock.mockResolvedValue(undefined);
    initializePageFeaturesMock.mockResolvedValue(undefined);
    refreshVirtualScrollMock.mockImplementation(() => {});
    refreshRecipesMock.mockResolvedValue('refreshed');
    getSessionItemMock.mockImplementation(() => null);
    removeSessionItemMock.mockImplementation(() => {});
    getStorageItemMock.mockImplementation(() => null);
    setStorageItemMock.mockImplementation(() => {});

    renderRecipesPage();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.recipeManager;
    delete window.importManager;
  });

  async function createManager() {
    ({ RecipeManager } = await import('../../../static/js/recipes.js'));
    const manager = new RecipeManager();
    await manager.initialize();
    return manager;
  }

  it('generates a seeded sort value when Random is picked', async () => {
    const sortSelect = renderSortSelect();
    const randomOpt = sortSelect.querySelector('option[value="random"]');
    await createManager();

    sortSelect.value = 'random';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(pageState.sortBy).toMatch(/^random:[a-z0-9]+$/);
    expect(setStorageItemMock).toHaveBeenCalledWith('recipes_sort', pageState.sortBy);
    expect(randomOpt.value).toBe(pageState.sortBy);
    expect(sortSelect.value).toBe(pageState.sortBy);
    expect(refreshVirtualScrollMock).toHaveBeenCalled();
  });

  it('reshuffles with a fresh seed every time Random is picked again', async () => {
    const sortSelect = renderSortSelect();
    const randomOpt = sortSelect.querySelector('option[value="random"]');
    await createManager();

    sortSelect.value = 'random';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();
    const firstSeed = pageState.sortBy;

    sortSelect.value = randomOpt.value;
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(pageState.sortBy).toMatch(/^random:[a-z0-9]+$/);
    expect(pageState.sortBy).not.toBe(firstSeed);
  });

  it('restores a persisted seeded random sort on load', async () => {
    const sortSelect = renderSortSelect();
    const savedSort = 'random:persistedseed';
    getStorageItemMock.mockImplementation((key) =>
      key === 'recipes_sort' ? savedSort : null
    );
    await createManager();

    expect(pageState.sortBy).toBe(savedSort);
    expect(sortSelect.value).toBe(savedSort);
    expect(sortSelect.querySelector('option[value="random:persistedseed"]')).not.toBeNull();
  });

  it('applies a non-random sort back to the plain random option', async () => {
    const sortSelect = renderSortSelect();
    const randomOpt = sortSelect.querySelector('option[value="random"]');
    await createManager();

    sortSelect.value = 'random';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();
    applySortToSelect('name:asc');

    expect(sortSelect.value).toBe('name:asc');
    expect(randomOpt.value).toBe('random');
  });

  it('resets the seeded option when switching away from Random via the change handler', async () => {
    const sortSelect = renderSortSelect();
    const randomOpt = sortSelect.querySelector('option[value="random"]');
    await createManager();

    sortSelect.value = 'random';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();
    expect(randomOpt.value).toMatch(/^random:[a-z0-9]+$/);

    sortSelect.value = 'name:asc';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(pageState.sortBy).toBe('name:asc');
    expect(sortSelect.value).toBe('name:asc');
    expect(randomOpt.value).toBe('random');
  });
});
