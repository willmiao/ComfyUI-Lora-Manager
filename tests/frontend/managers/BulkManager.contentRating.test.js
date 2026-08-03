import { describe, it, beforeEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));
const getNSFWLevelNameMock = vi.fn((level) => {
  if (level >= 16) return 'XXX';
  if (level >= 8) return 'X';
  if (level >= 4) return 'R';
  if (level >= 2) return 'PG13';
  if (level >= 1) return 'PG';
  return 'Unknown';
});

const loadingManagerStub = {
  showSimpleLoading: vi.fn(),
  showCancelButton: vi.fn(),
  hide: vi.fn(),
};

const stateStub = {
  currentPageType: 'recipes',
  bulkMode: false,
  selectedModels: new Set(),
  loadingManager: loadingManagerStub,
  virtualScroller: { updateSingleItem: vi.fn() },
  global: { settings: {} },
};

const saveModelMetadataMock = vi.fn();
const getModelApiClientMock = vi.fn(() => ({ saveModelMetadata: saveModelMetadataMock }));
const updateRecipeMetadataMock = vi.fn(() => Promise.resolve({ success: true }));

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
  getNSFWLevelName: getNSFWLevelNameMock,
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: getModelApiClientMock,
  resetAndReload: vi.fn(),
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  RecipeSidebarApiClient: class {},
  updateRecipeMetadata: updateRecipeMetadataMock,
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
  translate: translateMock,
}));

vi.mock('../../../static/js/utils/priorityTagHelpers.js', () => ({
  getPriorityTagSuggestions: vi.fn(),
}));

vi.mock('../../../static/js/components/shared/NsfwLevelSelector.js', () => ({
  getNsfwLevelSelector: vi.fn(),
}));

describe('BulkManager bulk content rating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stateStub.currentPageType = 'recipes';
    stateStub.bulkMode = false;
    stateStub.selectedModels.clear();
    saveModelMetadataMock.mockResolvedValue(undefined);
    updateRecipeMetadataMock.mockResolvedValue({ success: true });
  });

  async function createBulkManager() {
    const { BulkManager } = await import('../../../static/js/managers/BulkManager.js');
    return new BulkManager();
  }

  it('exposes the content rating action on the recipes page action config', async () => {
    const bulk = await createBulkManager();
    expect(bulk.actionConfig.recipes.setContentRating).toBe(true);
  });

  it('persists the rating through the recipe API when on the recipes page', async () => {
    const bulk = await createBulkManager();
    stateStub.currentPageType = 'recipes';
    stateStub.selectedModels.add('/recipes/test.webp');

    const ok = await bulk.setBulkContentRating(4, ['/recipes/test.webp']);

    expect(ok).toBe(true);
    expect(updateRecipeMetadataMock).toHaveBeenCalledWith('/recipes/test.webp', { preview_nsfw_level: 4 });
    expect(updateRecipeMetadataMock).toHaveBeenCalledTimes(1);
    expect(saveModelMetadataMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.models.bulkContentRatingSet',
      { count: 1, level: 'R' },
      'success'
    );
  });

  it('persists the rating through the model API on model pages', async () => {
    const bulk = await createBulkManager();
    stateStub.currentPageType = 'loras';
    stateStub.selectedModels.add('/models/test.safetensors');

    const ok = await bulk.setBulkContentRating(8, ['/models/test.safetensors']);

    expect(ok).toBe(true);
    expect(saveModelMetadataMock).toHaveBeenCalledWith('/models/test.safetensors', { preview_nsfw_level: 8 });
    expect(saveModelMetadataMock).toHaveBeenCalledTimes(1);
    expect(updateRecipeMetadataMock).not.toHaveBeenCalled();
  });
});
