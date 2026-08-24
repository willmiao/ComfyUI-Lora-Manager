import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));

const loadingManagerStub = {
  showSimpleLoading: vi.fn(),
  hide: vi.fn(),
  show: vi.fn(),
  restoreProgressBar: vi.fn(),
};

const recipeItems = [
  { id: 'recipe-1', file_path: '/recipes/first.json', title: 'First Recipe', tags: [], loras: [] },
  { id: 'recipe-2', file_path: '/recipes/second.json', title: 'Second Recipe', tags: [], loras: [] },
  { id: 'recipe-3', file_path: '/recipes/third.json', title: 'Third Recipe', tags: [], loras: [] },
];

const virtualScrollerStub = {
  updateSingleItem: vi.fn(),
  getNavigationState: vi.fn((filePath) => {
    const index = recipeItems.findIndex(item => item.file_path === filePath);
    return {
      index,
      hasPrev: index > 0,
      hasNext: index !== -1 && index < recipeItems.length - 1,
      loadedItems: recipeItems.length,
      totalItems: recipeItems.length,
    };
  }),
  getAdjacentItemByFilePath: vi.fn(async (filePath, direction) => {
    const currentIndex = recipeItems.findIndex(item => item.file_path === filePath);
    if (currentIndex === -1) return null;
    const targetIndex = currentIndex + (direction === 'prev' ? -1 : 1);
    if (targetIndex < 0 || targetIndex >= recipeItems.length) return null;
    return { item: recipeItems[targetIndex], index: targetIndex };
  }),
};

const stateStub = {
  global: { settings: {}, loadingManager: loadingManagerStub },
  loadingManager: loadingManagerStub,
  virtualScroller: virtualScrollerStub,
};

const modalManagerMock = {
  showModal: vi.fn(),
  closeModal: vi.fn(),
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

function recipeModalFixture() {
  return `
    <div id="recipeModal" class="modal">
      <div class="modal-content">
        <header class="recipe-modal-header">
          <div class="recipe-modal-header-row">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="modal-nav-controls">
              <button class="modal-nav-btn" id="recipeNavPrevBtn" disabled>
                <i class="fas fa-chevron-left"></i>
              </button>
              <button class="modal-nav-btn" id="recipeNavNextBtn" disabled>
                <i class="fas fa-chevron-right"></i>
              </button>
            </div>
          </div>
          <div class="recipe-header-actions" id="recipeHeaderActions">
            <button class="modal-send-btn" id="sendRecipeBtn"><i class="fas fa-paper-plane"></i></button>
          </div>
          <div id="recipeTagsContainer"></div>
        </header>
        <div class="modal-body">
          <div class="recipe-media-column">
            <div class="recipe-preview-container" id="recipePreviewContainer">
              <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
            </div>
          </div>
          <div class="info-section recipe-gen-params">
            <div class="gen-params-container">
              <div class="param-group info-item">
                <div class="param-content" id="recipePrompt"></div>
                <div class="param-editor" id="recipePromptEditor">
                  <textarea class="param-textarea" id="recipePromptInput"></textarea>
                </div>
              </div>
              <div class="param-group info-item">
                <div class="param-content" id="recipeNegativePrompt"></div>
                <div class="param-editor" id="recipeNegativePromptEditor">
                  <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                </div>
              </div>
              <div class="other-params" id="recipeOtherParams"></div>
            </div>
          </div>
          <div class="info-section recipe-bottom-section">
            <div class="recipe-section-actions">
              <span id="recipeLorasCount"></span>
              <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn"></button>
            </div>
            <div class="recipe-loras-list" id="recipeLorasList"></div>
          </div>
        </div>
      </div>
    </div>
  `;
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

describe('RecipeModal navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = recipeModalFixture();
    global.modalManager = modalManagerMock;
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({}),
    }));
  });

  afterEach(() => {
    createdModals.forEach(recipeModal => recipeModal.cleanupNavigationShortcuts());
    createdModals.length = 0;
    document.body.innerHTML = '';
    delete global.modalManager;
    delete global.fetch;
  });

  it('enables prev/next buttons according to the scroller position', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItems[0]);

    const prevBtn = document.getElementById('recipeNavPrevBtn');
    const nextBtn = document.getElementById('recipeNavNextBtn');

    expect(prevBtn.disabled).toBe(true);
    expect(nextBtn.disabled).toBe(false);
  });

  it('disables the next button when the last recipe is shown', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItems[2]);

    const prevBtn = document.getElementById('recipeNavPrevBtn');
    const nextBtn = document.getElementById('recipeNavNextBtn');

    expect(prevBtn.disabled).toBe(false);
    expect(nextBtn.disabled).toBe(true);
  });

  it('navigates to the next recipe when the next button is clicked', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItems[0]);

    document.getElementById('recipeNavNextBtn').click();
    await flushAsyncTasks();

    expect(virtualScrollerStub.getAdjacentItemByFilePath).toHaveBeenCalledWith('/recipes/first.json', 'next');
    expect(recipeModal.currentRecipe.id).toBe('recipe-2');
    expect(document.getElementById('recipeModalTitle').querySelector('.content-text').textContent).toBe('Second Recipe');
    expect(document.getElementById('recipeNavPrevBtn').disabled).toBe(false);
  });

  it('navigates to the previous recipe when the prev button is clicked', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItems[1]);

    document.getElementById('recipeNavPrevBtn').click();
    await flushAsyncTasks();

    expect(virtualScrollerStub.getAdjacentItemByFilePath).toHaveBeenCalledWith('/recipes/second.json', 'prev');
    expect(recipeModal.currentRecipe.id).toBe('recipe-1');
  });

  it('navigates with the ArrowRight and ArrowLeft keyboard shortcuts', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItems[1]);

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    await flushAsyncTasks();
    expect(recipeModal.currentRecipe.id).toBe('recipe-1');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    await flushAsyncTasks();
    expect(recipeModal.currentRecipe.id).toBe('recipe-2');
  });

  it('shows an info toast when navigating past the last recipe', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItems[2]);

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    await flushAsyncTasks();

    expect(showToastMock).toHaveBeenCalledWith('toast.recipes.noNextRecipe', {}, 'info', 'No next recipe available');
  });

  it('ignores arrow keys while focus is inside an input or textarea', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItems[1]);

    const input = document.getElementById('recipePromptInput');
    input.focus();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    await flushAsyncTasks();

    expect(virtualScrollerStub.getAdjacentItemByFilePath).not.toHaveBeenCalled();
    expect(recipeModal.currentRecipe.id).toBe('recipe-2');
  });

  it('removes the keyboard shortcut when the modal cleanup callback runs', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItems[1]);

    const cleanupCallback = modalManagerMock.showModal.mock.calls[0][3];
    expect(typeof cleanupCallback).toBe('function');

    cleanupCallback();
    expect(recipeModal.navigationKeyHandler).toBeNull();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    await flushAsyncTasks();

    expect(recipeModal.currentRecipe.id).toBe('recipe-2');
  });
});