import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';
import { renderTemplate } from '../utils/domFixtures.js';

const showToastMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));

const loadingManagerStub = {
  showSimpleLoading: vi.fn(),
  showCancelButton: vi.fn(),
  hide: vi.fn(),
};

const stateStub = {
  currentPageType: 'loras',
  bulkMode: false,
  selectedModels: new Set(),
  loadingManager: loadingManagerStub,
  virtualScroller: { updateSingleItem: vi.fn() },
  global: { settings: {} },
};

const saveModelMetadataMock = vi.fn();
const getModelApiClientMock = vi.fn(() => ({ saveModelMetadata: saveModelMetadataMock }));
const updateRecipeMetadataMock = vi.fn(() => Promise.resolve({ success: true }));
const showModalMock = vi.fn();
const closeModalMock = vi.fn();

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
  getNSFWLevelName: vi.fn(() => 'Unknown'),
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
  modalManager: { showModal: showModalMock, closeModal: closeModalMock },
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

import {
  setDynamicBaseModels,
  clearDynamicBaseModels,
} from '../../../static/js/utils/constants.js';

// jsdom does not implement scrollIntoView
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || vi.fn();

function getPickerContainer() {
  return document.getElementById('bulkBaseModelPicker');
}

function clickDropdownItem(value) {
  const item = Array.from(document.querySelectorAll('.base-model-dropdown-item'))
    .find((el) => el.dataset.value === value);
  expect(item, `dropdown item for "${value}"`).toBeTruthy();
  item.click();
}

