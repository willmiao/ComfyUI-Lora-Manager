import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));

const loadingManagerStub = {
  showSimpleLoading: vi.fn(),
  hide: vi.fn(),
  show: vi.fn(),
  restoreProgressBar: vi.fn(),
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

function recipeModalFixture() {
  return `
    <div id="recipeModal" class="modal">
      <div class="modal-content">
        <header class="recipe-modal-header">
          <h2 id="recipeModalTitle">Recipe Details</h2>
          <div id="recipeTagsContainer"></div>
        </header>
        <div class="modal-body">
          <div class="recipe-media-column">
            <div class="recipe-preview-container" id="recipePreviewContainer">
              <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
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

const recipeWithMissing = {
  id: 'recipe-missing',
  file_path: '/recipes/missing.json',
  title: 'Missing Recipe',
  tags: [],
  loras: [
    { name: 'present-lora', inLibrary: true },
    { name: 'gone-lora', inLibrary: false },
  ],
};

const recipeReady = {
  id: 'recipe-ready',
  file_path: '/recipes/ready.json',
  title: 'Ready Recipe',
  tags: [],
  loras: [
    { name: 'present-lora', inLibrary: true },
  ],
};

const createdModals = [];

async function createRecipeModal() {
  const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
  const recipeModal = new RecipeModal();
  createdModals.push(recipeModal);
  return recipeModal;
}

describe('RecipeModal missing LoRA status', () => {
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

  it('renders the missing status as a button with a persistent affordance', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeWithMissing);

    const status = document.querySelector('#recipeLorasCount .recipe-status.missing');
    expect(status).not.toBeNull();
    expect(status.tagName).toBe('BUTTON');
    expect(status.type).toBe('button');
    expect(status.classList.contains('clickable')).toBe(true);
    expect(status.getAttribute('aria-label')).toBe('Download 1 missing LoRAs');
    expect(status.title).toBe('Click to download missing LoRAs');
    // Leading download icon hints the action; the warning glyph was removed
    // because the red tint + text already encode the state
    expect(status.querySelector('i').classList.contains('fa-download')).toBe(true);
    expect(status.querySelector('.fa-exclamation-triangle')).toBeNull();
    expect(status.textContent).toContain('1 missing');

    // The hover-only tooltip was replaced by the always-visible button styling
    expect(status.querySelector('.missing-tooltip')).toBeNull();
  });

  it('opens the download-missing flow when the status button is clicked', async () => {
    const recipeModal = await createRecipeModal();
    const downloadSpy = vi
      .spyOn(recipeModal, 'showDownloadMissingLorasModal')
      .mockImplementation(() => {});

    recipeModal.showRecipeDetails(recipeWithMissing);

    const status = document.querySelector('#recipeLorasCount .recipe-status.missing');
    status.click();

    expect(downloadSpy).toHaveBeenCalledTimes(1);
  });

  it('renders a non-interactive ready badge when every LoRA is available', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeReady);

    const ready = document.querySelector('#recipeLorasCount .recipe-status.ready');
    expect(ready).not.toBeNull();
    expect(ready.tagName).toBe('DIV');
    expect(ready.textContent).toContain('Ready to use');
    expect(document.querySelector('#recipeLorasCount .recipe-status.missing')).toBeNull();
  });
});
