import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderRecipesPage } from '../utils/pageFixtures.js';

const initializeAppMock = vi.fn();
const initializePageFeaturesMock = vi.fn();
const getCurrentPageStateMock = vi.fn();
const getSessionItemMock = vi.fn();
const removeSessionItemMock = vi.fn();
const getStorageItemMock = vi.fn();
const setStorageItemMock = vi.fn();
const removeStorageItemMock = vi.fn();
const RecipeContextMenuMock = vi.fn();
const refreshVirtualScrollMock = vi.fn();
const refreshRecipesMock = vi.fn();
const fetchUnifiedFolderTreeMock = vi.fn();
const fetchModelFoldersMock = vi.fn();

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
  RecipeContextMenu: RecipeContextMenuMock,
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
    fetchUnifiedFolderTree: fetchUnifiedFolderTreeMock.mockResolvedValue({ success: true, tree: {} }),
    fetchModelFolders: fetchModelFoldersMock.mockResolvedValue({ success: true, folders: [] }),
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
      sortBy: 'date:desc',
      searchOptions: undefined,
      customFilter: undefined,
      duplicatesMode: false,
    };

    getCurrentPageStateMock.mockImplementation(() => pageState);
    initializeAppMock.mockResolvedValue(undefined);
    initializePageFeaturesMock.mockResolvedValue(undefined);
    refreshVirtualScrollMock.mockReset();
    refreshVirtualScrollMock.mockImplementation(() => { });
    refreshRecipesMock.mockResolvedValue('refreshed');

    getSessionItemMock.mockImplementation((key) => {
      const map = {
        lora_to_recipe_filterLoraName: 'Flux Dream',
        lora_to_recipe_filterLoraHash: 'abc123',
        checkpoint_to_recipe_filterCheckpointName: null,
        checkpoint_to_recipe_filterCheckpointHash: null,
        viewRecipeId: '42',
      };
      return map[key] ?? null;
    });
    removeSessionItemMock.mockImplementation(() => { });
    getStorageItemMock.mockImplementation((_, defaultValue = null) => defaultValue);

    renderRecipesPage();

    // Inject controls DOM that would normally come from components/controls.html
    // (raw template rendering doesn't process Jinja2 {% include %} tags)
    const customFilterIndicator = document.createElement('div');
    customFilterIndicator.id = 'customFilterIndicator';
    customFilterIndicator.className = 'control-group hidden';
    customFilterIndicator.innerHTML = `
      <div class="filter-active">
        <i class="fas fa-filter"></i> <span class="customFilterText" title=""></span>
        <i class="fas fa-times-circle clear-filter"></i>
      </div>
    `;
    document.body.appendChild(customFilterIndicator);

    ({ RecipeManager } = await import('../../../static/js/recipes.js'));
  });

  afterEach(() => {
    delete window.recipeManager;
    delete window.importManager;
    delete window.settingsManager;
  });

  it('initializes page controls, restores filters, and wires sort interactions', async () => {
    const sortSelectElement = document.createElement('select');
    sortSelectElement.id = 'sortSelect';
    sortSelectElement.innerHTML = `
      <option value="date:desc">Newest</option>
      <option value="name:asc">Name A-Z</option>
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
      prompt: true,
      recursive: true,
    });

    expect(pageState.customFilter).toEqual({
      active: true,
      loraName: 'Flux Dream',
      loraHash: 'abc123',
      checkpointName: null,
      checkpointHash: null,
      recipeId: '42',
    });

    const indicator = document.getElementById('customFilterIndicator');
    expect(indicator.classList.contains('hidden')).toBe(false);

    const clearButton = indicator.querySelector('.clear-filter');
    clearButton.dispatchEvent(new Event('click', { bubbles: true }));

    expect(removeSessionItemMock).toHaveBeenCalledWith('lora_to_recipe_filterLoraName');
    expect(removeSessionItemMock).toHaveBeenCalledWith('lora_to_recipe_filterLoraHash');
    expect(removeSessionItemMock).toHaveBeenCalledWith('checkpoint_to_recipe_filterCheckpointName');
    expect(removeSessionItemMock).toHaveBeenCalledWith('checkpoint_to_recipe_filterCheckpointHash');
    expect(removeSessionItemMock).toHaveBeenCalledWith('viewRecipeId');
    expect(pageState.customFilter.active).toBe(false);
    expect(indicator.classList.contains('hidden')).toBe(true);
    expect(refreshVirtualScrollMock).toHaveBeenCalledTimes(1);

    const sortSelect = document.getElementById('sortSelect');
    sortSelect.value = 'name:asc';
    sortSelect.dispatchEvent(new Event('change', { bubbles: true }));

    expect(pageState.sortBy).toBe('name:asc');
    expect(refreshVirtualScrollMock).toHaveBeenCalledTimes(2);
    expect(initializePageFeaturesMock).toHaveBeenCalledTimes(1);
  });

  it('wires the layout toggle and reflects the saved recipes layout setting', async () => {
    const gridBtn = document.createElement('button');
    gridBtn.className = 'layout-toggle-btn';
    gridBtn.dataset.recipesLayout = 'grid';
    gridBtn.setAttribute('aria-pressed', 'false');
    const masonryBtn = document.createElement('button');
    masonryBtn.className = 'layout-toggle-btn';
    masonryBtn.dataset.recipesLayout = 'masonry';
    masonryBtn.setAttribute('aria-pressed', 'false');
    document.body.appendChild(gridBtn);
    document.body.appendChild(masonryBtn);

    const saveRecipesLayoutMock = vi.fn().mockResolvedValue();
    window.settingsManager = { saveRecipesLayout: saveRecipesLayoutMock };

    const manager = new RecipeManager();
    await manager.initialize();

    // Initial state follows the saved setting (default grid)
    expect(gridBtn.classList.contains('active')).toBe(true);
    expect(gridBtn.getAttribute('aria-pressed')).toBe('true');
    expect(masonryBtn.classList.contains('active')).toBe(false);

    // Clicking the inactive option saves the new layout
    masonryBtn.dispatchEvent(new Event('click', { bubbles: true }));
    expect(saveRecipesLayoutMock).toHaveBeenCalledWith('masonry');

    // Clicking the already-active option is a no-op
    gridBtn.dispatchEvent(new Event('click', { bubbles: true }));
    expect(saveRecipesLayoutMock).toHaveBeenCalledTimes(1);
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

  it('supports preserve-scroll options while keeping boolean compatibility', async () => {
    const manager = new RecipeManager();

    await manager.loadRecipes({ preserveScroll: true });
    expect(refreshVirtualScrollMock).toHaveBeenNthCalledWith(1, { preserveScroll: true });

    await manager.loadRecipes(false);
    expect(refreshVirtualScrollMock).toHaveBeenCalledTimes(1);

    await manager.loadRecipes({ resetPage: true, preserveScroll: false });
    expect(refreshVirtualScrollMock).toHaveBeenNthCalledWith(2, { preserveScroll: false });
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

  it('restores checkpoint recipe filter state and indicator text', async () => {
    getSessionItemMock.mockImplementation((key) => {
      const map = {
        lora_to_recipe_filterLoraName: null,
        lora_to_recipe_filterLoraHash: null,
        checkpoint_to_recipe_filterCheckpointName: 'Flux Base',
        checkpoint_to_recipe_filterCheckpointHash: 'ckpt123',
        viewRecipeId: null,
      };
      return map[key] ?? null;
    });

    const manager = new RecipeManager();
    await manager.initialize();

    expect(pageState.customFilter).toEqual({
      active: true,
      loraName: null,
      loraHash: null,
      checkpointName: 'Flux Base',
      checkpointHash: 'ckpt123',
      recipeId: null,
    });

    const indicator = document.getElementById('customFilterIndicator');
    const filterText = indicator.querySelector('.customFilterText');

    expect(filterText.innerHTML).toContain('Recipes using checkpoint:');
    expect(filterText.innerHTML).toContain('Flux Base');
    expect(filterText.getAttribute('title')).toBe('Flux Base');
  });

  it('registers the R toolbar shortcut so the recipes page can refresh', async () => {
    const refreshBtn = document.createElement('button');
    refreshBtn.dataset.action = 'refresh';
    document.body.appendChild(refreshBtn);

    const manager = new RecipeManager();
    await manager.initialize();

    const { eventManager } = await import('../../../static/js/utils/EventManager.js');
    const entry = (eventManager.handlers.get('keydown') || [])
      .find((handler) => handler.source === 'pageControls-actions');
    expect(entry).toBeDefined();

    const keydownEvent = (key, target) => {
      const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
      Object.defineProperty(event, 'target', { value: target });
      return event;
    };

    // R clicks the refresh button, reusing its click handler
    const refreshEvent = keydownEvent('r', document.body);
    expect(entry.handler(refreshEvent)).toBe(true);
    expect(refreshEvent.defaultPrevented).toBe(true);
    expect(refreshRecipesMock).toHaveBeenCalledWith(false);

    // Not while typing
    refreshRecipesMock.mockClear();
    expect(entry.handler(keydownEvent('r', document.createElement('input')))).toBe(false);
    expect(refreshRecipesMock).not.toHaveBeenCalled();

    // Recipes has no fetch/download buttons, so F / D pass through
    expect(entry.handler(keydownEvent('f', document.body))).toBe(false);
    expect(entry.handler(keydownEvent('d', document.body))).toBe(false);
  });
});
