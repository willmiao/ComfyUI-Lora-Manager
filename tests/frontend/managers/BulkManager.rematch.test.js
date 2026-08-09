import { describe, it, beforeEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const rematchBulkModelsMock = vi.fn();
const updateSingleItemMock = vi.fn();

const loadingManagerStub = {
  showSimpleLoading: vi.fn(),
  hide: vi.fn(),
  restoreProgressBar: vi.fn(),
};

const stateStub = {
  currentPageType: 'recipes',
  bulkMode: false,
  selectedModels: new Set(),
  loadingManager: loadingManagerStub,
  virtualScroller: { updateSingleItem: updateSingleItemMock },
  global: { settings: {} },
};

vi.mock('../../../static/js/state/index.js', () => ({
  state: stateStub,
  getCurrentPageState: vi.fn(),
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  copyToClipboard: vi.fn(),
  sendLoraToWorkflow: vi.fn(),
  sendEmbeddingToWorkflow: vi.fn(),
  buildLoraSyntax: vi.fn(),
  getNSFWLevelName: vi.fn(),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: vi.fn(),
  resetAndReload: vi.fn(),
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  RecipeSidebarApiClient: class {
    constructor() {
      this.rematchBulkModels = rematchBulkModelsMock;
    }
  },
  updateRecipeMetadata: vi.fn(),
  extractRecipeId: vi.fn(),
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: { LORA: 'loras', CHECKPOINT: 'checkpoints', EMBEDDING: 'embeddings' },
  MODEL_CONFIG: {},
}));

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));

vi.mock('../../../static/js/components/shared/ModelCard.js', () => ({
  updateCardsForBulkMode: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key)),
}));

vi.mock('../../../static/js/utils/priorityTagHelpers.js', () => ({
  getPriorityTagSuggestions: vi.fn(),
}));

vi.mock('../../../static/js/components/shared/NsfwLevelSelector.js', () => ({
  getNsfwLevelSelector: vi.fn(),
}));

describe('BulkManager.rematchSelectedRecipes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stateStub.currentPageType = 'recipes';
    stateStub.bulkMode = false;
    stateStub.selectedModels.clear();
  });

  async function createBulkManager() {
    const { BulkManager } = await import('../../../static/js/managers/BulkManager.js');
    return new BulkManager();
  }

  it('exposes the rematch action on the recipes page action config', async () => {
    const bulk = await createBulkManager();
    expect(bulk.actionConfig.recipes.rematchMetadata).toBe(true);
  });

  // Oracle R4-F1 pin: the complete toast must branch on `rematched` — a blind
  // `repaired` mirror would fire the skipped toast with count 0 here.
  it('toasts the rematched count when the bulk rematch succeeds', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');
    stateStub.selectedModels.add('/recipes/b.webp');
    stateStub.selectedModels.add('/recipes/c.webp');

    const rematchedRecipe = { file_path: '/recipes/a.webp', title: 'A' };
    rematchBulkModelsMock.mockResolvedValue({
      success: true,
      total: 3,
      rematched: 2,
      skipped: 1,
      errors: 0,
      recipes: [rematchedRecipe],
    });

    await bulk.rematchSelectedRecipes();

    expect(rematchBulkModelsMock).toHaveBeenCalledWith([
      '/recipes/a.webp',
      '/recipes/b.webp',
      '/recipes/c.webp',
    ]);
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchComplete',
      { rematched: 2, skipped: 1, total: 3 },
      'success'
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchSkipped',
      expect.anything(),
      expect.anything()
    );
    expect(updateSingleItemMock).toHaveBeenCalledWith('/recipes/a.webp', rematchedRecipe);
    expect(loadingManagerStub.showSimpleLoading).toHaveBeenCalled();
    expect(loadingManagerStub.hide).toHaveBeenCalled();
    expect(loadingManagerStub.restoreProgressBar).toHaveBeenCalled();
  });

  it('toasts the skipped message when nothing was rematched', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');
    stateStub.selectedModels.add('/recipes/b.webp');

    rematchBulkModelsMock.mockResolvedValue({
      success: true,
      total: 2,
      rematched: 0,
      skipped: 2,
      errors: 0,
      recipes: [],
    });

    await bulk.rematchSelectedRecipes();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchSkipped',
      { total: 2 },
      'info'
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchComplete',
      expect.anything(),
      expect.anything()
    );
    expect(loadingManagerStub.hide).toHaveBeenCalled();
    expect(loadingManagerStub.restoreProgressBar).toHaveBeenCalled();
  });

  it('surfaces the backend error message when the bulk rematch fails', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');

    rematchBulkModelsMock.mockResolvedValue({
      success: false,
      error: 'Rematch already in progress',
    });

    await bulk.rematchSelectedRecipes();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchFailed',
      { message: 'Rematch already in progress' },
      'error'
    );
    expect(loadingManagerStub.hide).toHaveBeenCalled();
  });

  it('toasts the failure message when the API call throws', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');

    rematchBulkModelsMock.mockRejectedValue(new Error('network down'));

    await bulk.rematchSelectedRecipes();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchFailed',
      { message: 'network down' },
      'error'
    );
  });

  it('warns and does not call the API when nothing is selected', async () => {
    const bulk = await createBulkManager();

    await bulk.rematchSelectedRecipes();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.noRecipesSelected',
      {},
      'warning'
    );
    expect(rematchBulkModelsMock).not.toHaveBeenCalled();
  });

  it('warns and does not call the API outside the recipes page', async () => {
    const bulk = await createBulkManager();
    stateStub.currentPageType = 'loras';
    stateStub.selectedModels.add('/models/a.safetensors');

    await bulk.rematchSelectedRecipes();

    expect(showToastMock).toHaveBeenCalledWith(
      'This operation is only available for recipes',
      {},
      'warning'
    );
    expect(rematchBulkModelsMock).not.toHaveBeenCalled();
  });
});
