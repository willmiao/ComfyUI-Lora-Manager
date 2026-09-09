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

// The real RematchModalManager runs against the mocked modalManager; confirm
// is invoked explicitly, mirroring the user clicking Rematch in the dialog.
async function confirmRematchOptions() {
  const { rematchModalManager } = await import(
    '../../../static/js/managers/RematchModalManager.js'
  );
  return rematchModalManager.confirmOptions();
}

async function cancelRematchOptions() {
  const { rematchModalManager } = await import(
    '../../../static/js/managers/RematchModalManager.js'
  );
  rematchModalManager.cancelOptions();
}

describe('BulkManager.rematchSelectedRecipes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stateStub.currentPageType = 'recipes';
    stateStub.bulkMode = false;
    stateStub.selectedModels.clear();
    document.body.innerHTML = '';
  });

  async function createBulkManager() {
    const { BulkManager } = await import('../../../static/js/managers/BulkManager.js');
    return new BulkManager();
  }

  it('exposes the rematch action on the recipes page action config', async () => {
    const bulk = await createBulkManager();
    expect(bulk.actionConfig.recipes.rematchMetadata).toBe(true);
  });

  // Oracle R4-F1 pin: the summary modal must branch on `matched_entries` — a
  // blind `repaired` mirror would render 0 matched entries here.
  it('opens the summary modal when the bulk rematch succeeds', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');
    stateStub.selectedModels.add('/recipes/b.webp');
    stateStub.selectedModels.add('/recipes/c.webp');

    const rematchedRecipe = { file_path: '/recipes/a.webp', title: 'A' };
    rematchBulkModelsMock.mockResolvedValue({
      success: true,
      total: 3,
      rematched: 4,
      skipped: 1,
      errors: 0,
      matched_recipes: 2,
      matched_entries: 4,
      unresolved_recipes: 1,
      unresolved_entries: 1,
      recipes: [rematchedRecipe],
    });

    await bulk.rematchSelectedRecipes();
    await confirmRematchOptions();

    expect(rematchBulkModelsMock).toHaveBeenCalledWith(
      [
        '/recipes/a.webp',
        '/recipes/b.webp',
        '/recipes/c.webp',
      ],
      { relaxed: false }
    );
    // Non-noop runs open the summary modal instead of toasting.
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchComplete',
      expect.anything(),
      expect.anything()
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchSkipped',
      expect.anything(),
      expect.anything()
    );
    const summaryModal = document.getElementById('rematchSummaryModal');
    expect(summaryModal).not.toBeNull();
    // unresolved_entries > 0 forces the warning header
    expect(summaryModal.querySelector('.summary-header').classList.contains('warning')).toBe(true);
    expect(summaryModal.querySelector('.stat-card-success .stat-card-value').textContent).toBe('4');
    expect(summaryModal.querySelector('.stat-card-total .stat-card-value').textContent).toBe('1');
    expect(summaryModal.querySelector('.stat-card-failure .stat-card-value').textContent).toBe('0');
    expect(updateSingleItemMock).toHaveBeenCalledWith('/recipes/a.webp', rematchedRecipe);
    expect(loadingManagerStub.showSimpleLoading).toHaveBeenCalled();
    expect(loadingManagerStub.hide).toHaveBeenCalled();
    expect(loadingManagerStub.restoreProgressBar).toHaveBeenCalled();
  });

  it('opens the summary modal with a warning header when the bulk rematch has failures', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');
    stateStub.selectedModels.add('/recipes/b.webp');

    rematchBulkModelsMock.mockResolvedValue({
      success: true,
      total: 2,
      rematched: 3,
      skipped: 0,
      errors: 2,
      matched_recipes: 1,
      matched_entries: 3,
      unresolved_recipes: 0,
      unresolved_entries: 0,
      recipes: [],
    });

    await bulk.rematchSelectedRecipes();
    await confirmRematchOptions();

    const summaryModal = document.getElementById('rematchSummaryModal');
    expect(summaryModal).not.toBeNull();
    expect(summaryModal.querySelector('.summary-header').classList.contains('warning')).toBe(true);
    expect(summaryModal.querySelector('.stat-card-success .stat-card-value').textContent).toBe('3');
    expect(summaryModal.querySelector('.stat-card-failure .stat-card-value').textContent).toBe('2');
  });

  it('opens the summary modal with an error header when every selected recipe failed to rematch', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');
    stateStub.selectedModels.add('/recipes/b.webp');

    rematchBulkModelsMock.mockResolvedValue({
      success: true,
      total: 2,
      rematched: 0,
      skipped: 0,
      errors: 2,
      matched_recipes: 0,
      matched_entries: 0,
      unresolved_recipes: 0,
      unresolved_entries: 0,
      recipes: [],
    });

    await bulk.rematchSelectedRecipes();
    await confirmRematchOptions();

    const summaryModal = document.getElementById('rematchSummaryModal');
    expect(summaryModal).not.toBeNull();
    expect(summaryModal.querySelector('.summary-header').classList.contains('error')).toBe(true);
    expect(summaryModal.querySelector('.stat-card-failure .stat-card-value').textContent).toBe('2');
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchSkipped',
      expect.anything(),
      expect.anything()
    );
  });

  it('opens the summary modal when entries had no local match', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');
    stateStub.selectedModels.add('/recipes/b.webp');
    stateStub.selectedModels.add('/recipes/c.webp');

    rematchBulkModelsMock.mockResolvedValue({
      success: true,
      total: 3,
      rematched: 0,
      skipped: 2,
      errors: 0,
      matched_recipes: 0,
      matched_entries: 0,
      unresolved_recipes: 1,
      unresolved_entries: 2,
      recipes: [],
    });

    await bulk.rematchSelectedRecipes();
    await confirmRematchOptions();

    const summaryModal = document.getElementById('rematchSummaryModal');
    expect(summaryModal).not.toBeNull();
    expect(summaryModal.querySelector('.summary-header').classList.contains('warning')).toBe(true);
    expect(summaryModal.querySelector('.stat-card-success .stat-card-value').textContent).toBe('0');
    expect(summaryModal.querySelector('.stat-card-total .stat-card-value').textContent).toBe('2');
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchSkipped',
      expect.anything(),
      expect.anything()
    );
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
    await confirmRematchOptions();

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
    await confirmRematchOptions();

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
    await confirmRematchOptions();

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

  it('does not start the rematch until the options dialog is confirmed', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');

    await bulk.rematchSelectedRecipes();

    expect(rematchBulkModelsMock).not.toHaveBeenCalled();

    rematchBulkModelsMock.mockResolvedValue({
      success: true,
      total: 1,
      rematched: 1,
      skipped: 0,
      errors: 0,
      matched_recipes: 1,
      matched_entries: 1,
      recipes: [],
    });

    await confirmRematchOptions();

    expect(rematchBulkModelsMock).toHaveBeenCalledWith(['/recipes/a.webp'], { relaxed: false });
  });

  it('sends relaxed: true when the relaxed checkbox is checked', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');
    document.body.innerHTML = '<input type="checkbox" id="rematchOptionsRelaxed">';

    rematchBulkModelsMock.mockResolvedValue({
      success: true,
      total: 1,
      rematched: 0,
      skipped: 1,
      errors: 0,
      recipes: [],
    });

    await bulk.rematchSelectedRecipes();
    // The dialog resets the checkbox to unchecked on open; the user opts in.
    document.getElementById('rematchOptionsRelaxed').checked = true;
    await confirmRematchOptions();

    expect(rematchBulkModelsMock).toHaveBeenCalledWith(['/recipes/a.webp'], { relaxed: true });

    document.body.innerHTML = '';
  });

  it('starts nothing when the options dialog is cancelled', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');

    await bulk.rematchSelectedRecipes();
    await cancelRematchOptions();

    expect(rematchBulkModelsMock).not.toHaveBeenCalled();
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchComplete',
      expect.anything(),
      expect.anything()
    );
  });

  it('lists L4 filename matches in the summary modal with undo buttons', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/recipes/a.webp');

    const l4Matches = [
      { recipe_id: 'a', type: 'lora', entry: 'old.safetensors', file_name: 'new.safetensors', lora_index: 0 },
    ];
    rematchBulkModelsMock.mockResolvedValue({
      success: true,
      total: 1,
      rematched: 1,
      skipped: 0,
      errors: 0,
      matched_recipes: 1,
      matched_entries: 1,
      recipes: [],
      l4_matches: l4Matches,
    });

    await bulk.rematchSelectedRecipes();
    await confirmRematchOptions();

    const summaryModal = document.getElementById('rematchSummaryModal');
    expect(summaryModal).not.toBeNull();
    // L4 matches to review force the warning header
    expect(summaryModal.querySelector('.summary-header').classList.contains('warning')).toBe(true);
    expect(summaryModal.querySelector('.stat-card-skipped .stat-card-value').textContent).toBe('1');
    const rows = summaryModal.querySelectorAll('tr[data-l4-index]');
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain('old.safetensors');
    expect(rows[0].textContent).toContain('new.safetensors');
    expect(rows[0].querySelector('.rematch-undo-btn[data-action="undo-match"][data-index="0"]')).not.toBeNull();
  });
});
