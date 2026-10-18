import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
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

const sendRecipeWorkflowMock = vi.fn();
const fetchRecipeDetailsMock = vi.fn();
const updateRecipeMetadataMock = vi.fn(() => Promise.resolve({ success: true }));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  copyToClipboard: vi.fn(),
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
  fetchRecipeDetails: fetchRecipeDetailsMock,
  updateRecipeMetadata: updateRecipeMetadataMock,
  sendRecipeWorkflow: sendRecipeWorkflowMock,
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

describe('RecipeModal send workflow to ComfyUI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = `
      <div class="recipe-header-actions" id="recipeHeaderActions"></div>
    `;
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  describe('syncHeaderActions', () => {
    it('inserts the send-workflow button when the recipe embeds a workflow', async () => {
      const recipeModal = await createRecipeModal();
      recipeModal.currentRecipe = { has_workflow: true };
      recipeModal.recipeId = 'recipe-1';
      sendRecipeWorkflowMock.mockResolvedValue({ success: true });
      const sendSpy = vi.spyOn(recipeModal, 'sendWorkflowToComfyUI');

      recipeModal.syncHeaderActions();

      const button = document.getElementById('sendWorkflowBtn');
      expect(button).not.toBeNull();
      expect(button.classList.contains('recipe-source-url-btn')).toBe(true);

      button.dispatchEvent(new Event('click', { bubbles: true }));
      await flushAsyncTasks();

      expect(sendSpy).toHaveBeenCalledTimes(1);
      expect(sendRecipeWorkflowMock).toHaveBeenCalledWith('recipe-1');
    });

    it('does not insert the send-workflow button when has_workflow is not true', async () => {
      const recipeModal = await createRecipeModal();
      recipeModal.currentRecipe = { has_workflow: false };

      recipeModal.syncHeaderActions();

      expect(document.getElementById('sendWorkflowBtn')).toBeNull();

      recipeModal.currentRecipe = {};
      recipeModal.syncHeaderActions();

      expect(document.getElementById('sendWorkflowBtn')).toBeNull();
    });

    it('clears previously injected buttons on every call', async () => {
      const recipeModal = await createRecipeModal();
      recipeModal.currentRecipe = {
        has_workflow: true,
        source_path: 'https://civitai.com/models/123',
      };

      recipeModal.syncHeaderActions();
      recipeModal.syncHeaderActions();

      const buttons = document.querySelectorAll('#recipeHeaderActions .recipe-source-url-btn');
      expect(buttons).toHaveLength(2);
      expect(document.querySelectorAll('#sendWorkflowBtn')).toHaveLength(1);
    });

    it('inserts the Open Source URL button for http(s) source paths', async () => {
      const recipeModal = await createRecipeModal();
      recipeModal.currentRecipe = { source_path: 'https://civitai.com/models/123' };

      recipeModal.syncHeaderActions();

      const urlButton = document.querySelector('#recipeHeaderActions .recipe-source-url-btn');
      expect(urlButton).not.toBeNull();
      expect(urlButton.id).not.toBe('sendWorkflowBtn');
      expect(urlButton.title).toBe('https://civitai.com/models/123');

      recipeModal.currentRecipe = { source_path: '/local/path/recipe.webp' };
      recipeModal.syncHeaderActions();

      expect(document.querySelector('#recipeHeaderActions .recipe-source-url-btn')).toBeNull();
    });
  });

  describe('sendWorkflowToComfyUI', () => {
    it('shows a success toast when the workflow is sent', async () => {
      const recipeModal = await createRecipeModal();
      recipeModal.recipeId = 'recipe-1';
      sendRecipeWorkflowMock.mockResolvedValue({ success: true });

      await recipeModal.sendWorkflowToComfyUI();

      expect(sendRecipeWorkflowMock).toHaveBeenCalledWith('recipe-1');
      expect(showToastMock).toHaveBeenCalledWith(
        'toast.recipes.workflowSent',
        {},
        'success',
        'Workflow sent to ComfyUI'
      );
    });

    it('shows a warning toast in standalone mode', async () => {
      const recipeModal = await createRecipeModal();
      recipeModal.recipeId = 'recipe-1';
      sendRecipeWorkflowMock.mockResolvedValue({
        success: false,
        error: 'Standalone Mode Active',
      });

      await recipeModal.sendWorkflowToComfyUI();

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.general.cannotInteractStandalone',
        {},
        'warning',
        'Cannot interact with ComfyUI in standalone mode'
      );
    });

    it('shows a warning toast when the recipe has no embedded workflow', async () => {
      const recipeModal = await createRecipeModal();
      recipeModal.recipeId = 'recipe-1';
      sendRecipeWorkflowMock.mockResolvedValue({
        success: false,
        error: 'no_workflow',
      });

      await recipeModal.sendWorkflowToComfyUI();

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.recipes.workflowNoWorkflow',
        {},
        'warning',
        'No embedded workflow found in this recipe'
      );
    });

    it('shows an error toast for other backend errors', async () => {
      const recipeModal = await createRecipeModal();
      recipeModal.recipeId = 'recipe-1';
      sendRecipeWorkflowMock.mockResolvedValue({
        success: false,
        error: 'ComfyUI unreachable',
      });

      await recipeModal.sendWorkflowToComfyUI();

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.recipes.workflowSendFailed',
        { error: 'ComfyUI unreachable' },
        'error',
        'Failed to send workflow to ComfyUI: ComfyUI unreachable'
      );
    });

    it('shows an error toast when the API call throws', async () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const recipeModal = await createRecipeModal();
      recipeModal.recipeId = 'recipe-1';
      sendRecipeWorkflowMock.mockRejectedValue(new Error('network down'));

      await recipeModal.sendWorkflowToComfyUI();

      expect(showToastMock).toHaveBeenCalledWith(
        'toast.recipes.workflowSendFailed',
        { error: 'network down' },
        'error',
        'Failed to send workflow to ComfyUI: network down'
      );
      errorSpy.mockRestore();
    });

    it('does not call the API without a recipe ID', async () => {
      const recipeModal = await createRecipeModal();
      recipeModal.recipeId = null;

      await recipeModal.sendWorkflowToComfyUI();

      expect(sendRecipeWorkflowMock).not.toHaveBeenCalled();
      expect(showToastMock).not.toHaveBeenCalled();
    });
  });
});
