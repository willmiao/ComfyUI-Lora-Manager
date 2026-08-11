import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  UNDO_HELPERS_MODULE,
} = vi.hoisted(() => ({
  UNDO_HELPERS_MODULE: new URL('../../../static/js/utils/undoHelpers.js', import.meta.url).pathname,
}));

const showToastMock = vi.fn();
const showActionToastMock = vi.fn();
const handleUndoDeleteMock = vi.fn();
const resetAndReloadMock = vi.fn();
const bulkDeleteModelsMock = vi.fn();
const recipeBulkDeleteModelsMock = vi.fn();

const loadingManagerStub = {
  showSimpleLoading: vi.fn(),
  hide: vi.fn(),
  restoreProgressBar: vi.fn(),
};

const stateStub = {
  currentPageType: 'loras',
  bulkMode: false,
  selectedModels: new Set(),
  loadingManager: loadingManagerStub,
  virtualScroller: { removeItemByFilePath: vi.fn() },
  global: { settings: {} },
};

vi.mock('../../../static/js/state/index.js', () => ({
  state: stateStub,
  getCurrentPageState: vi.fn(),
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  showActionToast: showActionToastMock,
  copyToClipboard: vi.fn(),
  sendLoraToWorkflow: vi.fn(),
  sendEmbeddingToWorkflow: vi.fn(),
  buildLoraSyntax: vi.fn(),
  getNSFWLevelName: vi.fn(),
}));

