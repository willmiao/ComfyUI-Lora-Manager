import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const showToastMock = vi.fn();
const resetAndReloadMock = vi.fn();
const bulkActivateMock = vi.fn();
const bulkDeactivateMock = vi.fn();
const syncWildcardCardStateMock = vi.fn();
const loadingManagerStub = {
  showSimpleLoading: vi.fn(),
  hide: vi.fn(),
  restoreProgressBar: vi.fn(),
};
const stateStub = {
  currentPageType: 'wildcards',
  bulkMode: false,
  selectedModels: new Set(),
  loadingManager: loadingManagerStub,
  virtualScroller: { items: [] },
  global: { settings: {} },
};

vi.mock('../../../static/js/state/index.js', () => ({
  state: stateStub,
  getCurrentPageState: vi.fn(),
}));
vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  showActionToast: vi.fn(),
  copyToClipboard: vi.fn(),
  sendLoraToWorkflow: vi.fn(),
  sendEmbeddingToWorkflow: vi.fn(),
  buildLoraSyntax: vi.fn(),
  getNSFWLevelName: vi.fn(),
}));
vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: vi.fn(() => ({
    bulkActivate: bulkActivateMock,
    bulkDeactivate: bulkDeactivateMock,
  })),
  resetAndReload: resetAndReloadMock,
}));
vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings',
    WORKFLOW: 'workflows',
    WILDCARD: 'wildcards',
  },
  MODEL_CONFIG: {},
}));
vi.mock('../../../static/js/utils/wildcardCardState.js', () => ({
  syncWildcardCardState: syncWildcardCardStateMock,
}));
vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));
vi.mock('../../../static/js/components/shared/ModelCard.js', () => ({
  updateCardsForBulkMode: vi.fn(),
}));
vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: vi.fn((key, params, fallback) => fallback || key),
}));
vi.mock('../../../static/js/utils/priorityTagHelpers.js', () => ({
  getPriorityTagSuggestions: vi.fn(),
}));
vi.mock('../../../static/js/components/shared/NsfwLevelSelector.js', () => ({
  getNsfwLevelSelector: vi.fn(),
}));
vi.mock('../../../static/js/utils/undoHelpers.js', () => ({
  handleUndoDelete: vi.fn(),
}));
vi.mock('../../../static/js/api/recipeApi.js', () => ({
  RecipeSidebarApiClient: class {},
  updateRecipeMetadata: vi.fn(),
  extractRecipeId: vi.fn(),
}));

describe('BulkManager wildcard activation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stateStub.currentPageType = 'wildcards';
    stateStub.bulkMode = false;
    stateStub.selectedModels.clear();
    stateStub.selectedModels.add('/models/a.txt');
    stateStub.selectedModels.add('/models/b.txt');
    resetAndReloadMock.mockResolvedValue(undefined);
  });

  afterEach(() => {
    stateStub.selectedModels.clear();
  });

  async function createBulkManager() {
    const { BulkManager } = await import('../../../static/js/managers/BulkManager.js');
    return new BulkManager();
  }

  it('activates the selection and synchronizes every successful card', async () => {
    bulkActivateMock.mockResolvedValue({
      success: true,
      success_count: 2,
      failure_count: 0,
      results: [
        { file_path: '/models/a.txt', success: true, active: true },
        { file_path: '/models/b.txt', success: true, active: true },
      ],
    });
    const bulk = await createBulkManager();

    await bulk.activateSelectedWildcards();

    expect(bulkActivateMock).toHaveBeenCalledWith(['/models/a.txt', '/models/b.txt']);
    expect(syncWildcardCardStateMock).toHaveBeenCalledTimes(2);
    expect(syncWildcardCardStateMock).toHaveBeenCalledWith('/models/a.txt', true);
    expect(syncWildcardCardStateMock).toHaveBeenCalledWith('/models/b.txt', true);
    expect(showToastMock).toHaveBeenCalledWith('wildcards.bulk.activated', { count: 2 }, 'success');
    expect(resetAndReloadMock).toHaveBeenCalledWith(false);
    expect(loadingManagerStub.showSimpleLoading).toHaveBeenCalled();
    expect(loadingManagerStub.hide).toHaveBeenCalled();
    expect(loadingManagerStub.restoreProgressBar).toHaveBeenCalled();
  });

  it('reports partial failure with the first conflict and refreshes once', async () => {
    bulkDeactivateMock.mockResolvedValue({
      success: true,
      success_count: 1,
      failure_count: 1,
      results: [
        { file_path: '/models/a.txt', success: true, active: false },
        {
          file_path: '/models/b.txt',
          success: false,
          conflicts: [{ key: 'shared/color' }],
        },
      ],
    });
    const bulk = await createBulkManager();

    await bulk.deactivateSelectedWildcards();

    expect(bulkDeactivateMock).toHaveBeenCalledWith(['/models/a.txt', '/models/b.txt']);
    expect(syncWildcardCardStateMock).toHaveBeenCalledTimes(1);
    expect(syncWildcardCardStateMock).toHaveBeenCalledWith('/models/a.txt', false);
    expect(showToastMock).toHaveBeenCalledWith(
      'wildcards.bulk.partial',
      { succeeded: 1, failed: 1, message: 'shared/color' },
      'warning',
    );
    expect(resetAndReloadMock).toHaveBeenCalledTimes(1);
  });

  it('shows the first error when every item fails', async () => {
    bulkActivateMock.mockResolvedValue({
      success: true,
      success_count: 0,
      failure_count: 2,
      results: [
        { file_path: '/models/a.txt', success: false, error: 'Missing file' },
        { file_path: '/models/b.txt', success: false, error: 'Missing file' },
      ],
    });
    const bulk = await createBulkManager();

    await bulk.activateSelectedWildcards();

    expect(syncWildcardCardStateMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'wildcards.bulk.failed',
      { message: 'Missing file' },
      'error',
    );
    expect(resetAndReloadMock).toHaveBeenCalledWith(false);
  });

  it('does not call the API without a selection', async () => {
    stateStub.selectedModels.clear();
    const bulk = await createBulkManager();

    await bulk.activateSelectedWildcards();

    expect(bulkActivateMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith('wildcards.bulk.noSelection', {}, 'warning');
    expect(resetAndReloadMock).not.toHaveBeenCalled();
  });
});
