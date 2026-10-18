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

const recipeItem = {
  id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
  file_path: '/recipes/a1b2c3d4-e5f6-7890-abcd-ef1234567890.png',
  title: 'Demo Recipe',
  tags: [],
  loras: [],
};

const virtualScrollerStub = {
  updateSingleItem: vi.fn(),
  getNavigationState: vi.fn(() => ({
    index: 0,
    hasPrev: false,
    hasNext: false,
    loadedItems: 1,
    totalItems: 1,
  })),
  getAdjacentItemByFilePath: vi.fn(async () => null),
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

const fetchRecipeDetailsMock = vi.fn(async () => ({}));
const updateRecipeMetadataMock = vi.fn(() => Promise.resolve({ success: true }));

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
  fetchRecipeDetails: fetchRecipeDetailsMock,
  updateRecipeMetadata: updateRecipeMetadataMock,
  sendRecipeWorkflow: vi.fn(),
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
              <button class="modal-nav-btn" id="recipeNavPrevBtn" disabled></button>
              <button class="modal-nav-btn" id="recipeNavNextBtn" disabled></button>
            </div>
          </div>
          <div class="recipe-header-actions" id="recipeHeaderActions">
            <button class="modal-send-btn" id="sendRecipeBtn"><i class="fas fa-paper-plane"></i></button>
            <button class="modal-copy-btn" id="copyRecipeSyntaxBtn"><i class="fas fa-copy"></i></button>
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
        <footer class="recipe-meta-footer" id="recipeMetaFooter" hidden></footer>
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

function openLocationFetchCalls() {
  return global.fetch.mock.calls.filter(([url]) => url === '/api/lm/open-file-location');
}

describe('RecipeModal meta footer', () => {
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

  it('shows the folder path and a middle-truncated recipe ID', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItem);

    const footer = document.getElementById('recipeMetaFooter');
    expect(footer.hidden).toBe(false);

    const location = footer.querySelector('.recipe-meta-location');
    expect(location.querySelector('.recipe-meta-location-path').textContent).toBe('/recipes/');
    expect(location.dataset.filepath).toBe(recipeItem.file_path);

    const idValue = footer.querySelector('.recipe-meta-id-value');
    expect(idValue.textContent).toBe('a1b2c3d4…7890');
    expect(idValue.getAttribute('title')).toBe(recipeItem.id);
  });

  it('copies the full recipe ID when the copy button is clicked', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItem);

    document.querySelector('.recipe-meta-copy-btn').click();

    expect(copyToClipboardMock).toHaveBeenCalledWith(recipeItem.id);
  });

  it('opens the recipe file location when the path is clicked', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItem);

    document.querySelector('.recipe-meta-location').click();
    await flushAsyncTasks();

    const calls = openLocationFetchCalls();
    expect(calls).toHaveLength(1);
    expect(JSON.parse(calls[0][1].body)).toEqual({ file_path: recipeItem.file_path });
    expect(showToastMock).toHaveBeenCalledWith('recipes.modal.openFileLocation.success', {}, 'success');
  });

  it('opens the recipe JSON path once hydration provides it', async () => {
    const jsonPath = '/recipes/a1b2c3d4-e5f6-7890-abcd-ef1234567890.recipe.json';
    fetchRecipeDetailsMock.mockResolvedValueOnce({
      id: recipeItem.id,
      file_path: recipeItem.file_path,
      recipe_json_path: jsonPath,
    });

    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItem);
    await flushAsyncTasks();

    const location = document.querySelector('.recipe-meta-location');
    expect(location.dataset.filepath).toBe(jsonPath);
  });

  it('copies the path to clipboard when the backend reports clipboard mode', async () => {
    const writeTextMock = vi.fn(async () => {});
    Object.defineProperty(window.navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      configurable: true,
    });

    global.fetch = vi.fn(async (url) => ({
      ok: true,
      json: async () => (url === '/api/lm/open-file-location'
        ? { mode: 'clipboard', path: '/recipes' }
        : {}),
    }));

    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeItem);

    document.querySelector('.recipe-meta-location').click();
    await flushAsyncTasks();

    expect(writeTextMock).toHaveBeenCalledWith('/recipes');
    expect(showToastMock).toHaveBeenCalledWith(
      'recipes.modal.openFileLocation.copied',
      { path: '/recipes' },
      'success',
    );
  });

  it('hides the footer when neither ID nor file path is available', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails({ title: 'Orphan', tags: [], loras: [] });

    const footer = document.getElementById('recipeMetaFooter');
    expect(footer.hidden).toBe(true);
    expect(footer.innerHTML).toBe('');
  });
});