vi.mock(UNDO_HELPERS_MODULE, () => ({
  handleUndoDelete: handleUndoDeleteMock,
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: vi.fn(() => ({ bulkDeleteModels: bulkDeleteModelsMock })),
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  RecipeSidebarApiClient: class {
    constructor() {
      this.bulkDeleteModels = recipeBulkDeleteModelsMock;
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
  translate: vi.fn((key) => key),
}));

vi.mock('../../../static/js/utils/priorityTagHelpers.js', () => ({
  getPriorityTagSuggestions: vi.fn(),
}));

vi.mock('../../../static/js/components/shared/NsfwLevelSelector.js', () => ({
  getNsfwLevelSelector: vi.fn(),
}));

describe('BulkManager.confirmBulkDelete undo flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stateStub.currentPageType = 'loras';
    stateStub.bulkMode = false;
    stateStub.selectedModels.clear();
    stateStub.selectedModels.add('/models/a.safetensors');
    stateStub.selectedModels.add('/models/b.safetensors');
    handleUndoDeleteMock.mockResolvedValue(true);
  });

  afterEach(() => {
    delete window.recipeManager;
    delete window.modelDuplicatesManager;
  });

  async function createBulkManager() {
    const { BulkManager } = await import('../../../static/js/managers/BulkManager.js');
    return new BulkManager();
  }

  function lastActionToastOptions() {
    const call = showActionToastMock.mock.calls[showActionToastMock.mock.calls.length - 1];
    return call[3];
  }

  it('shows one action toast for the merged batch id and undoes it with a model refresh', async () => {
    bulkDeleteModelsMock.mockResolvedValue({
      success: true,
      deleted_count: 2,
      failed_count: 0,
      errors: [],
      batch_id: 'merged-1',
      batch_ids: null,
    });

    const bulk = await createBulkManager();
    await bulk.confirmBulkDelete();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    expect(showActionToastMock).toHaveBeenCalledWith(
      'toast.undo.deletedBulk',
      { count: 2 },
      'success',
      expect.objectContaining({
        actionText: 'toast.undo.action',
        onAction: expect.any(Function),
      })
    );
    // The legacy success and cancelled toasts must NOT fire
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.models.deletedSuccessfully',
      expect.anything(),
      expect.anything()
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.api.operationCancelled',
      expect.anything(),
      expect.anything()
    );

    lastActionToastOptions().onAction();

    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(1);
    expect(handleUndoDeleteMock).toHaveBeenCalledWith('merged-1', expect.any(Function));

    // The undo refresh targets the model library
    const refreshFn = handleUndoDeleteMock.mock.calls[0][1];
    refreshFn();
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('keeps the legacy success toast when both batch fields are null', async () => {
    bulkDeleteModelsMock.mockResolvedValue({
      success: true,
      deleted_count: 2,
      failed_count: 0,
      errors: [],
      batch_id: null,
      batch_ids: null,
    });

    const bulk = await createBulkManager();
    await bulk.confirmBulkDelete();

    expect(showActionToastMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.models.deletedSuccessfully',
      { count: 2, type: 'model' },
      'success'
    );
  });

  it('undoes the batch_ids fallback sequentially with exactly one final refresh and restored toast', async () => {
    bulkDeleteModelsMock.mockResolvedValue({
      success: true,
      deleted_count: 2,
      failed_count: 0,
      errors: [],
      batch_id: null,
      batch_ids: ['id-1', 'id-2'],
    });

    const bulk = await createBulkManager();
    await bulk.confirmBulkDelete();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    expect(showActionToastMock).toHaveBeenCalledWith(
      'toast.undo.deletedBulk',
      { count: 2 },
      'success',
      expect.objectContaining({ onAction: expect.any(Function) })
    );

    await lastActionToastOptions().onAction();

    // Sequential suppressed undos in order
    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(2);
    expect(handleUndoDeleteMock.mock.calls[0]).toEqual(['id-1', null, { showToast: false, refresh: false }]);
    expect(handleUndoDeleteMock.mock.calls[1]).toEqual(['id-2', null, { showToast: false, refresh: false }]);

    // Exactly ONE final refresh and ONE restored toast
    expect(resetAndReloadMock).toHaveBeenCalledTimes(1);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.undo.restored', {}, 'success');
  });

  it('stops the fallback loop on the first failure and skips the final refresh', async () => {
    bulkDeleteModelsMock.mockResolvedValue({
      success: true,
      deleted_count: 2,
      failed_count: 0,
      errors: [],
      batch_id: null,
      batch_ids: ['id-1', 'id-2', 'id-3'],
    });
    handleUndoDeleteMock
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false);

    const bulk = await createBulkManager();
    await bulk.confirmBulkDelete();
    await lastActionToastOptions().onAction();

    // The loop stops at the failing second id — the third is never attempted
    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(2);
    expect(handleUndoDeleteMock.mock.calls[1][0]).toBe('id-2');

    // The suppressed undo shows no error toast itself — the loop re-shows it
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.undo.failed', { error: '' }, 'error');

    // No final refresh, no restored toast
    expect(resetAndReloadMock).not.toHaveBeenCalled();
    expect(showToastMock).not.toHaveBeenCalledWith('toast.undo.restored', {}, 'success');
  });

  it('shows the action toast for a cancelled bulk that staged a subset (batch_id)', async () => {
    bulkDeleteModelsMock.mockResolvedValue({
      success: true,
      deleted_count: 1,
      failed_count: 0,
      errors: [],
      batch_id: 'partial-1',
      batch_ids: null,
    });

    const bulk = await createBulkManager();
    await bulk.confirmBulkDelete();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    expect(showActionToastMock).toHaveBeenCalledWith(
      'toast.undo.deletedBulk',
      { count: 1 },
      'success',
      expect.objectContaining({ onAction: expect.any(Function) })
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.api.operationCancelled',
      expect.anything(),
      expect.anything()
    );
  });

  it('shows the action toast for a cancelled bulk with the batch_ids fallback', async () => {
    bulkDeleteModelsMock.mockResolvedValue({
      success: true,
      deleted_count: 1,
      failed_count: 0,
      errors: [],
      batch_id: null,
      batch_ids: ['partial-1'],
    });

    const bulk = await createBulkManager();
    await bulk.confirmBulkDelete();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.api.operationCancelled',
      expect.anything(),
      expect.anything()
    );
  });

  it('keeps the cancelled toast when the user aborted and nothing was staged', async () => {
    bulkDeleteModelsMock.mockResolvedValue({ success: false, cancelled: true });

    const bulk = await createBulkManager();
    await bulk.confirmBulkDelete();

    expect(showToastMock).toHaveBeenCalledWith('toast.api.operationCancelled', {}, 'info');
    expect(showActionToastMock).not.toHaveBeenCalled();
  });

  it('refreshes recipes through window.recipeManager when undoing a recipe bulk delete', async () => {
    stateStub.currentPageType = 'recipes';
    stateStub.selectedModels.clear();
    stateStub.selectedModels.add('/recipes/a.webp');
    const loadRecipesMock = vi.fn();
    window.recipeManager = { loadRecipes: loadRecipesMock };

    recipeBulkDeleteModelsMock.mockResolvedValue({
      success: true,
      deleted_count: 1,
      failed_count: 0,
      errors: [],
      batch_id: 'recipe-batch-1',
      batch_ids: null,
    });

    const bulk = await createBulkManager();
    await bulk.confirmBulkDelete();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    lastActionToastOptions().onAction();

    expect(handleUndoDeleteMock).toHaveBeenCalledWith('recipe-batch-1', expect.any(Function));
    const refreshFn = handleUndoDeleteMock.mock.calls[0][1];
    refreshFn();
    expect(loadRecipesMock).toHaveBeenCalledWith(true);
    expect(resetAndReloadMock).not.toHaveBeenCalled();
  });
});

describe('BulkManager.showBulkDeleteModal delay-activate', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    stateStub.currentPageType = 'loras';
    stateStub.selectedModels.clear();
    stateStub.selectedModels.add('/models/a.safetensors');
    document.body.innerHTML = `
      <div id="bulkDeleteModal" class="modal delete-modal">
        <h2></h2>
        <p class="delete-message"></p>
        <div class="delete-model-info"><p></p></div>
        <button class="cancel-btn">Cancel</button>
        <button class="delete-btn">Delete</button>
      </div>
    `;
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('opens with the delete button disabled and enables it after 1500ms', async () => {
    const { BulkManager } = await import('../../../static/js/managers/BulkManager.js');
    const bulk = new BulkManager();
    bulk.showBulkDeleteModal();

    const deleteBtn = document.querySelector('#bulkDeleteModal .delete-btn');
    expect(deleteBtn.disabled).toBe(true);

    deleteBtn.click();
    expect(bulkDeleteModelsMock).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1500);
    expect(deleteBtn.disabled).toBe(false);
  });
});
