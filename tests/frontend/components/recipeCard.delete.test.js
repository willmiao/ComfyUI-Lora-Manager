import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  RECIPE_CARD_MODULE,
  UI_HELPERS_MODULE,
  RECIPE_API_MODULE,
  MODEL_CARD_MODULE,
  MODAL_MANAGER_MODULE,
  STATE_MODULE,
  BULK_MANAGER_MODULE,
  CONSTANTS_MODULE,
  I18N_MODULE,
  UNDO_HELPERS_MODULE,
} = vi.hoisted(() => ({
  RECIPE_CARD_MODULE: new URL('../../../static/js/components/RecipeCard.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  RECIPE_API_MODULE: new URL('../../../static/js/api/recipeApi.js', import.meta.url).pathname,
  MODEL_CARD_MODULE: new URL('../../../static/js/components/shared/ModelCard.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  BULK_MANAGER_MODULE: new URL('../../../static/js/managers/BulkManager.js', import.meta.url).pathname,
  CONSTANTS_MODULE: new URL('../../../static/js/utils/constants.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  UNDO_HELPERS_MODULE: new URL('../../../static/js/utils/undoHelpers.js', import.meta.url).pathname,
}));

const showToastMock = vi.fn();
const showActionToastMock = vi.fn();
const handleUndoDeleteMock = vi.fn();
const translateMock = vi.fn((key) => key);
const closeModalMock = vi.fn();
const removeItemByFilePathMock = vi.fn();

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
  showActionToast: showActionToastMock,
  copyToClipboard: vi.fn(),
  sendLoraToWorkflow: vi.fn(),
}));

vi.mock(RECIPE_API_MODULE, () => ({
  updateRecipeMetadata: vi.fn(),
}));

vi.mock(MODEL_CARD_MODULE, () => ({
  configureModelCardVideo: vi.fn(),
}));

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: {
    showModal: vi.fn(),
    closeModal: closeModalMock,
  },
}));

vi.mock(STATE_MODULE, () => ({
  state: {
    virtualScroller: {
      removeItemByFilePath: removeItemByFilePathMock,
    },
  },
  getCurrentPageState: vi.fn(() => ({})),
}));

vi.mock(BULK_MANAGER_MODULE, () => ({
  bulkManager: {},
}));

vi.mock(CONSTANTS_MODULE, () => ({
  NSFW_LEVELS: {},
  getBaseModelAbbreviation: vi.fn(),
  getMatureBlurThreshold: vi.fn(),
}));

vi.mock(I18N_MODULE, () => ({
  translate: translateMock,
}));

vi.mock(UNDO_HELPERS_MODULE, () => ({
  handleUndoDelete: handleUndoDeleteMock,
}));

function setupDeleteModal() {
  document.body.innerHTML = `
    <div id="deleteModal" data-recipe-id="recipe-1" data-file-path="/recipes/r1.json">
      <button class="delete-btn">Delete</button>
    </div>
  `;
  const deleteModal = document.getElementById('deleteModal');
  // jsdom maps data-file-path to dataset.filePath
  deleteModal.dataset.recipeId = 'recipe-1';
  deleteModal.dataset.filePath = '/recipes/r1.json';
  return deleteModal;
}

async function flushPromises() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('RecipeCard confirmDeleteRecipe undo flow', () => {
  beforeEach(() => {
    showToastMock.mockReset();
    showActionToastMock.mockReset();
    handleUndoDeleteMock.mockReset();
    translateMock.mockClear();
    closeModalMock.mockReset();
    removeItemByFilePathMock.mockReset();
    setupDeleteModal();
    window.recipeManager = { loadRecipes: vi.fn() };
  });

  afterEach(() => {
    delete global.fetch;
    delete window.recipeManager;
    document.body.innerHTML = '';
  });

  async function createCard() {
    const { RecipeCard } = await import(RECIPE_CARD_MODULE);
    const card = Object.create(RecipeCard.prototype);
    card.recipe = { id: 'recipe-1', title: 'My Recipe', file_path: '/recipes/r1.json' };
    return card;
  }

  it('shows the undo action toast and wires undo to handleUndoDelete + loadRecipes(true)', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: 'deleted', batch_id: 'recipe-batch-1' }),
    });

    const card = await createCard();
    card.confirmDeleteRecipe();
    await flushPromises();

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe-1', expect.objectContaining({
      method: 'DELETE',
    }));
    // No legacy success toast when the delete was staged
    expect(showToastMock).not.toHaveBeenCalledWith('toast.recipes.deletedSuccessfully', {}, 'success');
    expect(showActionToastMock).toHaveBeenCalledTimes(1);

    const [key, params, type, options] = showActionToastMock.mock.calls[0];
    expect(key).toBe('toast.undo.deleted');
    expect(params).toEqual({ name: 'My Recipe' });
    expect(type).toBe('success');
    expect(options.actionText).toBe('toast.undo.action');

    options.onAction();
    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(1);
    const [batchId, refreshFn] = handleUndoDeleteMock.mock.calls[0];
    expect(batchId).toBe('recipe-batch-1');

    refreshFn();
    expect(window.recipeManager.loadRecipes).toHaveBeenCalledWith(true);

    expect(removeItemByFilePathMock).toHaveBeenCalledWith('/recipes/r1.json');
    expect(closeModalMock).toHaveBeenCalledWith('deleteModal');
  });

  it('keeps the legacy success toast when the delete was not staged', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: 'deleted' }),
    });

    const card = await createCard();
    card.confirmDeleteRecipe();
    await flushPromises();

    expect(showToastMock).toHaveBeenCalledWith('toast.recipes.deletedSuccessfully', {}, 'success');
    expect(showActionToastMock).not.toHaveBeenCalled();
    expect(closeModalMock).toHaveBeenCalledWith('deleteModal');
  });

  it('shows the failure toast when the server rejects the delete', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false });

    const card = await createCard();
    const deleteBtn = document.querySelector('.delete-btn');
    card.confirmDeleteRecipe();
    await flushPromises();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.deleteFailed',
      expect.objectContaining({ message: expect.any(String) }),
      'error'
    );
    expect(deleteBtn.disabled).toBe(false);
    expect(deleteBtn.textContent).toBe('Delete');
  });
});
