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
  endpoints: { refreshUpdates: '/api/lm/loras/updates/refresh' },
}));
const getCurrentModelTypeMock = vi.fn(() => 'loras');

const getModelApiClientMock = vi.fn(() => ({
  saveModelMetadata: saveModelMetadataMock,
  downloadExampleImages: downloadExampleImagesApiMock,
  replaceModelPreview: replaceModelPreviewMock,
  refreshSingleModelMetadata: refreshSingleModelMetadataMock,
}));

const updateRecipeMetadataMock = vi.fn(() => Promise.resolve({ success: true }));

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
  updateRecipeMetadata: updateRecipeMetadataMock,
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: translateMock,
}));

async function flushAsyncTasks() {
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
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
    resetAndReloadMock.mockResolvedValue(undefined);
    getCompleteApiConfigMock.mockReturnValue({
      config: { displayName: 'LoRA' },
      endpoints: { refreshUpdates: '/api/lm/loras/updates/refresh' },
    });
    getCurrentModelTypeMock.mockReturnValue('loras');
    translateMock.mockImplementation((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));
    global.modalManager = modalManagerMock;
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
                      <button class="copy-btn" id="copyPromptBtn" title="Copy Prompt"><i class="fas fa-copy"></i></button>
                    </div>
                    <div class="param-content" id="recipePrompt"></div>
                  </div>
                  <div class="param-group info-item">
                    <div class="param-header">
                      <label>Negative Prompt</label>
                      <button class="copy-btn" id="copyNegativePromptBtn" title="Copy Negative Prompt"><i class="fas fa-copy"></i></button>
                    </div>
                    <div class="param-content" id="recipeNegativePrompt"></div>
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

    expect(updateRecipeMetadataMock).toHaveBeenCalledWith('/recipes/test.json', { title: 'Updated Title' });
    expect(updateRecipeMetadataMock).toHaveBeenCalledTimes(1);
    await updateRecipeMetadataMock.mock.results[0].value;
    await flushAsyncTasks();

    const titleContainer = document.getElementById('recipeModalTitle');
    expect(titleContainer.querySelector('.content-text').textContent).toBe('Updated Title');
    expect(titleContainer.querySelector('#recipeTitleEditor').classList.contains('active')).toBe(false);
    expect(recipeModal.currentRecipe.title).toBe('Updated Title');
  });

  it('processes global context menu actions for downloads and cleanup', async () => {
    document.body.innerHTML = `
      <div id="globalContextMenu" class="context-menu">
        <div class="context-menu-item" data-action="download-example-images"></div>
        <div class="context-menu-item" data-action="cleanup-example-images-folders"></div>
        <div class="context-menu-item" data-action="check-model-updates"></div>
      </div>
    `;

    const { GlobalContextMenu } = await import('../../../static/js/components/ContextMenu/GlobalContextMenu.js');
    const menu = new GlobalContextMenu();

    stateStub.global.settings.example_images_path = '/tmp/examples';
    window.exampleImagesManager = {
      handleDownloadButton: vi.fn().mockResolvedValue(undefined),
    };

    menu.showMenu(100, 200);
    const downloadItem = document.querySelector('[data-action="download-example-images"]');
    downloadItem.dispatchEvent(new Event('click', { bubbles: true }));
    expect(downloadItem.classList.contains('disabled')).toBe(true);

    expect(window.exampleImagesManager.handleDownloadButton).toHaveBeenCalledTimes(1);
    await window.exampleImagesManager.handleDownloadButton.mock.results[0].value;
    await flushAsyncTasks();
    expect(downloadItem.classList.contains('disabled')).toBe(false);
    expect(document.getElementById('globalContextMenu').style.display).toBe('none');

    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, moved_total: 2 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, records: [{ id: 1 }] }),
      });

    menu.showMenu(240, 320);
    const cleanupItem = document.querySelector('[data-action="cleanup-example-images-folders"]');
    cleanupItem.dispatchEvent(new Event('click', { bubbles: true }));
    expect(cleanupItem.classList.contains('disabled')).toBe(true);

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/cleanup-example-image-folders', { method: 'POST' });
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const responsePromise = global.fetch.mock.results[0].value;
    const response = await responsePromise;
    await response.json();
    await flushAsyncTasks();
    expect(cleanupItem.classList.contains('disabled')).toBe(false);
    expect(menu._cleanupInProgress).toBe(false);

    menu.showMenu(360, 420);
    const checkUpdatesItem = document.querySelector('[data-action="check-model-updates"]');
    checkUpdatesItem.dispatchEvent(new Event('click', { bubbles: true }));
    expect(checkUpdatesItem.classList.contains('disabled')).toBe(true);

    expect(global.fetch).toHaveBeenLastCalledWith('/api/lm/loras/updates/refresh', {
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
  });
});
