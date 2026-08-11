import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  RECIPE_CARD_MODULE,
  UI_HELPERS_MODULE,
  RECIPE_API_MODULE,
  MODEL_CARD_MODULE,
  MODAL_MANAGER_MODULE,
  BULK_MANAGER_MODULE,
  I18N_MODULE,
  UNDO_HELPERS_MODULE,
  API_FACTORY_MODULE,
  STATE_MODULE,
} = vi.hoisted(() => ({
  RECIPE_CARD_MODULE: new URL('../../../static/js/components/RecipeCard.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  RECIPE_API_MODULE: new URL('../../../static/js/api/recipeApi.js', import.meta.url).pathname,
  MODEL_CARD_MODULE: new URL('../../../static/js/components/shared/ModelCard.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
  BULK_MANAGER_MODULE: new URL('../../../static/js/managers/BulkManager.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  UNDO_HELPERS_MODULE: new URL('../../../static/js/utils/undoHelpers.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
}));

const showModalMock = vi.fn();
const closeModalMock = vi.fn();

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
  showActionToast: vi.fn(),
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
    showModal: showModalMock,
    closeModal: closeModalMock,
  },
}));

vi.mock(BULK_MANAGER_MODULE, () => ({
  bulkManager: {},
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key) => key),
}));

vi.mock(UNDO_HELPERS_MODULE, () => ({
  handleUndoDelete: vi.fn(),
}));

// modalUtils.js is intentionally NOT mocked — its real armDeleteButton drives
// the delay-activate behavior under test. Its own imports are mocked below.
vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(),
  resetAndReload: vi.fn(),
}));

describe('RecipeCard delete confirmation delay-activate', () => {
  let capturedOnClose;

  beforeEach(async () => {
    vi.useFakeTimers();
    showModalMock.mockReset();
    closeModalMock.mockReset();
    capturedOnClose = null;
    document.body.innerHTML = '<div id="deleteModal" class="modal delete-modal"></div>';
    showModalMock.mockImplementation((id, content, onClose) => {
      if (content) {
        document.getElementById(id).innerHTML = content;
      }
      capturedOnClose = onClose;
    });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });
    window.recipeManager = { loadRecipes: vi.fn() };
    const { state } = await import(STATE_MODULE);
    state.virtualScroller = { removeItemByFilePath: vi.fn() };
  });

  afterEach(() => {
    vi.useRealTimers();
    delete global.fetch;
    delete window.recipeManager;
    document.body.innerHTML = '';
  });

  async function createCard() {
    const { RecipeCard } = await import(RECIPE_CARD_MODULE);
    const card = Object.create(RecipeCard.prototype);
    card.recipe = { id: 'recipe-1', title: 'My Recipe', file_path: '/recipes/r1.json', file_url: '/preview.png' };
    return card;
  }

  it('opens with a disabled delete button that ignores clicks until 1500ms elapse', async () => {
    const card = await createCard();
    card.showDeleteConfirmation();

    const deleteBtn = document.querySelector('#deleteModal .delete-btn');
    expect(deleteBtn.disabled).toBe(true);

    deleteBtn.click();
    expect(global.fetch).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1500);
    expect(deleteBtn.disabled).toBe(false);

    deleteBtn.click();
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/recipe/recipe-1',
      expect.objectContaining({ method: 'DELETE' })
    );
  });

  it('clears the pending arm timer when the modal closes during the countdown', async () => {
    const card = await createCard();
    card.showDeleteConfirmation();

    const deleteBtn = document.querySelector('#deleteModal .delete-btn');
    expect(deleteBtn.disabled).toBe(true);

    vi.advanceTimersByTime(700);
    capturedOnClose();

    expect(deleteBtn.disabled).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('re-arms a full 1500ms countdown when the modal is reopened', async () => {
    const card = await createCard();
    card.showDeleteConfirmation();

    vi.advanceTimersByTime(1400);
    capturedOnClose();

    card.showDeleteConfirmation();
    const deleteBtn = document.querySelector('#deleteModal .delete-btn');
    expect(deleteBtn.disabled).toBe(true);

    vi.advanceTimersByTime(1499);
    expect(deleteBtn.disabled).toBe(true);

    vi.advanceTimersByTime(1);
    expect(deleteBtn.disabled).toBe(false);
  });
});
