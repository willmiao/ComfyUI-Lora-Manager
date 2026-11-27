import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const copyToClipboardMock = vi.fn();
const sendLoraToWorkflowMock = vi.fn();
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
  sendLoraToWorkflow: sendLoraToWorkflowMock,
  sendModelPathToWorkflow: vi.fn(),
  openCivitaiByMetadata: vi.fn(),
  stripLoraTags: vi.fn((text) => text),
  sendPromptToWorkflow: vi.fn(),
  sendGenParamsToWorkflow: vi.fn(),
  isUnresolvableDownloadError: vi.fn(() => false),
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
  extractRecipeId: vi.fn(() => null),
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings',
  },
}));

function recipeFixture() {
  return {
    id: 'recipe-1',
    loras: [
      {
        modelName: 'Foo',
        inLibrary: true,
        strength: 0.8,
        hash: 'hash-foo',
        modelVersionName: 'v1',
        baseModel: 'Illustrious',
      },
      {
        modelName: 'Gone',
        inLibrary: false,
        isDeleted: true,
        strength: 1,
        hash: 'hash-gone',
      },
    ],
  };
}

async function flushAsyncTasks() {
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

const createdModals = [];

async function createRecipeModal() {
  const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
  const recipeModal = new RecipeModal();
  createdModals.push(recipeModal);
  return recipeModal;
}

async function renderResources(recipe = recipeFixture()) {
  const recipeModal = await createRecipeModal();
  recipeModal.recipeId = 'recipe-1';
  recipeModal.currentRecipe = recipe;
  recipeModal.syncResourcesSection(recipe);
  // The modal wires actions from a deferred callback; wire synchronously so
  // the test does not depend on the delay.
  recipeModal.setupLoraItemActions();
  recipeModal.setupLoraItemsClickable();
  return { recipeModal, rows: document.querySelectorAll('.recipe-lora-item') };
}

describe('RecipeModal per-LoRA row actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = `
      <div id="recipeLorasCount"></div>
      <div class="recipe-loras-list" id="recipeLorasList"></div>
    `;
    global.fetch = vi.fn();
  });

  afterEach(() => {
    createdModals.forEach((recipeModal) => recipeModal.dispose());
    createdModals.length = 0;
    document.body.innerHTML = '';
    delete global.fetch;
  });

  it('renders send then copy on in-library rows only', async () => {
    const { rows } = await renderResources();

    expect(rows).toHaveLength(2);

    const quickActions = rows[0].querySelectorAll('.recipe-lora-quick-action');
    expect(quickActions).toHaveLength(2);
    // Order mirrors the prompt/params header buttons: send, then copy.
    expect(quickActions[0].classList.contains('lora-send')).toBe(true);
    expect(quickActions[1].classList.contains('lora-copy')).toBe(true);

    // Missing/deleted entries keep an empty remediation row instead.
    expect(rows[1].querySelector('.recipe-lora-quick-actions')).toBeNull();
  });

  it('copies a single LoRA syntax without navigating to the library', async () => {
    const { recipeModal, rows } = await renderResources();
    const navigateSpy = vi.spyOn(recipeModal, 'navigateToLorasPage');
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, syntax: '<lora:foo:0.8>' }),
    });

    rows[0].querySelector('.lora-copy').click();
    await flushAsyncTasks();

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe-1/syntax?index=0');
    expect(copyToClipboardMock).toHaveBeenCalledWith(
      '<lora:foo:0.8>',
      'LoRA syntax copied to clipboard'
    );
    expect(navigateSpy).not.toHaveBeenCalled();
    navigateSpy.mockRestore();
  });

  it('sends a single LoRA syntax to the workflow', async () => {
    const { recipeModal, rows } = await renderResources();
    const navigateSpy = vi.spyOn(recipeModal, 'navigateToLorasPage');
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, syntax: '<lora:foo:0.8>' }),
    });

    rows[0].querySelector('.lora-send').click();
    await flushAsyncTasks();

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe-1/syntax?index=0');
    expect(sendLoraToWorkflowMock).toHaveBeenCalledWith('<lora:foo:0.8>', false, 'lora');
    expect(navigateSpy).not.toHaveBeenCalled();
    navigateSpy.mockRestore();
  });

  it('keeps keyboard activation of the row actions from navigating', async () => {
    const { recipeModal, rows } = await renderResources();
    const navigateSpy = vi.spyOn(recipeModal, 'navigateToLorasPage');

    rows[0]
      .querySelector('.lora-copy')
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(navigateSpy).not.toHaveBeenCalled();
    navigateSpy.mockRestore();
  });

  it('reports a failed single-LoRA copy', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { rows } = await renderResources();
    global.fetch.mockResolvedValue({ ok: false, statusText: 'Bad Request' });

    rows[0].querySelector('.lora-copy').click();
    await flushAsyncTasks();

    expect(copyToClipboardMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.copyLoraFailed',
      { message: 'Failed to get LoRA syntax: Bad Request' },
      'error'
    );
    errorSpy.mockRestore();
  });
});
