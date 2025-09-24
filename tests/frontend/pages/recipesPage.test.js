import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderRecipesPage } from '../utils/pageFixtures.js';

const initializeAppMock = vi.fn();
const initializePageFeaturesMock = vi.fn();
const getCurrentPageStateMock = vi.fn();
const getSessionItemMock = vi.fn();
const removeSessionItemMock = vi.fn();
const RecipeContextMenuMock = vi.fn();
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
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
  getSessionItem: getSessionItemMock,
  removeSessionItem: removeSessionItemMock,
}));

vi.mock('../../../static/js/components/ContextMenu/index.js', () => ({
  RecipeContextMenu: RecipeContextMenuMock,
}));

vi.mock('../../../static/js/components/DuplicatesManager.js', () => ({
  DuplicatesManager: DuplicatesManagerMock,
}));

vi.mock('../../../static/js/utils/infiniteScroll.js', () => ({
  refreshVirtualScroll: refreshVirtualScrollMock,
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  refreshRecipes: refreshRecipesMock,
}));

describe('RecipeManager', () => {
  let RecipeManager;
  let pageState;

  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();

    importManagerInstance = {
      showImportModal: vi.fn(),
    };
    recipeModalInstance = {
      showRecipeDetails: vi.fn(),
    };
    duplicatesManagerInstance = {
      findDuplicates: vi.fn(),
      selectLatestDuplicates: vi.fn(),
      deleteSelectedDuplicates: vi.fn(),
      confirmDeleteDuplicates: vi.fn(),
      exitDuplicateMode: vi.fn(),
    };

    pageState = {
      sortBy: 'date',
      searchOptions: undefined,
      customFilter: undefined,
      duplicatesMode: false,
    };

    getCurrentPageStateMock.mockImplementation(() => pageState);
    initializeAppMock.mockResolvedValue(undefined);
    initializePageFeaturesMock.mockResolvedValue(undefined);
    refreshVirtualScrollMock.mockReset();
    refreshVirtualScrollMock.mockImplementation(() => {});
    refreshRecipesMock.mockResolvedValue('refreshed');

    getSessionItemMock.mockImplementation((key) => {
      const map = {
        lora_to_recipe_filterLoraName: 'Flux Dream',
        lora_to_recipe_filterLoraHash: 'abc123',
        viewRecipeId: '42',
      };
      return map[key] ?? null;
    });
    removeSessionItemMock.mockImplementation(() => {});

    renderRecipesPage();

    ({ RecipeManager } = await import('../../../static/js/recipes.js'));
  });

  afterEach(() => {
    delete window.recipeManager;
    delete window.importManager;
  });

  it('initializes page controls, restores filters, and wires sort interactions', async () => {
    const sortSelectElement = document.createElement('select');
    sortSelectElement.id = 'sortSelect';
    sortSelectElement.innerHTML = `
      <option value="date">Date</option>
      <option value="name">Name</option>
    `;
    document.body.appendChild(sortSelectElement);

    const manager = new RecipeManager();
    await manager.initialize();

    expect(ImportManagerMock).toHaveBeenCalledTimes(1);
    expect(RecipeModalMock).toHaveBeenCalledTimes(1);
    expect(DuplicatesManagerMock).toHaveBeenCalledWith(manager);
    expect(RecipeContextMenuMock).toHaveBeenCalledTimes(1);

    expect(window.recipeManager).toBe(manager);
    expect(window.importManager).toBe(importManagerInstance);

    expect(pageState.searchOptions).toEqual({
      title: true,
      tags: true,
      loraName: true,
      loraModel: true,
    });

    expect(pageState.customFilter).toEqual({
      active: true,
      loraName: 'Flux Dream',
      loraHash: 'abc123',
      recipeId: '42',
    });

    const indicator = document.getElementById('customFilterIndicator');
    expect(indicator.classList.contains('hidden')).toBe(false);

    const clearButton = indicator.querySelector('.clear-filter');
    clearButton.dispatchEvent(new Event('click', { bubbles: true }));

    expect(removeSessionItemMock).toHaveBeenCalledWith('lora_to_recipe_filterLoraName');
    expect(removeSessionItemMock).toHaveBeenCalledWith('lora_to_recipe_filterLoraHash');
    expect(removeSessionItemMock).toHaveBeenCalledWith('viewRecipeId');
    expect(pageState.customFilter.active).toBe(false);
    expect(indicator.classList.contains('hidden')).toBe(true);
    expect(refreshVirtualScrollMock).toHaveBeenCalledTimes(1);

    const sortSelect = document.getElementById('sortSelect');
    sortSelect.value = 'name';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));

    expect(pageState.sortBy).toBe('name');
    expect(refreshVirtualScrollMock).toHaveBeenCalledTimes(2);
    expect(initializePageFeaturesMock).toHaveBeenCalledTimes(1);
  });

  it('skips loading when duplicates mode is active and refreshes otherwise', async () => {
    const manager = new RecipeManager();

    pageState.duplicatesMode = true;
    await manager.loadRecipes();
    expect(refreshVirtualScrollMock).not.toHaveBeenCalled();

    pageState.duplicatesMode = false;
    await manager.loadRecipes();
    expect(refreshVirtualScrollMock).toHaveBeenCalledTimes(1);
  });

  it('proxies duplicate management and refresh helpers', async () => {
    const manager = new RecipeManager();

    await manager.findDuplicateRecipes();
    expect(duplicatesManagerInstance.findDuplicates).toHaveBeenCalledTimes(1);

    manager.selectLatestDuplicates();
    expect(duplicatesManagerInstance.selectLatestDuplicates).toHaveBeenCalledTimes(1);

    manager.deleteSelectedDuplicates();
    expect(duplicatesManagerInstance.deleteSelectedDuplicates).toHaveBeenCalledTimes(1);

    manager.confirmDeleteDuplicates();
    expect(duplicatesManagerInstance.confirmDeleteDuplicates).toHaveBeenCalledTimes(1);

    const grid = document.getElementById('recipeGrid');
    grid.innerHTML = '<div>content</div>';
    manager.exitDuplicateMode();
    expect(grid.innerHTML).toBe('');
    expect(duplicatesManagerInstance.exitDuplicateMode).toHaveBeenCalledTimes(1);

    await manager.refreshRecipes();
    expect(refreshRecipesMock).toHaveBeenCalledTimes(1);
  });
});