describe('BulkManager bulk base model', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearDynamicBaseModels();
    stateStub.currentPageType = 'loras';
    stateStub.bulkMode = false;
    stateStub.selectedModels.clear();
    saveModelMetadataMock.mockResolvedValue(undefined);
    updateRecipeMetadataMock.mockResolvedValue({ success: true });
    renderTemplate('components/modals/bulk_base_model_modal.html');
  });

  afterEach(() => {
    clearDynamicBaseModels();
  });

  async function createBulkManager() {
    const { BulkManager } = await import('../../../static/js/managers/BulkManager.js');
    return new BulkManager();
  }

  it('warns when opening the modal without a selection', async () => {
    const bulk = await createBulkManager();
    bulk.showBulkBaseModelModal();

    expect(showToastMock).toHaveBeenCalledWith('toast.models.noModelsSelected', {}, 'warning');
    expect(showModalMock).not.toHaveBeenCalled();
  });

  it('initializes the picker inside the modal container', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/models/sdxl_a.safetensors');
    stateStub.selectedModels.add('/models/sdxl_b.safetensors');

    bulk.showBulkBaseModelModal();

    expect(document.getElementById('bulkBaseModelCount').textContent).toBe('2');
    const container = getPickerContainer();
    expect(container.querySelector('.base-model-search-wrapper')).toBeTruthy();
    expect(bulk.bulkBaseModelPicker).toBeTruthy();

    // Filename-based suggestions from the selected paths
    const suggestedHeader = container.querySelector('.base-model-dropdown-header.suggested-header');
    expect(suggestedHeader).toBeTruthy();
    const suggestedSection = suggestedHeader.closest('.base-model-dropdown-section');
    expect(suggestedSection.querySelector('.base-model-dropdown-item')?.dataset.value).toBe('SDXL 1.0');

    bulk.cleanupBulkBaseModelModal();
  });

  it('offers dynamic models such as MiniMax H3 under "Other (API)"', async () => {
    setDynamicBaseModels(['MiniMax H3'], new Date().toISOString());
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/models/test.safetensors');

    bulk.showBulkBaseModelModal();

    const headers = Array.from(document.querySelectorAll('.base-model-dropdown-header'));
    const otherHeader = headers.find((el) => el.textContent === 'Other (API)');
    expect(otherHeader).toBeTruthy();
    const section = otherHeader.closest('.base-model-dropdown-section');
    const values = Array.from(section.querySelectorAll('.base-model-dropdown-item'))
      .map((el) => el.dataset.value);
    expect(values).toContain('MiniMax H3');

    bulk.cleanupBulkBaseModelModal();
  });

  it('saves a dynamic base model through the model API on model pages', async () => {
    setDynamicBaseModels(['MiniMax H3'], new Date().toISOString());
    const bulk = await createBulkManager();
    stateStub.currentPageType = 'loras';
    stateStub.selectedModels.add('/models/a.safetensors');
    stateStub.selectedModels.add('/models/b.safetensors');

    bulk.showBulkBaseModelModal();
    clickDropdownItem('MiniMax H3');
    expect(bulk.bulkBaseModelValue).toBe('MiniMax H3');

    await bulk.saveBulkBaseModel();

    expect(closeModalMock).toHaveBeenCalledWith('bulkBaseModelModal');
    expect(saveModelMetadataMock).toHaveBeenCalledTimes(2);
    expect(saveModelMetadataMock).toHaveBeenCalledWith('/models/a.safetensors', { base_model: 'MiniMax H3' });
    expect(saveModelMetadataMock).toHaveBeenCalledWith('/models/b.safetensors', { base_model: 'MiniMax H3' });
    expect(updateRecipeMetadataMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.models.bulkBaseModelUpdateSuccess',
      { count: 2 },
      'success'
    );
  });

  it('saves through the recipe API when on the recipes page', async () => {
    const bulk = await createBulkManager();
    stateStub.currentPageType = 'recipes';
    stateStub.selectedModels.add('/recipes/test.webp');

    bulk.showBulkBaseModelModal();
    clickDropdownItem('SD 1.5');

    await bulk.saveBulkBaseModel();

    expect(updateRecipeMetadataMock).toHaveBeenCalledWith('/recipes/test.webp', { base_model: 'SD 1.5' });
    expect(updateRecipeMetadataMock).toHaveBeenCalledTimes(1);
    expect(saveModelMetadataMock).not.toHaveBeenCalled();
  });

  it('warns and skips saving when no base model is selected', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/models/a.safetensors');

    bulk.showBulkBaseModelModal();
    await bulk.saveBulkBaseModel();

    expect(showToastMock).toHaveBeenCalledWith('toast.models.baseModelNotSelected', {}, 'warning');
    expect(saveModelMetadataMock).not.toHaveBeenCalled();
    expect(closeModalMock).not.toHaveBeenCalledWith('bulkBaseModelModal');

    bulk.cleanupBulkBaseModelModal();
  });

  it('accepts arbitrary typed values in bulk mode, matching the single-model modal', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/models/a.safetensors');

    bulk.showBulkBaseModelModal();
    const input = document.querySelector('#bulkBaseModelPicker .base-model-search-input');
    input.value = 'Not A Listed Model';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 70));

    expect(bulk.bulkBaseModelValue).toBe('Not A Listed Model');

    await bulk.saveBulkBaseModel();

    expect(saveModelMetadataMock).toHaveBeenCalledWith('/models/a.safetensors', { base_model: 'Not A Listed Model' });
    expect(closeModalMock).toHaveBeenCalledWith('bulkBaseModelModal');

    bulk.cleanupBulkBaseModelModal();
  });

  it('uses a dedicated layout without the settings-page control wrapper', () => {
    const modal = document.getElementById('bulkBaseModelModal');
    expect(modal).toBeTruthy();
    expect(modal.querySelector('.setting-control')).toBeNull();
    expect(modal.querySelector('.metadata-edit-container')).toBeNull();
    const footer = modal.querySelector('.bulk-base-model-footer');
    expect(footer).toBeTruthy();
    // Buttons follow the app-wide modal-actions convention
    expect(footer.classList.contains('modal-actions')).toBe(true);
    expect(footer.querySelector('.primary-btn.bulk-save-base-model-btn')).toBeTruthy();
    expect(footer.querySelector('.cancel-btn')).toBeTruthy();
  });

  it('focuses the search input when the modal opens', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/models/a.safetensors');

    bulk.showBulkBaseModelModal();

    const input = document.querySelector('#bulkBaseModelPicker .base-model-search-input');
    expect(document.activeElement).toBe(input);

    bulk.cleanupBulkBaseModelModal();
  });

  it('reports partial failures', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/models/ok.safetensors');
    stateStub.selectedModels.add('/models/fail.safetensors');
    saveModelMetadataMock
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('boom'));

    bulk.showBulkBaseModelModal();
    clickDropdownItem('SDXL 1.0');
    await bulk.saveBulkBaseModel();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.models.bulkBaseModelUpdatePartial',
      { success: 1, failed: 1 },
      'warning'
    );
  });

  it('destroys the picker and clears the staged value on cleanup', async () => {
    const bulk = await createBulkManager();
    stateStub.selectedModels.add('/models/a.safetensors');

    bulk.showBulkBaseModelModal();
    clickDropdownItem('SDXL 1.0');
    expect(bulk.bulkBaseModelValue).toBe('SDXL 1.0');

    bulk.cleanupBulkBaseModelModal();

    expect(bulk.bulkBaseModelPicker).toBeNull();
    expect(bulk.bulkBaseModelValue).toBe('');
    expect(getPickerContainer().innerHTML).toBe('');
  });
});
