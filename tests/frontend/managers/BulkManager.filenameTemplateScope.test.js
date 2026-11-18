import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const showToastMock = vi.fn();
const resetAndReloadMock = vi.fn();
const previewFilenameTemplateMock = vi.fn();
const applyFilenameTemplateMock = vi.fn();
const showConfirmationModalMock = vi.fn();

const stateStub = {
  currentPageType: 'loras',
  bulkMode: true,
  selectedModels: new Set(),
  loadingManager: {},
  global: { settings: { download_filename_templates: { lora: '{model_name}' } } },
};

const apiClientStub = {
  previewFilenameTemplate: previewFilenameTemplateMock,
  applyFilenameTemplate: applyFilenameTemplateMock,
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

vi.mock('../../../static/js/utils/modalUtils.js', () => ({
  showConfirmationModal: showConfirmationModalMock,
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
  summary: { total: 2, success: 2, skipped: 0, failures: 0, operation_type: 'filename_template' },
  planned_moves: [
    { model: 'A', from: '/models/abc123.safetensors', to: '/models/Alpha.safetensors' },
    { model: 'B', from: '/models/def456.safetensors', to: '/models/Beta.safetensors' },
  ],
};

describe('BulkManager scoped filename template apply', () => {
  let bulk;

  beforeEach(async () => {
    vi.clearAllMocks();
    stateStub.bulkMode = true;
    stateStub.currentPageType = 'loras';
    stateStub.selectedModels = new Set([
      '/models/abc123.safetensors',
      '/models/def456.safetensors',
    ]);
    previewFilenameTemplateMock.mockResolvedValue(previewResult);
    applyFilenameTemplateMock.mockResolvedValue(undefined);
    showConfirmationModalMock.mockResolvedValue(true);

    const { BulkManager } = await import('../../../static/js/managers/BulkManager.js');
    bulk = new BulkManager();
    bulk.toggleBulkMode = vi.fn(() => {
      stateStub.bulkMode = false;
    });
  });

  afterEach(() => {
    bulk?.autoOrganizePreviewModal?.close();
  });

  it('previews the selection, then renames only those files after confirmation', async () => {
    await bulk.applyFilenameTemplateToSelectedModels();

    expect(previewFilenameTemplateMock).toHaveBeenCalledWith({
      filePaths: ['/models/abc123.safetensors', '/models/def456.safetensors'],
    });
    expect(showConfirmationModalMock).toHaveBeenCalledTimes(1);

    expect(applyFilenameTemplateMock).toHaveBeenCalledWith([
      '/models/abc123.safetensors',
      '/models/def456.safetensors',
    ]);
    expect(bulk.toggleBulkMode).toHaveBeenCalledTimes(1);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('leaves the library untouched when the confirmation is cancelled', async () => {
    showConfirmationModalMock.mockResolvedValue(false);

    await bulk.applyFilenameTemplateToSelectedModels();

    expect(applyFilenameTemplateMock).not.toHaveBeenCalled();
    expect(resetAndReloadMock).not.toHaveBeenCalled();
    expect(bulk.toggleBulkMode).not.toHaveBeenCalled();
  });

  it('reports "nothing to rename" without confirmation when the dry run changes nothing', async () => {
    previewFilenameTemplateMock.mockResolvedValue({
      success: true,
      summary: { total: 2, success: 0, skipped: 2, failures: 0 },
      planned_moves: [],
    });

    await bulk.applyFilenameTemplateToSelectedModels();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.filenameTemplateNothingToRename',
      {},
      'info'
    );
    expect(showConfirmationModalMock).not.toHaveBeenCalled();
    expect(applyFilenameTemplateMock).not.toHaveBeenCalled();
  });

  it('surfaces preview failures as a toast without confirming', async () => {
    previewFilenameTemplateMock.mockRejectedValue(
      new Error('Another library operation is already running.')
    );

    await bulk.applyFilenameTemplateToSelectedModels();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.filenameTemplateFailed',
      { error: 'Another library operation is already running.' },
      'error'
    );
    expect(applyFilenameTemplateMock).not.toHaveBeenCalled();
  });

  it('does nothing on pages without a filename template', async () => {
    stateStub.currentPageType = 'workflows';

    await bulk.applyFilenameTemplateToSelectedModels();

    expect(previewFilenameTemplateMock).not.toHaveBeenCalled();
    expect(showConfirmationModalMock).not.toHaveBeenCalled();
  });

  it('requires a selection', async () => {
    stateStub.selectedModels = new Set();

    await bulk.applyFilenameTemplateToSelectedModels();

    expect(showToastMock).toHaveBeenCalledWith('toast.loras.noModelsSelected', {}, 'error');
    expect(previewFilenameTemplateMock).not.toHaveBeenCalled();
  });
});
