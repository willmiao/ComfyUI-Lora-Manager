import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const copyToClipboardMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));

const loadingManagerStub = {
  showSimpleLoading: vi.fn(),
  hide: vi.fn(),
  show: vi.fn(),
  restoreProgressBar: vi.fn(),
};

const stateStub = {
  global: { settings: {}, loadingManager: loadingManagerStub },
  loadingManager: loadingManagerStub,
  virtualScroller: { updateSingleItem: vi.fn() },
};

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  copyToClipboard: copyToClipboardMock,
  sendLoraToWorkflow: vi.fn(),
  sendModelPathToWorkflow: vi.fn(),
  openCivitaiByMetadata: vi.fn(),
  stripLoraTags: vi.fn((text) => text),
  sendPromptToWorkflow: vi.fn(),
  sendGenParamsToWorkflow: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: translateMock,
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state: stateStub,
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
  setSessionItem: vi.fn(),
  removeSessionItem: vi.fn(),
  getStorageItem: vi.fn(() => null),
  setStorageItem: vi.fn(),
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  fetchRecipeDetails: vi.fn(),
  updateRecipeMetadata: vi.fn(() => Promise.resolve({ success: true })),
  sendRecipeWorkflow: vi.fn(),
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings',
  },
}));

async function flushAsyncTasks() {
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function createRecipeModal() {
  const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
  return new RecipeModal();
}

describe('RecipeModal copy recipe syntax', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = `
      <div class="recipe-header-actions" id="recipeHeaderActions">
        <button class="modal-send-btn" id="sendRecipeBtn"><i class="fas fa-paper-plane"></i></button>
        <button class="modal-copy-btn" id="copyRecipeSyntaxBtn"><i class="fas fa-copy"></i></button>
      </div>
    `;
    global.fetch = vi.fn();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete global.fetch;
  });

  it('copies the recipe syntax when the header copy button is clicked', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.recipeId = 'recipe-1';
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, syntax: '<lora:foo:1>' }),
    });

    recipeModal.setupCopyButtons();
    document.getElementById('copyRecipeSyntaxBtn').dispatchEvent(new Event('click', { bubbles: true }));
    await flushAsyncTasks();

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe-1/syntax');
    expect(copyToClipboardMock).toHaveBeenCalledWith('<lora:foo:1>', 'Recipe syntax copied to clipboard');
  });

  it('shows an error toast and skips the API call without a recipe ID', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.recipeId = null;

    await recipeModal.fetchAndCopyRecipeSyntax();

    expect(global.fetch).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith('toast.recipes.noRecipeId', {}, 'error');
  });

  it('shows an error toast when the backend returns no syntax', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const recipeModal = await createRecipeModal();
    recipeModal.recipeId = 'recipe-1';
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: false, error: 'no syntax' }),
    });

    await recipeModal.fetchAndCopyRecipeSyntax();

    expect(copyToClipboardMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.copyFailed',
      { message: 'no syntax' },
      'error'
    );
    errorSpy.mockRestore();
  });
});
