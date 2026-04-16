import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));
const copyToClipboardMock = vi.fn();
const getNSFWLevelNameMock = vi.fn((level) => {
  if (level >= 16) return 'XXX';
  if (level >= 8) return 'X';
  if (level >= 4) return 'R';
  if (level >= 2) return 'PG13';
  if (level >= 1) return 'PG';
  return 'Unknown';
});
const copyLoraSyntaxMock = vi.fn();
const sendLoraToWorkflowMock = vi.fn();
const buildLoraSyntaxMock = vi.fn((fileName) => `lora:${fileName}`);
const openExampleImagesFolderMock = vi.fn();

const modalManagerMock = {
  showModal: vi.fn(),
  closeModal: vi.fn(),
  registerModal: vi.fn(),
  getModal: vi.fn(() => ({ element: { style: { display: 'none' } }, isOpen: false })),
  isAnyModalOpen: vi.fn(),
};

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

const saveModelMetadataMock = vi.fn();
const downloadExampleImagesApiMock = vi.fn();
const replaceModelPreviewMock = vi.fn();
const refreshSingleModelMetadataMock = vi.fn();
const resetAndReloadMock = vi.fn();
const getCompleteApiConfigMock = vi.fn(() => ({
  config: { displayName: 'LoRA' },
  endpoints: {
    refreshUpdates: '/api/lm/loras/updates/refresh',
    fetchMissingLicenses: '/api/lm/loras/updates/fetch-missing-license',
  },
}));
const getCurrentModelTypeMock = vi.fn(() => 'loras');

const getModelApiClientMock = vi.fn(() => ({
  saveModelMetadata: saveModelMetadataMock,
  downloadExampleImages: downloadExampleImagesApiMock,
  replaceModelPreview: replaceModelPreviewMock,
  refreshSingleModelMetadata: refreshSingleModelMetadataMock,
}));

const updateRecipeMetadataMock = vi.fn(() => Promise.resolve({ success: true }));
const fetchRecipeDetailsMock = vi.fn();

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  copyToClipboard: copyToClipboardMock,
  getNSFWLevelName: getNSFWLevelNameMock,
  copyLoraSyntax: copyLoraSyntaxMock,
  sendLoraToWorkflow: sendLoraToWorkflowMock,
  buildLoraSyntax: buildLoraSyntaxMock,
  openExampleImagesFolder: openExampleImagesFolderMock,
}));

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: modalManagerMock,
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
  setSessionItem: vi.fn(),
  removeSessionItem: vi.fn(),
  getSessionItem: vi.fn(),
  getStorageItem: vi.fn((key, defaultValue = null) => {
    const value = localStorage.getItem(`lora_manager_${key}`);
    if (value === null) {
      return defaultValue;
    }

    try {
      return JSON.parse(value);
    } catch (error) {
      return value;
    }
  }),
  setStorageItem: vi.fn((key, value) => {
    const prefixedKey = `lora_manager_${key}`;
    if (typeof value === 'object' && value !== null) {
      localStorage.setItem(prefixedKey, JSON.stringify(value));
    } else {
      localStorage.setItem(prefixedKey, value);
    }
  }),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: getModelApiClientMock,
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  getCompleteApiConfig: getCompleteApiConfigMock,
  getCurrentModelType: getCurrentModelTypeMock,
  MODEL_TYPES: {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings',
  },
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state: stateStub,
}));

vi.mock('../../../static/js/utils/modalUtils.js', () => ({
  showExcludeModal: vi.fn(),
  showDeleteModal: vi.fn(),
}));

vi.mock('../../../static/js/managers/MoveManager.js', () => ({
  moveManager: { showMoveModal: vi.fn() },
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  fetchRecipeDetails: fetchRecipeDetailsMock,
  updateRecipeMetadata: updateRecipeMetadataMock,
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: translateMock,
}));

async function flushAsyncTasks() {
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });

  return { promise, resolve, reject };
}

