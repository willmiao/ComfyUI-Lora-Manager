import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const showToastMock = vi.fn();
const resetAndReloadMock = vi.fn();
const previewAutoOrganizeModelsMock = vi.fn();
const autoOrganizeModelsMock = vi.fn();

const stateStub = {
  currentPageType: 'loras',
  bulkMode: true,
  selectedModels: new Set(),
  loadingManager: {},
  global: { settings: {} },
};

const apiClientStub = {
  previewAutoOrganizeModels: previewAutoOrganizeModelsMock,
  autoOrganizeModels: autoOrganizeModelsMock,
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

vi.mock('../../../static/js/utils/undoHelpers.js', () => ({
  handleUndoDelete: vi.fn(),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: vi.fn(() => apiClientStub),
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  RecipeSidebarApiClient: class {},
  updateRecipeMetadata: vi.fn(),
  extractRecipeId: vi.fn(),
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: { LORA: 'loras', CHECKPOINT: 'checkpoints', EMBEDDING: 'embeddings', WORKFLOW: 'workflows' },
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

const previewResult = {
  success: true,
  dry_run: true,
  summary: { total: 2, success: 1, skipped: 1, failures: 0, operation_type: 'bulk', organization_type: 'structured', path_template: '{base_model}' },
  planned_moves: [{ model: 'A', from: '/models/a.safetensors', to: '/models/SDXL/a.safetensors', status: 'planned_move', reason: 'path_template' }],
  results: [{ model: 'B', success: false, status: 'skipped', reason: 'already_organized', message: 'Already in the correct location', from: '/models/b.safetensors', to: '/models/b.safetensors' }],
};

describe('BulkManager auto-organize preview flow', () => {
  let bulk;

  beforeEach(async () => {
    vi.clearAllMocks();
    stateStub.bulkMode = true;
    stateStub.selectedModels = new Set(['/models/a.safetensors', '/models/b.safetensors']);
    previewAutoOrganizeModelsMock.mockResolvedValue(previewResult);
    autoOrganizeModelsMock.mockResolvedValue(undefined);
    const { BulkManager } = await import('../../../static/js/managers/BulkManager.js');
    bulk = new BulkManager();
    bulk.toggleBulkMode = vi.fn(() => {
      stateStub.bulkMode = false;
    });
  });

  afterEach(() => {
    bulk?.autoOrganizePreviewModal?.close();
  });

  it('previews the captured selection and only executes after confirmation', async () => {
    await bulk.autoOrganizeSelectedModels();

    expect(previewAutoOrganizeModelsMock).toHaveBeenCalledWith([
      '/models/a.safetensors',
      '/models/b.safetensors',
    ]);
    expect(autoOrganizeModelsMock).not.toHaveBeenCalled();
    expect(resetAndReloadMock).not.toHaveBeenCalled();
    expect(bulk.toggleBulkMode).not.toHaveBeenCalled();
    expect(stateStub.selectedModels.size).toBe(2);

    document.querySelector('[data-action="apply"]').click();

    await vi.waitFor(() => expect(bulk.toggleBulkMode).toHaveBeenCalledTimes(1));
    expect(autoOrganizeModelsMock).toHaveBeenCalledWith([
      '/models/a.safetensors',
      '/models/b.safetensors',
    ]);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('keeps preview failures inside the modal and retries without executing', async () => {
    previewAutoOrganizeModelsMock
      .mockRejectedValueOnce(new Error('Another organize is running'))
      .mockResolvedValueOnce(previewResult);

    await bulk.autoOrganizeSelectedModels();

    expect(document.querySelector('[role="alert"]').textContent).toContain('Another organize is running');
    expect(autoOrganizeModelsMock).not.toHaveBeenCalled();
    expect(stateStub.selectedModels.size).toBe(2);

    document.querySelector('[data-action="refresh"]').click();

    await vi.waitFor(() => expect(document.querySelector('[data-action="apply"]')).not.toBeNull());
    expect(previewAutoOrganizeModelsMock).toHaveBeenCalledTimes(2);
    expect(autoOrganizeModelsMock).not.toHaveBeenCalled();
  });

  it('closing the preview preserves selection and skips execution', async () => {
    await bulk.autoOrganizeSelectedModels();

    document.querySelector('.cancel-btn[data-action="close-modal"]').click();

    expect(document.getElementById('autoOrganizePreviewModal')).toBeNull();
    expect(stateStub.selectedModels.size).toBe(2);
    expect(stateStub.bulkMode).toBe(true);
    expect(autoOrganizeModelsMock).not.toHaveBeenCalled();
    expect(resetAndReloadMock).not.toHaveBeenCalled();
  });
});