describe('Interaction-level regression coverage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    document.body.innerHTML = '';
    stateStub.global.settings = {};
    saveModelMetadataMock.mockResolvedValue(undefined);
    downloadExampleImagesApiMock.mockResolvedValue(undefined);
    updateRecipeMetadataMock.mockResolvedValue({ success: true });
    fetchRecipeDetailsMock.mockResolvedValue(null);
    resetAndReloadMock.mockResolvedValue(undefined);
    getCompleteApiConfigMock.mockReturnValue({
      config: { displayName: 'LoRA' },
      endpoints: {
        refreshUpdates: '/api/lm/loras/updates/refresh',
        fetchMissingLicenses: '/api/lm/loras/updates/fetch-missing-license',
      },
    });
    getCurrentModelTypeMock.mockReturnValue('loras');
    translateMock.mockImplementation((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));
    global.modalManager = modalManagerMock;
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({}),
    }));
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
    delete window.exampleImagesManager;
    delete global.fetch;
    delete global.modalManager;
  });

  it('opens the NSFW selector from the LoRA context menu and persists the new rating', async () => {
    document.body.innerHTML = `
      <div id="loraContextMenu" class="context-menu">
        <div class="context-menu-item" data-action="set-nsfw"></div>
      </div>
      <div id="nsfwLevelSelector" class="nsfw-level-selector" style="display: none;">
        <div class="nsfw-level-header">
          <button class="close-nsfw-selector"></button>
        </div>
        <div class="nsfw-level-content">
          <div class="current-level"><span id="currentNSFWLevel"></span></div>
          <div class="nsfw-level-options">
            <button class="nsfw-level-btn" data-level="1"></button>
            <button class="nsfw-level-btn" data-level="4"></button>
          </div>
        </div>
      </div>
    `;

    const card = document.createElement('div');
    card.className = 'model-card';
    card.dataset.filepath = '/models/test.safetensors';
    card.dataset.meta = JSON.stringify({ preview_nsfw_level: 1 });
    document.body.appendChild(card);

    const { LoraContextMenu } = await import('../../../static/js/components/ContextMenu/LoraContextMenu.js');
    const helpers = await import('../../../static/js/utils/uiHelpers.js');
    expect(helpers.showToast).toBe(showToastMock);
    const contextMenu = new LoraContextMenu();

    contextMenu.showMenu(120, 140, card);

    const nsfwMenuItem = document.querySelector('#loraContextMenu .context-menu-item[data-action="set-nsfw"]');
    nsfwMenuItem.dispatchEvent(new Event('click', { bubbles: true }));

    const selector = document.getElementById('nsfwLevelSelector');
    expect(selector.style.display).toBe('block');
    expect(selector.dataset.cardPath).toBe('/models/test.safetensors');
    expect(document.getElementById('currentNSFWLevel').textContent).toBe('PG');

    const levelButton = selector.querySelector('.nsfw-level-btn[data-level="4"]');
    levelButton.dispatchEvent(new Event('click', { bubbles: true }));

    expect(saveModelMetadataMock).toHaveBeenCalledWith('/models/test.safetensors', { preview_nsfw_level: 4 });
    expect(saveModelMetadataMock).toHaveBeenCalledTimes(1);
    await saveModelMetadataMock.mock.results[0].value;
    await flushAsyncTasks();
    expect(selector.style.display).toBe('none');
    expect(document.getElementById('loraContextMenu').style.display).toBe('none');
  });

  it('wires recipe modal title editing to update metadata and UI state', async () => {
    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    const recipe = {
      id: 'recipe-1',
      file_path: '/recipes/test.json',
      title: 'Original Title',
      tags: ['tag1', 'tag2', 'tag3', 'tag4', 'tag5', 'tag6'],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: {
        prompt: 'Prompt text',
        negative_prompt: 'Negative prompt',
        steps: '30',
      },
      loras: [],
    };

    recipeModal.showRecipeDetails(recipe);
    await new Promise((resolve) => setTimeout(resolve, 60));
    await flushAsyncTasks();

    expect(modalManagerMock.showModal).toHaveBeenCalledWith('recipeModal');

    const editIcon = document.querySelector('#recipeModalTitle .edit-icon');
    editIcon.dispatchEvent(new Event('click', { bubbles: true }));

    const titleInput = document.querySelector('#recipeTitleEditor .title-input');
    titleInput.value = 'Updated Title';

    recipeModal.saveTitleEdit();

    expect(updateRecipeMetadataMock).toHaveBeenCalledWith(
      '/recipes/test.json',
      { title: 'Updated Title' },
      { listFilePath: '/recipes/test.json' }
    );
    expect(updateRecipeMetadataMock).toHaveBeenCalledTimes(1);
    await updateRecipeMetadataMock.mock.results[0].value;
    await flushAsyncTasks();

    const titleContainer = document.getElementById('recipeModalTitle');
    expect(titleContainer.querySelector('.content-text').textContent).toBe('Updated Title');
    expect(titleContainer.querySelector('#recipeTitleEditor').classList.contains('active')).toBe(false);
    expect(recipeModal.currentRecipe.title).toBe('Updated Title');
  });

  it('hydrates recipe source URL from the backend when opening the modal', async () => {
    fetchRecipeDetailsMock.mockResolvedValueOnce({
      id: 'recipe-4',
      file_path: '/recipes/source.json',
      title: 'Hydrated Recipe',
      source_path: 'https://example.com/source-url',
      gen_params: {
        prompt: 'hydrated prompt',
      },
      loras: [],
    });

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-4',
      file_path: '/recipes/source.json',
      title: 'Cached Title',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: {
        prompt: 'cached prompt',
      },
      loras: [],
    });

    await flushAsyncTasks();
    await flushAsyncTasks();

    expect(fetchRecipeDetailsMock).toHaveBeenCalledWith('recipe-4');
    expect(document.querySelector('.source-url-text').textContent).toBe('https://example.com/source-url');
    expect(recipeModal.currentRecipe.source_path).toBe('https://example.com/source-url');
    expect(recipeModal.filePath).toBe('/recipes/source.json');
  });

  it('drops stale cached preview URLs when hydration corrects only the recipe file path', async () => {
    const deferred = createDeferred();
    fetchRecipeDetailsMock.mockReturnValueOnce(deferred.promise);

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-preview',
      file_path: '/recipes/original.webp',
      title: 'Preview Recipe',
      tags: [],
      file_url: '/loras_static/root1/preview/stale.webp',
      preview_url: '',
      source_path: '',
      gen_params: { prompt: 'cached prompt' },
      loras: [],
    });

    const previewBefore = document.getElementById('recipeModalImage');
    expect(previewBefore.getAttribute('src')).toContain('/loras_static/root1/preview/stale.webp');

    deferred.resolve({
      id: 'recipe-preview',
      file_path: '/recipes/moved.webp',
      title: 'Preview Recipe',
      source_path: '',
      gen_params: { prompt: 'cached prompt' },
      loras: [],
    });

    await flushAsyncTasks();

    const previewAfter = document.getElementById('recipeModalImage');
    expect(previewAfter.getAttribute('src')).toContain('/loras_static/root1/preview/moved.webp');
    expect(recipeModal.filePath).toBe('/recipes/moved.webp');
    expect(recipeModal.listFilePath).toBe('/recipes/original.webp');
  });

  it('keeps source URL controls when hydration switches preview media type', async () => {
    fetchRecipeDetailsMock.mockResolvedValueOnce({
      id: 'recipe-video',
      file_path: '/recipes/clip.mp4',
      title: 'Video Recipe',
      source_path: 'https://example.com/video-source',
      gen_params: { prompt: 'video prompt' },
      loras: [],
    });

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-video',
      file_path: '/recipes/still.webp',
      title: 'Video Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: 'https://example.com/video-source',
      gen_params: { prompt: 'cached prompt' },
      loras: [],
    });

    await flushAsyncTasks();
    await flushAsyncTasks();

    expect(document.getElementById('recipeModalVideo')).not.toBeNull();
    expect(document.querySelector('.source-url-container')).not.toBeNull();
    expect(document.querySelector('.source-url-editor')).not.toBeNull();
    expect(document.querySelector('.source-url-text').textContent).toBe('https://example.com/video-source');
  });

  it('replaces source URL controls when reopening the modal', async () => {
    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-reopen-1',
      file_path: '/recipes/reopen-1.webp',
      title: 'First Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: 'https://example.com/first',
      gen_params: { prompt: 'first prompt' },
      loras: [],
    });

    recipeModal.showRecipeDetails({
      id: 'recipe-reopen-2',
      file_path: '/recipes/reopen-2.webp',
      title: 'Second Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: 'https://example.com/second',
      gen_params: { prompt: 'second prompt' },
      loras: [],
    });

    expect(document.querySelectorAll('.source-url-container')).toHaveLength(1);
    expect(document.querySelectorAll('.source-url-editor')).toHaveLength(1);
    expect(document.querySelector('.source-url-text').textContent).toBe('https://example.com/second');

    document.querySelector('.source-url-edit-btn').click();
    expect(document.querySelector('.source-url-input').value).toBe('https://example.com/second');
  });

  it('preserves local title tags and prompt edits when hydration resolves later', async () => {
    const deferred = createDeferred();
    fetchRecipeDetailsMock.mockReturnValueOnce(deferred.promise);

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-5',
      file_path: '/recipes/editing.json',
      title: 'Cached Title',
      tags: ['cached-tag'],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: {
        prompt: 'cached prompt',
        negative_prompt: 'cached negative',
      },
      loras: [],
    });

    recipeModal.markFieldDirty('title');
    recipeModal.markFieldDirty('tags');
    recipeModal.markFieldDirty('prompt');
    recipeModal.markFieldDirty('negative_prompt');

    document.querySelector('#recipeTitleEditor .title-input').value = 'Local Title';
    document.querySelector('#recipeTagsEditor .tags-input').value = 'local-tag-1, local-tag-2';
    document.getElementById('recipePromptInput').value = 'local prompt';
    document.getElementById('recipeNegativePromptInput').value = 'local negative';

    deferred.resolve({
      id: 'recipe-5',
      file_path: '/recipes/editing.json',
      title: 'Hydrated Title',
      tags: ['hydrated-tag'],
      source_path: 'https://example.com/hydrated',
      gen_params: {
        prompt: 'hydrated prompt',
        negative_prompt: 'hydrated negative',
      },
      loras: [],
    });

    await flushAsyncTasks();
    await flushAsyncTasks();

    expect(document.querySelector('#recipeTitleEditor .title-input').value).toBe('Local Title');
    expect(document.querySelector('#recipeTagsEditor .tags-input').value).toBe('local-tag-1, local-tag-2');
    expect(document.getElementById('recipePromptInput').value).toBe('local prompt');
    expect(document.getElementById('recipeNegativePromptInput').value).toBe('local negative');
    expect(recipeModal.currentRecipe.title).toBe('Hydrated Title');
    expect(recipeModal.currentRecipe.tags).toEqual(['hydrated-tag']);
    expect(recipeModal.currentRecipe.gen_params.prompt).toBe('hydrated prompt');
    expect(recipeModal.currentRecipe.gen_params.negative_prompt).toBe('hydrated negative');
    expect(recipeModal.currentRecipe.source_path).toBe('https://example.com/hydrated');
  });

  it('cancels dirty edits back to hydrated values after hydration resolves', async () => {
    const deferred = createDeferred();
    fetchRecipeDetailsMock.mockReturnValueOnce(deferred.promise);

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-cancel-hydrated',
      file_path: '/recipes/cancel-hydrated.json',
      title: 'Cached Title',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: 'https://example.com/cached-source',
      gen_params: {
        prompt: 'cached prompt',
        negative_prompt: 'cached negative',
      },
      loras: [],
    });

    document.querySelector('#recipeModalTitle .edit-icon').click();
    const titleInput = document.querySelector('#recipeTitleEditor .title-input');
    titleInput.value = 'Local Title';
    titleInput.dispatchEvent(new Event('input', { bubbles: true }));

    document.getElementById('editPromptBtn').click();
    const promptInput = document.getElementById('recipePromptInput');
    promptInput.value = 'local prompt';
    promptInput.dispatchEvent(new Event('input', { bubbles: true }));

    document.querySelector('.source-url-edit-btn').click();
    const sourceInput = document.querySelector('.source-url-input');
    sourceInput.value = 'https://example.com/local-source';
    sourceInput.dispatchEvent(new Event('input', { bubbles: true }));

    deferred.resolve({
      id: 'recipe-cancel-hydrated',
      file_path: '/recipes/cancel-hydrated.json',
      title: 'Hydrated Title',
      source_path: 'https://example.com/hydrated-source',
      gen_params: {
        prompt: 'hydrated prompt',
        negative_prompt: 'hydrated negative',
      },
      loras: [],
    });

    await flushAsyncTasks();
    await flushAsyncTasks();

    expect(recipeModal.currentRecipe.title).toBe('Hydrated Title');
    expect(recipeModal.currentRecipe.source_path).toBe('https://example.com/hydrated-source');
    expect(recipeModal.currentRecipe.gen_params.prompt).toBe('hydrated prompt');

    recipeModal.cancelTitleEdit();
    recipeModal.cancelPromptEdit({
      contentId: 'recipePrompt',
      editorId: 'recipePromptEditor',
      inputId: 'recipePromptInput',
      field: 'prompt',
    });
    document.querySelector('.source-url-cancel-btn').click();

    expect(document.querySelector('#recipeTitleEditor .title-input').value).toBe('Hydrated Title');
    expect(document.getElementById('recipePromptInput').value).toBe('hydrated prompt');
    expect(document.querySelector('.source-url-input').value).toBe('https://example.com/hydrated-source');
  });

  it('replaces removed gen_params keys when hydration returns a smaller parameter set', async () => {
    const deferred = createDeferred();
    fetchRecipeDetailsMock.mockReturnValueOnce(deferred.promise);

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div id="recipeCheckpoint"></div>
              <div id="recipeResourceDivider"></div>
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-gen-params',
      file_path: '/recipes/gen-params.json',
      title: 'Gen Params Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: {
        prompt: 'old prompt',
        negative_prompt: 'old negative',
        sampler: 'euler',
        cfg_scale: 7,
      },
      loras: [],
    });

    deferred.resolve({
      id: 'recipe-gen-params',
      file_path: '/recipes/gen-params.json',
      title: 'Gen Params Recipe',
      gen_params: {
        sampler: 'dpmpp_2m',
      },
      loras: [],
    });

    await flushAsyncTasks();
    await flushAsyncTasks();

    expect(recipeModal.currentRecipe.gen_params).toEqual({ sampler: 'dpmpp_2m' });
    expect(document.getElementById('recipePrompt').textContent).toBe('No prompt information available');
    expect(document.getElementById('recipeNegativePrompt').textContent).toBe('No negative prompt information available');
    const otherParamsText = document.getElementById('recipeOtherParams').textContent;
    expect(otherParamsText).toContain('sampler:');
    expect(otherParamsText).toContain('dpmpp_2m');
    expect(otherParamsText).not.toContain('cfg_scale');
  });

  it('filters dirty generation params from recipe modal display', async () => {
    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div id="recipeModalTitle"></div>
        <div id="recipePreviewContainer"></div>
        <div id="recipeTagsCompact"></div>
        <div id="recipeTagsTooltip"><div id="recipeTagsTooltipContent"></div></div>
        <div id="recipePrompt"></div>
        <textarea id="recipePromptInput"></textarea>
        <div id="recipeNegativePrompt"></div>
        <textarea id="recipeNegativePromptInput"></textarea>
        <div class="other-params" id="recipeOtherParams"></div>
        <div id="recipeCheckpoint"></div>
        <div id="recipeResourceDivider"></div>
        <div id="recipeLorasList"></div>
        <span id="recipeLorasCount"></span>
        <button id="viewRecipeLorasBtn"></button>
        <button id="copyRecipeSyntaxBtn"></button>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: '',
      file_path: '/recipes/dirty-gen-params.json',
      title: 'Dirty Gen Params Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: {
        Prompt: 'visible prompt',
        negativePrompt: 'visible negative',
        Sampler: 'euler',
        cfgScale: 7,
        Version: 'ComfyUI',
        raw_metadata: { prompt: 'hidden prompt' },
        RNG: 'cpu',
      },
      loras: [],
    });

    const otherParamsText = document.getElementById('recipeOtherParams').textContent;
    expect(document.getElementById('recipePrompt').textContent).toContain('visible prompt');
    expect(document.getElementById('recipeNegativePrompt').textContent).toContain('visible negative');
    expect(otherParamsText).toContain('sampler:');
    expect(otherParamsText).toContain('cfg_scale:');
    expect(otherParamsText).not.toContain('Version');
    expect(otherParamsText).not.toContain('raw_metadata');
    expect(otherParamsText).not.toContain('RNG');
  });

  it('prefers canonical generation params over legacy aliases in modal display', async () => {
    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div id="recipeModalTitle"></div>
        <div id="recipePreviewContainer"></div>
        <div id="recipeTagsCompact"></div>
        <div id="recipeTagsTooltip"><div id="recipeTagsTooltipContent"></div></div>
        <div id="recipePrompt"></div>
        <textarea id="recipePromptInput"></textarea>
        <div id="recipeNegativePrompt"></div>
        <textarea id="recipeNegativePromptInput"></textarea>
        <div class="other-params" id="recipeOtherParams"></div>
        <div id="recipeCheckpoint"></div>
        <div id="recipeResourceDivider"></div>
        <div id="recipeLorasList"></div>
        <span id="recipeLorasCount"></span>
        <button id="viewRecipeLorasBtn"></button>
        <button id="copyRecipeSyntaxBtn"></button>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: '',
      file_path: '/recipes/canonical-wins.json',
      title: 'Canonical Wins Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: {
        Prompt: 'stale prompt',
        prompt: 'fresh prompt',
        negativePrompt: 'stale negative',
        negative_prompt: 'fresh negative',
        cfgScale: 3,
        cfg_scale: 7,
      },
      loras: [],
    });

    const otherParamsText = document.getElementById('recipeOtherParams').textContent;
    expect(document.getElementById('recipePrompt').textContent).toContain('fresh prompt');
    expect(document.getElementById('recipePrompt').textContent).not.toContain('stale prompt');
    expect(document.getElementById('recipeNegativePrompt').textContent).toContain('fresh negative');
    expect(document.getElementById('recipeNegativePrompt').textContent).not.toContain('stale negative');
    expect(otherParamsText).toContain('cfg_scale:');
    expect(otherParamsText).toContain('7');
    expect(otherParamsText).not.toContain('3');
  });

  it('replaces cached checkpoint and loras with hydrated resources', async () => {
    fetchRecipeDetailsMock.mockResolvedValueOnce({
      id: 'recipe-resources',
      file_path: '/recipes/resources.json',
      title: 'Resources Recipe',
      gen_params: { prompt: 'hydrated prompt' },
      checkpoint: {
        name: 'New Checkpoint',
        modelName: 'New Checkpoint',
        preview_url: '/previews/checkpoint-new.png',
        inLibrary: true,
      },
      loras: [
        {
          modelName: 'Hydrated LoRA',
          modelVersionName: 'v2',
          preview_url: '/previews/lora-new.png',
          inLibrary: true,
          strength: 0.8,
        },
      ],
    });

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div id="recipeCheckpoint"></div>
              <div id="recipeResourceDivider"></div>
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-resources',
      file_path: '/recipes/resources.json',
      title: 'Resources Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: { prompt: 'cached prompt' },
      checkpoint: {
        name: 'Old Checkpoint',
        modelName: 'Old Checkpoint',
        preview_url: '/previews/checkpoint-old.png',
        inLibrary: true,
      },
      loras: [
        {
          modelName: 'Cached LoRA',
          modelVersionName: 'v1',
          preview_url: '/previews/lora-old.png',
          inLibrary: true,
          strength: 1.0,
        },
      ],
    });

    await flushAsyncTasks();
    await flushAsyncTasks();

    expect(recipeModal.currentRecipe.checkpoint.modelName).toBe('New Checkpoint');
    expect(recipeModal.currentRecipe.loras).toHaveLength(1);
    expect(recipeModal.currentRecipe.loras[0].modelName).toBe('Hydrated LoRA');
    expect(document.getElementById('recipeCheckpoint').textContent).toContain('New Checkpoint');
    expect(document.getElementById('recipeLorasList').textContent).toContain('Hydrated LoRA');
    expect(document.getElementById('recipeLorasList').textContent).not.toContain('Cached LoRA');
  });

  it('clears optional recipe fields when hydration omits them', async () => {
    fetchRecipeDetailsMock.mockResolvedValueOnce({
      id: 'recipe-clear-optional',
      file_path: '/recipes/clear-optional.json',
      title: 'Cleared Recipe',
    });

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div id="recipeCheckpoint"></div>
              <div id="recipeResourceDivider"></div>
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-clear-optional',
      file_path: '/recipes/clear-optional.json',
      title: 'Cached Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: 'https://example.com/stale-source',
      gen_params: {
        prompt: 'stale prompt',
        negative_prompt: 'stale negative',
        sampler: 'euler',
      },
      checkpoint: {
        name: 'Stale Checkpoint',
        modelName: 'Stale Checkpoint',
        preview_url: '/previews/stale-checkpoint.png',
        inLibrary: true,
      },
      loras: [
        {
          modelName: 'Stale LoRA',
          modelVersionName: 'v1',
          preview_url: '/previews/stale-lora.png',
          inLibrary: true,
          strength: 1.0,
        },
      ],
    });

    await flushAsyncTasks();
    await flushAsyncTasks();

    expect(recipeModal.currentRecipe.source_path).toBe('');
    expect(recipeModal.currentRecipe.gen_params).toEqual({});
    expect(recipeModal.currentRecipe.checkpoint).toBeUndefined();
    expect(recipeModal.currentRecipe.loras).toBeUndefined();
    expect(document.querySelector('.source-url-text').textContent).toBe('No source URL');
    expect(document.getElementById('recipePrompt').textContent).toBe('No prompt information available');
    expect(document.getElementById('recipeNegativePrompt').textContent).toBe('No negative prompt information available');
    expect(document.getElementById('recipeOtherParams').textContent).toContain('No additional parameters available');
    expect(document.getElementById('recipeCheckpoint').textContent).toBe('');
    expect(document.getElementById('recipeLorasList').textContent).toContain('No LoRAs associated with this recipe');
  });

  it('refreshes the source URL input when hydration completes while editing', async () => {
    const deferred = createDeferred();
    fetchRecipeDetailsMock.mockReturnValueOnce(deferred.promise);

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-5',
      file_path: '/recipes/editing.json',
      title: 'Editing Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: { prompt: 'cached' },
      loras: [],
    });

    await new Promise((resolve) => setTimeout(resolve, 60));

    const editButton = document.querySelector('.source-url-edit-btn');
    editButton.click();

    const sourceInput = document.querySelector('.source-url-input');
    sourceInput.value = 'https://example.com/local-edit';
    sourceInput.dispatchEvent(new Event('input', { bubbles: true }));

    deferred.resolve({
      id: 'recipe-5',
      file_path: '/recipes/editing.json',
      title: 'Editing Recipe',
      source_path: 'https://example.com/hydrated-edit',
      gen_params: { prompt: 'hydrated' },
      loras: [],
    });

    await flushAsyncTasks();

    expect(sourceInput.value).toBe('https://example.com/local-edit');
    expect(document.querySelector('.source-url-text').textContent).toBe('https://example.com/hydrated-edit');
    expect(recipeModal.currentRecipe.source_path).toBe('https://example.com/hydrated-edit');
  });

  it('keeps a freshly saved source URL when hydration resolves later', async () => {
    const deferred = createDeferred();
    fetchRecipeDetailsMock.mockReturnValueOnce(deferred.promise);

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-6',
      file_path: '/recipes/saved.json',
      title: 'Saved Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: { prompt: 'cached' },
      loras: [],
    });

    await new Promise((resolve) => setTimeout(resolve, 60));

    const editButton = document.querySelector('.source-url-edit-btn');
    editButton.click();
    const sourceInput = document.querySelector('.source-url-input');
    sourceInput.value = 'https://example.com/new-source';
    sourceInput.dispatchEvent(new Event('input', { bubbles: true }));

    document.querySelector('.source-url-save-btn').click();
    await updateRecipeMetadataMock.mock.results[0].value;
    await flushAsyncTasks();

    deferred.resolve({
      id: 'recipe-6',
      file_path: '/recipes/saved.json',
      title: 'Saved Recipe',
      source_path: 'https://example.com/stale-source',
      gen_params: { prompt: 'hydrated' },
      loras: [],
    });

    await flushAsyncTasks();

    expect(recipeModal.currentRecipe.source_path).toBe('https://example.com/new-source');
    expect(document.querySelector('.source-url-text').textContent).toBe('https://example.com/new-source');
    expect(recipeModal.filePath).toBe('/recipes/saved.json');
  });

  it('writes metadata using the hydrated path while keeping list updates keyed to the original card path', async () => {
    fetchRecipeDetailsMock.mockResolvedValueOnce({
      id: 'recipe-moved',
      file_path: '/recipes/new-folder/moved.json',
      title: 'Moved Recipe',
      source_path: '',
      gen_params: { prompt: 'hydrated prompt' },
      loras: [],
    });

    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                  <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn" title="View all LoRAs in this recipe">
                    <i class="fas fa-external-link-alt"></i>
                  </button>
                  <button class="copy-btn" id="copyRecipeSyntaxBtn" title="Copy Recipe Syntax">
                    <i class="fas fa-copy"></i>
                  </button>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-moved',
      file_path: '/recipes/original-folder/moved.json',
      title: 'Moved Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: { prompt: 'cached prompt' },
      loras: [],
    });

    await flushAsyncTasks();
    await flushAsyncTasks();

    const editIcon = document.querySelector('#recipeModalTitle .edit-icon');
    editIcon.dispatchEvent(new Event('click', { bubbles: true }));

    const titleInput = document.querySelector('#recipeTitleEditor .title-input');
    titleInput.value = 'Updated After Move';
    recipeModal.saveTitleEdit();

    expect(updateRecipeMetadataMock).toHaveBeenCalledWith(
      '/recipes/new-folder/moved.json',
      { title: 'Updated After Move' },
      { listFilePath: '/recipes/original-folder/moved.json' }
    );
  });

  it('saves prompt edits on Enter while preserving Shift+Enter for new lines', async () => {
    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();
    const promptConfig = {
      contentId: 'recipePrompt',
      editorId: 'recipePromptEditor',
      inputId: 'recipePromptInput',
      field: 'prompt',
      placeholder: 'No prompt information available',
      successKey: 'toast.recipes.promptUpdated',
      successFallback: 'Prompt updated successfully',
    };

    recipeModal.showRecipeDetails({
      id: 'recipe-2',
      file_path: '/recipes/prompt.json',
      title: 'Prompt Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: {
        prompt: 'old prompt',
        negative_prompt: 'keep negative',
        steps: 30,
        cfg_scale: 7,
        raw_metadata: { prompt: 'preserve me' },
        Version: 'ComfyUI',
      },
      loras: [],
    });

    await flushAsyncTasks();

    document.getElementById('editPromptBtn').click();
    const textarea = document.getElementById('recipePromptInput');
    textarea.focus();
    textarea.value = 'new prompt text';
    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true }));
    await flushAsyncTasks();

    expect(updateRecipeMetadataMock).not.toHaveBeenCalled();

    await recipeModal.savePromptEdit(promptConfig);
    await flushAsyncTasks();
    await updateRecipeMetadataMock.mock.results[0].value;
    await flushAsyncTasks();

    expect(updateRecipeMetadataMock).toHaveBeenCalledWith(
      '/recipes/prompt.json',
      {
        gen_params: {
          prompt: 'new prompt text',
          negative_prompt: 'keep negative',
          steps: 30,
          cfg_scale: 7,
          raw_metadata: { prompt: 'preserve me' },
          Version: 'ComfyUI',
        },
      },
      { listFilePath: '/recipes/prompt.json' }
    );
    expect(document.getElementById('recipePrompt').textContent).toBe('new prompt text');
    expect(recipeModal.currentRecipe.gen_params.prompt).toBe('new prompt text');
  });

  it('cancels negative prompt edits on Escape without saving', async () => {
    document.body.innerHTML = `
      <div id="recipeModal" class="modal">
        <div class="modal-content">
          <header class="recipe-modal-header">
            <h2 id="recipeModalTitle">Recipe Details</h2>
            <div class="recipe-tags-container">
              <div class="recipe-tags-compact" id="recipeTagsCompact"></div>
              <div class="recipe-tags-tooltip" id="recipeTagsTooltip">
                <div class="tooltip-content" id="recipeTagsTooltipContent"></div>
              </div>
            </div>
          </header>
          <div class="modal-body">
            <div class="recipe-top-section">
              <div class="recipe-preview-container" id="recipePreviewContainer">
                <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
              </div>
              <div class="info-section recipe-gen-params">
                <div class="gen-params-container">
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editPromptBtn" title="Edit Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                    <div class="param-editor" id="recipePromptEditor">
                      <textarea class="param-textarea" id="recipePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <div class="param-actions">
                        <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                        <button class="edit-btn" id="editNegativePromptBtn" title="Edit Negative Prompt"><i class="fas fa-pencil-alt"></i></button>
                      </div>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
                    <div class="param-editor" id="recipeNegativePromptEditor">
                      <textarea class="param-textarea" id="recipeNegativePromptInput"></textarea>
                    </div>
                  </div>
                  <div class="other-params" id="recipeOtherParams"></div>
                </div>
              </div>
            </div>
            <div class="info-section recipe-bottom-section">
              <div class="recipe-section-header">
                <h3>Resources</h3>
                <div class="recipe-section-actions">
                  <span id="recipeLorasCount"><i class="fas fa-layer-group"></i> 0 LoRAs</span>
                </div>
              </div>
              <div class="recipe-loras-list" id="recipeLorasList"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    const recipeModal = new RecipeModal();

    recipeModal.showRecipeDetails({
      id: 'recipe-3',
      file_path: '/recipes/negative.json',
      title: 'Negative Recipe',
      tags: [],
      file_url: '',
      preview_url: '',
      source_path: '',
      gen_params: {
        prompt: '',
        negative_prompt: 'existing negative',
        steps: 20,
      },
      loras: [],
    });

    document.getElementById('editNegativePromptBtn').click();
    const textarea = document.getElementById('recipeNegativePromptInput');
    textarea.value = 'changed negative';
    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

    expect(updateRecipeMetadataMock).not.toHaveBeenCalled();
    expect(modalManagerMock.closeModal).not.toHaveBeenCalled();
    expect(document.getElementById('recipeNegativePrompt').textContent).toBe('existing negative');
    expect(document.getElementById('recipeNegativePromptEditor').classList.contains('active')).toBe(false);
  });

  it('processes global context menu actions for downloads and cleanup', async () => {
    document.body.innerHTML = `
      <div id="globalContextMenu" class="context-menu">
        <div class="context-menu-item" data-action="download-example-images"></div>
        <div class="context-menu-item" data-action="check-model-updates"></div>
        <div class="context-menu-item" data-action="fetch-missing-licenses"></div>
        <div class="context-menu-item" data-action="cleanup-example-images-folders"></div>
        <div class="context-menu-item" data-action="manage-excluded-models"></div>
      </div>
    `;

    const { GlobalContextMenu } = await import('../../../static/js/components/ContextMenu/GlobalContextMenu.js');
    const menu = new GlobalContextMenu();

    stateStub.global.settings.example_images_path = '/tmp/examples';
    stateStub.global.settings.optimize_example_images = false;
    window.exampleImagesManager = {
      isDownloading: false,
      isPaused: false,
      isStopping: false,
      hasShownCompletionToast: false,
      updateUI: vi.fn(),
      showProgressPanel: vi.fn(),
      startProgressUpdates: vi.fn(),
      updateDownloadButtonText: vi.fn(),
    };
    window.pageControls = {
      enterExcludedView: vi.fn().mockResolvedValue(undefined),
    };

    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, moved_total: 2 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, records: [{ id: 1 }] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, updated: [{ modelId: 42 }] }),
      });

    menu.showMenu(100, 200);
    const downloadItem = document.querySelector('[data-action="download-example-images"]');
    downloadItem.dispatchEvent(new Event('click', { bubbles: true }));
    expect(downloadItem.classList.contains('disabled')).toBe(true);

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/download-example-images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force: true, optimize: false, model_types: ['lora', 'checkpoint', 'embedding'] })
    });
    expect(global.fetch).toHaveBeenCalledTimes(1);

    const responsePromise = global.fetch.mock.results[0].value;
    const response = await responsePromise;
    await response.json();
    await flushAsyncTasks();
    expect(downloadItem.classList.contains('disabled')).toBe(false);
    expect(window.exampleImagesManager.isDownloading).toBe(true);
    expect(document.getElementById('globalContextMenu').style.display).toBe('none');

    menu.showMenu(240, 320);
    const cleanupItem = document.querySelector('[data-action="cleanup-example-images-folders"]');
    cleanupItem.dispatchEvent(new Event('click', { bubbles: true }));
    expect(cleanupItem.classList.contains('disabled')).toBe(true);

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/cleanup-example-image-folders', { method: 'POST' });
    expect(global.fetch).toHaveBeenCalledTimes(2);
    const cleanupResponsePromise = global.fetch.mock.results[1].value;
    const cleanupResponse = await cleanupResponsePromise;
    await response.json();
    await flushAsyncTasks();
    expect(cleanupItem.classList.contains('disabled')).toBe(false);
    expect(menu._cleanupInProgress).toBe(false);

    localStorage.setItem('lora_manager_ack_check_updates_for_all_models', 'true');

    menu.showMenu(360, 420);
    const checkUpdatesItem = document.querySelector('[data-action="check-model-updates"]');
    checkUpdatesItem.dispatchEvent(new Event('click', { bubbles: true }));
    expect(checkUpdatesItem.classList.contains('disabled')).toBe(true);

    await flushAsyncTasks();

    expect(global.fetch).toHaveBeenNthCalledWith(3, '/api/lm/loras/updates/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force: false }),
    });

    const updateResponse = await global.fetch.mock.results[1].value;
    await updateResponse.json();
    await flushAsyncTasks();

    expect(showToastMock).toHaveBeenCalledWith(
      'globalContextMenu.checkModelUpdates.success',
      { count: 1, type: 'LoRA' },
      'success'
    );
    expect(loadingManagerStub.showSimpleLoading).toHaveBeenCalledWith('Checking for LoRA updates...');
    expect(loadingManagerStub.hide).toHaveBeenCalled();
    expect(resetAndReloadMock).toHaveBeenCalledWith(false);
    expect(checkUpdatesItem.classList.contains('disabled')).toBe(false);

    menu.showMenu(480, 520);
    const fetchMissingItem = document.querySelector('[data-action="fetch-missing-licenses"]');
    fetchMissingItem.dispatchEvent(new Event('click', { bubbles: true }));
    expect(fetchMissingItem.classList.contains('disabled')).toBe(true);

    const fetchMissingResponse = await global.fetch.mock.results[3].value;
    await fetchMissingResponse.json();
    await flushAsyncTasks();

    expect(global.fetch).toHaveBeenNthCalledWith(4, '/api/lm/loras/updates/fetch-missing-license', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });

    expect(showToastMock).toHaveBeenCalledWith(
      'globalContextMenu.fetchMissingLicenses.success',
      { count: 1, type: 'LoRA', typePlural: 'LoRAs' },
      'success'
    );
    expect(loadingManagerStub.showSimpleLoading).toHaveBeenNthCalledWith(2, 'Refreshing license metadata for LoRAs...');
    expect(fetchMissingItem.classList.contains('disabled')).toBe(false);

    menu.showMenu(560, 600);
    const excludedItem = document.querySelector('[data-action="manage-excluded-models"]');
    excludedItem.dispatchEvent(new Event('click', { bubbles: true }));
    expect(window.pageControls.enterExcludedView).toHaveBeenCalledTimes(1);
  });
});
